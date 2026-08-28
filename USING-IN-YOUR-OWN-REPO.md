# Using an example in your own repo

The examples here depend on the shared building blocks in `libraries/` via Gradle
(`implementation project(':libraries:power')`), so copying a single example directory on its
own won't compile. This guide shows how to lift an example **plus the `libraries/*` it uses**
into a fresh repo and stand up a build that produces an PlanDev-uploadable JAR.

> The building blocks are **not published** to Maven — there are no coordinates to depend on.
> You copy the source and link it as a Gradle subproject (what this repo does), exactly as
> below.

## 1. Pick an example and find its building blocks

Check the example's `build.gradle` `dependencies {}` block (and the "Building Blocks Used"
column in the top [README](README.md)). For instance, `examples/04-hopper` uses:

```gradle
dependencies {
  implementation project(':libraries:power')
  implementation project(':libraries:data')
}
```

So you need `04-hopper` + `libraries/power` + `libraries/data`. (The orbiter additionally
needs `libraries/geometry`, which has extra requirements — see step 6.)

## 2. Lay out the new repo

Mirror the multi-project layout (keep the example and the blocks as separate subprojects —
this is the composition pattern the examples teach):

```
my-mission/
├── settings.gradle
├── build.gradle
├── gradle/ + gradlew + gradlew.bat   # copy the wrapper from this repo
├── libraries/
│   ├── power/                        # copied from plandev-examples/libraries/power
│   └── data/                         # copied from plandev-examples/libraries/data
└── mission/                          # your model — start from the copied example
    ├── build.gradle
    └── src/main/java/...
```

Copy `gradlew`, `gradlew.bat`, and the `gradle/wrapper/` directory from this repo so you get
the same Gradle version without a local install.

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

The geometry block (and the orbiter) need two extra things:

- **The `jplTime` jar** — this repo vendors it under `third-party/` and exposes it with a
  `flatDir` repository. Copy `third-party/jplTime-*.jar` into your repo and add to the root
  `repositories {}` block:
  ```gradle
  flatDir { dirs "$rootDir/third-party" }
  ```
- **SPICE kernels via Git LFS.** Copy the `spice-kernels/` set, track them with Git LFS, and
  point the workers at them with `SPICE_DIRECTORY`. See
  [spice-kernels/README.md](spice-kernels/README.md) and
  [examples/05-orbiter/README.md](examples/05-orbiter/README.md).

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

Upload that JAR to your PlanDev instance as a mission model. Done — you now have a standalone
repo that still tracks the building blocks you copied (re-copy from `plandev-examples` to pick
up improvements).
