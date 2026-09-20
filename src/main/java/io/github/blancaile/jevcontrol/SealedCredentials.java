package io.github.blancaile.jevcontrol;

import com.google.gson.*;
import javax.crypto.Cipher;
import javax.crypto.spec.OAEPParameterSpec;
import javax.crypto.spec.PSource;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.nio.file.attribute.*;
import java.security.*;
import java.security.interfaces.RSAPrivateCrtKey;
import java.security.spec.*;
import java.util.*;

/** Encrypted admin handoff. Only the server OS owner can read the decryption key. */
final class SealedCredentials {
    static final String PREFIX = "sealed-rsa-oaep256:";
    static final OAEPParameterSpec OAEP = new OAEPParameterSpec("SHA-256", "MGF1", MGF1ParameterSpec.SHA256, PSource.PSpecified.DEFAULT);
    private static final Set<PosixFilePermission> PRIVATE_FILE = PosixFilePermissions.fromString("rw-------");
    private static final Set<PosixFilePermission> PRIVATE_DIR = PosixFilePermissions.fromString("rwx------");

    private static Path directory(Path config) { return config.toAbsolutePath().getParent(); }
    private static Path secretDirectory(Path config) { return directory(config).resolve("secrets"); }
    private static Path privateFile(Path config) { return secretDirectory(config).resolve("credential-private.pk8"); }

