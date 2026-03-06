# plandev-examples

Composable mission model libraries and progressive examples for [NASA-AMMOS Aerie](https://github.com/NASA-AMMOS/aerie).

Build reusable spacecraft subsystem models (power, data, geometry, telecom) and combine them into complete mission models — from a simple data recorder to a full Mars orbiter.

## Quick Start

```bash
# Prerequisites: Java 21, GITHUB_USER and GITHUB_TOKEN env vars
# (GITHUB_TOKEN needs read:packages scope for GitHub Packages)

git clone https://github.com/NASA-AMMOS/plandev-examples.git
cd plandev-examples
./gradlew build
```

## Learning Path

Start with the tutorial and work your way up:

| Step | Directory | What You Build | Libraries Used |
|------|-----------|---------------|----------------|
| 0 | `00-tutorial/` | Simple SSR data recorder | None (standalone) |
| 1 | `examples/01-power-only/` | Power + battery model | `libraries/power` |
| 2 | `examples/02-data-only/` | Data storage + downlink | `libraries/data` |
| 3 | `examples/03-power-and-data/` | Combined subsystems | `libraries/power` + `libraries/data` |
| 4 | `examples/04-orbiter/` | Full Mars orbiter | All libraries |
| 5 | `examples/05-constraints-and-scheduling/` | Constraints + scheduling goals | `libraries/power` + `libraries/data` |
| 6 | `examples/06-activity-patterns/` | Common activity idioms | None (standalone) |
| 7 | `examples/07-testing-patterns/` | Model testing strategies | `libraries/power` + `libraries/data` |
| 8 | `examples/08-external-events/` | Scheduling with external events | `libraries/power` + `libraries/data` + `libraries/telecom` |

## Repository Structure

```
plandev-examples/
├── 00-tutorial/                    # Start here! Basic SSR model
├── libraries/                      # Reusable subsystem models (Gradle subprojects)
│   ├── power/                      # Power, battery, solar array modeling
│   ├── data/                       # Data storage, buckets, downlink
│   ├── geometry/                   # SPICE, orbital geometry, visibility
│   ├── gnc/                        # Attitude, pointing, targets
│   └── telecom/                    # Link budgets, antennas, ground stations
├── examples/                       # Integrated examples (depend on libraries)
│   ├── 01-power-only/
│   ├── 02-data-only/
│   ├── 03-power-and-data/
│   ├── 04-orbiter/
│   ├── 05-constraints-and-scheduling/
│   ├── 06-activity-patterns/
│   ├── 07-testing-patterns/
│   └── 08-external-events/
├── archive/lander/                 # Legacy reference (unmaintained)
└── tools/                          # PEL generator, SPICE helpers
```

## Building

Each subproject builds independently:

```bash
# Build everything
./gradlew build

# Build a single library
./gradlew :libraries:power:build

# Build a single example
./gradlew :examples:01-power-only:build

# Run tests
./gradlew test
```

Each example produces a standalone JAR that can be uploaded directly to an Aerie instance.

## Using Libraries in Your Own Model

The libraries are designed to be imported into your mission model:

```gradle
// In your mission model's build.gradle
dependencies {
  implementation project(':libraries:power')
  implementation project(':libraries:data')
}
```

```java
// In your Mission.java
public class Mission {
  public final PowerModel power;
  public final DataModel data;

  public Mission(Registrar registrar, Configuration config) {
    this.power = new PowerModel(registrar, config);
    this.data = new DataModel(registrar, config);
  }
}
```

See [RECIPES.md](RECIPES.md) for common patterns and copy-paste examples.

## Requirements

- **Java 21** (via Gradle toolchain — will auto-download if needed)
- **GitHub credentials** for Aerie Maven packages:
  ```bash
  export GITHUB_USER=your-username
  export GITHUB_TOKEN=ghp_your-token  # needs read:packages scope
  ```

## Aerie Version

All projects target **Aerie v2.7.0** (`merlin-framework`, `merlin-sdk`, `contrib`).

## Contributing

Each library and example has its own README with details on what it models and how to extend it. When adding new content:

1. Libraries go in `libraries/` and should be reusable across missions
2. Examples go in `examples/` and demonstrate specific concepts
3. Every subproject must build independently (`./gradlew :<project>:build`)
4. Every subproject must have a `README.md`

## License

See [LICENSE](LICENSE) for details.
