package io.github.blancaile.jevcontrol;

import com.google.gson.*;
import java.util.*;

/** Pure geometry and bounded execution. Never chooses a destination. */
final class AssistedControl {
    static final double LENGTH = 0.8, TOLERANCE = 0.12, MAX_DISTANCE = 1.0;
    static final int MAX_TICKS = 12, WAIT_TICKS = 4, STALL_TICKS = 3;
    static final double STALL_DISTANCE = 0.01;
    static final String INSTRUCTIONS = "Choose one nearby destination or WAIT to reach the given goal. "
            + "Coordinates use world axes, independent of facing. Code only steers toward your chosen fixed endpoint "
            + "for at most 12 ticks and stops on arrival, collision, unknown space, stall or deadline. "
            + "You choose any detour, retreat, continuation or return toward the goal in a new decision. "
            + "Use the last four measured segment outcomes to avoid repeating unsuccessful back-and-forth movement. "
            + "A detour can temporarily increase the goal distance. "
            + "When goalward movement is blocked, choose a clear sideways destination and keep progressing "
            + "on that side until a goalward destination has a CLEAR observed sweep. "
            + "Do not undo a completed sideways step just to reduce goal distance while the goalward path is blocked. "
            + "If that side is also blocked or unknown, reassess using the observed cells and your recent outcomes. "
            + "Unknown cells are not known to be empty. No automatic detour or pathfinder exists.";

    record Point(String id, double x, double y, double z, boolean waitOnly) {
        JsonObject json() {
            var value = new JsonObject(); value.addProperty("id", id);
            var p = new JsonArray(); p.add(x); p.add(y); p.add(z); value.add("endpoint", p);
            value.addProperty("max_ticks", waitOnly ? WAIT_TICKS : MAX_TICKS);
            value.addProperty("kind", waitOnly ? "WAIT" : "WALK"); return value;
        }
    }
    record Candidates(List<Point> points, JsonObject merges) {}
    static Candidates candidates(double x, double y, double z, double gx, double gz) {
        if (!Double.isFinite(x+y+z+gx+gz)) throw new IllegalArgumentException("Nonfinite geometry");
        var points = new ArrayList<Point>(); var merges = new JsonObject();
        String[] ids = {"E", "SE", "S", "SW", "W", "NW", "N", "NE"};
        for (int i=0; i<8; i++) {
            double angle = i*Math.PI/4;
            points.add(new Point(ids[i], x+LENGTH*Math.cos(angle), y, z+LENGTH*Math.sin(angle), false));
        }
        double distance = Math.hypot(gx-x, gz-z);
        if (distance > 1e-9) {
            double length = Math.min(LENGTH, distance);
            var target = new Point("GOAL_DIRECTION", x+length*(gx-x)/distance, y, z+length*(gz-z)/distance, false);
            var duplicate = points.stream().filter(p -> Math.hypot(p.x-target.x,p.z-target.z)<1e-9).findFirst();
            if (duplicate.isPresent()) merges.addProperty(target.id, duplicate.get().id);
            else points.add(target);
        } else merges.addProperty("GOAL_DIRECTION", "WAIT");
        points.add(new Point("WAIT", x, y, z, true));
        return new Candidates(List.copyOf(points), merges);
    }

