package io.github.blancaile.jevcontrol;

import com.mojang.authlib.GameProfile;
import io.netty.channel.ChannelFutureListener;
import io.netty.channel.embedded.EmbeddedChannel;
import net.minecraft.core.BlockPos;
import net.minecraft.network.protocol.Packet;
import net.minecraft.network.protocol.PacketFlow;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.*;
import net.minecraft.server.network.CommonListenerCookie;
import net.minecraft.world.level.GameType;
import net.minecraft.world.phys.Vec3;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.UUID;

/** Version-pinned Paper body. No pathfinder, velocity assignment or movement teleport. */
final class FakePlayerBody extends ServerPlayer {
    static final String NAME = "JevBot";
    static final UUID ID = UUID.nameUUIDFromBytes("blancaile:jev-control:JevBot".getBytes(StandardCharsets.UTF_8));
    private final LocalConnection localConnection = new LocalConnection();
    private float forward;
    private float strafe;

    private FakePlayerBody(MinecraftServer server, ServerLevel world) {
        super(server, world, new GameProfile(ID, NAME), ClientInformation.createDefault());
    }

    static FakePlayerBody spawn(MinecraftServer server, ServerLevel world, Vec3 position, float yaw) {
        if (server.getPlayerList().getPlayerByName(NAME) != null || server.getPlayerList().getPlayer(ID) != null)
            throw new IllegalStateException("JevBot name or UUID is already in use");
        if (!world.hasChunkAt(BlockPos.containing(position))) throw new IllegalStateException("Spawn chunk is not loaded");
        if (!world.getWorldBorder().isWithinBounds(BlockPos.containing(position))) throw new IllegalStateException("Spawn outside world border");
        if (position.y < world.getMinY() || position.y >= world.getMaxY() - 2) throw new IllegalStateException("Spawn outside world height");
        var bot = new FakePlayerBody(server, world);
        try {
            bot.snapTo(position.x, position.y, position.z, yaw, 0);
            if (!world.noCollision(bot)) throw new IllegalStateException("Spawn position intersects solid blocks");
            bot.getBukkitEntity().setPersistent(false);
            // This repeatable synthetic body is not a first-time human login. Initialize only
            // CraftPlayer's in-memory bookkeeping, without reading/writing a real player's data.
            // Multiverse 5.6.1 otherwise asynchronously applies first-spawn-override after join.
            bot.getBukkitEntity().readExtraData(net.minecraft.world.level.storage.TagValueInput.createGlobal(
                    net.minecraft.util.ProblemReporter.DISCARDING, new net.minecraft.nbt.CompoundTag()));
            server.getPlayerList().placeNewPlayer(bot.localConnection, bot, CommonListenerCookie.createInitial(bot.getGameProfile(), false));
            if (server.getPlayerList().getPlayer(ID) != bot || bot.connection.isDisconnected())
                throw new IllegalStateException("Another plugin rejected the fake player join");
            if (bot.level() != world || bot.position().distanceTo(position) > 0.1)
                throw new IllegalStateException("Another plugin changed the requested spawn position");
            bot.setGameMode(GameType.SURVIVAL);
            bot.getAbilities().flying = false;
            bot.getAbilities().mayfly = false;
            bot.getAbilities().invulnerable = false;
            bot.onUpdateAbilities();
            bot.getInventory().clearContent();
            bot.setHealth(20);
            bot.getFoodData().setFoodLevel(20);
            stop(bot);
            return bot;
        } catch (RuntimeException ex) {
            if (server.getPlayerList().getPlayer(ID) == bot) server.getPlayerList().remove(bot);
            bot.localConnection.channel.close();
            throw ex;
        }
    }

    @Override public void tick() {
        super.tick();
        // No remote client exists to invoke the player/living-entity movement tick.
        xxa = strafe;
        zza = forward;
        super.doTick();
    }

    static void apply(FakePlayerBody bot, ControlAction action) {
        stop(bot);
        switch (action) {
            case WAIT -> { }
            case FORWARD -> bot.forward = 1;
            case BACK -> bot.forward = -1;
            case STRAFE_LEFT -> bot.strafe = 1;
            case STRAFE_RIGHT -> bot.strafe = -1;
            case TURN_LEFT -> bot.setYRot(bot.getYRot() - 15);
            case TURN_RIGHT -> bot.setYRot(bot.getYRot() + 15);
            case JUMP_FORWARD -> {
                if (!bot.onGround()) throw new IllegalStateException("Jump precondition no longer holds");
                bot.forward = 1;
                bot.jumpFromGround();
            }
        }
        bot.setYHeadRot(bot.getYRot());
    }

    static void stop(FakePlayerBody bot) {
        bot.forward = bot.strafe = bot.xxa = bot.zza = 0;
        bot.jumping = false;
    }

    static void despawn(FakePlayerBody bot) {
        stop(bot);
        bot.disconnect();
        if (bot.level().getServer().getPlayerList().getPlayer(bot.getUUID()) == bot)
            bot.level().getServer().getPlayerList().remove(bot);
        bot.localConnection.channel.close();
    }

    private static final class LocalConnection extends net.minecraft.network.Connection {
        LocalConnection() {
            super(PacketFlow.SERVERBOUND);
            channel = new EmbeddedChannel();
            address = new InetSocketAddress("127.0.0.1", 0);
        }
        @Override public void send(Packet<?> packet) { }
        @Override public void send(Packet<?> packet, ChannelFutureListener listener) { }
        @Override public void send(Packet<?> packet, ChannelFutureListener listener, boolean flush) { }
        @Override public boolean isConnected() { return channel.isOpen(); }
        @Override public boolean isMemoryConnection() { return true; }
    }
}
