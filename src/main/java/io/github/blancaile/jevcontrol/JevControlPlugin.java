package io.github.blancaile.jevcontrol;

import org.bukkit.Bukkit;
import org.bukkit.Location;
import org.bukkit.command.*;
import org.bukkit.craftbukkit.CraftServer;
import org.bukkit.craftbukkit.CraftWorld;
import org.bukkit.entity.Player;
import org.bukkit.plugin.java.JavaPlugin;
import net.minecraft.world.phys.Vec3;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;

/** Paper owns lifecycle, command permissions and the main-thread tick scheduler. */
public final class JevControlPlugin extends JavaPlugin implements CommandExecutor, TabCompleter {
    private ControlRuntime runtime;
    private String artifactHash;
    private CommandInbox inbox;

    @Override public void onEnable() {
        if (!Bukkit.getMinecraftVersion().equals("1.21.11")) {
            throw new IllegalStateException("JevControl supports Paper 1.21.11 only");
        }
        try {
            var config = getDataFolder().toPath().resolve("jev-control.json");
            ControlConfig.createIfAbsent(config);
            artifactHash = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(getFile().toPath())));
            runtime = new ControlRuntime(((CraftServer) getServer()).getServer(), config,
                    getDataFolder().toPath().resolve("traces"), getDescription().getVersion(), artifactHash, getLogger());
            Objects.requireNonNull(getCommand("jev")).setExecutor(this);
            getCommand("jev").setTabCompleter(this);
            getServer().getScheduler().runTaskTimer(this, () -> runtime.tick(), 1L, 1L);
            inbox = new CommandInbox(this);
            getLogger().info("JEV_READY version=" + getDescription().getVersion() + " sha256=" + artifactHash
                    + " minecraft=" + Bukkit.getMinecraftVersion() + " body=PAPER_SERVER_PLAYER");
        } catch (Exception ex) {
            if (runtime != null) { runtime.shutdown(); runtime = null; }
            throw new IllegalStateException("Cannot initialize JevControl (check configuration and server version)", ex);
        }
    }

    @Override public void onDisable() {
        if (inbox != null) { inbox.close(); inbox = null; }
        getServer().getScheduler().cancelTasks(this);
        if (runtime != null) { runtime.shutdown(); runtime = null; }
        getLogger().info("JEV_DISABLED inputs released, bot removed, decisions cancelled");
    }

    @Override public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        if (!sender.hasPermission("jev.admin")) { sender.sendMessage("JEV_ERROR Permission denied"); return true; }
        if (runtime == null) { sender.sendMessage("JEV_ERROR Runtime not ready"); return true; }
        try {
            var verb = args.length == 0 ? "help" : args[0].toLowerCase(Locale.ROOT);
            var location = sender instanceof Player player ? player.getLocation() : Bukkit.getWorlds().getFirst().getSpawnLocation();
            String message = switch (verb) {
                case "site", "spawn-near" -> {
                    if (args.length != 2) throw new IllegalArgumentException("Usage: jev " + verb + " PLAYER");
                    var reference = Bukkit.getPlayerExact(args[1]);
                    if (reference == null) throw new IllegalStateException("Reference player is not online");
                    var target = NearbyTestSite.find(reference);
                    if (verb.equals("spawn-near")) {
                        runtime.spawn(((CraftWorld) target.getWorld()).getHandle(), new Vec3(target.getX(), target.getY(), target.getZ()), 0);
                        yield "Spawned JevBot " + NearbyTestSite.describe(reference, target);
                    }
                    yield NearbyTestSite.describe(reference, target);
                }
                case "spawn" -> {
                    if (!(sender instanceof Player) && args.length == 1)
                        throw new IllegalArgumentException("Console spawn requires x y z [world]");
                    var target = coordinates(args, location);
                    runtime.spawn(((CraftWorld) target.getWorld()).getHandle(), new Vec3(target.getX(), target.getY(), target.getZ()), target.getYaw());
                    yield "Spawned JevBot in survival mode";
                }
                case "goal" -> {
                    if (args.length < 4) throw new IllegalArgumentException("Usage: jev goal x y z [world]");
                    var target = coordinates(args, location);
                    runtime.goal(((CraftWorld) target.getWorld()).getHandle(), new Vec3(target.getX(), target.getY(), target.getZ()));
                    yield "Goal set";
                }
                case "start" -> { runtime.start(); yield "Jev run started"; }
                case "stop" -> { runtime.stop(); yield runtime.status(); }
                case "status" -> "sha256=" + artifactHash + " " + runtime.status();
                case "observe" -> "Observation written: " + runtime.observe();
                case "smoke" -> { runtime.manual(ControlAction.FORWARD, true); yield "Smoke started: NO MODEL, forward 8 ticks then verify release"; }
                case "step" -> {
                    if (args.length != 2) throw new IllegalArgumentException("Usage: jev step ACTION");
                    runtime.manual(ControlAction.valueOf(args[1].toUpperCase(Locale.ROOT)), false);
                    yield "Manual finite input started: NO MODEL";
                }
                case "despawn" -> { runtime.despawn(); yield "Despawn requested"; }
                default -> "Jev: site PLAYER, spawn-near PLAYER, spawn [x y z [world]], goal x y z [world], start, stop, status, observe, step ACTION, smoke, despawn";
            };
            sender.sendMessage("JEV_OK " + message);
        } catch (Exception ex) {
            var message = ex instanceof IllegalStateException || ex instanceof IllegalArgumentException || ex instanceof java.io.IOException
                    ? ex.getMessage() : "Command failed: " + ex.getClass().getSimpleName();
            sender.sendMessage("JEV_ERROR " + message);
        }
        return true;
    }

    private Location coordinates(String[] args, Location origin) {
        if (args.length == 1) return origin.clone();
        if (args.length != 4 && args.length != 5) throw new IllegalArgumentException("Expected x y z [world]");
        var world = args.length == 5 ? Bukkit.getWorld(args[4]) : origin.getWorld();
        if (world == null) throw new IllegalArgumentException("World is not loaded");
        if (world != origin.getWorld() && Arrays.stream(args).anyMatch(s -> s.startsWith("~")))
            throw new IllegalArgumentException("Cross-world coordinates must be absolute");
        return new Location(world, Coordinate.parse(args[1], origin.getX()), Coordinate.parse(args[2], origin.getY()),
                Coordinate.parse(args[3], origin.getZ()), origin.getYaw(), 0);
    }

    @Override public List<String> onTabComplete(CommandSender sender, Command command, String alias, String[] args) {
        if (!sender.hasPermission("jev.admin")) return List.of();
        var choices = args.length == 1 ? List.of("site", "spawn-near", "spawn", "goal", "start", "stop", "status", "observe", "step", "smoke", "despawn")
                : args.length == 2 && args[0].equalsIgnoreCase("step") ? Arrays.stream(ControlAction.values()).map(Enum::name).toList() : List.<String>of();
        return choices.stream().filter(s -> s.toLowerCase(Locale.ROOT).startsWith(args[args.length - 1].toLowerCase(Locale.ROOT))).toList();
    }
}
