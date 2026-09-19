package io.github.blancaile.jevcontrol;

import carpet.patches.EntityPlayerMPFake;
import com.google.gson.*;
import net.fabricmc.loader.api.FabricLoader;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.phys.Vec3;
import java.io.IOException;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.CompletableFuture;

/** Entire mutable state belongs to the Minecraft server thread; HTTP completion only fills a future. */
final class ControlRuntime {
    private final MinecraftServer server;
    private final Path configPath;
    private final Path logs;
    private EntityPlayerMPFake bot;
    private Vec3 spawn;
    private Vec3 goal;
    private String dimension;
    private long tick;
    private String status = "IDLE";
    private String lastReason = "No run yet";
    private String lastLog = "none";
    private Run run;

    private static final class Run {
        final ControlConfig config;
        final DecisionLease lease = new DecisionLease();
        final long startedNanos = System.nanoTime();
        final String policy;
        TraceLog log;
        JevClient client;
        CompletableFuture<JevClient.Decision> pending;
        String requestId;
        long actionStart;
        long actionEnd;
        int decisions;
        ControlAction action;
        Vec3 before;
        JsonObject previous = new JsonObject();
        int smokePhase;
        long smokeDeadline;
        Vec3 stopPosition;
        Run(ControlConfig config, String policy) { this.config = config; this.policy = policy; }
    }

    ControlRuntime(MinecraftServer server) {
        this.server = server;
        configPath = FabricLoader.getInstance().getConfigDir().resolve("jev-control.json");
        logs = FabricLoader.getInstance().getGameDir().resolve("logs/jev-control");
    }

    void spawn(ServerLevel world, Vec3 position, float yaw) {
        if (bot != null) throw new IllegalStateException("Despawn the managed bot before spawning another");
        bot = FakePlayerBody.spawn(server, world, position, yaw);
        spawn = position;
        goal = null;
        dimension = world.dimension().location().toString();
        status = "READY";
        lastReason = "Bot spawned; set /jev goal x y z";
    }

    void goal(Vec3 target) {
        requireBot();
        requireIdle();
        if (!Double.isFinite(target.x) || !Double.isFinite(target.y) || !Double.isFinite(target.z))
            throw new IllegalArgumentException("Goal must be finite");
        goal = target;
        lastReason = "Goal set";
    }

    void start() throws IOException {
        requireBot(); requireIdle();
        if (goal == null) throw new IllegalStateException("Set /jev goal x y z first");
        var config = readConfig();
        config.requireKey();
        if (goal.distanceTo(spawn) > config.maxDistanceFromSpawn()) throw new IllegalStateException("Goal exceeds maxDistanceFromSpawn");
        begin(config, "JEV");
        try {
            run.client = new JevClient(config);
            status = "OBSERVING";
        } catch (RuntimeException ex) {
            finish("ERROR", "Could not initialize Jev client");
            throw new IllegalStateException("Could not initialize Jev client");
        }
    }

    void manual(ControlAction action, boolean smoke) throws IOException {
        requireBot(); requireIdle();
        if (smoke && !bot.onGround()) throw new IllegalStateException("Smoke requires a grounded bot on a clear flat floor");
        begin(readConfig(), smoke ? "SMOKE_NO_MODEL" : "MANUAL_NO_MODEL");
        try {
            apply(action, smoke ? 8 : run.config.actionTicks());
            if (smoke) run.smokePhase = 1;
        } catch (RuntimeException | IOException ex) {
            finish("ERROR", "Manual input failed");
            throw new IllegalStateException("Manual input failed");
        }
    }

    Path observe() throws IOException {
        requireBot(); requireIdle();
        var capture = Observation.capture(bot, goal, tick, "OBSERVE_ONLY", UUID.randomUUID().toString(), readConfig(), new JsonObject());
        try (var log = new TraceLog(logs, "observe-" + UUID.randomUUID())) {
            log.write("observation", tick, capture.state());
            return log.path;
        }
    }

