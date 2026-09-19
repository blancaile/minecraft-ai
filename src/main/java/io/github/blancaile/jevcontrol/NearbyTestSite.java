package io.github.blancaile.jevcontrol;

import com.google.gson.Gson;
import org.bukkit.Location;
import org.bukkit.Material;
import org.bukkit.entity.Player;
import org.bukkit.util.BoundingBox;
import java.util.Map;
import java.util.Set;

/** Operator-only fixture placement. Never part of observation, candidate generation or movement policy. */
final class NearbyTestSite {
    private static final Set<Material> FLOOR = Set.of(Material.STONE, Material.SMOOTH_STONE,
            Material.COBBLESTONE, Material.STONE_BRICKS, Material.DIRT, Material.GRASS_BLOCK,
            Material.DEEPSLATE, Material.COBBLED_DEEPSLATE, Material.SANDSTONE, Material.END_STONE,
            Material.POLISHED_ANDESITE, Material.ANDESITE, Material.GRANITE, Material.DIORITE);

    static Location find(Player player) {
        if (!player.isOnline() || player.isDead()) throw new IllegalStateException("Reference player must be online and alive");
        var origin = player.getLocation();
        var world = origin.getWorld();
        for (int radius = 3; radius <= 10; radius++) {
            for (int dx = -radius; dx <= radius; dx++) for (int dz = -radius; dz <= radius; dz++) {
                if (Math.max(Math.abs(dx), Math.abs(dz)) != radius) continue;
                for (int dy : new int[]{0, -1, 1, -2, 2, -3, 3}) {
                    int x = origin.getBlockX() + dx, y = origin.getBlockY() + dy, z = origin.getBlockZ() + dz;
                    if (y <= world.getMinHeight() || y + 3 >= world.getMaxHeight()) continue;
                    boolean clear = true;
                    for (int sx = x - 1; sx <= x + 1 && clear; sx++) for (int sz = z - 1; sz <= z + 5 && clear; sz++) {
                        if (!world.isChunkLoaded(sx >> 4, sz >> 4)
                                || !world.getWorldBorder().isInside(new Location(world, sx + .5, y, sz + .5))) { clear = false; break; }
                        if (!FLOOR.contains(world.getBlockAt(sx, y - 1, sz).getType())) { clear = false; break; }
                        for (int sy = y; sy <= y + 2; sy++) if (!world.getBlockAt(sx, sy, sz).getType().isAir()) { clear = false; break; }
                    }
                    if (!clear) continue;
                    // Keep every entity, including the reference player, outside the complete test lane and a margin.
                    if (!world.getNearbyEntities(new BoundingBox(x - 2, y - 1, z - 2, x + 3, y + 4, z + 7)).isEmpty()) continue;
                    return new Location(world, x + .5, y, z + .5, 0, 0);
                }
            }
        }
        throw new IllegalStateException("No clear loaded 3x7 test lane within 10 blocks horizontally / 3 vertically; no terrain changed");
    }

    static String describe(Player player, Location site) {
        var origin = player.getLocation();
        return new Gson().toJson(Map.of("purpose", "OPERATOR_FIXTURE_ONLY", "player", player.getName(),
                "world", site.getWorld().getName(), "player_position", new double[]{origin.getX(), origin.getY(), origin.getZ()},
                "spawn_position", new double[]{site.getX(), site.getY(), site.getZ()}, "yaw", 0,
                "checked_at_ms", System.currentTimeMillis(), "terrain_changed", false));
    }
}
