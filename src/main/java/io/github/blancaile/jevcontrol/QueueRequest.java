package io.github.blancaile.jevcontrol;

import com.google.gson.JsonParser;
import java.util.Set;
import java.util.UUID;

record QueueRequest(String id, String command, long expiresAtMillis) {
    static QueueRequest parse(String filename, String json, long now) {
        try {
            var value = JsonParser.parseString(json).getAsJsonObject();
            if (!value.keySet().equals(Set.of("id", "command", "expires_at_ms"))) throw new IllegalArgumentException();
            String id = value.get("id").getAsString();
            if (!UUID.fromString(id).toString().equals(id) || !filename.equals(id + ".json")) throw new IllegalArgumentException();
            String command = value.get("command").getAsString();
            long expires = value.get("expires_at_ms").getAsBigDecimal().longValueExact();
            if (expires <= now || expires > now + 60_000) throw new IllegalArgumentException();
            boolean sealedInstall = command.matches("jev key-install [A-Za-z0-9+/]{512}");
            if ((!sealedInstall && command.length() > 256) || command.contains("\n") || command.contains("\r") || !command.startsWith("jev ")) throw new IllegalArgumentException();
            String action = command.substring(4).split(" ")[0];
            if (!Set.of("key-prepare", "key-install", "key-status", "site", "spawn-near", "spawn", "despawn", "status", "observe", "goal", "smoke", "step", "start", "stop", "fixture-wall").contains(action))
                throw new IllegalArgumentException();
            if (action.equals("key-install") && !sealedInstall) throw new IllegalArgumentException();
            return new QueueRequest(id, command, expires);
        } catch (RuntimeException ex) {
            throw new IllegalArgumentException("Invalid or expired Jev command request");
        }
    }
}