    private void begin(ControlConfig config, String policy) throws IOException {
        FakePlayerBody.stop(bot);
        var next = new Run(config, policy);
        next.log = new TraceLog(logs, next.lease.runId());
        run = next;
        lastReason = "Started " + policy;
        lastLog = next.log.path.toString();
        try {
            var metadata = new JsonObject();
            metadata.addProperty("run_id", next.lease.runId());
            metadata.addProperty("policy", policy);
            metadata.addProperty("minecraft", "1.21.3");
            metadata.addProperty("carpet", "1.4.158");
            metadata.addProperty("mod_version", FabricLoader.getInstance().getModContainer("jev_control").orElseThrow().getMetadata().getVersion().getFriendlyString());
            var publicConfig = new Gson().toJsonTree(config).getAsJsonObject();
            publicConfig.remove("apiKey");
            metadata.add("config", publicConfig);
            metadata.add("spawn", Observation.vector(spawn));
            if (goal != null) metadata.add("goal", Observation.vector(goal));
            metadata.addProperty("dimension", dimension);
            next.log.write("run_started", tick, metadata);
        } catch (IOException | RuntimeException ex) {
            finish("ERROR", "Could not record run metadata");
            throw new IOException("Could not record run metadata");
        }
    }

    void tick() {
        tick++;
        if (run == null) return;
        try {
            if (bot == null || bot.isRemoved() || !bot.isAlive() || server.getPlayerList().getPlayer(bot.getUUID()) != bot) {
                finish("DEAD_OR_DISCONNECTED", "Managed bot no longer present/alive"); return;
            }
            if (!dimension.equals(bot.serverLevel().dimension().location().toString())) {
                finish("ERROR", "Dimension changed"); return;
            }
            if (bot.position().distanceTo(spawn) > run.config.maxDistanceFromSpawn()) {
                finish("ERROR", "Bot exceeded maxDistanceFromSpawn"); return;
            }
            if (System.nanoTime() - run.startedNanos > run.config.maxRunSeconds() * 1_000_000_000L) {
                finish("BUDGET_EXCEEDED", "Wall-time budget reached"); return;
            }
            if (run.action != null) {
                if (tick < run.actionEnd) return;
                FakePlayerBody.stop(bot);
                recordResult();
                if (run.policy.equals("MANUAL_NO_MODEL")) { finish("MANUAL_COMPLETED", "Input released"); return; }
                if (run.smokePhase == 1) {
                    if (bot.position().distanceTo(run.before) < 0.05) { finish("ERROR", "Smoke: no physical displacement"); return; }
                    run.smokePhase = 2; run.smokeDeadline = tick + 20; status = "SMOKE_SETTLING"; return;
                }
            }
            if (run.smokePhase == 2 && tick >= run.smokeDeadline) {
                run.stopPosition = bot.position(); run.smokeDeadline = tick + 5; run.smokePhase = 3;
                return;
            }
            if (run.smokePhase == 3 && tick >= run.smokeDeadline) {
                if (bot.position().distanceTo(run.stopPosition) > 0.05) finish("ERROR", "Smoke: motion continued after input release/settling");
                else finish("SMOKE_PASSED", "Physical movement and input release verified; no Jev call made");
                return;
            }
            if (run.smokePhase > 0) return;
            if (goal != null && bot.position().distanceTo(goal) <= run.config.goalRadius()) {
                finish("GOAL_REACHED", "Actual player position within goal radius"); return;
            }
            if (run.pending != null) {
                if (!run.pending.isDone()) return;
                var decision = run.pending.join();
                run.lease.accept(run.requestId, tick, run.config.maxObservationAgeTicks());
                // Fresh mechanical check; does not select a replacement action.
                if (decision.action() == ControlAction.JUMP_FORWARD && !bot.onGround())
                    throw new IllegalStateException("Jump precondition changed");
                var chosen = new JsonObject();
                chosen.addProperty("request_id", run.requestId);
                chosen.addProperty("latency_ms", decision.latencyMillis());
                chosen.add("response", decision.response());
                run.log.write("decision", tick, chosen);
                run.pending = null;
                run.decisions++;
                apply(decision.action(), run.config.actionTicks());
                return;
            }
            if (run.decisions >= run.config.maxDecisions()) {
                finish("BUDGET_EXCEEDED", "Decision budget reached"); return;
            }
            run.requestId = run.lease.begin(tick);
            var capture = Observation.capture(bot, goal, tick, run.lease.runId(), run.requestId, run.config, run.previous);
            run.log.write("observation", tick, capture.state());
            run.pending = run.client.choose(capture.state(), capture.candidates());
            status = "WAITING_FOR_POLICY";
        } catch (Exception ex) {
            String reason = "Control failure: " + ex.getClass().getSimpleName();
            // These local errors contain only fixed messages, never raw HTTP bodies or config values.
            if (ex instanceof IllegalStateException) reason = ex.getMessage();
            if (ex instanceof java.util.concurrent.CompletionException && ex.getCause() instanceof IllegalStateException)
                reason = ex.getCause().getMessage();
            finish("ERROR", reason);
        }
    }

