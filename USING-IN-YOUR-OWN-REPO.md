# Using an example in your own repo

The examples here depend on the shared building blocks in `libraries/` via Gradle
(`implementation project(':libraries:power')`), so copying a single example directory on its
own won't compile. This guide shows how to lift an example **plus the `libraries/*` it uses**
into a fresh repo and stand up a build that produces a PlanDev-uploadable mission model JAR.

> The building blocks are **not published** to Maven.
> You copy the source and link it as a Gradle subproject (what this repo does), exactly as
> below.

## 1. Pick an example and find its building blocks

Check the example's `build.gradle` `dependencies {}` block (and the "Building Blocks Used"
column in the top [README](README.md)). For instance,
[examples/04-hopper/build.gradle](examples/04-hopper/build.gradle) declares:

```gradle
dependencies {
  implementation project(':libraries:power')
  implementation project(':libraries:data')
}
```

So you need `examples/04-hopper/` + `libraries/power/` + `libraries/data/`. (The orbiter
additionally needs `libraries/geometry/`, which has extra requirements — see step 6.)

## 2. Lay out the new repo

Mirror the multi-project layout (keep the example and the blocks as separate subprojects —
this is the composition pattern the examples teach):

```
my-mission/
├── settings.gradle
├── build.gradle
├── gradlew                           # copied from plandev-examples/gradlew (keep it executable)
├── gradle/
│   └── wrapper/                      # copied from plandev-examples/gradle/wrapper/
│       ├── gradle-wrapper.jar        #   (committed — see .gitignore's ! exception)
│       └── gradle-wrapper.properties
├── libraries/
│   ├── power/                        # copied from plandev-examples/libraries/power/
│   └── data/                         # copied from plandev-examples/libraries/data/
└── mission/                          # your model — start from the copied example
    ├── build.gradle
    └── src/main/java/...
```

Copy `gradlew` and `gradle/wrapper/` from this repo so you get the same Gradle version
without a local install. Note `gradle/wrapper/gradle-wrapper.jar` must be committed — this
repo's `.gitignore` ignores `*.jar` and then re-allows it with an explicit `!` exception.

## 3. `settings.gradle`

```gradle
rootProject.name = 'my-mission'
include 'libraries:power'
include 'libraries:data'
include 'mission'
```

## 4. Root `build.gradle`

This carries the shared PlanDev dependencies for every Java subproject (PlanDev **4.4.0** here —
match whatever PlanDev version your instance runs):

```gradle
ext.plandevVersion = '4.4.0'

allprojects {
  repositories {
    mavenCentral()
    maven {
      name = "GitHubPackages"
      url  = "https://maven.pkg.github.com/nasa-ammos/plandev"
      credentials {
        username = System.getenv('GITHUB_USER')
        password = System.getenv('GITHUB_TOKEN')   // needs read:packages scope
      }
    }
  }
}

subprojects {
  if (it.name == 'libraries') return   // the 'libraries' grouping dir isn't a Java project

  apply plugin: 'java'
  java { toolchain { languageVersion = JavaLanguageVersion.of(21) } }

  dependencies {
    annotationProcessor "gov.nasa.ammos.plandev:merlin-framework-processor:${plandevVersion}"
    implementation      "gov.nasa.ammos.plandev:contrib:${plandevVersion}"
    implementation      "gov.nasa.ammos.plandev:merlin-framework:${plandevVersion}"
    implementation      "gov.nasa.ammos.plandev:merlin-sdk:${plandevVersion}"
    compileOnly         "gov.nasa.ammos.plandev:merlin-driver:${plandevVersion}"

    testImplementation  "gov.nasa.ammos.plandev:merlin-framework-junit:${plandevVersion}"
    testImplementation  'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly     'org.junit.platform:junit-platform-launcher'
  }
  test { useJUnitPlatform() }
}
```

## 5. The mission `build.gradle`

```gradle
dependencies {
  implementation project(':libraries:power')
  implementation project(':libraries:data')
}

// IMPORTANT: include the building-block *sources* so PlanDev's annotation processor can
// generate value mappers for the @AutoValueMapper.Record types defined in the libraries.
// (This is the same pattern the examples use — it's required, not a workaround.)
sourceSets {
  main {
    java {
      srcDir project(':libraries:power').file('src/main/java')
      srcDir project(':libraries:data').file('src/main/java')
    }
  }
}

// Fat JAR for uploading to PlanDev
jar {
  dependsOn configurations.runtimeClasspath
  from {
    configurations.runtimeClasspath.filter { it.exists() }.collect { it.isDirectory() ? it : zipTree(it) }
  }
  duplicatesStrategy = DuplicatesStrategy.EXCLUDE
  archiveFileName.set("my-mission.jar")
}
```

Then copy the example's `src/main/java/...` as your starting point and rename the package to
your own.

