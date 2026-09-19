package io.github.blancaile.jevcontrol;

import com.google.gson.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.Instant;

final class TraceLog implements AutoCloseable {
    private final BufferedWriter writer;
    final Path path;
    TraceLog(Path directory, String run) throws IOException {
        Files.createDirectories(directory);
        path = directory.resolve(run + ".jsonl");
        writer = Files.newBufferedWriter(path, StandardCharsets.UTF_8, StandardOpenOption.CREATE_NEW);
    }
    void write(String kind, long tick, JsonObject data) throws IOException {
        var event = new JsonObject();
        event.addProperty("schema_version", "jev-control-trace-v1");
        event.addProperty("event", kind);
        event.addProperty("server_tick", tick);
        event.addProperty("time", Instant.now().toString());
        event.add("data", data);
        writer.write(event.toString()); writer.newLine(); writer.flush();
    }
    @Override public void close() throws IOException { writer.close(); }
}
