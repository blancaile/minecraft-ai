package io.github.blancaile.jevcontrol;

import com.google.gson.GsonBuilder;
import com.google.gson.JsonParser;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

/** Defaults are written once, never substituted for missing/invalid user values. */
public record ControlConfig(String apiKey, String model, int actionTicks, int timeoutSeconds,
                            int maxObservationAgeTicks, int maxDecisions, int maxRunSeconds,
                            int observationRadius, double goalRadius, double maxDistanceFromSpawn) {
    public static ControlConfig defaults() {
        return new ControlConfig("", "jev-1.13.0", 4, 10, 200, 200, 600, 3, 1.0, 64.0);
    }

    public static void createIfAbsent(Path path) throws IOException {
        if (!Files.exists(path)) {
            Files.createDirectories(path.getParent());
            Files.writeString(path, new GsonBuilder().setPrettyPrinting().create().toJson(defaults()) + "\n",
                    StandardCharsets.UTF_8, StandardOpenOption.CREATE_NEW);
        }
    }

    public static ControlConfig read(Path path) throws IOException {
        var json = JsonParser.parseString(Files.readString(path, StandardCharsets.UTF_8)).getAsJsonObject();
        var required = java.util.Set.of("apiKey", "model", "actionTicks", "timeoutSeconds",
                "maxObservationAgeTicks", "maxDecisions", "maxRunSeconds", "observationRadius",
                "goalRadius", "maxDistanceFromSpawn");
        if (!json.keySet().equals(required)) throw new IllegalArgumentException("Config fields are missing or unknown");
        for (String key : required) {
            if (!json.get(key).isJsonPrimitive()) throw new IllegalArgumentException("Invalid config field: " + key);
            var value = json.getAsJsonPrimitive(key);
            if ((key.equals("apiKey") || key.equals("model")) ? !value.isString() : !value.isNumber())
                throw new IllegalArgumentException("Wrong config field type: " + key);
        }
        for (String key : java.util.List.of("actionTicks", "timeoutSeconds", "maxObservationAgeTicks",
                "maxDecisions", "maxRunSeconds", "observationRadius")) {
            try { json.get(key).getAsBigDecimal().intValueExact(); }
            catch (ArithmeticException ex) { throw new IllegalArgumentException("Expected integer: " + key); }
        }
        var config = new GsonBuilder().create().fromJson(json, ControlConfig.class);
        config.validate();
        return config;
    }

    public void validate() {
        if (apiKey == null || apiKey.contains("\n") || apiKey.contains("\r"))
            throw new IllegalArgumentException("Invalid apiKey");
        if (model == null || !model.matches("jev-[0-9]+\\.[0-9]+\\.[0-9]+"))
            throw new IllegalArgumentException("Pin model to a version such as jev-1.13.0");
        range(actionTicks, 1, 20, "actionTicks");
        range(timeoutSeconds, 1, 30, "timeoutSeconds");
        range(maxObservationAgeTicks, 1, 600, "maxObservationAgeTicks");
        range(maxDecisions, 1, 10000, "maxDecisions");
        range(maxRunSeconds, 1, 3600, "maxRunSeconds");
        range(observationRadius, 1, 5, "observationRadius");
        if (!Double.isFinite(goalRadius) || goalRadius < 0.25 || goalRadius > 4)
            throw new IllegalArgumentException("goalRadius must be 0.25..4");
        if (!Double.isFinite(maxDistanceFromSpawn) || maxDistanceFromSpawn < 4 || maxDistanceFromSpawn > 256)
            throw new IllegalArgumentException("maxDistanceFromSpawn must be 4..256");
    }

    private static void range(int value, int min, int max, String field) {
        if (value < min || value > max) throw new IllegalArgumentException(field + " out of range");
    }

    public void requireKey() {
        if (apiKey.isBlank()) throw new IllegalStateException("Set apiKey in config/jev-control.json before /jev start");
    }

    @Override public String toString() { return "ControlConfig[credentials redacted]"; }
}