    static final class Segment {
        final String id, requestId;
        final Point endpoint;
        final double startX, startY, startZ;
        final long startTick;
        final int duration;
        double path, lastX, lastZ;
        int stalled;
        Segment(String requestId, Point endpoint, double x, double y, double z, long tick, int budget) {
            if (Math.hypot(endpoint.x-x,endpoint.z-z)>MAX_DISTANCE || Math.abs(endpoint.y-y)>.1 || budget<1)
                throw new IllegalStateException("Selected endpoint no longer satisfies segment bounds");
            this.id=UUID.randomUUID().toString(); this.requestId=requestId; this.endpoint=endpoint;
            startX=lastX=x; startY=y; startZ=lastZ=z; startTick=tick;
            duration=Math.min(budget, endpoint.waitOnly ? WAIT_TICKS : MAX_TICKS);
        }
        String observe(double x, double y, double z, long tick, boolean collision) {
            double moved=Math.hypot(x-lastX,z-lastZ); path+=moved; lastX=x; lastZ=z;
            if (tick>startTick) stalled=moved<STALL_DISTANCE ? stalled+1 : 0;
            if (path>MAX_DISTANCE+1e-6 || Math.abs(y-startY)>.1) return "DISTANCE_LIMIT";
            if (endpoint.waitOnly) return tick-startTick>=duration ? "WAIT_COMPLETED" : null;
            if (collision && tick>startTick) return "COLLISION";
            if (Math.hypot(endpoint.x-x,endpoint.z-z)<=TOLERANCE) return "ENDPOINT_REACHED";
            if (tick-startTick>=duration) return "DEADLINE";
            if (stalled>=STALL_TICKS) return "STALLED";
            return null;
        }
        float yaw(double x, double z) { return (float)Math.toDegrees(Math.atan2(-(endpoint.x-x), endpoint.z-z)); }
        float forward(double x,double z) {
            return endpoint.waitOnly ? 0 : (float)Math.min(1, Math.hypot(endpoint.x-x,endpoint.z-z)*2);
        }
    }

    /** Inspect only recorded OBSERVED cells along a short swept player footprint. */
    static String guard(JsonArray cells, double x, double y, double z, double toX, double toZ) {
        var known = new HashMap<String,JsonObject>();
        for (var item:cells) {
            var c=item.getAsJsonObject(); var p=c.getAsJsonArray("position");
            known.put(p.get(0).getAsInt()+","+p.get(1).getAsInt()+","+p.get(2).getAsInt(), c);
        }
        String unresolved=null;
        for(int step=0;step<=10;step++) {
            double px=x+(toX-x)*step/10, pz=z+(toZ-z)*step/10;
            for(int bx=(int)Math.floor(px-.3+1e-7);bx<=Math.floor(px+.3-1e-7);bx++)
                for(int bz=(int)Math.floor(pz-.3+1e-7);bz<=Math.floor(pz+.3-1e-7);bz++) {
                    for(int by=(int)Math.floor(y);by<=Math.floor(y+1.8-1e-7);by++) {
                        var c=known.get(bx+","+by+","+bz);
                        if(c==null || !c.get("knowledge").getAsString().equals("OBSERVED")) { unresolved="UNKNOWN"; continue; }
                        if(c.get("fluid").getAsBoolean() && unresolved==null) unresolved="UNSUPPORTED_TERRAIN";
                        for(var b:c.getAsJsonArray("local_collision_boxes")) {
                            var box=b.getAsJsonArray();
                            if(px+.3>bx+box.get(0).getAsDouble()+1e-7 && px-.3<bx+box.get(3).getAsDouble()-1e-7
                                    && y+1.8>by+box.get(1).getAsDouble()+1e-7 && y<by+box.get(4).getAsDouble()-1e-7
                                    && pz+.3>bz+box.get(2).getAsDouble()+1e-7 && pz-.3<bz+box.get(5).getAsDouble()-1e-7) return "OBSERVED_OBSTACLE";
                        }
                    }
                    int floorY=(int)Math.floor(y-1e-6);
                    var floor=known.get(bx+","+floorY+","+bz);
                    if(floor==null || !floor.get("knowledge").getAsString().equals("OBSERVED")) { unresolved="UNKNOWN"; continue; }
                    boolean supported=false;
                    for(var b:floor.getAsJsonArray("local_collision_boxes")) {
                        var box=b.getAsJsonArray();
                        if(Math.abs(floorY+box.get(4).getAsDouble()-y)<.01
                                && box.get(0).getAsDouble()==0 && box.get(2).getAsDouble()==0
                                && box.get(3).getAsDouble()==1 && box.get(5).getAsDouble()==1) supported=true;
                    }
                    if(!supported && unresolved==null) unresolved="UNSUPPORTED_TERRAIN";
                }
        }
        return unresolved==null ? "CLEAR" : unresolved;
    }
}
