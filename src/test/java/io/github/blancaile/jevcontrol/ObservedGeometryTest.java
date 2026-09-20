package io.github.blancaile.jevcontrol;

import com.google.gson.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ObservedGeometryTest {
    private JsonObject scene(double x, double z, double yaw, boolean wallKnown) {
        var state = new JsonObject();
        var self = new JsonObject();
        self.add("position", JsonParser.parseString("[" + x + ",81," + z + "]"));
        self.addProperty("yaw", yaw);
        state.add("self", self);
        var cells = new JsonArray();
        for (int bx = -4; bx <= 5; bx++) for (int by = 81; by <= 83; by++) for (int bz = -3; bz <= 7; bz++) {
            var cell = new JsonObject();
            cell.add("position", JsonParser.parseString("[" + bx + "," + by + "," + bz + "]"));
            boolean wall = bx >= -1 && bx <= 1 && bz == 4;
            cell.addProperty("knowledge", wall && !wallKnown ? "UNKNOWN" : "OBSERVED");
            if (wallKnown || !wall) cell.add("local_collision_boxes", JsonParser.parseString(wall ? "[[0,0,0,1,1,1]]" : "[]"));
            cells.add(cell);
        }
        state.add("local_cells", cells);
        return state;
    }
    private JsonElement distance(JsonObject result, String direction, String field) {
        return result.getAsJsonObject(direction).get(field + "_distance_blocks");
    }
    @Test void bodyEdgeRatherThanCenterDeterminesContact() {
        var nearEdge = ObservedGeometry.capture(scene(2.0, 3.7, 0, true), .3, 1.8);
        assertEquals(0, distance(nearEdge, "FORWARD", "observed_collision").getAsDouble(), 1e-8);
        var beyondEdge = ObservedGeometry.capture(scene(2.31, 3.7, 0, true), .3, 1.8);
        assertTrue(distance(beyondEdge, "FORWARD", "observed_collision").isJsonNull());
        assertEquals(2, beyondEdge.getAsJsonObject("FORWARD").get("observed_clear_distance_blocks").getAsDouble(), 1e-8);
        assertFalse(nearEdge.has("choice"));
    }
    @Test void distancesRotateWithInputAxes() {
        var south = ObservedGeometry.capture(scene(.5, 2.5, 0, true), .3, 1.8);
        var west = ObservedGeometry.capture(scene(.5, 2.5, 90, true), .3, 1.8);
        assertEquals(1.2, distance(south, "FORWARD", "observed_collision").getAsDouble(), 1e-8);
        assertEquals(1.2, distance(west, "STRAFE_LEFT", "observed_collision").getAsDouble(), 1e-8);
        assertTrue(distance(south, "BACK", "observed_collision").isJsonNull());
    }
    @Test void unknownAndUnlistedCellsDoNotBecomeClearSpace() {
        var unknown = ObservedGeometry.capture(scene(.5, 2.5, 0, false), .3, 1.8);
        assertTrue(distance(unknown, "FORWARD", "observed_collision").isJsonNull());
        assertEquals(1.2, distance(unknown, "FORWARD", "unknown").getAsDouble(), 1e-8);
        var empty = scene(.5, 2.5, 0, true);
        empty.add("local_cells", new JsonArray());
        assertEquals(0, distance(ObservedGeometry.capture(empty, .3, 1.8), "BACK", "unknown").getAsDouble(), 1e-8);
        assertEquals(0, ObservedGeometry.capture(empty, .3, 1.8).getAsJsonObject("BACK").get("observed_clear_distance_blocks").getAsDouble(), 1e-8);
    }
}
