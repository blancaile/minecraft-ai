package io.github.blancaile.jevcontrol;

import com.google.gson.Gson;
import net.kyori.adventure.text.serializer.plain.PlainTextComponentSerializer;
import org.bukkit.Bukkit;
import java.io.IOException;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;

/** Trusted server-admin SFTP boundary. I/O off-thread, command execution on the main thread. */
final class CommandInbox implements AutoCloseable {
    private final JevControlPlugin plugin;
    private final Path inbox;
    private final Path receipts;
    private final ScheduledExecutorService io = Executors.newSingleThreadScheduledExecutor(r -> {
        var thread = new Thread(r, "jev-command-inbox"); thread.setDaemon(true); return thread;
    });
    private volatile boolean active = true;

    CommandInbox(JevControlPlugin plugin) throws IOException {
        this.plugin = plugin;
        inbox = plugin.getDataFolder().toPath().resolve("inbox");
        receipts = plugin.getDataFolder().toPath().resolve("receipts");
        Files.createDirectories(inbox);
        Files.createDirectories(receipts);
        io.scheduleWithFixedDelay(this::poll, 1, 1, TimeUnit.SECONDS);
    }

    private void poll() {
        if (!active) return;
        try (var stream = Files.list(inbox)) {
            for (var file : stream.filter(p -> p.getFileName().toString().matches("[0-9a-f-]{36}\\.json")).limit(16).toList()) {
                if (!active) return;
                var claimed = file.resolveSibling(file.getFileName() + ".processing");
                Files.move(file, claimed, StandardCopyOption.ATOMIC_MOVE);
                String id = file.getFileName().toString().replace(".json", "");
                if (Files.exists(receipts.resolve(id + ".json"))) { Files.delete(claimed); continue; }
                try {
                    if (Files.isSymbolicLink(claimed) || Files.size(claimed) > 2048) throw new IllegalArgumentException();
                    var request = QueueRequest.parse(file.getFileName().toString(), Files.readString(claimed), System.currentTimeMillis());
                    Bukkit.getScheduler().runTask(plugin, () -> execute(request, claimed));
                } catch (RuntimeException ex) {
                    receipt(id, false, List.of("Invalid, expired or disabled command request"), claimed);
                }
            }
        } catch (IOException ex) {
            // Fail closed: avoid an endlessly repeating error in the shared server log.
            active = false;
            plugin.getLogger().severe("JEV_INBOX_ERROR stopped after I/O failure; inspect directory permissions");
        }
    }

    private void execute(QueueRequest request, Path claimed) {
        var output = new ArrayList<String>();
        if (!active || request.expiresAtMillis() <= System.currentTimeMillis()) {
            output.add("JEV_ERROR Cancelled or expired before execution");
        } else {
            var sender = Bukkit.createCommandSender(message -> output.add(PlainTextComponentSerializer.plainText().serialize(message)));
            plugin.onCommand(sender, Objects.requireNonNull(plugin.getCommand("jev")), "jev", request.command().substring(4).split(" +"));
        }
        boolean success = !output.isEmpty() && output.stream().allMatch(s -> s.startsWith("JEV_OK "));
        if (!io.isShutdown()) io.execute(() -> {
            try { receipt(request.id(), success, output, claimed); }
            catch (IOException ex) { plugin.getLogger().severe("JEV_INBOX_ERROR receipt write failed"); }
        });
    }

    private void receipt(String id, boolean success, List<String> output, Path claimed) throws IOException {
        Path destination = receipts.resolve(id + ".json");
        Path staging = receipts.resolve(id + ".tmp");
        Files.writeString(staging, new Gson().toJson(Map.of("id", id, "success", success, "output", output,
                "completed_at_ms", System.currentTimeMillis())), StandardOpenOption.CREATE_NEW);
        Files.move(staging, destination, StandardCopyOption.ATOMIC_MOVE);
        Files.delete(claimed);
    }

    @Override public void close() {
        active = false;
        io.shutdown(); // Claimed requests are never replayed after disable/reload.
    }
}
