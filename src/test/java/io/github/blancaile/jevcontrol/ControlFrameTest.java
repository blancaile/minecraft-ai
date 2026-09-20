package io.github.blancaile.jevcontrol;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ControlFrameTest {
    @Test void oppositeProjectionsRepresentActualGoalDisplacementAtEveryYaw() {
        for (double yaw : new double[]{0, 15, 90, 180, -90, 285}) {
            var frame = ControlFrame.capture(yaw, -2.36, .744);
            for (String[] pair : new String[][]{{"FORWARD", "forward"}, {"BACK", "back"},
                    {"STRAFE_LEFT", "left"}, {"STRAFE_RIGHT", "right"}}) {
                var axis = frame.getAsJsonArray(pair[0] + "_world_unit_xz");
                double projection = -2.36 * axis.get(0).getAsDouble() + .744 * axis.get(1).getAsDouble();
                assertEquals(projection, frame.get("goal_" + pair[1] + "_blocks").getAsDouble(), 1e-9);
            }
            assertEquals(-frame.get("goal_left_blocks").getAsDouble(), frame.get("goal_right_blocks").getAsDouble(), 1e-9);
            assertEquals(-frame.get("goal_forward_blocks").getAsDouble(), frame.get("goal_back_blocks").getAsDouble(), 1e-9);
        }
        assertEquals(2.36, ControlFrame.capture(0, -2.36, .744).get("goal_right_blocks").getAsDouble(), 1e-9);
    }
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
