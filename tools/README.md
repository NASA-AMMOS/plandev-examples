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
# with pel.json in the current directory
python3 tools/pel_java_generator.py
```

### Caveat — adjust the output path/package before use

The script currently hardcodes a **pre-consolidation** output path and package
(`missionmodel/src/main/java/demosystem/models/pel`, package `demosystem.models.pel`). Before
using it in this repo, edit the `path` variable and the `package` string near the top of the
script to match the target example's convention (e.g. `examples.orbiter.power.pel`). Treat the
generated code as a starting point — the maintained PELs in `examples/01-power-only/` and
`examples/05-orbiter/src/.../power/pel/` show the current expected shape.

## `generate_external_events.py` — scale-test external events

Generates large, varied [PlanDev external-event](../examples/10-external-events/) datasets for
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

The default `DSNContact` comms type lines up with example 10's `ScheduleDownlinksDuringContacts`
goal (which queries that type). Output JSON is generated on demand and **not committed** —
thousands of events is a multi-MB source file; size `--count` to your ingest budget (PlanDev
ingests external events at roughly hundreds/sec).
