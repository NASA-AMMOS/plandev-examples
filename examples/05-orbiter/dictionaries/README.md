# Orbiter Dictionaries

AMMOS AMPCS-style command and telemetry dictionaries for the orbiter example mission model.

## Files

- [command_dictionary.xml](command_dictionary.xml) — 20 FSW commands across power, radar, telecom, data management, and bus subsystems.
- [channel_dictionary.xml](channel_dictionary.xml) — 50+ channels covering PEL component states, dual-battery (CBE/MEV) telemetry, solar array, geometry, data buckets, telecom, and radar. (AMPCS convention: filename is `channel_dictionary.xml` but the root XML element is `<telemetry_dictionary>`.)

## Mapping to the model

Commands and channels are derived from the orbiter mission model in [../src/main/java/examples/orbiter/](../src/main/java/examples/orbiter/) and the shared subsystem libraries in [../../../libraries/](../../../libraries/).

| Dictionary entity | Model source |
|---|---|
| `RADAR_TAKE_OBS` | `TakeRadarObservation` activity |
| `RADAR_SET_MODE` | `ChangeRadarDataMode` activity |
| `TLM_DOWNLINK_START` | `Downlink` activity |
| `DATA_GEN_SET_RATE` | `ChangeDataGenerationRate` activity |
| `DATA_PLAYBACK` | `PlaybackData` activity |
| `DATA_DELETE` | `DeleteData` activity |
| `PWR_DEPLOY_SOLAR_ARRAY` | `SolarArrayDeployment` activity |
| `PWR_*_STATE` channels | `PELModel` component enums |
| `BAT_{CBE,MEV}_*` channels | `BatteryModel` resources |
| `GEO_*` channels | `GenericGeometryResources` / SPICE-derived resources |
| `DAT_*` channels | Binned data buckets in `data` library |

## Notes

- **Opcodes** (`0xNNNN`) are illustrative only; the byte groups commands by subsystem (`0x01xx` power, `0x02xx` radar, etc.).
- **Channel IDs** follow `SUBSYS-NNNN` format and are also illustrative.
- **Measurement IDs** are illustrative; a real mission would assign these from a controlled registry.
- Activities tagged as orbital-event "spawners" (`AddPeriapsis`, `AddApoapsis`, `AddOccultations`, `AddSpacecraftEclipses`) are model-internal scheduling helpers and intentionally have no command equivalents.
- Per-bin data channels are enumerated for bins 0–3; extend if the model is reconfigured for more bins.
- Schema matches the AMPCS multimission conventions used by `aerie-cli`/`aerie-sequence-languages` test fixtures (e.g. `command_banananation.xml`, `channel_banananation.xml`): `<unsigned_arg>`/`<integer_arg>`/`<enum_arg>` (not the alternate `<numeric_arg type="...">` form), element-style `<categories>` with `<module>` + `<ops_category>` children, and channel telemetry with `<measurement_id>`, `<enum_format>`, `<raw_units>` child elements.

## Validation

Both files round-trip cleanly through the canonical Aerie parser, [`@nasa-jpl/aerie-ampcs`](https://github.com/NASA-AMMOS/aerie-ampcs):

```js
import { parse, parseChannelDictionary } from '@nasa-jpl/aerie-ampcs';
const cmd = parse(fs.readFileSync('command_dictionary.xml','utf8'));
// → 20 fswCommands, 4 enums
const tlm = parseChannelDictionary(fs.readFileSync('channel_dictionary.xml','utf8'));
// → 53 telemetries
```
