package io.github.blancaile.jevcontrol;

import com.google.gson.JsonObject;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class SegmentHistoryTest {
    @Test void retainsOnlyLastFourActualResultsAndDoesNotShareMutableSnapshots() {
        var history=new SegmentHistory(); assertEquals(0,history.snapshot().size());
        for(int i=0;i<6;i++) {
            var result=new JsonObject();result.addProperty("request_id","request-"+i);history.add(result);
            result.addProperty("request_id","mutated");
        }
        var first=history.snapshot();assertEquals(4,first.size());
        assertEquals("request-2",first.get(0).getAsJsonObject().get("request_id").getAsString());
        first.get(0).getAsJsonObject().addProperty("request_id","changed-output");
        assertEquals("request-2",history.snapshot().get(0).getAsJsonObject().get("request_id").getAsString());
        assertEquals(0,new SegmentHistory().snapshot().size());
    }
}
