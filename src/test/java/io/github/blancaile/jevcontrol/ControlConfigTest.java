package io.github.blancaile.jevcontrol;

import com.google.gson.Gson;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.*;
import static org.junit.jupiter.api.Assertions.*;

class ControlConfigTest {
    @TempDir Path directory;
    @Test void createsTemplateButDoesNotRepairBrokenConfiguration() throws Exception {
        var file = directory.resolve("config/jev-control.json");
        ControlConfig.createIfAbsent(file);
        var c = ControlConfig.read(file);
        assertEquals("jev-1.13.0", c.model());
        assertThrows(IllegalStateException.class, c::requireKey);
        Files.writeString(file, "{}");
        ControlConfig.createIfAbsent(file);
        assertEquals("{}", Files.readString(file));
        assertThrows(IllegalArgumentException.class, () -> ControlConfig.read(file));
    }
    @Test void malformedMissingFractionalAndUnboundedFieldsFail() throws Exception {
        var file = directory.resolve("config.json");
        String valid = new Gson().toJson(ControlConfig.defaults());
        for (String bad : new String[]{valid.replace("\"actionTicks\":4", "\"actionTicks\":4.5"),
                valid.replace("\"actionTicks\":4", "\"actionTicks\":200"),
                valid.replace("jev-1.13.0", "jev-latest"),
                valid.replace("\"apiKey\":\"\"", "\"apiKey\":123")}) {
            Files.writeString(file, bad);
            assertThrows(RuntimeException.class, () -> ControlConfig.read(file));
        }
    }
}
