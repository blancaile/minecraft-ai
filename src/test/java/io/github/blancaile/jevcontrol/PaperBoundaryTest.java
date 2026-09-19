package io.github.blancaile.jevcontrol;

import com.google.gson.Gson;
import org.junit.jupiter.api.Test;
import java.util.Map;
import static org.junit.jupiter.api.Assertions.*;

class PaperBoundaryTest {
    private static final String ID = "a191726f-be71-4072-879c-a3c9f93f2adf";
    private String request(String command, long expires) {
        return new Gson().toJson(Map.of("id", ID, "command", command, "expires_at_ms", expires));
    }
    @Test void acceptsOnlyFreshBoundedJevCommands() {
        assertEquals("jev status", QueueRequest.parse(ID + ".json", request("jev status", 2000), 1000).command());
        for (String command : new String[]{"op somebody", "jev status\nstop", "jev config apiKey SECRET", "jev " + "a".repeat(300)})
            assertThrows(IllegalArgumentException.class, () -> QueueRequest.parse(ID + ".json", request(command, 2000), 1000));
    }
    @Test void rejectsExpiredMismatchedAndUnboundedLeases() {
        for (long expires : new long[]{999, 1000, 62000})
            assertThrows(IllegalArgumentException.class, () -> QueueRequest.parse(ID + ".json", request("jev status", expires), 1000));
        assertThrows(IllegalArgumentException.class, () -> QueueRequest.parse("other.json", request("jev status", 2000), 1000));
        assertThrows(IllegalArgumentException.class, () -> QueueRequest.parse(ID + ".json", "{}", 1000));
    }
    @Test void coordinatesRejectNonFiniteAndSupportRelative() {
        assertEquals(12, Coordinate.parse("~2", 10));
        assertEquals(10, Coordinate.parse("~", 10));
        assertEquals(-5, Coordinate.parse("-5", 10));
        for (String bad : new String[]{"NaN", "Infinity", "~Infinity", "1e999", "^2", ""})
            assertThrows(IllegalArgumentException.class, () -> Coordinate.parse(bad, 0));
    }
}
