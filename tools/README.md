# tools

Helper scripts for mission modeling.

## `pel_java_generator.py` — Power Equipment List → Java

Generates Java for a spacecraft's **Power Equipment List (PEL)** from a JSON spec: instead of
hand-writing one enum per power-consuming component, you describe the components and their
power states in `pel.json` and the script emits the Java.

### Input: `pel.json`

A `power_loads` array, where each entry is one component. Two load types:

- **`states`** — a fixed set of modes, each with a power value. Generates a `<Name>_State`
  enum whose constants carry CBE (Current Best Estimate) and MEV (Maximum Expected Value)
  loads in Watts. Example shape (see the working sample in
  [`examples/01-power-only/pel.json`](../examples/01-power-only/pel.json)):
  ```json
  {
    "power_loads": [
      {
        "name": "Camera",
        "load_type": "states",
        "power_states": [
          { "state": "off", "CBE_power_usage": {"value": 0.0}, "MEV_power_usage": {"value": 0.0} },
          { "state": "on",  "CBE_power_usage": {"value": 48.0}, "MEV_power_usage": {"value": 60.0} }
        ]
      }
    ]
  }
  ```
- **`dynamic`** — a continuously-variable load. Generates a mutable CBE resource and a derived
  MEV resource (`MEV = CBE * MEV_factor`).

The script also generates a `PELModel`-style class that instantiates each load and sums them
into `spacecraft.cbeLoad` / `spacecraft.mevLoad`.

### Run

```bash
python3 tools/pel_java_generator.py \
  --input examples/01-power-only/pel.json \
  --output-dir examples/01-power-only/src/main/java/examples/power/models/pel \
  --package examples.power.models.pel
```

| Flag | Required | Default | Meaning |
|---|---|---|---|
| `--input` / `-i` | no | `pel.json` | Path to the PEL JSON spec |
| `--output-dir` / `-o` | **yes** | — | Directory for the generated `.java` files; created if missing |
| `--package` / `-p` | **yes** | — | Java package for the generated classes |

The two maintained PELs in this repo both round-trip through the script:

```bash
# Regenerates examples/01-power-only/.../pel/ byte-for-byte
python3 tools/pel_java_generator.py -i examples/01-power-only/pel.json \
  -o /tmp/pel-check -p examples.power.models.pel
diff -r /tmp/pel-check examples/01-power-only/src/main/java/examples/power/models/pel/
```

### Caveat — the orbiter's PEL has hand-edits

[`examples/05-orbiter/pel.json`](../examples/05-orbiter/pel.json) regenerates 13 of its 15 Java
files exactly, but **two carry post-generation hand-edits that regenerating would discard**:

- `PELModel.java` wraps the two total-load registrations in `withUnit("W", …)`, and imports
  `UnitRegistrar.withUnit`. The generator does not emit units.
- `Radar_State.java` uses integer literals (`ON_LOW(1000, 1000)`) where the generator emits
  doubles (`1000.0`). Cosmetic only.

So treat generated code as a **starting point**: regenerate into a scratch directory, diff, and
port your changes across rather than overwriting in place.

## `run_transfer/` — import a simulation PlanDev did not perform

A **run transfer** is one JSON file holding a simulation somebody else already ran: the model's type
declaration, the plan's directives, and the results. PlanDev imports it as a first-class run — it
renders on the timeline and constraints check against it — with nothing behind the model to compile
or to call. That makes it the way to get a run out of a simulator PlanDev cannot itself drive, and
the way to hand a finished run to someone who has none of the tooling that produced it.

[`run_transfer/README.md`](run_transfer/README.md) is the normative format reference;
[`run_transfer/writer.py`](run_transfer/writer.py) is the reference producer, stdlib only and
self-contained, so it can be copied next to whatever code is doing the simulating.

```python
import writer as run_transfer

document = run_transfer.RunTransfer(
    declaration=declaration, mission="Demo", plan_name="Recorded run",
    plan_start=start, plan_duration_us=3600 * 1_000_000,
    directives=[run_transfer.RunDirective("a1", "Observe", arguments={"target": "Europa"})],
    response={"realProfiles": ..., "discreteProfiles": ..., "spans": [...]},
).to_json()

for problem in run_transfer.run_problems(document):   # PlanDev's own rules, before the upload
    print(problem)
run_transfer.write_run(document, "my.run.json")
```

Upload the file on the plans page exactly like a plan export. Two things the format will bite a
producer with if they are not known in advance, both of which `writer.py` handles:

- **The two timestamps in one file use different calendars.** `plan.start_time` is an ISO calendar
  date with a literal `+00:00`; `results.startTime` is day-of-year. That asymmetry is inherited from
  the two formats a run file embeds.
- **A non-finite number must be written `1e400`.** `NaN` and `Infinity` are not JSON — Python emits
  them and nothing else accepts them — and a value re-serialized by JavaScript along the way becomes
  `null`, which is the wire spelling of a profile *gap*: a wrong run, stored, with no complaint.

```bash
python3 tools/run_transfer/test_writer.py              # stdlib only
python3 -m pytest tools/run_transfer/test_run_transfer.py   # the JSON schema; needs jsonschema
python3 tools/run_transfer/make_fixtures.py --check    # the invalid fixtures are generated
```

## `generate_external_events.py` — scale-test external events

Generates large, varied [PlanDev external-event](../examples/07-external-events/) datasets for
hopper/orbiter scale testing. Stdlib only. Emits two files in PlanDev's canonical ingest format:

- `<prefix>_schema.json` — event-type + source-type definitions (upload to PlanDev **first**)
- `<prefix>_source.json` — one external source with N events spanning a mission window

Eight hopper/orbiter-relevant event types, each with its own attribute schema: `DSNContact`
(station / band / peak elevation / bitrate), `Eclipse`, `Occultation`, `ThermalCycle`,
`KeepOutWindow`, `MomentumDump`, `SolarFlare`, `GroundStationOutage`. Events are placed with
simple per-type cadences (exponential spacing) over the window — the aim is **scale and
variety, not physical accuracy** (no SPICE/geometry; randomized attributes).

```bash
# ~5000 events across 2028 (defaults)
python3 tools/generate_external_events.py --out-dir /tmp/ev

# 20k events, custom window + seed
python3 tools/generate_external_events.py --count 20000 --start 2028-100 --end 2028-200 --seed 7 --out-dir /tmp/ev

# match the hopper comms_pass_schema (event type DSS_Pass instead of DSNContact)
python3 tools/generate_external_events.py --contact-type DSS_Pass --out-dir /tmp/ev
```

The default `DSNContact` comms type lines up with example 07's `ScheduleDownlinksDuringContacts`
goal (which queries that type). Output JSON is generated on demand and **not committed** —
thousands of events is a multi-MB source file; size `--count` to your ingest budget (PlanDev
ingests external events at roughly hundreds/sec).
