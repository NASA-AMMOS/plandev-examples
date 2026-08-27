# plandev-examples

Progressive **mission-modeling examples** and reusable subsystem building blocks for
[NASA-AMMOS Aerie](https://github.com/NASA-AMMOS/aerie).

Learn to build Aerie mission models by working through a graded series of examples — from a
simple data recorder, through a lunar hopper, up to a full Mars orbiter — reusing shared
subsystem building blocks (power, data, geometry) along the way.

> **New to Aerie mission modeling?** Read the concept docs first, then follow the learning
> path below — the examples are the runnable companions to the docs. See
> [Concepts & docs](#concepts--docs).

## Quick Start

* Ensure you have Git, Git LFS, Java JDK 21 installed. 
* Create a `.env` file based on `.env.template`, fill in your Github username and a "classic" Github Personal Access Token 

## Requirements

- **Git** must be installed. 
- To clone this repo, you need to [setup an SSH key](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/generating-a-new-ssh-key-and-adding-it-to-the-ssh-agent) on your Github account if you haven't before.
- **Java 21** (via Gradle toolchain — will auto-download if needed)
- **Git LFS** for SPICE kernel files used by the orbiter and geometry library (~238 MB).
  Install with `brew install git-lfs` or by downloading the installer from [git-lfs.com](https://git-lfs.com/). 
  Then run the command `git lfs install` before cloning this repo. If you already cloned without LFS, run `git lfs pull` to fetch the kernel files.
- **GitHub credentials** for Aerie Maven packages:
  ```bash
  export GITHUB_USER=your-username
  export GITHUB_TOKEN=ghp_your-token  # needs read:packages scope
  ```
  If you have not done so before, you need to create a **[personal access token](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens#creating-a-personal-access-token-classic) in your GitHub account** that includes the `read-packages` scope, so that you can download the PlanDev Maven packages from the [GitHub Maven package registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-apache-maven-registry). Keep track of the username and token after you generate it.


## Quick Start

```bash
git lfs install          # one-time setup for SPICE kernel files
git clone https://github.com/NASA-AMMOS/plandev-examples.git
cd plandev-examples
./gradlew build
```

## Learning Path

Work through these **in order** — each step adds one new idea on top of the previous. Start
at the tutorial.

| Step | Directory                                 | What You Build | Building Blocks Used |
|------|-------------------------------------------|---------------|----------------------|
| 0 | `examples/00-tutorial/`                   | Simple SSR data recorder | None (standalone) |
| 1 | `examples/01-power-only/`                 | Power + battery model | `power` |
| 2 | `examples/02-data-only/`                  | Data storage + downlink | `data` |
| 3 | `examples/03-power-and-data/`             | Combine two subsystems | `power` + `data` |
| 4 | `examples/04-hopper/`                     | Lunar hopper — composition at small scale | `power` + `data` |
| 5 | `examples/05-orbiter/`                    | Full Mars orbiter — the deep end | `power` + `data` + `geometry` |
| 6 | `examples/06-constraints-and-scheduling/` | Constraints + scheduling goals | Procedures for the 03 model |
| 7 | `examples/07-advanced-resources/`         | Streamline resource types | None (standalone) |
| 8 | `examples/08-activity-patterns/`          | Common activity idioms | None (standalone) |
| 9 | `examples/09-testing-patterns/`           | Model testing strategies | None (self-contained model) |
| 10 | `examples/10-external-events/`            | Scheduling against external events | Procedures for the 03 model |

**04-hopper** is the gentle first taste of composing the building blocks; **05-orbiter** is
the realistic, full-complexity model that shows what those blocks look like at scale plus
mission-specific additions (radar, an equipment-level PEL, SPICE-driven orbital events).

## Other Aerie surfaces (not the modeling path)

Two example sets in this repo are **not** part of the mission-modeling learning path above.
They demonstrate different parts of Aerie and use a different language/toolchain (TypeScript,
not Java). You don't need them to learn mission modeling — explore them once you're
comfortable with the core workflow.

| Directory | What it is | Language |
|-----------|-----------|----------|
| `examples/actions/` | **Actions** — server-side automation that runs against a plan (validation, calling external services) *after* a model exists | TypeScript / Node |
| `examples/ui-plugins/` | **UI plugins** — Aerie web-UI customizations (e.g. showing Mars LMST or a fixed timezone on the timeline) | TypeScript / JS |

## Repository Structure

```
plandev-examples/
├── examples/                       # Mission-modeling learning path (depend on libraries)
│   ├──00-tutorial/                 # Start here! Basic SSR model
│   ├── 01-power-only/  
│   ├── 02-data-only/
│   ├── 03-power-and-data/
│   ├── 04-hopper/                  # Lunar hopper (compose power + data)
│   ├── 05-orbiter/                 # Full Mars orbiter
│   ├── 06-constraints-and-scheduling/
│   ├── 07-advanced-resources/
│   ├── 08-activity-patterns/
│   ├── 09-testing-patterns/
│   ├── 10-external-events/
│   ├── actions/                    # Other surface: server-side automation (TypeScript)
│   └── ui-plugins/                 # Other surface: Aerie UI customizations (TypeScript)
├── libraries/                      # Reusable subsystem building blocks (Gradle subprojects)
│   ├── power/                      # Power, battery, solar array, RTG
│   ├── data/                       # Prioritized storage bins, downlink, deletion
│   ├── geometry/                   # SPICE, orbital geometry, visibility, events
│   ├── gnc/                        # Attitude, pointing, targets (in progress)
│   └── telecom/                    # Link budgets, antennas, ground stations (experimental)
├── archive/lander/                 # Legacy reference (unmaintained)
└── tools/                          # PEL generator (see tools/README.md)
```

## The subsystem building blocks (`libraries/`)

`libraries/` holds reusable subsystem models that the examples compose. **They are not a
published SDK** — there are no Maven coordinates and no API-stability guarantees. Use them by
linking within this repo (`implementation project(':libraries:power')`) or by copying the
relevant `libraries/*` into your own repo (see
[USING-IN-YOUR-OWN-REPO.md](USING-IN-YOUR-OWN-REPO.md)). Maturity varies:

| Block | Models | Maturity |
|-------|--------|----------|
| `power` | battery, solar array, RTG, power loads | **Solid** — used by 01, 03, 04, 05 |
| `data` | prioritized storage bins, downlink, deletion, reprioritization | **Solid** — used by 02, 03, 04, 05, 06, 09, 10 |
| `geometry` | SPICE, orbital geometry, visibility windows, orbital events | **Functional** — used by 05; a few spawner activities lack tests |
| `gnc` | attitude, pointing, targets, rotation math | **Partial / in progress** — interfaces present, some impls are stubs |
| `telecom` | Friis link budget, DSN stations, frequency bands | **Experimental** — geometry is mocked; no example consumes it yet |

## Building

Each subproject builds independently:

```bash
# Build everything
./gradlew build

# Build a single building block
./gradlew :libraries:power:build

# Build a single example
./gradlew :examples:01-power-only:build

# Run tests
./gradlew test
```

Each example produces a standalone JAR that can be uploaded directly to an Aerie instance.

## Using these in your own mission

The building blocks are meant to be composed — link them within this repo, or lift an example
plus the `libraries/*` it uses into a fresh repo of your own. The composition pattern:

```gradle
// In your mission model's build.gradle
dependencies {
  implementation project(':libraries:power')
  implementation project(':libraries:data')
}
```

```java
// In your Mission.java — instantiate the subsystem models and wire their resources together
public final class Mission {
  public final PowerModel power;
  public final Data data;

  public Mission(Registrar registrar, Configuration config) {
    this.power = new PowerModel(registrar, config);
    this.data  = new Data(/* ... */);
  }
}
```

To take an example out of this repo and stand it up on its own, see
[USING-IN-YOUR-OWN-REPO.md](USING-IN-YOUR-OWN-REPO.md).

## Concepts & docs

This repo is **runnable code, not a textbook.** For how Aerie mission models work — the
`@MissionModel` class, activities, resource types, constraints, and scheduling goals — see the
Aerie / PlanDev documentation; the examples here are the worked companions to it:

- Mission modeling tutorial, resources, and activities
- Constraints (procedural + declarative) and scheduling goals
- Uploading a model and running a simulation

Docs: <https://nasa-ammos.github.io/aerie-docs/>

## Aerie Version

All projects target **Aerie v4.1.1** (`merlin-framework`, `merlin-sdk`, `contrib`).

## Contributing

Each example and building block has its own README. When adding new content:

1. Reusable subsystem code goes in `libraries/`; it should be mission-agnostic.
2. Mission-modeling examples go in `examples/NN-*` and demonstrate specific concepts in order.
3. Every Java subproject must build independently (`./gradlew :<project>:build`).
4. Every subproject should have a `README.md`.

## License

Licensed under the MIT License — see [LICENSE](LICENSE).
