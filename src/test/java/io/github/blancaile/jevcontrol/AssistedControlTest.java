package io.github.blancaile.jevcontrol;

import com.google.gson.*;
import org.junit.jupiter.api.Test;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;

class AssistedControlTest {
    @Test void candidatesRetainAllDirectionsAndOnlyMergeIdenticalPoints() {
        var c=AssistedControl.candidates(.5,81,.5,.5,20.5);
        assertEquals(9,c.points().size()); assertEquals("S",c.merges().get("GOAL_DIRECTION").getAsString());
        assertTrue(c.points().stream().anyMatch(p->p.id().equals("N") && p.z()<.5));
        assertEquals(10,AssistedControl.candidates(.5,81,.5,4,20).points().size());
        for(var p:c.points()) assertTrue(Math.hypot(p.x()-.5,p.z()-.5)<=1);
    }
    private AssistedControl.Segment segment(boolean wait) {
        return new AssistedControl.Segment("request",new AssistedControl.Point("E",1.3,81,.5,wait),.5,81,.5,10,240);
    }
    @Test void destinationNeverChangesAndYawOnlyTracksSelectedEndpoint() {
        var s=segment(false); assertEquals(-90,s.yaw(.5,.5),1e-6);
        assertEquals(1.3,s.endpoint.x()); assertEquals(.5,s.endpoint.z());
        assertThrows(IllegalStateException.class,()->new AssistedControl.Segment("id",s.endpoint,10,81,.5,1,10));
        assertEquals("ENDPOINT_REACHED",s.observe(1.2,81,.5,12,false));
    }
    @Test void releasesForCollisionStallDistanceAndDeadline() {
        assertEquals("COLLISION",segment(false).observe(.6,81,.5,11,true));
        assertEquals("DISTANCE_LIMIT",segment(false).observe(2,81,.5,11,false));
        assertEquals("DEADLINE",segment(false).observe(.6,81,.5,22,false));
        var s=segment(false);
        assertNull(s.observe(.5,81,.5,11,false)); assertNull(s.observe(.5,81,.5,12,false));
        assertEquals("STALLED",s.observe(.5,81,.5,13,false));
        assertNull(segment(true).observe(.5,81,.5,13,false));
        assertEquals("WAIT_COMPLETED",segment(true).observe(.5,81,.5,14,false));
    }
    static JsonArray floor() {
        var cells=new JsonArray();
        for(int x=-2;x<=2;x++) for(int z=-2;z<=2;z++) for(int y=80;y<=82;y++) {
            var c=new JsonObject(); var p=new JsonArray(); p.add(x);p.add(y);p.add(z);
            c.add("position",p);c.addProperty("knowledge","OBSERVED");c.addProperty("fluid",false);
            c.add("local_collision_boxes",JsonParser.parseString(y==80?"[[0,0,0,1,1,1]]":"[]"));cells.add(c);
        }
        return cells;
    }
    @Test void unknownAndBlockedCellsNeverBecomeEmptySpace() {
        var cells=floor(); assertEquals("CLEAR",AssistedControl.guard(cells,.5,81,.5,1.3,.5));
        for(var c:cells) {
            var o=c.getAsJsonObject(); var p=o.getAsJsonArray("position");
            if(p.get(0).getAsInt()==1 && p.get(1).getAsInt()==81 && p.get(2).getAsInt()==0) {
                o.addProperty("knowledge","UNKNOWN");
                assertEquals("UNKNOWN",AssistedControl.guard(cells,.5,81,.5,1.3,.5));
                o.addProperty("knowledge","OBSERVED");o.add("local_collision_boxes",JsonParser.parseString("[[0,0,0,1,1,1]]"));
                assertEquals("OBSERVED_OBSTACLE",AssistedControl.guard(cells,.5,81,.5,1.3,.5));
            }
        }
        assertEquals("UNKNOWN",AssistedControl.guard(new JsonArray(),.5,81,.5,1.3,.5));
    }
    @Test void assistedResponseMustBelongToOfferedIds() {
        String response="{\"model\":\"jev-1.13.0\",\"answers\":{\"next_action\":{\"choice\":\"E\",\"confidence\":1,\"probabilities\":{\"E\":1,\"WAIT\":0}}}}";
        assertEquals("E",JevClient.parseChoices(response,List.of("E","WAIT"),"jev-1.13.0",1).choice());
        assertThrows(IllegalStateException.class,()->JevClient.parseChoices(response,List.of("W","WAIT"),"jev-1.13.0",1));
    }
}
