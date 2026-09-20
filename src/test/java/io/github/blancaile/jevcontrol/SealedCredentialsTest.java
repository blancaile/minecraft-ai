package io.github.blancaile.jevcontrol;

import com.google.gson.JsonParser;
import javax.crypto.Cipher;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.io.TempDir;
import java.math.BigInteger;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.nio.file.attribute.*;
import java.security.*;
import java.security.spec.RSAPublicKeySpec;
import java.util.Base64;
import static org.junit.jupiter.api.Assertions.*;

class SealedCredentialsTest {
    @TempDir Path root;
    private Path config() throws Exception {
        Assumptions.assumeTrue(Files.getFileStore(root).supportsFileAttributeView(PosixFileAttributeView.class));
        Path config = root.resolve("jev-control.json");
        ControlConfig.createIfAbsent(config);
        return config;
    }
    private String encrypt(Path config, String secret) throws Exception {
        var published = JsonParser.parseString(Files.readString(root.resolve("credential-public.json"))).getAsJsonObject();
        var decoder = Base64.getDecoder();
        var publicKey = KeyFactory.getInstance("RSA").generatePublic(new RSAPublicKeySpec(
                new BigInteger(1, decoder.decode(published.get("modulus").getAsString())),
                new BigInteger(1, decoder.decode(published.get("exponent").getAsString()))));
        var cipher = Cipher.getInstance("RSA/ECB/OAEPPadding");
        cipher.init(Cipher.ENCRYPT_MODE, publicKey, SealedCredentials.OAEP);
        return Base64.getEncoder().encodeToString(cipher.doFinal(secret.getBytes(StandardCharsets.UTF_8)));
    }
    @Test void encryptedInstallPersistsWithoutPlaintextAndSurvivesPreparationAgain() throws Exception {
        var config = config();
        SealedCredentials.prepare(config);
        String ciphertext = encrypt(config, "fixture-private-api-key");
        SealedCredentials.install(config, ciphertext);
        assertFalse(Files.readString(config).contains("fixture-private-api-key"));
        assertEquals("fixture-private-api-key", ControlConfig.read(config).apiKey());
        assertEquals(PosixFilePermissions.fromString("rw-------"), Files.getPosixFilePermissions(config));
        var info = SealedCredentials.status(config);
        assertEquals("SEALED_RSA_OAEP256", info.get("storage").getAsString());
        assertEquals("600", info.get("private_key_mode").getAsString());
        assertEquals("700", info.get("private_directory_mode").getAsString());
        assertFalse(info.toString().contains("fixture-private-api-key"));
        String originalPublic = Files.readString(root.resolve("credential-public.json"));
        SealedCredentials.prepare(config);
        assertEquals(originalPublic, Files.readString(root.resolve("credential-public.json")));
        assertEquals("fixture-private-api-key", ControlConfig.read(config).apiKey());
    }
    @Test void malformedCiphertextAndHeaderInjectionNeverReplaceConfig() throws Exception {
        var config = config(); SealedCredentials.prepare(config);
        String original = Files.readString(config);
        for (String bad : new String[]{"plaintext-api-key", "A".repeat(512), encrypt(config, "bad\nheader")}) {
            var error = assertThrows(java.io.IOException.class, () -> SealedCredentials.install(config, bad));
            assertFalse(error.getMessage().contains(bad));
            assertEquals(original, Files.readString(config));
        }
    }
    @Test void readablePrivateKeyAndSymlinkAreRejected() throws Exception {
        var config = config(); SealedCredentials.prepare(config);
        String ciphertext = encrypt(config, "fixture-private-api-key");
        Path privateKey = root.resolve("secrets/credential-private.pk8");
        Files.setPosixFilePermissions(privateKey, PosixFilePermissions.fromString("rw-r--r--"));
        assertThrows(java.io.IOException.class, () -> SealedCredentials.install(config, ciphertext));
        Files.setPosixFilePermissions(privateKey, PosixFilePermissions.fromString("rw-------"));
        Path moved = root.resolve("original-private.pk8"); Files.move(privateKey, moved);
        Files.createSymbolicLink(privateKey, moved);
        assertThrows(java.io.IOException.class, () -> SealedCredentials.install(config, ciphertext));
    }
    @Test void platformsWithoutPosixDoNotPretendCredentialsAreProtected() throws Exception {
        Assumptions.assumeFalse(Files.getFileStore(root).supportsFileAttributeView(PosixFileAttributeView.class));
        Path config = root.resolve("jev-control.json"); ControlConfig.createIfAbsent(config);
        assertThrows(java.io.IOException.class, () -> SealedCredentials.prepare(config));
        assertEquals("", ControlConfig.read(config).apiKey());
    }
}
