package io.github.blancaile.jevcontrol;

import com.mojang.brigadier.arguments.StringArgumentType;
import net.fabricmc.api.ModInitializer;
import net.fabricmc.fabric.api.command.v2.CommandRegistrationCallback;
import net.fabricmc.fabric.api.event.lifecycle.v1.*;
import net.fabricmc.loader.api.FabricLoader;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.commands.Commands;
import net.minecraft.commands.arguments.coordinates.Vec3Argument;
import net.minecraft.network.chat.Component;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import java.io.IOException;
import java.util.Locale;

public final class JevControlMod implements ModInitializer {
    static final Logger LOGGER = LoggerFactory.getLogger("jev-control");
    private ControlRuntime runtime;
    @FunctionalInterface private interface Operation { String run() throws Exception; }

    @Override public void onInitialize() {
        try { ControlConfig.createIfAbsent(FabricLoader.getInstance().getConfigDir().resolve("jev-control.json")); }
        catch (IOException ex) { throw new IllegalStateException("Cannot create Jev configuration", ex); }
        ServerLifecycleEvents.SERVER_STARTED.register(server -> runtime = new ControlRuntime(server));
        ServerTickEvents.END_SERVER_TICK.register(server -> { if (runtime != null) runtime.tick(); });
        ServerLifecycleEvents.SERVER_STOPPING.register(server -> { if (runtime != null) { runtime.shutdown(); runtime = null; } });
        CommandRegistrationCallback.EVENT.register((dispatcher, registry, environment) -> dispatcher.register(
                Commands.literal("jev").requires(source -> source.hasPermission(2))
                .executes(ctx -> execute(ctx.getSource(), () -> "Jev: spawn [x y z], goal x y z, start, stop, status, observe, step ACTION, smoke, despawn"))
                .then(Commands.literal("spawn")
                    .executes(ctx -> execute(ctx.getSource(), () -> {
                        runtime.spawn(ctx.getSource().getLevel(), ctx.getSource().getPosition(), ctx.getSource().getRotation().y);
                        return "Spawned JevBot in survival mode";
                    }))
                    .then(Commands.argument("position", Vec3Argument.vec3()).executes(ctx -> execute(ctx.getSource(), () -> {
                        runtime.spawn(ctx.getSource().getLevel(), Vec3Argument.getVec3(ctx, "position"), ctx.getSource().getRotation().y);
                        return "Spawned JevBot in survival mode";
                    }))))
                .then(Commands.literal("goal").then(Commands.argument("position", Vec3Argument.vec3()).executes(ctx -> execute(ctx.getSource(), () -> {
                    runtime.goal(Vec3Argument.getVec3(ctx, "position")); return "Goal set";
                }))))
                .then(Commands.literal("start").executes(ctx -> execute(ctx.getSource(), () -> { runtime.start(); return "Jev run started"; })))
                .then(Commands.literal("stop").executes(ctx -> execute(ctx.getSource(), () -> { runtime.stop(); return runtime.status(); })))
                .then(Commands.literal("status").executes(ctx -> execute(ctx.getSource(), () -> runtime.status())))
                .then(Commands.literal("observe").executes(ctx -> execute(ctx.getSource(), () -> "Observation written: " + runtime.observe())))
                .then(Commands.literal("smoke").executes(ctx -> execute(ctx.getSource(), () -> {
                    runtime.manual(ControlAction.FORWARD, true); return "Smoke started: NO MODEL, forward 8 ticks then verify release";
                })))
                .then(Commands.literal("step").then(Commands.argument("action", StringArgumentType.word())
                    .suggests((ctx, builder) -> { for (var a : ControlAction.values()) builder.suggest(a.name()); return builder.buildFuture(); })
                    .executes(ctx -> execute(ctx.getSource(), () -> {
                        var action = ControlAction.valueOf(StringArgumentType.getString(ctx, "action").toUpperCase(Locale.ROOT));
                        runtime.manual(action, false); return "Manual finite input started: NO MODEL";
                    }))))
                .then(Commands.literal("despawn").executes(ctx -> execute(ctx.getSource(), () -> { runtime.despawn(); return "Despawn requested"; })))
        ));
    }

    private int execute(CommandSourceStack source, Operation operation) {
        if (runtime == null) { source.sendFailure(Component.literal("Jev runtime is not ready")); return 0; }
        try { String message = operation.run(); source.sendSuccess(() -> Component.literal(message), false); return 1; }
        catch (Exception ex) {
            String message = ex instanceof IllegalStateException || ex instanceof IOException
                    ? ex.getMessage() : "Command failed: " + ex.getClass().getSimpleName();
            source.sendFailure(Component.literal(message));
            return 0;
        }
    }
}
