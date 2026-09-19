# Bundled runtime dependencies

The distributable is a Fabric server mod for Minecraft 1.21.3. It includes the
following unmodified upstream mod JARs as nested dependencies, not copied source.

- **Fabric Carpet 1.4.158** (Modrinth version `ZF8ufR9V`). MIT, copyright (c) 2020 gnembon.
  - Source: https://github.com/gnembon/fabric-carpet/tree/1.4.158
  - Artifact: https://cdn.modrinth.com/data/TQTTVgYE/versions/ZF8ufR9V/fabric-carpet-1.21.2-1.4.158%2Bv241022.jar
  - SHA-1: `812c218cf224168dcb70bc529bd0bf3f282a939c`
  - The filename says 1.21.2; the published version also declares 1.21.3 compatibility.
  - Full MIT notice: `licenses/Carpet-MIT.txt` in this repository and the outer JAR.
  - Its upstream fake-player implementation includes internal behavior outside this
    mod's ownership (including an upstream tick NPE catch). Our controller reports
    observed failures; it does not claim to remove all behavior inside Carpet.
- **Fabric API 0.114.1+1.21.3**. Apache License 2.0, FabricMC contributors.
  - Source: https://github.com/FabricMC/fabric-api
  - Artifact: https://maven.fabricmc.net/net/fabricmc/fabric-api/fabric-api/0.114.1+1.21.3/fabric-api-0.114.1+1.21.3.jar
  - SHA-256: `357a4fe24c7a7248320d2099b8567b65fd2f4271a3faf9c7f369dd2c18ab4157`
  - Upstream notices/licenses are preserved in the included JAR and its nested modules.

Minecraft and Fabric Loader are server prerequisites and are not included.
No Jev API key, local `.env`, game world or Mojang game JAR is distributed.
