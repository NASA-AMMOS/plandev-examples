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
