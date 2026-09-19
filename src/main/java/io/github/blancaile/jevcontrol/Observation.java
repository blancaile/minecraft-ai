package io.github.blancaile.jevcontrol;

import com.google.gson.*;
import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.level.ClipContext;
import net.minecraft.world.phys.*;
import java.time.Instant;
import java.util.*;

/** Read only, server thread only; unloaded/occluded cells stay UNKNOWN. */
final class Observation {
    record Capture(JsonObject state, List<ControlAction> candidates) {}

    static Capture capture(ServerPlayer bot, Vec3 goal, long tick, String run, String request,
                           ControlConfig config, JsonObject previous) {
        var world = bot.level();
        var state = new JsonObject();
        state.addProperty("schema_version", "jev-control-v1");
        state.addProperty("episode_id", run);
        state.addProperty("observation_id", request);
        state.addProperty("bot_id", bot.getUUID().toString());
        state.addProperty("server_tick", tick);
        state.addProperty("observed_at", Instant.now().toString());
        state.addProperty("dimension", world.dimension().identifier().toString());
        state.addProperty("action_ticks", config.actionTicks());
        state.addProperty("coordinate_convention", "+x east, +y up, +z south; yaw 0=south, 90=west, 180=north, -90=east");
        state.add("self", self(bot));
        if (goal != null) {
            var g = new JsonObject();
            g.addProperty("source", "OPERATOR_GIVEN_KNOWN_POSITION");
            g.add("position", vector(goal));
            g.add("relative", vector(goal.subtract(bot.position())));
            g.addProperty("arrival_radius", config.goalRadius());
            state.add("goal", g);
        }
        state.add("previous", previous.deepCopy());
        int radius = config.observationRadius();
        var cells = new JsonArray();
        var origin = bot.blockPosition();
        for (int dx = -radius; dx <= radius; dx++) {
            for (int dy = -1; dy <= 2; dy++) {
                for (int dz = -radius; dz <= radius; dz++) {
                    var pos = origin.offset(dx, dy, dz);
                    var cell = new JsonObject();
                    cell.add("position", vector(Vec3.atLowerCornerOf(pos)));
                    boolean loaded = world.hasChunkAt(pos);
                    boolean visible = false;
                    if (loaded) {
                        var hit = world.clip(new ClipContext(bot.getEyePosition(), Vec3.atCenterOf(pos),
                                ClipContext.Block.COLLIDER, ClipContext.Fluid.ANY, bot));
                        visible = hit.getType() == HitResult.Type.MISS || hit.getBlockPos().equals(pos);
                    }
                    cell.addProperty("knowledge", visible ? "OBSERVED" : "UNKNOWN");
                    cell.addProperty("unknown_reason", visible ? "" : loaded ? "occluded" : "unloaded");
                    if (visible) {
                        var block = world.getBlockState(pos);
                        cell.addProperty("block", BuiltInRegistries.BLOCK.getKey(block.getBlock()).toString());
                        cell.addProperty("fluid", !block.getFluidState().isEmpty());
                        var boxes = new JsonArray();
                        for (AABB box : block.getCollisionShape(world, pos).toAabbs()) {
                            var bounds = new JsonArray();
                            for (double number : new double[]{box.minX, box.minY, box.minZ, box.maxX, box.maxY, box.maxZ}) bounds.add(number);
                            boxes.add(bounds);
                        }
                        cell.add("local_collision_boxes", boxes);
                        cell.addProperty("observed_tick", tick);
                    }
                    cells.add(cell);
                }
            }
        }
        state.add("local_cells", cells);
        state.addProperty("cell_origin_note", "Collision boxes are relative to each integer block position; unlisted cells are UNKNOWN");
        var entities = new JsonArray();
        List<Entity> visible = world.getEntities(bot, bot.getBoundingBox().inflate(radius * 2.0),
                        entity -> entity.isAlive() && bot.hasLineOfSight(entity))
                .stream().sorted(Comparator.comparingDouble(bot::distanceToSqr)).toList();
        for (Entity entity : visible.stream().limit(16).toList()) {
            var e = new JsonObject();
            e.addProperty("id", entity.getUUID().toString());
            e.addProperty("type", BuiltInRegistries.ENTITY_TYPE.getKey(entity.getType()).toString());
            e.add("relative", vector(entity.position().subtract(bot.position())));
            e.addProperty("knowledge", "OBSERVED");
            e.addProperty("observed_tick", tick);
            entities.add(e);
        }
        state.add("visible_entities", entities);
        state.addProperty("visible_entities_truncated", visible.size() > 16);
        state.addProperty("visibility_rule", "Radius plus line of sight; no camera FOV restriction. Entity private inventory/health/intent excluded.");
        var candidates = new ArrayList<>(List.of(ControlAction.values()));
        var exclusions = new JsonObject();
        if (!bot.onGround()) {
            candidates.remove(ControlAction.JUMP_FORWARD);
            exclusions.addProperty("JUMP_FORWARD", "Requires grounded state");
        }
        var names = new JsonArray();
        candidates.forEach(a -> names.add(a.name()));
        state.add("legal_candidates", names);
        state.add("excluded_candidates", exclusions);
        return new Capture(state, List.copyOf(candidates));
    }

    static JsonObject self(ServerPlayer bot) {
        var s = new JsonObject();
        s.add("position", vector(bot.position()));
        s.add("velocity", vector(bot.getDeltaMovement()));
        s.addProperty("yaw", bot.getYRot());
        s.addProperty("pitch", bot.getXRot());
        s.addProperty("on_ground", bot.onGround());
        s.addProperty("health", bot.getHealth());
        s.addProperty("hunger", bot.getFoodData().getFoodLevel());
        s.addProperty("horizontal_collision", bot.horizontalCollision);
        return s;
    }

    static JsonArray vector(Vec3 v) {
        var result = new JsonArray();
        result.add(v.x); result.add(v.y); result.add(v.z);
        return result;
    }
}
