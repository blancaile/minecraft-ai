package io.github.blancaile.jevcontrol;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ControlFrameTest {
    @Test void yawTransformMatchesMinecraftAndDoesNotChooseActions() {
        var south = ControlFrame.capture(0, 4, 7);
        assertEquals(7, south.get("goal_forward_blocks").getAsDouble(), 1e-9);
        assertEquals(4, south.get("goal_left_blocks").getAsDouble(), 1e-9);
        assertEquals(-1, south.getAsJsonArray("STRAFE_RIGHT_world_unit_xz").get(0).getAsDouble(), 1e-9);
        var north = ControlFrame.capture(180, -4, -7);
        assertEquals(7, north.get("goal_forward_blocks").getAsDouble(), 1e-9);
        assertEquals(4, north.get("goal_left_blocks").getAsDouble(), 1e-9);
        var west = ControlFrame.capture(90, -4, 7);
        assertEquals(4, west.get("goal_forward_blocks").getAsDouble(), 1e-9);
        assertEquals(7, west.get("goal_left_blocks").getAsDouble(), 1e-9);
        assertFalse(west.has("choice"));
    }
}
