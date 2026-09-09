# plandev-examples

**BETA RELEASE** — APIs, examples, and project structure may continue to evolve as PlanDev develops.

Progressive **mission-modeling examples** and reusable subsystem building blocks for [NASA-AMMOS PlanDev & SeqDev](https://github.com/NASA-AMMOS/plandev).

Learn to build PlanDev mission models by working through a series of runnable examples — from a simple data recorder, through a lunar hopper, up to a full Mars orbiter — while reusing shared subsystem building blocks such as power, data, and geometry.

> **New to PlanDev mission modeling?** Start with the [PlanDev documentation](https://nasa-ammos.github.io/plandev-docs/), then work through `examples/00-tutorial/`. The examples here are runnable companions to the documentation.

---

## Get started

There are two setup paths depending on your experience.

**Already comfortable with Git, Java, and GitHub?** Use the [Quick Start](#quick-start).

**New to development tools?** Follow [Set up your development environment](#set-up-your-development-environment).

### Quick Start

You need Git, Git LFS, and JDK 21 installed. You also need a GitHub account with a classic personal access token that has the `read:packages` scope.

```bash
git lfs install
git clone git@github.com:NASA-AMMOS/plandev-examples.git
cd plandev-examples

cp .env.template .env
# Edit .env and set:
#   GITHUB_USER=your-github-username
#   GITHUB_TOKEN=your-token

./gradlew build
```

The full setup guide below explains these steps in more detail.

---

## Set up your development environment

Follow this section if you're new to Git, Java, Gradle, or GitHub development.

This repository contains Java mission models built with Gradle. The repository includes the Gradle Wrapper (`./gradlew`), so **you do not need to install Gradle separately**.

### What you need

| Tool / account     | Why you need it                                                 |
| ------------------ | --------------------------------------------------------------- |
| **Git**            | Download and manage the source code                             |
| **Git LFS**        | Download large SPICE kernel files used by the geometry examples |
| **JDK 21**         | Compile and run the Java mission models                         |
| **GitHub account** | Access the repository and GitHub Packages                       |
| **GitHub token**   | Download the PlanDev packages used by the build                 |

### 1. Install Git

Install Git for your operating system:

- [Git for Windows](https://git-scm.com/download/win)
- macOS: Git is normally available through Xcode Command Line Tools. You can also install it with Homebrew: `brew install git`
- Linux: install the `git` package using your distribution's package manager.

Verify the installation:

```bash
git --version
```

### 2. Install Git LFS

Some of the geometry examples use NASA SPICE kernel data. These are large binary files, so they are stored with [Git LFS](https://git-lfs.com/) rather than ordinary Git.

Install Git LFS, then run:

```bash
git lfs install
```

Verify it:

```bash
git lfs version
```

The shared SPICE kernel set is about 238 MB. Without Git LFS, you may get small pointer files instead of the actual kernel data. See [`spice-kernels/README.md`](spice-kernels/README.md) for more information.

### 3. Install JDK 21

The Java mission models in this repository require **JDK 21**.

A JDK includes the tools needed to compile Java programs as well as the Java runtime used to run them.

For macOS with Homebrew:

```bash
brew install --cask temurin@21
```

Other JDK 21 distributions are also fine.

Verify your installation:

```bash
java -version
```

You should see Java 21 in the output.

> You do not need to install Gradle separately. The repository includes the Gradle Wrapper and uses it to run the build.

### 4. Set up GitHub SSH

The recommended way to clone this repository is with SSH:

```bash
git clone git@github.com:NASA-AMMOS/plandev-examples.git
```

If you have never used GitHub with SSH before, follow GitHub's official guide:

[Connecting to GitHub with SSH](https://docs.github.com/en/authentication/connecting-to-github-with-ssh)

After setting up SSH, test your connection:

```bash
ssh -T git@github.com
```

You should get a response confirming that GitHub recognizes your account.

> You can also clone the repository over HTTPS instead of SSH. SSH is recommended for a normal Git development workflow.

### 5. Clone the repository

From a terminal:

```bash
git lfs install
git clone git@github.com:NASA-AMMOS/plandev-examples.git
cd plandev-examples
```


### 6. Create a GitHub Packages token

The PlanDev Java libraries used by this repository are distributed through the [GitHub Maven package registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry).

GitHub requires authentication to download these packages.

Create a **classic GitHub personal access token** with the `read:packages` scope:

[Creating a personal access token (classic)](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens#creating-a-personal-access-token-classic)

You will use the token in the next step.

> **Keep your token secret.** Never commit it to Git or put it in source code.

### 7. Configure your GitHub credentials

This repository uses a local `.env` file for the GitHub Packages credentials.

From the repository root:

```bash
cp .env.template .env
```

Open `.env` and set:

```text
GITHUB_USER=your-github-username
GITHUB_TOKEN=your-token
```

The `.env` file contains local credentials and should not be committed.

### 8. Verify your development environment

Check the major tools:

```bash
java -version
./gradlew --version
```

Then build the repository:

```bash
./gradlew build
```

The first build may take some time because Gradle needs to download dependencies.

A successful build means your development environment is ready.

### 9. Start learning PlanDev

Start with:

[`examples/00-tutorial/`](examples/00-tutorial/)

For the concepts behind the examples, see [Concepts & docs](#concepts--docs).

---

## Learning Path

The examples below form a **suggested learning path**, but they are not all one continuous sequence.

### Core mission-modeling path

**00 → 01 → 02 → 03 → 04 → 05**

| Step | Directory                                                    | What You Build                            | Building Blocks Used          |
| ---- | ------------------------------------------------------------ | ----------------------------------------- | ----------------------------- |
| 0    | [`examples/00-tutorial/`](examples/00-tutorial/)             | Simple SSR data recorder                  | None                          |
| 1    | [`examples/01-power-only/`](examples/01-power-only/)         | Power + battery model                     | `power`                       |
| 2    | [`examples/02-data-only/`](examples/02-data-only/)           | Data storage + downlink                   | `data`                        |
| 3    | [`examples/03-power-and-data/`](examples/03-power-and-data/) | Combine two subsystems                    | `power` + `data`              |
| 4    | [`examples/04-hopper/`](examples/04-hopper/)                 | Lunar hopper — composition at small scale | `power` + `data`              |
| 5    | [`examples/05-orbiter/`](examples/05-orbiter/)               | Full Mars orbiter — the deep end          | `power` + `data` + `geometry` |

**04-hopper** is the gentle first taste of composing multiple building blocks. **05-orbiter** is the most complex mission model in the repository, combining the shared power, data, and geometry libraries with mission-specific features such as radar, an equipment-level PEL, telecom behavior, and SPICE-driven orbital events.

### Companion topics

These examples are standalone topics or procedures rather than steps in the core progression. Explore them once you are comfortable with the basic mission-modeling workflow.

| Directory                                                                            | Topic                                | Depends on                               |
| ------------------------------------------------------------------------------------ | ------------------------------------ | ---------------------------------------- |
| [`examples/06-constraints-and-scheduling/`](examples/06-constraints-and-scheduling/) | Constraints + scheduling goals       | Model from example 03                    |
| [`examples/07-advanced-resources/`](examples/07-advanced-resources/)                 | Advanced resource types and dynamics | Standalone                               |
| [`examples/08-activity-patterns/`](examples/08-activity-patterns/)                   | Common activity patterns             | Standalone                               |
| [`examples/09-testing-patterns/`](examples/09-testing-patterns/)                     | Model testing strategies             | Standalone                               |
| [`examples/10-external-events/`](examples/10-external-events/)                       | Scheduling against external events   | Procedures for the model from example 03 |

Each example has its own README with details about what it demonstrates and how to build or use it.

---

## Other PlanDev surfaces

Two example sets in this repository are **not** part of the mission-modeling learning path.

They demonstrate other parts of PlanDev and use a different language/toolchain.

| Directory                                      | What it is                                                                                                                           | Language                |
| ---------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ | ----------------------- |
| [`examples/actions/`](examples/actions/)       | **Actions** — server-side automation that runs against a plan, such as validation or calling external services, after a model exists | TypeScript / Node       |
| [`examples/ui-plugins/`](examples/ui-plugins/) | **UI plugins** — PlanDev web-UI customizations, such as timeline displays                                                            | TypeScript / JavaScript |

You do not need these examples to learn mission modeling. Explore them once you are comfortable with the core workflow.

---

## The subsystem building blocks (`libraries/`)

[`libraries/`](libraries/) contains reusable subsystem models that the examples compose.

These are **not a published SDK**. They do not have published Maven coordinates or API-stability guarantees. Use them by linking them within this repository or by copying the relevant library source into your own mission repository.

| Block      | Models                                                         | Maturity                                                                                    |
| ---------- | -------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| `power`    | Battery, solar array, RTG, power loads                         | **Solid** — used by 01, 03, 04, 05                                                          |
| `data`     | Prioritized storage bins, downlink, deletion, reprioritization | **Solid** — used by 02, 03, 04, 05, 06, 09, 10                                              |
| `geometry` | SPICE, orbital geometry, visibility windows, orbital events    | **Functional** — used by 05; a few spawner activities lack tests                            |
| `gnc`      | Attitude, pointing, targets, rotation math                     | **Partial / in progress** — interfaces are present and some implementations are still stubs |
| `telecom`  | Friis link budget, DSN stations, frequency bands               | **Experimental** — geometry is mocked and no example currently consumes it                  |

---

## Building

The Gradle build covers the Java libraries and examples.

Build everything:

```bash
./gradlew build
```

Build a single building block:

```bash
./gradlew :libraries:power:build
```

Build a single mission-model example:

```bash
./gradlew :examples:01-power-only:build
```

Run tests:

```bash
./gradlew test
```

Most mission-model examples produce a standalone JAR that can be uploaded to a PlanDev instance.

Some examples are procedure-only rather than mission models. For example, `examples/06-constraints-and-scheduling/` uses the mission model from example 03 and contains constraint and scheduling procedures instead of its own mission model. See the README in each example for its exact build and deployment instructions.

The `examples/actions/` and `examples/ui-plugins/` directories are separate TypeScript/Node projects and are not built by the root Java Gradle build.

---

## Using these in your own mission

The building blocks are intended to be composed into larger mission models.

For example:

```gradle
dependencies {
  implementation project(':libraries:power')
  implementation project(':libraries:data')
}
```

and in a mission model:

```java
public final class Mission {
  public final PowerModel power;
  public final Data data;

  public Mission(Registrar registrar, Configuration config) {
    this.power = new PowerModel(registrar, config);
    this.data = new Data(/* ... */);
  }
}
```

To take an example out of this repository and stand it up in its own repository, see:

**[Using an example in your own repo](USING-IN-YOUR-OWN-REPO.md)**

That guide covers the Gradle project structure, copying the required building blocks, packaging a mission-model JAR, and additional requirements for geometry/SPICE-based models.

---

## Concepts & docs

This repository is **runnable code, not a textbook**.

For how PlanDev mission models work — including mission models, activities, resource types, constraints, and scheduling goals — see the [PlanDev documentation](https://nasa-ammos.github.io/plandev-docs/).

Useful starting points include:

- [Mission modeling introduction](https://nasa-ammos.github.io/plandev-docs/mission-modeling/introduction/) — mission models, activities, and resource types
- [Modeling tutorial](https://nasa-ammos.github.io/plandev-docs/tutorials/mission-modeling/introduction/) — companion to `examples/00-tutorial/`
- [Procedural constraints and scheduling goals](https://nasa-ammos.github.io/plandev-docs/scheduling-and-constraints/procedural/introduction/)
- [Declarative constraints and scheduling goals](https://nasa-ammos.github.io/plandev-docs/scheduling-and-constraints/declarative/introduction/)
- [Uploading a mission model](https://nasa-ammos.github.io/plandev-docs/planning/upload-mission-model/)
- [Creating a plan and running a simulation](https://nasa-ammos.github.io/plandev-docs/planning/create-plan-and-simulate/)
- [Actions](https://nasa-ammos.github.io/plandev-docs/sequencing/actions/)

---

## PlanDev version

The PlanDev dependency version is configured in the root [`build.gradle`](build.gradle).

**The repository's dependency version should be kept synchronized with the PlanDev release being used by the examples.**

---

## Contributing

Each example and building block has its own README. When adding new content:

1. Reusable subsystem code goes in `libraries/`; it should be mission-agnostic.

2. Mission-modeling examples go in `examples/NN-*` and should demonstrate specific concepts or patterns.

3. Every Java subproject should build independently:

   ```bash
   ./gradlew :<project>:build
   ```

4. Every subproject should have a `README.md`.

---

## License

Licensed under the MIT License — see [`LICENSE`](LICENSE).
