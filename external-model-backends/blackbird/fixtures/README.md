# Blackbird plan fixtures

`powermodel-export.plan.json` is **Blackbird's own output**, not hand-written. It was produced by
running `gov.nasa.jpl.Blackbird` against the `powermodel` classpath with this command script:

```
NEW_ACTIVITY SciencePass   (2024-001T01:00:00)
NEW_ACTIVITY ActivityOne   (2024-001T02:00:00,01:00:00)
NEW_ACTIVITY ActivityEight (2024-001T03:00:00,"Earth",x)
NEW_ACTIVITY ActivityTwo   (2024-001T04:00:00,42.5)
NEW_ACTIVITY ActivityThree (2024-001T05:00:00,00:30:00,[a,b,c])
NEW_ACTIVITY ActivityFour  (2024-001T06:00:00,00:10:00,{k1=v1,k2=v2})
NEW_ACTIVITY ActivityNine  (2024-001T07:00:00,2024-001T08:00:00)
REMODEL
WRITE fixture.plan.json
```

The `.plan.json` extension routes `WRITE` to Blackbird's `JSONPlanWriter`, so every shape below is
authoritative — it is what Blackbird emits and, because writing and re-opening a plan round-trips
exactly, what its reader accepts.

It exists because the adapter previously guessed at these shapes and got two of them wrong.

## What it covers

11 activities: **7 top-level and 4 decomposition children** (`SciencePass` spawns `CollectScience`
and `Downlink`). Only the 7 with `parent == null` are PlanDev *directives*; the children are spans
that re-simulation regenerates, so importing them as directives would double-count.

Every parameter type Blackbird can write:

| Blackbird type | JSON value in `.plan.json` |
|---|---|
| `float` | bare number — `42.5` |
| `string` | bare string, **no quotes** — `"Earth"` |
| `duration` | `"01:00:00.000000"` |
| `time` | `"2024-001T08:00:00.000000"` (UTC day-of-year) |
| `list<string>` | real JSON array — `["a","b","c"]` |
| `map<string, string>` | real JSON object — `{"k1":"v1"}` (note the space in the type name) |

There is **no header** — the file is exactly `{"activities": [...]}`. No plan start, no duration, no
model reference. Anything importing this has to source those elsewhere.

## The corresponding TOL shapes

The same values in simulation output (`WRITE out.xml`) are `<DoubleValue>`, `<StringValue>`,
`<DurationValue>`, `<TimeValue>`, and for the structured ones:

```xml
<ListValue>   <Element index="0"><StringValue>a</StringValue></Element>  ... </ListValue>
<StructValue> <Element index="k1"><StringValue>v1</StringValue></Element> ... </StructValue>
```

`Element` wraps an ordinary value tag, so one recursive reader handles both.
