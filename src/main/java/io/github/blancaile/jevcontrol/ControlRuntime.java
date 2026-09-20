package io.github.blancaile.jevcontrol;

import com.google.gson.*;
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
    private FakePlayerBody bot;
    private final String version;
    private final String artifactHash;
    private final java.util.logging.Logger logger;
    private Vec3 spawn;
    private Vec3 goal;
    private String dimension;
    private long tick;
    private String status = "IDLE";
    private String lastReason = "No run yet";
    private String lastLog = "none";
    private Run run;
    private String fixtureWall = "off";

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
        long lastTickNanos = System.nanoTime();
        long maxTickGapNanos;
        long observedTick;
        String mode = "direct";
        boolean comparison;
        int inputTicks;
        List<AssistedControl.Point> points = List.of();
        AssistedControl.Segment segment;
        final SegmentHistory segmentHistory=new SegmentHistory();
        long segmentBodyStart;
        boolean wallPlaced;
        Run(ControlConfig config, String policy) { this.config = config; this.policy = policy; }
    }

    ControlRuntime(MinecraftServer server, Path configPath, Path logs, String version, String artifactHash, java.util.logging.Logger logger) {
        this.server = server;
        this.configPath = configPath;
        this.logs = logs;
        this.version = version;
        this.artifactHash = artifactHash;
        this.logger = logger;
    }

    void spawn(ServerLevel world, Vec3 position, float yaw) {
        if (bot != null) throw new IllegalStateException("Despawn the managed bot before spawning another");
        bot = FakePlayerBody.spawn(server, world, position, yaw);
        spawn = position;
        goal = null;
        dimension = world.dimension().identifier().toString();
        status = "READY";
        lastReason = "Bot spawned; set /jev goal x y z";
    }

    void goal(ServerLevel world, Vec3 target) {
        requireBot();
        requireIdle();
        if (world != bot.level()) throw new IllegalArgumentException("Goal must be in the bot's world");
        if (!Double.isFinite(target.x) || !Double.isFinite(target.y) || !Double.isFinite(target.z))
            throw new IllegalArgumentException("Goal must be finite");
        goal = target;
        lastReason = "Goal set";
    }

    void start(String mode) throws IOException {
        if (!Set.of("legacy", "direct", "assisted").contains(mode)) throw new IllegalArgumentException("Expected direct or assisted");
        requireBot(); requireIdle();
        if (goal == null) throw new IllegalStateException("Set /jev goal x y z first");
        var config = readConfig();
        config.requireKey();
        if (goal.distanceTo(spawn) > config.maxDistanceFromSpawn()) throw new IllegalStateException("Goal exceeds maxDistanceFromSpawn");
        begin(config, "JEV", mode);
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
        begin(config, policy, "legacy");
    }

    private void begin(ControlConfig config, String policy, String mode) throws IOException {
        FakePlayerBody.stop(bot);
        var next = new Run(config, policy);
        next.mode = mode.equals("assisted") ? "assisted" : "direct";
        next.comparison = !mode.equals("legacy");
        next.log = new TraceLog(logs, next.lease.runId());
        run = next;
        lastReason = "Started " + policy;
        lastLog = next.log.path.toString();
        try {
            var metadata = new JsonObject();
            metadata.addProperty("run_id", next.lease.runId());
            metadata.addProperty("policy", policy);
            metadata.addProperty("execution_mode", next.mode);
            metadata.addProperty("comparison_budget", next.comparison);
            metadata.addProperty("input_tick_budget", next.comparison ? 240 : config.maxDecisions()*config.actionTicks());
            metadata.addProperty("fault_fixture", System.getProperty("jev.fixture.endpoint") != null);
            metadata.addProperty("minecraft", "1.21.11");
            metadata.addProperty("body", "PAPER_SERVER_PLAYER");
            metadata.addProperty("plugin_version", version);
            metadata.addProperty("artifact_sha256", artifactHash);
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
            long now = System.nanoTime();
            run.maxTickGapNanos = Math.max(run.maxTickGapNanos, now - run.lastTickNanos);
            run.lastTickNanos = now;
            if (bot == null || bot.isRemoved() || !bot.isAlive() || server.getPlayerList().getPlayer(bot.getUUID()) != bot) {
                finish("DEAD_OR_DISCONNECTED", "Managed bot no longer present/alive"); return;
            }
            if (!dimension.equals(bot.level().dimension().identifier().toString())) {
                finish("ERROR", "Dimension changed"); return;
            }
            if (bot.position().distanceTo(spawn) > run.config.maxDistanceFromSpawn()) {
                finish("ERROR", "Bot exceeded maxDistanceFromSpawn"); return;
            }
            if (System.nanoTime() - run.startedNanos > (run.comparison ? Math.min(120, run.config.maxRunSeconds()) : run.config.maxRunSeconds()) * 1_000_000_000L) {
                finish("BUDGET_EXCEEDED", "Wall-time budget reached"); return;
            }
            if (run.comparison && !fixtureWall.equals("off") && !run.wallPlaced && bot.getZ()>=2.5) {
                var intervention=new JsonObject(); intervention.add("self",Observation.self(bot));
                intervention.addProperty("request_id",run.requestId);
                intervention.addProperty("segment_id",run.segment==null ? null : run.segment.id);
                intervention.addProperty("valid_before_wall",bot.getZ()+.3<4);
                int minX=fixtureWall.equals("mirrored-wall") ? -2 : -1;
                var bounds=new JsonArray();
                bounds.add(Observation.vector(new Vec3(minX,81,4))); bounds.add(Observation.vector(new Vec3(minX+2,83,4)));
                intervention.add("wall",bounds);
                for(int x=minX;x<=minX+2;x++) for(int y=81;y<=83;y++)
                    bot.level().setBlock(new net.minecraft.core.BlockPos(x,y,4),net.minecraft.world.level.block.Blocks.STONE.defaultBlockState(),3);
                run.wallPlaced=true; run.log.write("fixture_intervention",tick,intervention);
            }
            if (run.segment != null) {
                advanceSegment();
                if (run.segment != null) return;
            }
            if (run.action != null) {
                if (tick < run.actionEnd) {
                    if (run.comparison) recordDirectTick();
                    return;
                }
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
                if (run.mode.equals("direct") && decision.action() == ControlAction.JUMP_FORWARD && !bot.onGround())
                    throw new IllegalStateException("Jump precondition changed");
                var chosen = new JsonObject();
                chosen.addProperty("request_id", run.requestId);
                chosen.addProperty("latency_ms", decision.latencyMillis());
                chosen.addProperty("snapshot_age_ticks", tick - run.observedTick);
                chosen.add("response", decision.response());
                run.log.write("decision", tick, chosen);
                run.pending = null;
                run.decisions++;
                if (run.mode.equals("assisted")) {
                    var selected = run.points.stream().filter(p -> p.id().equals(decision.choice())).findFirst().orElseThrow();
                    startSegment(selected);
                } else apply(decision.action(), run.comparison ? Math.min(run.config.actionTicks(),240-run.inputTicks) : run.config.actionTicks());
                return;
            }
            if (run.comparison && run.inputTicks >= 240) {
                finish("BUDGET_EXCEEDED", "Input tick budget reached"); return;
            }
            if (run.decisions >= (run.comparison ? Math.min(60, run.config.maxDecisions()) : run.config.maxDecisions())) {
                finish("BUDGET_EXCEEDED", "Decision budget reached"); return;
            }
            run.requestId = run.lease.begin(tick);
            run.observedTick = tick;
            var capture = Observation.capture(bot, goal, tick, run.lease.runId(), run.requestId, run.config, run.previous);
            if (run.mode.equals("assisted")) {
                var generated = AssistedControl.candidates(bot.getX(),bot.getY(),bot.getZ(),goal.x,goal.z);
                run.points = generated.points();
                var names = new JsonArray(); var coordinates = new JsonArray();
                for (var p:run.points) {
                    names.add(p.id()); var point=p.json();
                    point.addProperty("observed_sweep", p.waitOnly() ? "WAIT" : AssistedControl.guard(capture.state().getAsJsonArray("local_cells"),bot.getX(),bot.getY(),bot.getZ(),p.x(),p.z()));
                    coordinates.add(point);
                }
                capture.state().addProperty("schema_version", "jev-assisted-v2");
                capture.state().add("recent_segments",run.segmentHistory.snapshot());
                capture.state().addProperty("execution_mode", "assisted");
                capture.state().addProperty("instructions", AssistedControl.INSTRUCTIONS);
                capture.state().add("legal_candidates", names);
                capture.state().add("point_candidates", coordinates);
                capture.state().add("merged_candidates", generated.merges());
                capture.state().add("excluded_candidates", new JsonObject());
                capture.state().remove("action_ticks");
            }
            run.log.write("observation", tick, capture.state());
            run.pending = run.mode.equals("assisted") ? run.client.choosePoints(capture.state(), run.points) : run.client.choose(capture.state(), capture.candidates());
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
        if (run.comparison) recordDirectTick();
        status = "APPLYING";
    }

    private void recordDirectTick() throws IOException {
        var data = new JsonObject(); data.addProperty("request_id",run.requestId);
        data.addProperty("action",run.action.name()); data.add("self",Observation.self(bot));
        run.log.write("direct_tick",tick,data);
    }

    private void startSegment(AssistedControl.Point point) throws IOException {
        run.segment = new AssistedControl.Segment(run.requestId,point,bot.getX(),bot.getY(),bot.getZ(),tick,240-run.inputTicks);
        run.segmentBodyStart=bot.physicalTicks();
        var event=segmentEvent(); event.add("before",Observation.physicalSelf(bot));
        event.addProperty("max_ticks",run.segment.duration);
        run.log.write("segment_start",tick,event);
        advanceSegment();
    }

    private JsonObject segmentEvent() {
        var event=new JsonObject(); event.addProperty("schema_version","jev-segment-v1");
        event.addProperty("segment_id",run.segment.id); event.addProperty("request_id",run.segment.requestId);
        event.add("selected",run.segment.endpoint.json()); return event;
    }

    private void advanceSegment() throws IOException {
        var s=run.segment;
        String reason=s.observe(bot.getX(),bot.getY(),bot.getZ(),s.startTick+bot.physicalTicks()-run.segmentBodyStart,bot.horizontalCollision);
        JsonObject observation=null;
        if(reason==null && !s.endpoint.waitOnly()) {
            if(!bot.onGround()) reason="UNSUPPORTED_TERRAIN";
            // Conservative input plus inertia bound; the full endpoint stays fixed.
            double speed=bot.getDeltaMovement().horizontalDistance();
            double remaining=Math.hypot(s.endpoint.x()-bot.getX(),s.endpoint.z()-bot.getZ());
            double lookahead=Math.min(remaining,.25+speed*2.3);
            if(s.path+lookahead>AssistedControl.MAX_DISTANCE) reason="DISTANCE_LIMIT";
            if(reason==null) {
                observation=Observation.capture(bot,goal,tick,run.lease.runId(),run.requestId,run.config,run.previous).state();
                String guard=AssistedControl.guard(observation.getAsJsonArray("local_cells"),bot.getX(),bot.getY(),bot.getZ(),
                        bot.getX()+(s.endpoint.x()-bot.getX())*lookahead/remaining,
                        bot.getZ()+(s.endpoint.z()-bot.getZ())*lookahead/remaining);
                if(!guard.equals("CLEAR")) reason=guard;
            }
        }
        if(reason!=null) { endSegment(reason); return; }
        float yaw=s.endpoint.waitOnly()?bot.getYRot():s.yaw(bot.getX(),bot.getZ());
        float forward=s.forward(bot.getX(),bot.getZ());
        var event=segmentEvent(); event.add("before",Observation.physicalSelf(bot));
        event.addProperty("yaw",yaw); event.addProperty("forward",forward);
        event.addProperty("strafe",0); event.addProperty("jump",false);
        event.addProperty("correction_reason",s.endpoint.waitOnly()?"SELECTED_WAIT":"FIXED_ENDPOINT_GEOMETRY");
        if(observation!=null) event.add("local_cells",observation.get("local_cells"));
        var executingRun=run;
        FakePlayerBody.assistedInput(bot,yaw,forward,()->{
            // Record consumed input, not an input released before the body tick.
            if(run!=executingRun || run.segment!=s) { FakePlayerBody.stop(bot); return; }
            event.add("before",Observation.physicalSelf(bot));
            try { run.log.write("segment_tick",tick,event); }
            catch(IOException ex) { finish("ERROR","Segment input trace write failed"); }
        });
        status="APPLYING_SEGMENT";
    }

    private void endSegment(String reason) throws IOException {
        FakePlayerBody.stop(bot);
        var s=run.segment; var event=segmentEvent();
        s.path+=Math.hypot(bot.getX()-s.lastX,bot.getZ()-s.lastZ);
        int elapsed=(int)(bot.physicalTicks()-run.segmentBodyStart); run.inputTicks+=elapsed;
        event.addProperty("actual_ticks",elapsed); event.addProperty("reason",reason);
        event.addProperty("path_length",s.path); event.add("after",Observation.physicalSelf(bot));
        event.add("displacement",Observation.vector(bot.position().subtract(new Vec3(s.startX,s.startY,s.startZ))));
        run.log.write("segment_result",tick,event); run.segmentHistory.add(event);
        run.previous=event; run.segment=null; status="OBSERVING";
    }

    private void recordResult() throws IOException {
        var result = new JsonObject();
        result.addProperty("request_id", run.requestId);
        result.addProperty("action", run.action.name());
        result.addProperty("actual_ticks", tick - run.actionStart);
        run.inputTicks += (int)(tick-run.actionStart);
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

    void fixtureWall(String name) {
        requireIdle();
        if (!Boolean.getBoolean("jev.fixture.enabled") || !org.bukkit.Bukkit.getIp().equals("127.0.0.1"))
            throw new IllegalStateException("Fixture commands require an explicitly isolated loopback server");
        if(!Set.of("off","original-wall","mirrored-wall","initial-yaw").contains(name))
            throw new IllegalArgumentException("Unknown fixed wall fixture");
        fixtureWall=name;
    }

    private void finish(String terminal, String reason) {
        if (bot != null) FakePlayerBody.stop(bot);
        if (run != null && run.segment != null && bot != null) {
            try { endSegment(terminal); }
            catch (IOException ex) { terminal="ERROR"; reason="Segment trace write failed"; }
        }
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
            data.addProperty("input_ticks", ended.inputTicks + (ended.action == null ? 0 : tick-ended.actionStart));
            data.addProperty("elapsed_ms", (System.nanoTime() - ended.startedNanos) / 1_000_000);
            data.addProperty("max_tick_gap_ms", ended.maxTickGapNanos / 1_000_000.0);
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
            logger.info("Jev run " + ended.lease.runId() + " ended " + status + ": " + lastReason);
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
        if (!dimension.equals(bot.level().dimension().identifier().toString()))
            throw new IllegalStateException("Bot changed world outside the experiment; despawn and inspect other plugins");
        if (bot.position().distanceTo(spawn) > readDistanceLimit())
            throw new IllegalStateException("Bot moved outside the spawn boundary before input; despawn and inspect other plugins");
    }
    private double readDistanceLimit() {
        try { return readConfig().maxDistanceFromSpawn(); }
        catch (IOException ex) { throw new IllegalStateException("Cannot validate spawn boundary; check Jev configuration"); }
    }
    private void requireIdle() { if (run != null) throw new IllegalStateException("Stop the active run first"); }
    private ControlConfig readConfig() throws IOException {
        try { return ControlConfig.read(configPath); }
        catch (RuntimeException ex) { throw new IOException("Invalid plugins/JevControl/jev-control.json; check required fields and ranges"); }
    }
}
