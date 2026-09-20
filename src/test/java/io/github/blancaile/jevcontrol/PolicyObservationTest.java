package io.github.blancaile.jevcontrol;

import com.google.gson.*;
import java.util.List;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class PolicyObservationTest {
    private JsonObject raw() {
        return JsonParser.parseString("""
                {"server_tick":27,"self":{"position":[0.5,81,3.7]},"goal":{"relative":[-2,0,1]},
                 "control_frame":{"goal_forward_blocks":1,"goal_left_blocks":-2},"legal_candidates":["WAIT","FORWARD"],
                 "local_cells":[
                   {"position":[1,81,4],"knowledge":"OBSERVED","unknown_reason":"","block":"minecraft:stone","fluid":false,"local_collision_boxes":[[0,0,0,1,1,1]],"observed_tick":27},
                   {"position":[2,81,4],"knowledge":"OBSERVED","unknown_reason":"","block":"minecraft:air","fluid":false,"local_collision_boxes":[],"observed_tick":27},
                   {"position":[1,81,5],"knowledge":"UNKNOWN","unknown_reason":"occluded"}]}
                """).getAsJsonObject();
    }
    @Test void observedObstacleSummaryNeverTurnsUnknownIntoAirOrChangesCandidates() {
        var original = raw(); var before = original.deepCopy(); var compact = PolicyObservation.compact(original);
        assertEquals(before, original);
        assertEquals(original.get("goal"), compact.get("goal"));
        assertEquals(original.get("legal_candidates"), compact.get("legal_candidates"));
        assertEquals(1, compact.getAsJsonArray("observed_obstacles").size());
        assertEquals(original.getAsJsonArray("local_cells").get(0), compact.getAsJsonArray("observed_obstacles").get(0));
        assertTrue(compact.get("terrain_note").getAsString().contains("NOT empty"));
        assertTrue(compact.get("goal_direction_description").getAsString().contains("2.000 blocks to your RIGHT"));
        assertFalse(compact.has("local_cells"));
    }
    @Test void httpPayloadUsesExactlyTracedPolicyStateAndOriginalLegalChoices() {
        var raw = raw(); var compact = PolicyObservation.compact(raw); raw.add("policy_state", compact);
        var payload = JevClient.payload(raw, List.of(ControlAction.WAIT, ControlAction.FORWARD), ControlConfig.defaults());
        assertEquals(compact.toString(), payload.get("state").getAsString());
        assertEquals(2, payload.getAsJsonObject("questions").getAsJsonObject("next_action").getAsJsonObject("criteria").size());
    }
}
