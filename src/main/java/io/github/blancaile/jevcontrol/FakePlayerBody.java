package io.github.blancaile.jevcontrol;

import carpet.fakes.ServerPlayerInterface;
import carpet.helpers.EntityPlayerActionPack;
import carpet.patches.EntityPlayerMPFake;
import carpet.patches.FakeClientConnection;
import com.mojang.authlib.GameProfile;
import net.minecraft.core.BlockPos;
import net.minecraft.network.chat.Component;
import net.minecraft.network.protocol.PacketFlow;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.*;
import net.minecraft.server.network.CommonListenerCookie;
import net.minecraft.world.level.GameType;
import net.minecraft.world.phys.Vec3;
import java.nio.charset.StandardCharsets;
import java.util.*;

final class FakePlayerBody {
    static final String NAME = "JevBot";
    static final UUID ID = UUID.nameUUIDFromBytes("blancaile:jev-control:JevBot".getBytes(StandardCharsets.UTF_8));

    static EntityPlayerMPFake spawn(MinecraftServer server, ServerLevel world, Vec3 position, float yaw) {
        if (server.getPlayerList().getPlayerByName(NAME) != null || server.getPlayerList().getPlayer(ID) != null)
            throw new IllegalStateException("JevBot name or UUID is already in use");
        if (!world.hasChunkAt(BlockPos.containing(position))) throw new IllegalStateException("Spawn chunk is not loaded");
        if (!world.getWorldBorder().isWithinBounds(BlockPos.containing(position))) throw new IllegalStateException("Spawn outside world border");
        if (position.y < world.getMinY() || position.y >= world.getMaxY() - 2) throw new IllegalStateException("Spawn outside world height");
        var profile = new GameProfile(ID, NAME);
        // This factory uses the supplied profile directly: no remote skin/auth lookup or offline-profile fallback.
        var bot = EntityPlayerMPFake.respawnFake(server, world, profile, ClientInformation.createDefault());
        bot.fixStartingPosition = () -> bot.moveTo(position.x, position.y, position.z, yaw, 0);
        bot.moveTo(position.x, position.y, position.z, yaw, 0);
        if (!world.noCollision(bot)) throw new IllegalStateException("Spawn position intersects solid blocks");
        server.getPlayerList().placeNewPlayer(new FakeClientConnection(PacketFlow.SERVERBOUND), bot,
                new CommonListenerCookie(profile, 0, bot.clientInformation(), false));
        bot.teleportTo(world, position.x, position.y, position.z, Set.of(), yaw, 0, true);
        bot.gameMode.changeGameModeForPlayer(GameType.SURVIVAL);
        bot.getAbilities().flying = false;
        bot.getAbilities().mayfly = false;
        bot.getAbilities().invulnerable = false;
        bot.onUpdateAbilities();
        bot.setHealth(20);
        bot.getFoodData().setFoodLevel(20);
        bot.getInventory().clearContent();
        stop(bot);
        return bot;
    }

    static void apply(EntityPlayerMPFake bot, ControlAction action) {
        stop(bot);
        var pack = ((ServerPlayerInterface) bot).getActionPack();
        switch (action) {
            case WAIT -> { }
            case FORWARD -> pack.setForward(1);
            case BACK -> pack.setForward(-1);
            case STRAFE_LEFT -> pack.setStrafing(1);
            case STRAFE_RIGHT -> pack.setStrafing(-1);
            case TURN_LEFT -> pack.turn(-15, 0);
            case TURN_RIGHT -> pack.turn(15, 0);
            case JUMP_FORWARD -> {
                if (!bot.onGround()) throw new IllegalStateException("Jump precondition no longer holds");
                pack.setForward(1);
                pack.start(EntityPlayerActionPack.ActionType.JUMP, EntityPlayerActionPack.Action.once());
            }
        }
    }
    static void stop(EntityPlayerMPFake bot) {
        ((ServerPlayerInterface) bot).getActionPack().stopAll();
    }
    static void despawn(EntityPlayerMPFake bot) { stop(bot); bot.kill(Component.literal("Jev control despawn")); }
}
