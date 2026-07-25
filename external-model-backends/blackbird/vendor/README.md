# vendor/ — provide the JNISpice jar here

`jplTime` has a **compile-time** dependency on JNISpice, which is **not** on Maven Central and
is **not** redistributable through this repository. You must obtain it yourself and drop it here
before building the Blackbird image.

```bash
# From the NAIF/JPL SPICE toolkit. v2022-05 matches the jplTime 2025-10a tag the Dockerfile builds.
cp /path/to/JNISpice-v2022-05.jar \
   external-model-backends/blackbird/vendor/JNISpice-v2022-05.jar
```

The Dockerfile installs whatever jar you provide into the build stage's local Maven repo under
the coordinate `gov.nasa.jpl.spice:jnispice:v2022-05` — the coordinate **jplTime's pom requires**.

To use a **differently-named jar**, override only the filename:

```bash
docker build \
  --build-arg JNISPICE_JAR=JNISpice-N0067.jar \
  -t plandev/blackbird-adapter external-model-backends/blackbird
```

> ⚠️ Do **not** also set `--build-arg JNISPICE_VERSION=N0067`. That arg is the Maven *coordinate*
> jplTime depends on, not a label for your jar. Changing it installs the jar under a coordinate
> nothing asks for and the build fails with:
> `Could not find artifact gov.nasa.jpl.spice:jnispice:jar:N0067 in central`.

> This repo already ships a `third-party/JNISpice-N0067.jar` (used by the Java mission-model
> examples). It is a **different** SPICE toolkit release than the `v2022-05` that jplTime `2025-10a`
> pins, but it resolves and builds fine when installed under the expected coordinate as above.
> SPICE natives are only needed at *runtime* if your model actually calls the `Spice` class
> (the demo `powermodel` does not).

Jars in this directory are git-ignored (both by this folder's `.gitignore` and the repo-root
`*.jar` rule) and must never be committed.
