package io.github.blancaile.jevcontrol;

import com.google.gson.*;
import java.util.*;

/** Swept body geometry from the observed snapshot only; no policy or world queries. */
final class ObservedGeometry {
    private static final double HORIZON = 2.0;
    private static final double EPS = 1e-8;

    static JsonObject capture(JsonObject state, double halfWidth, double height) {
        var self = state.getAsJsonObject("self");
        var position = self.getAsJsonArray("position");
        double x = position.get(0).getAsDouble(), y = position.get(1).getAsDouble(), z = position.get(2).getAsDouble();
        double yaw = Math.toRadians(self.get("yaw").getAsDouble());
        double fx = -Math.sin(yaw), fz = Math.cos(yaw);
        double lx = Math.cos(yaw), lz = Math.sin(yaw);
        var cells = new HashMap<String, JsonObject>();
        for (var element : state.getAsJsonArray("local_cells")) {
            var cell = element.getAsJsonObject();
            var p = cell.getAsJsonArray("position");
            cells.put(key(p.get(0).getAsInt(), p.get(1).getAsInt(), p.get(2).getAsInt()), cell);
        }
        var result = new JsonObject();
        result.addProperty("source", "OBSERVED_COLLISION_BOX_SWEEP_NOT_POLICY");
        result.addProperty("horizon_blocks", HORIZON);
        result.addProperty("body_width", halfWidth * 2);
        result.addProperty("body_height", height);
        result.addProperty("note", "Horizontal straight sweeps at current height, not paths or predicted actions. "
                + "Distances are to body contact. Null means none within horizon; unknown space is separate. "
                + "Ground support, jumping, future motion and dynamics are not predicted.");
        String[] names = {"FORWARD", "BACK", "STRAFE_LEFT", "STRAFE_RIGHT"};
        double[][] axes = {{fx, fz}, {-fx, -fz}, {lx, lz}, {-lx, -lz}};
        for (int index = 0; index < names.length; index++) {
            double collision = Double.POSITIVE_INFINITY, unknown = Double.POSITIVE_INFINITY;
            for (int bx = (int)Math.floor(x - HORIZON - halfWidth); bx <= Math.floor(x + HORIZON + halfWidth); bx++) {
                for (int by = (int)Math.floor(y); by <= Math.floor(y + height - EPS); by++) {
                    for (int bz = (int)Math.floor(z - HORIZON - halfWidth); bz <= Math.floor(z + HORIZON + halfWidth); bz++) {
                        var cell = cells.get(key(bx, by, bz));
                        if (cell == null || !cell.get("knowledge").getAsString().equals("OBSERVED")) {
                            unknown = Math.min(unknown, contact(x, z, axes[index],
                                    bx - halfWidth, bz - halfWidth, bx + 1 + halfWidth, bz + 1 + halfWidth));
                            continue;
                        }
                        for (var element : cell.getAsJsonArray("local_collision_boxes")) {
                            var box = element.getAsJsonArray();
                            if (by + box.get(4).getAsDouble() <= y + EPS || by + box.get(1).getAsDouble() >= y + height - EPS) continue;
                            collision = Math.min(collision, contact(x, z, axes[index],
                                    bx + box.get(0).getAsDouble() - halfWidth, bz + box.get(2).getAsDouble() - halfWidth,
                                    bx + box.get(3).getAsDouble() + halfWidth, bz + box.get(5).getAsDouble() + halfWidth));
                        }
                    }
                }
            }
            var direction = new JsonObject();
            direction.addProperty("observed_clear_distance_blocks", Math.max(0, Math.min(HORIZON, Math.min(collision, unknown))));
            distance(direction, "observed_collision_distance_blocks", collision);
            distance(direction, "unknown_distance_blocks", unknown);
            result.add(names[index], direction);
        }
        return result;
    }

    private static String key(int x, int y, int z) { return x + ":" + y + ":" + z; }
    private static void distance(JsonObject target, String name, double distance) {
        if (Double.isFinite(distance) && distance <= HORIZON) target.addProperty(name, Math.max(0, distance));
        else target.add(name, JsonNull.INSTANCE);
    }
    private static double contact(double x, double z, double[] direction, double minX, double minZ, double maxX, double maxZ) {
        double enter = Double.NEGATIVE_INFINITY, exit = Double.POSITIVE_INFINITY;
        double[] p = {x, z}, min = {minX, minZ}, max = {maxX, maxZ};
        for (int axis = 0; axis < 2; axis++) {
            if (Math.abs(direction[axis]) < EPS) {
                if (p[axis] <= min[axis] + EPS || p[axis] >= max[axis] - EPS) return Double.POSITIVE_INFINITY;
            } else {
                double a = (min[axis] - p[axis]) / direction[axis], b = (max[axis] - p[axis]) / direction[axis];
                enter = Math.max(enter, Math.min(a, b));
                exit = Math.min(exit, Math.max(a, b));
            }
        }
        if (exit <= EPS || enter >= exit - EPS || enter > HORIZON) return Double.POSITIVE_INFINITY;
        return Math.max(0, enter);
    }
}
