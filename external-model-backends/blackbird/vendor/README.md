# vendor/ — provide the JNISpice jar here

`jplTime` has a **compile-time** dependency on JNISpice, which is **not** on Maven Central and
is **not** redistributable through this repository. You must obtain it yourself and drop it here
before building the Blackbird image.

```bash
# From the NAIF/JPL SPICE toolkit. v2022-05 matches the jplTime 2025-10a tag the Dockerfile builds.
cp /path/to/JNISpice-v2022-05.jar \
   external-model-backends/blackbird/vendor/JNISpice-v2022-05.jar
```

The Dockerfile installs it into the build stage's local Maven repo as
`gov.nasa.jpl.spice:jnispice:v2022-05`. To use a different jar/version, pass build args:

```bash
docker build \
  --build-arg JNISPICE_JAR=JNISpice-N0067.jar \
  --build-arg JNISPICE_VERSION=N0067 \
  -t plandev/blackbird-adapter external-model-backends/blackbird
```

> This repo already ships a `third-party/JNISpice-N0067.jar` (used by the Java mission-model
> examples). It is a **different** SPICE toolkit version than the `v2022-05` the Blackbird build
> pins to jplTime `2025-10a`; try it via the build args above only if you don't have `v2022-05`.

Jars in this directory are git-ignored (both by this folder's `.gitignore` and the repo-root
`*.jar` rule) and must never be committed.