    private void apply(ControlAction action, int duration) throws IOException {
        run.before = bot.position();
        run.actionStart = tick;
        run.actionEnd = tick + duration;
        run.action = action;
        var event = new JsonObject();
        event.addProperty("source", run.policy);
        event.addProperty("request_id", run.requestId);
        event.addProperty("action", action.name());
        event.addProperty("duration_ticks", duration);
        event.add("before", Observation.self(bot));
        run.log.write("input", tick, event);
        FakePlayerBody.apply(bot, action);
        status = "APPLYING";
    }

    private void recordResult() throws IOException {
        var result = new JsonObject();
        result.addProperty("request_id", run.requestId);
        result.addProperty("action", run.action.name());
        result.addProperty("actual_ticks", tick - run.actionStart);
        result.add("displacement", Observation.vector(bot.position().subtract(run.before)));
        result.add("after", Observation.self(bot));
        result.addProperty("horizontal_collision", bot.horizontalCollision);
        result.addProperty("outcome", bot.horizontalCollision ? "BLOCKED" : "INTERVAL_COMPLETED");
        run.log.write("result", tick, result);
        run.previous = result;
        run.action = null;
        status = "OBSERVING";
    }

    void stop() { finish("CANCELLED", "Operator stopped run"); }

    private void finish(String terminal, String reason) {
        if (bot != null) FakePlayerBody.stop(bot);
        var ended = run;
        run = null; // No late HTTP completion can refer to an active run after this point.
        status = terminal; lastReason = reason;
        if (ended != null) {
            ended.lease.close();
            if (ended.pending != null) ended.pending.cancel(true);
            if (ended.client != null) ended.client.close();
            var data = new JsonObject();
            data.addProperty("status", terminal);
            data.addProperty("reason", reason);
            data.addProperty("decisions", ended.decisions);
            data.addProperty("elapsed_ms", (System.nanoTime() - ended.startedNanos) / 1_000_000);
            if (bot != null) data.add("final", Observation.self(bot));
            if (ended.action != null) {
                data.addProperty("interrupted_action", ended.action.name());
                data.addProperty("actual_action_ticks", tick - ended.actionStart);
            }
            try { ended.log.write("terminal", tick, data); }
            catch (IOException ex) { status = "ERROR"; lastReason = "Trace write failed; original terminal: " + terminal; }
            finally {
                try { ended.log.close(); }
                catch (IOException ex) { status = "ERROR"; lastReason = "Trace close failed"; }
            }
            JevControlMod.LOGGER.info("Jev run {} ended {}: {}", ended.lease.runId(), status, lastReason);
        }
    }

    void despawn() {
        if (bot == null) throw new IllegalStateException("No managed bot");
        finish("CANCELLED", "Despawn requested");
        FakePlayerBody.despawn(bot);
        bot = null; goal = null;
    }
    void shutdown() {
        finish("CANCELLED", "Server stopping");
        if (bot != null) { FakePlayerBody.despawn(bot); bot = null; }
    }
    String status() {
        return "state=" + status + " bot=" + (bot == null ? "none" : bot.getUUID())
                + " goal=" + (goal == null ? "unset" : goal)
                + " decisions=" + (run == null ? "see trace" : run.decisions)
                + " reason=" + lastReason + " trace=" + lastLog;
    }
    private void requireBot() {
        if (bot == null || bot.isRemoved() || !bot.isAlive()) throw new IllegalStateException("Spawn a live bot first");
    }
    private void requireIdle() { if (run != null) throw new IllegalStateException("Stop the active run first"); }
    private ControlConfig readConfig() throws IOException {
        try { return ControlConfig.read(configPath); }
        catch (RuntimeException ex) { throw new IOException("Invalid config/jev-control.json; check required fields and ranges"); }
    }
}
