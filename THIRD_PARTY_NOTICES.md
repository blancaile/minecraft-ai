# JevControl Paper runtime dependencies

The 0.2.x distribution is a Paper plugin for Minecraft 1.21.11 / Java 21.
It contains this project's code and plugin metadata. It does not bundle Minecraft,
Paper, Fabric, Carpet, Citizens, or third-party sources.

Paper provides the server APIs, Minecraft runtime, Gson, Netty and Adventure.
The development bundle is compile-only, pinned to
`io.papermc.paper:dev-bundle:1.21.11-R0.1-20260215.191825-75`.
Paper source and license: https://github.com/PaperMC/Paper
Build tool: https://github.com/PaperMC/paperweight (2.0.0-beta.23).

Historical Fabric notices are available at commit `be2833f8`.
Files in `licenses/` document those historical dependencies and are not bundled
in the Paper JAR. No API key, local deployment configuration, world or game JAR
is distributed.
