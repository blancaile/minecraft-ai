package io.github.blancaile.jevcontrol;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;

/** Coordinate transform only; never ranks, removes or selects an action. */
final class ControlFrame {
    static JsonObject capture(double yaw, double goalX, double goalZ) {
        double angle = Math.toRadians(yaw);
        double fx = -Math.sin(angle), fz = Math.cos(angle);
        double lx = Math.cos(angle), lz = Math.sin(angle);
        var frame = new JsonObject();
        frame.addProperty("source", "MECHANICAL_COORDINATE_TRANSFORM_NOT_POLICY");
        frame.add("FORWARD_world_unit_xz", pair(fx, fz));
        frame.add("BACK_world_unit_xz", pair(-fx, -fz));
        frame.add("STRAFE_LEFT_world_unit_xz", pair(lx, lz));
        frame.add("STRAFE_RIGHT_world_unit_xz", pair(-lx, -lz));
        frame.addProperty("goal_forward_blocks", goalX * fx + goalZ * fz);
        frame.addProperty("goal_left_blocks", goalX * lx + goalZ * lz);
        return frame;
    }
    private static JsonArray pair(double a, double b) {
        var pair = new JsonArray(); pair.add(a); pair.add(b); return pair;
    }
}
