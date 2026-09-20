package io.github.blancaile.jevcontrol;

import com.google.gson.*;
import java.util.ArrayDeque;

/** Bounded measured results only. No destination ranking or inferred route. */
final class SegmentHistory {
    static final int LIMIT=4;
    private final ArrayDeque<JsonObject> results=new ArrayDeque<>();
    void add(JsonObject result) {
        results.addLast(result.deepCopy());
        if(results.size()>LIMIT) results.removeFirst();
    }
    JsonArray snapshot() {
        var value=new JsonArray();results.forEach(r->value.add(r.deepCopy()));return value;
    }
}
