# Attribution

This repository consolidates content from several NASA-AMMOS Aerie repositories. The table below records the upstream source each top-level directory was **initially derived from**. Once content lands here it continues to evolve independently — this file documents provenance, not current parity.

All upstream repos referenced are at https://github.com/NASA-AMMOS.

## Directory mapping

| Path | Initially derived from | Notes |
|---|---|---|
| [`00-tutorial/`](00-tutorial/) | [`aerie-modeling-tutorial`](https://github.com/NASA-AMMOS/aerie-modeling-tutorial) | End state of the official docs tutorial. Package renamed `missionmodel` → `tutorial`. |
| [`libraries/power/`](libraries/power/) | [`aerie-simple-model-power`](https://github.com/NASA-AMMOS/aerie-simple-model-power) | PEL machinery, battery + solar array models. Package renamed `demosystem` → `gov.nasa.jpl.aerie.power`. PEL generator script moved to [`tools/pel_generator.py`](tools/pel_generator.py). |
| [`libraries/data/`](libraries/data/) | [`aerie-simple-model-data`](https://github.com/NASA-AMMOS/aerie-simple-model-data) (`model/` subdir) | Multi-bin onboard storage + canonical data activities. Package renamed `gov.nasa.jpl.aerie_data` → `gov.nasa.jpl.aerie.data`. |
| [`libraries/geometry/`](libraries/geometry/) | [`aerie-multimission-models-bb`](https://github.com/NASA-AMMOS/aerie-multimission-models-bb) (Blackbird) + [`aerie-orbiter-model`](https://github.com/NASA-AMMOS/aerie-orbiter-model) | SPICE infrastructure originates in multimission-bb; orbital event generators and resource models were consolidated here from the orbiter repo during the 2026-03 migration. |
| [`libraries/gnc/`](libraries/gnc/) | [`aerie-multimission-models-bb`](https://github.com/NASA-AMMOS/aerie-multimission-models-bb) | Attitude / targeting code from Blackbird. Package renamed `missionmodel.gnc` → `gov.nasa.jpl.aerie.gnc`. |
| [`libraries/telecom/`](libraries/telecom/) | [`aerie-simple-model-telecom`](https://github.com/NASA-AMMOS/aerie-simple-model-telecom) | Friis link equation, DSN ground station configs, per-link bit-rate resources. Package renamed `gov.nasa.ammos.aerie.simplemodels.telecom` → `gov.nasa.jpl.aerie.telecom`. Originally a private POC. **Experimental — not currently consumed by any example in this repo; see [libraries/telecom/README.md](libraries/telecom/README.md) for the full status writeup.** |
| [`examples/01-power-only/`](examples/01-power-only/) | [`aerie-simple-model-power`](https://github.com/NASA-AMMOS/aerie-simple-model-power) (`demosystem` package) | Demo activities (`TurnOnCamera`, `Drive`, etc.) that exercise [`libraries/power/`](libraries/power/). |
| [`examples/02-data-only/`](examples/02-data-only/) | [`aerie-simple-model-data`](https://github.com/NASA-AMMOS/aerie-simple-model-data) (`demo/` subdir) | Demo wrapper around [`libraries/data/`](libraries/data/). |
| [`examples/03-power-and-data/`](examples/03-power-and-data/) | *(new in this repo)* | Composition example showing how to integrate two library subsystems. No upstream source. |
| [`examples/05-orbiter/`](examples/05-orbiter/) | [`aerie-orbiter-model`](https://github.com/NASA-AMMOS/aerie-orbiter-model) | Mars-orbiter-style mission model. Refactored to import [`libraries/{power,data,geometry}`](libraries/) rather than duplicate the subsystem code; adds an equipment-level PEL, radar, SPICE-driven event activities, and a local telecom stub on top. |
| [`examples/06-constraints-and-scheduling/`](examples/06-constraints-and-scheduling/) | *(new in this repo)* | — |
| [`examples/07-advanced-resources/`](examples/07-advanced-resources/) | *(new in this repo)* | Streamline resource-type cheatsheet. |
| [`examples/08-activity-patterns/`](examples/08-activity-patterns/) | *(new in this repo)* | Common activity idioms (state machines, loops, conditional logic, …). |
| [`examples/09-testing-patterns/`](examples/09-testing-patterns/) | *(new in this repo)* | Model testing recipes. |
| [`examples/10-external-events/`](examples/10-external-events/) | *(new in this repo)* | External events + scheduling integration. |
| [`examples/actions/`](examples/actions/) | [`aerie-action-examples`](https://github.com/NASA-AMMOS/aerie-action-examples) | Node.js Aerie actions (`ascii-art`, `basic`, `fresh`). |
| [`examples/ui-plugins/`](examples/ui-plugins/) | [`aerie-ui-plugin-examples`](https://github.com/NASA-AMMOS/aerie-ui-plugin-examples) | Aerie UI plugin examples (TypeScript). |
| [`archive/lander/`](archive/lander/) | [`aerie-lander`](https://github.com/NASA-AMMOS/aerie-lander) | Unmaintained legacy InSight-derived reference. Kept for posterity only. |
| [`tools/pel_generator.py`](tools/pel_generator.py) | [`aerie-simple-model-power`](https://github.com/NASA-AMMOS/aerie-simple-model-power) | Originally at `python/pel_generator.py` in the source repo. |

## A note on file-level provenance

Per-file attribution would go stale every time we refactor — and we expect this repo's content to keep evolving. The table above is the authoritative record at the **directory** level, which is robust to file renames, splits, and rewrites. To trace a specific file back to its original location, check the corresponding upstream repo's `git log` at the migration date (2026-03-06).

Java packages also carry a short attribution pointer in their `package-info.java` that refers back to this file.
