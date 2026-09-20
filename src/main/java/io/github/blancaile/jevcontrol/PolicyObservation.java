package io.github.blancaile.jevcontrol;

import com.google.gson.*;
import java.util.List;
import java.util.Locale;

/** Observed task facts only; no action ranking, filtering, waypoints or recovery policy. */
final class PolicyObservation {
    static JsonObject compact(JsonObject raw) {
        var state = new JsonObject();
        for (String key : List.of("schema_version", "observation_id", "server_tick", "action_ticks", "self", "goal",
                "control_frame", "previous", "legal_candidates", "excluded_candidates", "observed_body_sweeps", "visible_entities")) {
            if (raw.has(key)) state.add(key, raw.get(key).deepCopy());
        }
        state.addProperty("policy_encoding", "jev-task-facts-v1");
        state.addProperty("terrain_note", "Only OBSERVED solid geometry above the feet is listed. Omitted cells are unrepresented, NOT empty. "
                + "Four body sweeps separately report observed contact and UNKNOWN distances; no jump or route prediction. Support is measured by self.on_ground.");
        var obstacles = new JsonArray();
        double feet = raw.getAsJsonObject("self").getAsJsonArray("position").get(1).getAsDouble();
        for (var element : raw.getAsJsonArray("local_cells")) {
            var cell = element.getAsJsonObject();
            if (!cell.get("knowledge").getAsString().equals("OBSERVED")) continue;
            boolean aboveFeet = false;
            for (var box : cell.getAsJsonArray("local_collision_boxes")) {
                if (cell.getAsJsonArray("position").get(1).getAsDouble() + box.getAsJsonArray().get(4).getAsDouble() > feet + 1e-8)
                    aboveFeet = true;
            }
            if (aboveFeet) obstacles.add(cell.deepCopy());
        }
        state.add("observed_obstacles", obstacles);
        if (raw.has("control_frame")) {
            var frame = raw.getAsJsonObject("control_frame");
            double forward = frame.get("goal_forward_blocks").getAsDouble();
            double left = frame.get("goal_left_blocks").getAsDouble();
            state.addProperty("goal_direction_description", String.format(Locale.ROOT,
                    "Goal displacement relative to your current facing: %.3f blocks %s; %.3f blocks to your %s. This states location, not a route.",
                    Math.abs(forward), forward >= 0 ? "FORWARD" : "BACK", Math.abs(left), left >= 0 ? "LEFT" : "RIGHT"));
        }
        if (raw.has("goal") && raw.has("previous") && raw.getAsJsonObject("previous").has("after")) {
            var previous = raw.getAsJsonObject("previous");
            var goal = raw.getAsJsonObject("goal").getAsJsonArray("position");
            var after = previous.getAsJsonObject("after").getAsJsonArray("position");
            var delta = previous.getAsJsonArray("displacement");
            double beforeSquared = 0, afterSquared = 0;
            for (int i = 0; i < 3; i++) {
                double remaining = goal.get(i).getAsDouble() - after.get(i).getAsDouble();
                afterSquared += remaining * remaining;
                double priorRemaining = remaining + delta.get(i).getAsDouble();
                beforeSquared += priorRemaining * priorRemaining;
            }
            state.addProperty("last_input_goal_distance_change_blocks", Math.sqrt(afterSquared) - Math.sqrt(beforeSquared));
        }
        return state;
    }
}
