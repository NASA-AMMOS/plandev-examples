# plandev-examples

Consolidation of ~10 NASA-AMMOS Aerie mission model repos into one composable monorepo with progressive examples.

Full consolidation plan: `/Users/aplave/Documents/aerie-repo-consolidation-plan.md` (~960 lines, 10 sections + appendices)

## Repo Structure

```
plandev-examples/
├── 00-tutorial/                    # Basic SSR model (from aerie-modeling-tutorial)
├── libraries/                      # Reusable subsystem models (Gradle subprojects)
│   ├── power/                      # from aerie-simple-model-power
│   ├── data/                       # from aerie-simple-model-data/model
│   ├── geometry/                   # from aerie-multimission-models-bb + orbiter
│   ├── gnc/                        # from aerie-multimission-models-bb
│   └── telecom/                    # from aerie-simple-model-telecom
├── examples/                       # Integrated examples that depend on libraries
│   ├── 01-power-only/
│   ├── 02-data-only/
│   ├── 03-power-and-data/
│   ├── 04-orbiter/                 # from aerie-orbiter-model (refactored to use libraries)
│   ├── 05-constraints-and-scheduling/
│   ├── 06-advanced-resources/      # Streamline resource types beyond Discrete
│   ├── 07-activity-patterns/
│   ├── 08-testing-patterns/
│   ├── 09-external-events/
│   ├── actions/                    # from aerie-action-examples
│   └── ui-plugins/                 # from aerie-ui-plugin-examples
├── archive/lander/                 # Legacy reference (from aerie-lander)
└── tools/                          # PEL generator, SPICE helpers
```

## Build System

- **Gradle multi-project build** with Java 21
- Root `settings.gradle` includes all subprojects
- Root `build.gradle` defines shared Aerie dependencies (merlin-framework, merlin-sdk, contrib v2.7.0)
- Libraries publish as Maven artifacts; examples depend on libraries via `implementation project(':libraries:power')`
- Each example produces a standalone JAR uploadable to Aerie

## Java Package Naming Convention

All packages follow `gov.nasa.jpl.aerie.<subsystem>` for libraries, `examples.<name>` for examples, `tutorial` for 00-tutorial.

| Subsystem | Package |
|-----------|---------|
| Power | `gov.nasa.jpl.aerie.power` |
| Data | `gov.nasa.jpl.aerie.data` |
| Geometry | `gov.nasa.jpl.aerie.geometry` |
| GNC | `gov.nasa.jpl.aerie.gnc` |
| Telecom | `gov.nasa.jpl.aerie.telecom` |

**Do NOT use the old package names** (`demosystem`, `generic`, `missionmodel`, `gov.nasa.jpl.aerie_data`, `gov.nasa.ammos.aerie.simplemodels.*`).

## Migration Rules

1. **Migrate code as-is first**, verify it builds and tests pass, THEN rename packages. Never do both in one step.
2. **Use `git subtree` for migration** to preserve commit history from source repos.
3. **The `demosystem` package collides** between simple-model-power and simple-model-telecom — must rename before both exist in this build.
4. **Git LFS for SPICE kernels** — set up LFS tracking for `*.bsp`, `*.tls`, `*.tpc`, `*.tf`, `*.ck` before committing any kernels.
5. **Each library must build independently** — `./gradlew :libraries:power:build` must work.
6. **Each example must produce a JAR** — uploadable to Aerie without modification.

## Source Repos

| Repo | Files | Complexity | Status | Notes |
|------|-------|------------|--------|-------|
| `aerie-modeling-tutorial` | 7 | Basic | Functional | End result of docs tutorial |
| `aerie-simple-model-power` | 25 | Medium | Functional | PEL model, Python generator |
| `aerie-simple-model-data` | 17 | Medium | Functional | Best structure: library+demo split |
| `aerie-simple-model-geometry` | 9 | Skeleton | Private stub | Only SPICE utils useful. Local: `~/code/aerie-simple-model-geometry` |
| `aerie-simple-model-telecom` | 16 | Medium | Private POC | Friis link equation, 6 DSN stations, mocked geometry. Local: `~/code/aerie-simple-model-telecom` |
| `aerie-orbiter-model` | 85 | High | Functional | Duplicates power code from simple-model-power |
| `aerie-lander` | 147 | Very High | Stale (2022) | Monolithic, archive only |
| `aerie-multimission-models-bb` | 63 | High | Partial | Geometry+GNC from Blackbird |
| `aerie-action-examples` | 3 | Low | Active | Node.js actions (ascii-art, basic, fresh) |
| `aerie-ui-plugin-examples` | 1 | Low | Semi-stale | Time plugin |

Clone from `NASA-AMMOS` GitHub org as needed. Private repos are already cloned locally.

## Coding Style

- Follow existing Aerie Java conventions from source repos
- Every library and example gets a `README.md` explaining what it does and how to use it
- Prefer composition over inheritance for model integration
- The user doesn't know Java well — explain Java-specific concepts when they come up
- Set up CI/CD early — GitHub Actions should build all subprojects from the start, even empty ones