## 6. Geometry & SPICE (only if your example uses `libraries/geometry`)

The geometry block (and the orbiter) add requirements in two separate places. Keep them
straight — they fail differently, and satisfying one does nothing for the other.

### 6a. Build time — vendored JARs on the compile classpath

Two JARs are vendored in this repo under `third-party/` and resolved through a `flatDir`
repository. Copy **both** into your repo's `third-party/` and add the `flatDir` line to the
root `repositories {}` block from step 4:

```gradle
flatDir { dirs "$rootDir/third-party" }
```

| Copy this file | Provides | Declared by |
|---|---|---|
| `third-party/JNISpice-N0067.jar` | the `spice.basic.*` Java API (`CSPICE`, `SpiceErrorException`, …) | [libraries/geometry/build.gradle](libraries/geometry/build.gradle) as `api ':JNISpice-N0067'` |
| `third-party/jplTime-2022-08.jar` | `gov.nasa.jpl.time.Time` / `Duration` | [libraries/geometry/build.gradle](libraries/geometry/build.gradle) as `api ':jplTime-2022-08'` |

Because `libraries/geometry` declares both as `api`, a subproject that depends on
`project(':libraries:geometry')` inherits them. Any subproject that names those classes
*directly* must still declare them itself — see
[examples/05-orbiter/build.gradle](examples/05-orbiter/build.gradle) and
[examples/05-orbiter/scheduling/build.gradle](examples/05-orbiter/scheduling/build.gradle),
which both repeat `implementation name: 'JNISpice-N0067'`.

`third-party/JNISpice-N0067.jar` contains **only `.class` files — no native code**. It is a
compile-time artifact. Getting this wrong shows up as a compile error
(`package spice.basic does not exist`).

### 6b. Run time — the native library, which you do *not* vendor

The actual CSPICE native library ships inside the PlanDev `contrib` artifact you already
depend on in step 4, alongside the loader that unpacks it:

```
gov/nasa/ammos/plandev/spice/SpiceLoader.class
gov/nasa/ammos/plandev/spice/libJNISpice_M1.so      # Linux arm64
gov/nasa/ammos/plandev/spice/libJNISpice_Intel.so   # Linux x86_64
gov/nasa/ammos/plandev/spice/libJNISpice.jnilib     # macOS
```

[libraries/geometry/.../SpiceUtils.java](libraries/geometry/src/main/java/gov/nasa/ammos/plandev/geometry/spice/SpiceUtils.java)
calls `SpiceLoader.loadSpice()`, which extracts and loads the right one for the platform. So
there is **nothing to install, vendor, or put on `java.library.path`** — do not try to build
CSPICE yourself. This is also why `contrib` is a plain `implementation` dependency rather than
`compileOnly`: the fat JAR from step 5 must carry those native libraries into the worker.

### 6c. Run time — SPICE kernels, mounted into the workers

Kernels are data, not code, and they are **not** in the JAR. Copy the `spice-kernels/`
directory, track it with Git LFS, and point the workers at it with `SPICE_DIRECTORY`:

- The kernel set and the Git LFS requirement:
  [spice-kernels/README.md](spice-kernels/README.md) (~238 MB — a non-LFS clone leaves you
  with pointer files, and simulation fails at kernel load).
- The lookup convention (`SPICE_DIRECTORY`, falling back to `spice-kernels` relative to the
  JVM working directory):
  [libraries/geometry/.../SpiceConstants.java](libraries/geometry/src/main/java/gov/nasa/ammos/plandev/geometry/spice/SpiceConstants.java)
  and [examples/05-orbiter/.../Mission.java](examples/05-orbiter/src/main/java/examples/orbiter/Mission.java).
- The Docker Compose bind mount — every `plandev_merlin_worker_*` **and**
  `plandev_scheduler_worker_*` replica needs the volume, using an absolute host path:
  [examples/05-orbiter/README.md](examples/05-orbiter/README.md).

If you run the geometry tests in your own repo, mirror the `test { environment(...) }` block
in [libraries/geometry/build.gradle](libraries/geometry/build.gradle) — tests run with the
subproject as the working directory, so the relative fallback does not resolve.

## 7. Credentials

The PlanDev packages live in GitHub Packages, so you need a token with `read:packages`:

```bash
export GITHUB_USER=your-username
export GITHUB_TOKEN=ghp_your-token
```

## 8. Build and upload

```bash
./gradlew :mission:build      # produces mission/build/libs/my-mission.jar
```

(For reference, the equivalent artifacts in this repo are
`examples/04-hopper/build/libs/hopper.jar` and
`examples/05-orbiter/build/libs/orbiter-example.jar`.)

Upload that JAR to your PlanDev instance as a mission model. Done — you now have a standalone
repo that still tracks the building blocks you copied (re-copy from `plandev-examples` to pick
up improvements).
