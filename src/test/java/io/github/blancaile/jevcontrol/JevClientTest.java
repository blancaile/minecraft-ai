package io.github.blancaile.jevcontrol;

import com.google.gson.*;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.Test;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import static org.junit.jupiter.api.Assertions.*;

class JevClientTest {
    static final List<ControlAction> CANDIDATES = List.of(ControlAction.WAIT, ControlAction.FORWARD);
    static final String VALID = """
        {"model":"jev-1.13.0","answers":{"next_action":{"choice":"FORWARD",
        "confidence":0.8,"probabilities":{"WAIT":0.1,"FORWARD":0.9}}},
        "usage":{"input_tokens":30,"output_tokens":10},"untrusted":"do not log me"}
        """;
    static ControlConfig config(int timeout) {
        return new ControlConfig("unit-test-secret", "jev-1.13.0", 4, timeout, 200, 200, 600, 3, 1, 64);
    }
    @Test void fixtureEndpointCannotReceiveProductionCredentialsOrLeaveLoopback() {
        assertEquals("https", JevClient.runtimeEndpoint(config(2), null).getScheme());
        assertThrows(IllegalArgumentException.class, () -> JevClient.runtimeEndpoint(config(2), "http://127.0.0.1:1234/"));
        var dummy = new ControlConfig("fixture-only-no-credential", "jev-1.13.0", 4, 2, 200, 20, 60, 3, 1, 64);
        assertEquals("127.0.0.1", JevClient.runtimeEndpoint(dummy, "http://127.0.0.1:1234/").getHost());
        for (String bad : List.of("http://example.com:80/", "https://127.0.0.1:1234/", "http://secret@127.0.0.1:1234/"))
            assertThrows(IllegalArgumentException.class, () -> JevClient.runtimeEndpoint(dummy, bad));
    }
    @Test void actualHttpRequestAndTypedResponseWork() throws Exception {
        var server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        var received = new AtomicReference<JsonObject>();
        var auth = new AtomicReference<String>();
        server.createContext("/", exchange -> {
            received.set(JsonParser.parseString(new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8)).getAsJsonObject());
            auth.set(exchange.getRequestHeaders().getFirst("Authorization"));
            byte[] bytes = VALID.getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, bytes.length); exchange.getResponseBody().write(bytes); exchange.close();
        });
        server.start();
        try (var client = new JevClient(config(2), URI.create("http://127.0.0.1:" + server.getAddress().getPort()))) {
            var snapshot = new JsonObject(); snapshot.addProperty("observation_id", "123");
            var decision = client.choose(snapshot, CANDIDATES).get(5, TimeUnit.SECONDS);
            assertEquals(ControlAction.FORWARD, decision.action());
            assertEquals("Bearer unit-test-secret", auth.get());
            assertEquals(snapshot.toString(), received.get().get("state").getAsString());
            assertEquals("jev-1.13.0", received.get().get("model").getAsString());
            assertFalse(decision.response().has("untrusted"));
            assertFalse(decision.response().toString().contains("unit-test-secret"));
        } finally { server.stop(0); }
    }
    @Test void malformedAndUnavailableActionsDoNotTurnIntoWait() {
        for (String bad : List.of("{}", "not json", VALID.replace("\"choice\":\"FORWARD\"", "\"choice\":\"JUMP_FORWARD\""),
                VALID.replace("0.8", "1.8"), VALID.replace("0.9", "0.2"),
                VALID.replace("jev-1.13.0", "jev-latest"), VALID.replace("0.8", "\"0.8\""))) {
            var error = assertThrows(IllegalStateException.class, () -> JevClient.parse(bad, CANDIDATES, "jev-1.13.0", 10));
            assertFalse(error.getMessage().contains(bad));
        }
    }
    @Test void httpErrorsAreNotRetriedOrLoggedWithResponseSecrets() throws Exception {
        var server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        var count = new AtomicInteger();
        server.createContext("/", exchange -> {
            count.incrementAndGet();
            byte[] bytes = "unit-test-secret".getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(401, bytes.length); exchange.getResponseBody().write(bytes); exchange.close();
        });
        server.start();
        try (var client = new JevClient(config(2), URI.create("http://127.0.0.1:" + server.getAddress().getPort()))) {
            var error = assertThrows(ExecutionException.class, () -> client.choose(new JsonObject(), CANDIDATES).get(5, TimeUnit.SECONDS));
            assertEquals("Jev HTTP 401", error.getCause().getMessage());
            assertEquals(1, count.get());
        } finally { server.stop(0); }
    }
    @Test void timeoutIsAnErrorNotASyntheticDecision() throws Exception {
        var server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        var count = new AtomicInteger();
        server.createContext("/", exchange -> {
            count.incrementAndGet();
            try { Thread.sleep(1800); } catch (InterruptedException ex) { Thread.currentThread().interrupt(); }
            exchange.close();
        });
        server.start();
        try (var client = new JevClient(config(1), URI.create("http://127.0.0.1:" + server.getAddress().getPort()))) {
            assertThrows(ExecutionException.class, () -> client.choose(new JsonObject(), CANDIDATES).get(4, TimeUnit.SECONDS));
            assertEquals(1, count.get());
        } finally { server.stop(0); }
    }
}
