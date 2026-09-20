# Persistent Jev credential — 2026-09-20

User explicitly approved persistent configuration, provided the key is not exposed as readable plaintext. Implemented in `d296d6ea9b08575b868999741f77eb5d4b88fd57`; deployed JAR SHA-256 `ccd880f347345c2e81415fd77e11162a7f17df34512b62f4ce4433c6b6222c54`.

## Storage and boundary

- Actual SFTP UID 1001 differs from Minecraft UID 1000; SFTP cannot chown to the server user. Thus uploading a SFTP-owned 600 file would not solve server access.
- `jev key-prepare` generates a server-owned RSA-3072 key. Private key: `plugins/JevControl/secrets/credential-private.pk8`, owner-only **600**, enclosing directory **700**. The published public key is 644; plugin data directory becomes 755 so other OS users cannot replace its immediate contents.
- The existing README loader reads the local `.env` key into memory. The provisioning script uses the server public key and **RSA-OAEP SHA256 / MGF1-SHA256**. Only ciphertext passes through the command inbox. The server validates/decrypts it and atomically writes the ciphertext reference to `jev-control.json`, also **600**. No cleartext credential is written into server config, inbox, commands, evidence or source.
- Direct SFTP attempts to open both config and private key produced `SftpPermissionDeniedException`; server `key-status` simultaneously verified successful decryption and 600/600/700 permissions.
- This is **not isolation from root, the Minecraft OS owner, or plugins running inside the same JVM**. Access to both encrypted config and the private-key backup permits decryption. Keep backups owner-protected; losing the private key requires provisioning a new keypair/credential.
- POSIX is required for this mode. Unsupported platforms fail rather than pretend protection exists; use a separately configured process environment there.

OAEP digest parameters are explicitly matched across [Java's MGF1 parameters](https://docs.oracle.com/javase/jp/21/docs/api/java.base/java/security/spec/MGF1ParameterSpec.html) and [.NET's SHA256 OAEP padding](https://learn.microsoft.com/en-us/dotnet/api/system.security.cryptography.rsaencryptionpadding). On Windows the script selects RSACng, not the legacy provider limited to SHA1 OAEP.

## Verification

- `tools/runtime/build.ps1 -Smoke`: unit checks, 7 offline transport checks, 3 evidence-verifier tests and 22 Paper body checks passed. POSIX-only unit cases run on Linux CI; Windows verifies rejection of unsupported protected storage.
- Provisioning receipt group: `.runtime-harness/remote-credential-b516bc9a-8626-419e-a8a9-31db9ccf4973/`.
- `live-near-player.ps1 -UseConfiguredKey -Player Philia_Gray -Execute`: **real Jev, 3 completed cycles, GOAL_REACHED**, without reading/modifying/restoring config. Audit: `.runtime-harness/remote-live-10b830f1-d702-4295-b297-8b8553b69011/audit-87d5fef6.json`; trace `2cb8a5c3-8a57-4706-9eef-3bc7c4c5cf4c.jsonl`. Latencies 789/388/509 ms. Bot removed; credential retained.
- Separate reload persistence check: `.runtime-harness/remote-1d753d9c-98bc-4eab-91f0-eb4c9bb991b8/`, followed by `.runtime-harness/remote-persistent-key-after-reload/Command.json`: `configured=true`, `storage=SEALED_RSA_OAEP256`, config/private-key=600, secrets-directory=700, model `jev-1.13.0`. Bot remains absent; no automatic run started.
- [CI run for the implementation](https://github.com/blancaile/minecraft-ai/actions/runs/35481942689): **SUCCESS**, including Linux POSIX credential tests and isolated runtime faults.

## User check (OP / jev.admin)

Stand on flat ground, keep position while entering the commands, and leave five clear blocks toward +Z (south):

```text
/jev key-status
/jev spawn
/jev goal ~ ~ ~5
/jev start
/jev status
```

The goal uses the command sender's feet coordinates, not the bot's position or viewing direction. A flying player's elevated target can remain unreachable. Stop with `/jev stop`; remove with `/jev despawn`. Neither deletes the persistent credential.