    static boolean supported(Path config) throws IOException {
        return Files.getFileStore(directory(config)).supportsFileAttributeView(PosixFileAttributeView.class);
    }
    private static void requireSupported(Path config) throws IOException {
        if (!supported(config)) throw new IOException("Sealed credentials require POSIX owner-only permissions; use a server environment variable on Windows");
        if (Files.isSymbolicLink(directory(config))) throw new IOException("Credential data directory must not be a symbolic link");
    }
    private static void check(Path path, Set<PosixFilePermission> permissions, UserPrincipal owner, boolean directory) throws IOException {
        var attrs = Files.readAttributes(path, PosixFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
        if (attrs.isSymbolicLink() || (directory ? !attrs.isDirectory() : !attrs.isRegularFile())
                || !attrs.permissions().equals(permissions) || !attrs.owner().equals(owner))
            throw new IOException("Credential storage ownership or permissions are unsafe");
    }
    private static RSAPrivateCrtKey readPrivate(Path config) throws IOException, GeneralSecurityException {
        requireSupported(config);
        var owner = Files.getOwner(directory(config), LinkOption.NOFOLLOW_LINKS);
        check(secretDirectory(config), PRIVATE_DIR, owner, true);
        check(privateFile(config), PRIVATE_FILE, owner, false);
        if (Files.size(privateFile(config)) > 8192) throw new IOException("Invalid credential private-key file");
        var key = (RSAPrivateCrtKey) KeyFactory.getInstance("RSA").generatePrivate(new PKCS8EncodedKeySpec(Files.readAllBytes(privateFile(config))));
        if (key.getModulus().bitLength() != 3072) throw new IOException("Unexpected credential RSA key size");
        return key;
    }
    static void prepare(Path config) throws IOException {
        requireSupported(config);
        // Do not let another OS user replace the published public key or secret directory.
        Files.setPosixFilePermissions(directory(config), PosixFilePermissions.fromString("rwxr-xr-x"));
        var owner = Files.getOwner(directory(config), LinkOption.NOFOLLOW_LINKS);
        if (!Files.exists(secretDirectory(config), LinkOption.NOFOLLOW_LINKS))
            Files.createDirectory(secretDirectory(config), PosixFilePermissions.asFileAttribute(PRIVATE_DIR));
        check(secretDirectory(config), PRIVATE_DIR, owner, true);
        try {
            if (!Files.exists(privateFile(config), LinkOption.NOFOLLOW_LINKS)) {
                var generator = KeyPairGenerator.getInstance("RSA"); generator.initialize(3072);
                byte[] encoded = generator.generateKeyPair().getPrivate().getEncoded();
                try (var stream = Files.newByteChannel(privateFile(config), Set.of(StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE),
                        PosixFilePermissions.asFileAttribute(PRIVATE_FILE))) {
                    var bytes = java.nio.ByteBuffer.wrap(encoded);
                    while (bytes.hasRemaining()) stream.write(bytes);
                } finally { Arrays.fill(encoded, (byte) 0); }
            }
            var key = readPrivate(config);
            var info = new JsonObject();
            info.addProperty("algorithm", "RSA-OAEP-SHA256-MGF1-SHA256");
            info.addProperty("bits", 3072);
            info.addProperty("modulus", unsignedBase64(key.getModulus()));
            info.addProperty("exponent", unsignedBase64(key.getPublicExponent()));
            atomicWrite(directory(config).resolve("credential-public.json"), info.toString(), PosixFilePermissions.fromString("rw-r--r--"));
        } catch (GeneralSecurityException | ClassCastException ex) { throw new IOException("Cannot prepare sealed credential storage"); }
    }
    private static String unsignedBase64(java.math.BigInteger number) {
        byte[] bytes = number.toByteArray();
        if (bytes[0] == 0) bytes = Arrays.copyOfRange(bytes, 1, bytes.length);
        return Base64.getEncoder().encodeToString(bytes);
    }
    static String decrypt(Path config, String ciphertext) throws IOException {
        byte[] plaintext = null;
        try {
            byte[] sealed = Base64.getDecoder().decode(ciphertext);
            if (sealed.length != 384) throw new GeneralSecurityException();
            var cipher = Cipher.getInstance("RSA/ECB/OAEPPadding");
            cipher.init(Cipher.DECRYPT_MODE, readPrivate(config), OAEP);
            plaintext = cipher.doFinal(sealed);
            if (plaintext.length < 1 || plaintext.length > 300) throw new GeneralSecurityException();
            for (byte value : plaintext) if (value < 33 || value > 126) throw new GeneralSecurityException();
            return new String(plaintext, StandardCharsets.US_ASCII);
        } catch (GeneralSecurityException | IllegalArgumentException | ClassCastException ex) {
            throw new IOException("Invalid sealed credential; use the current server public key");
        } finally { if (plaintext != null) Arrays.fill(plaintext, (byte) 0); }
    }
    static void install(Path config, String ciphertext) throws IOException {
        decrypt(config, ciphertext); // Validate before modifying anything; never persist cleartext.
        if (Files.isSymbolicLink(config)) throw new IOException("Config must not be a symbolic link");
        ControlConfig.read(config); // Do not repair malformed or missing configuration silently.
        var json = JsonParser.parseString(Files.readString(config, StandardCharsets.UTF_8)).getAsJsonObject();
        json.addProperty("apiKey", PREFIX + ciphertext);
        atomicWrite(config, new GsonBuilder().setPrettyPrinting().create().toJson(json) + "\n", PRIVATE_FILE);
        ControlConfig.read(config).requireKey();
    }
    private static void atomicWrite(Path target, String text, Set<PosixFilePermission> permissions) throws IOException {
        var stage = Files.createTempFile(target.getParent(), ".jev-credential-", ".tmp", PosixFilePermissions.asFileAttribute(permissions));
        try {
            Files.writeString(stage, text, StandardCharsets.UTF_8, StandardOpenOption.TRUNCATE_EXISTING);
            Files.move(stage, target, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
        } finally { Files.deleteIfExists(stage); }
    }
    static JsonObject status(Path config) throws IOException {
        var raw = JsonParser.parseString(Files.readString(config, StandardCharsets.UTF_8)).getAsJsonObject();
        String reference = raw.get("apiKey").getAsString();
        var resolved = ControlConfig.read(config);
        var result = new Gson().toJsonTree(resolved).getAsJsonObject();
        result.remove("apiKey");
        result.addProperty("configured", !resolved.apiKey().isBlank());
        result.addProperty("storage", reference.startsWith(PREFIX) ? "SEALED_RSA_OAEP256" : reference.startsWith("env:") ? "ENVIRONMENT" : reference.isBlank() ? "UNSET" : "LITERAL");
        result.addProperty("posix_supported", supported(config));
        if (reference.startsWith(PREFIX)) {
            var owner = Files.getOwner(directory(config), LinkOption.NOFOLLOW_LINKS);
            check(config, PRIVATE_FILE, owner, false);
            check(secretDirectory(config), PRIVATE_DIR, owner, true);
            check(privateFile(config), PRIVATE_FILE, owner, false);
            result.addProperty("config_mode", "600");
            result.addProperty("private_key_mode", "600");
            result.addProperty("private_directory_mode", "700");
        }
        return result;
    }
}
