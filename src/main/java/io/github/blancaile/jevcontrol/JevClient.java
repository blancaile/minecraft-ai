package io.github.blancaile.jevcontrol;

import com.google.gson.*;
import java.io.IOException;
import java.net.URI;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.CompletableFuture;

/** No retry, no alternate endpoint/model/policy and no response body in error messages. */
public final class JevClient implements AutoCloseable {
    public record Decision(ControlAction action, JsonObject response, long latencyMillis) {}
    private final HttpClient client;
    private final URI endpoint;
    private final ControlConfig config;

    public JevClient(ControlConfig config) {
        this(config, runtimeEndpoint(config, System.getProperty("jev.fixture.endpoint")));
    }
    static URI runtimeEndpoint(ControlConfig config, String fixture) {
        if (fixture == null) return URI.create("https://api.typesafe.ai/v1/systemone");
        // Explicit isolated-server fault injection, never a production credential or fallback.
        URI uri = URI.create(fixture);
        if (!config.apiKey().equals("fixture-only-no-credential") || !"http".equals(uri.getScheme())
                || !"127.0.0.1".equals(uri.getHost()) || uri.getPort() < 1
                || uri.getUserInfo() != null || uri.getQuery() != null || uri.getFragment() != null)
            throw new IllegalArgumentException("Fixture endpoint requires loopback and dummy credential");
        return uri;
    }
    // Only tests supply a local HTTP endpoint. Production uses the fixed HTTPS endpoint above.
    JevClient(ControlConfig config, URI endpoint) {
        config.validate();
        config.requireKey();
        this.config = config;
        this.endpoint = endpoint;
        this.client = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(config.timeoutSeconds()))
                .followRedirects(HttpClient.Redirect.NEVER).build();
    }

    public static JsonObject payload(JsonObject snapshot, List<ControlAction> candidates, ControlConfig config) {
        if (candidates.isEmpty()) throw new IllegalArgumentException("No legal candidates");
        var criteria = new JsonObject();
        for (var action : candidates) criteria.addProperty(action.name(), action.description);
        var question = new JsonObject();
        question.addProperty("type", "choice");
        question.addProperty("instructions", "Choose the next short controller input to reach the given goal. "
                + "Use observed geometry, current yaw, goal relative position and previous input outcome. "
                + "Unknown cells are not known to be empty. Inputs last action_ticks server ticks. "
                + "No pathfinder or automatic obstacle recovery will execute for you.");
        question.add("criteria", criteria);
        var questions = new JsonObject();
        questions.add("next_action", question);
        var payload = new JsonObject();
        payload.addProperty("model", config.model());
        // Textual JSON is accepted by the documented state-string API contract.
        // The raw snapshot and this exact derived policy representation are both traced.
        payload.addProperty("state", snapshot.has("policy_state") ? snapshot.get("policy_state").toString() : snapshot.toString());
        payload.add("questions", questions);
        return payload;
    }

    public CompletableFuture<Decision> choose(JsonObject snapshot, List<ControlAction> candidates) {
        long started = System.nanoTime();
        var request = HttpRequest.newBuilder(endpoint).timeout(Duration.ofSeconds(config.timeoutSeconds()))
                .header("Authorization", "Bearer " + config.apiKey())
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(payload(snapshot, candidates, config).toString(), StandardCharsets.UTF_8))
                .build();
        return client.sendAsync(request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8)).thenApply(response -> {
            if (response.statusCode() != 200) throw new IllegalStateException("Jev HTTP " + response.statusCode());
            if (response.body().length() > 131072) throw new IllegalStateException("Oversized Jev response");
            return parse(response.body(), candidates, config.model(), (System.nanoTime() - started) / 1_000_000);
        });
    }

    static Decision parse(String body, List<ControlAction> candidates, String expectedModel, long latency) {
        try {
            var raw = JsonParser.parseString(body).getAsJsonObject();
            if (!string(raw, "model").equals(expectedModel)) throw new IllegalArgumentException();
            var answer = raw.getAsJsonObject("answers").getAsJsonObject("next_action");
            var action = ControlAction.valueOf(string(answer, "choice"));
            if (!candidates.contains(action)) throw new IllegalArgumentException();
            double confidence = probability(answer.get("confidence"));
            var distribution = answer.getAsJsonObject("probabilities");
            var expected = new HashSet<String>();
            candidates.forEach(a -> expected.add(a.name()));
            if (!distribution.keySet().equals(expected)) throw new IllegalArgumentException();
            double sum = 0;
            var safeDistribution = new JsonObject();
            for (String key : expected) {
                double value = probability(distribution.get(key));
                sum += value;
                safeDistribution.addProperty(key, value);
            }
            // Rounded distributions can deviate slightly; never normalize/change the chosen action.
            if (Math.abs(sum - 1) > 0.05) throw new IllegalArgumentException();
            var safe = new JsonObject();
            safe.addProperty("model", expectedModel);
            safe.addProperty("choice", action.name());
            safe.addProperty("confidence", confidence);
            safe.add("probabilities", safeDistribution);
            if (raw.has("usage")) {
                var usage = raw.getAsJsonObject("usage");
                var safeUsage = new JsonObject();
                for (String field : List.of("input_tokens", "output_tokens")) {
                    var p = usage.getAsJsonPrimitive(field);
                    if (p == null || !p.isNumber()) throw new IllegalArgumentException();
                    long count = p.getAsBigDecimal().longValueExact();
                    if (count < 0) throw new IllegalArgumentException();
                    safeUsage.addProperty(field, count);
                }
                safe.add("usage", safeUsage);
            }
            return new Decision(action, safe, latency);
        } catch (RuntimeException ex) {
            // Avoid exposing server response text, headers, tokens or parser excerpts.
            throw new IllegalStateException("Invalid Jev response (schema/model/action/probabilities)");
        }
    }

    private static String string(JsonObject obj, String key) {
        var value = obj.getAsJsonPrimitive(key);
        if (value == null || !value.isString()) throw new IllegalArgumentException();
        return value.getAsString();
    }
    private static double probability(JsonElement element) {
        if (element == null || !element.isJsonPrimitive() || !element.getAsJsonPrimitive().isNumber())
            throw new IllegalArgumentException();
        double value = element.getAsDouble();
        if (!Double.isFinite(value) || value < 0 || value > 1) throw new IllegalArgumentException();
        return value;
    }
    @Override public void close() { client.shutdownNow(); }
}
