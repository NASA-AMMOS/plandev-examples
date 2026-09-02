# 07 - External Events

**What this teaches:** scheduling activities in response to **external events** — data that
comes from outside PlanDev, such as DSN ground contacts, orbital events, or any externally
defined window. Two things make this more than a "place an activity" example: the scheduled
activity is **sized to the event's window**, and the goal **reads the event's payload**.

**Prerequisite:** this project contains **no mission model**. Its scheduling goal runs against
the model from [03-power-and-data](../03-power-and-data/), so build and upload that first.

## What's in this example

**Scheduling goal** — [`ScheduleDownlinksDuringContacts`](src/main/java/examples/events/procedures/ScheduleDownlinksDuringContacts.java)

For each `DSNContact` event it creates a `Downlink` that **spans the whole contact window**
(a 1h45m pass gets a 1h45m downlink), skipping contacts that already have a nearby Downlink.
It reads two things off the event's attributes: `bitrate_kbps`, to skip passes below a
configurable floor, and `station`, which goes into the directive's name.

Both behaviors are the point of the example. Hardcoding a duration would waste most of a real
contact, and a goal that ignores `attributes` isn't really using external events for anything
a plain time window couldn't do.

| Parameter | Default | Meaning |
|---|---|---|
| `minimumBitrateKbps` | `0.0` | Contacts slower than this are skipped |

**Example external event data** — [`src/main/resources/`](src/main/resources/)

| File | Description |
|---|---|
| [`dsn_contact_schema.json`](src/main/resources/dsn_contact_schema.json) | Defines the `DSNContact` event type (`station`, `band`, `bitrate_kbps`) and the `DSNSchedule` source type |
| [`dsn_contact_source.json`](src/main/resources/dsn_contact_source.json) | Three example DSN contacts spanning January 1–2, 2025, of 1h30m, 2h and 1h45m |

## Build

```bash
# The mission model this goal runs against (example 03)
./gradlew :examples:03-power-and-data:build

# The procedure — compile first, then build the JAR
./gradlew :examples:07-external-events:compileJava
./gradlew :examples:07-external-events:buildAllProcedureJars
```

> Two commands are needed here, and `:build` on its own produces **no artifacts**.

**Artifact:** `build/libs/ScheduleDownlinksDuringContacts.jar`. The mission model JAR is
`examples/03-power-and-data/build/libs/power-and-data-example.jar`.

## Try it

1. Upload `power-and-data-example.jar` as a mission model.
2. Create a plan covering **January 1–2, 2025**, the period the example contacts fall in.
3. On the External Sources page,
   [upload](https://nasa-ammos.github.io/plandev-docs/tutorials/external-events/uploading-an-external-source/)
   `dsn_contact_schema.json` as an external event schema, then `dsn_contact_source.json` as a
   source. Its events belong to the `DSNSchedule Default` derivation group.
4. In the plan's External Sources panel choose **Manage Derivation Groups** and associate
   `DSNSchedule Default` with the plan. The three `DSNContact` events should appear on the
   timeline.
5. Add a few `TakePicture` or `GenerateData` activities so there is data worth downlinking.
6. Upload `ScheduleDownlinksDuringContacts.jar` and run it.
7. Three `Downlink` activities appear, each named for its station and each **as long as its
   contact** — 1h30m, 2h and 1h45m, not a uniform hour.
8. Simulate. Each `Downlink` turns on telecom power and spawns `PlaybackData` to transfer
   stored data.
9. Re-run the goal with `minimumBitrateKbps` set to `1000` — the 512 kbps `DSS-63` pass is now
   skipped, and only two downlinks are created. That is the event payload driving the decision.

No tests in this example — see [10-testing-patterns](../10-testing-patterns/).

## Docs

- [External events](https://nasa-ammos.github.io/plandev-docs/planning/external-events/introduction/) and [event attributes](https://nasa-ammos.github.io/plandev-docs/planning/external-events/external-events-attributes/)
- ["Creating a Scheduling Goal with External Events" tutorial](https://nasa-ammos.github.io/plandev-docs/tutorials/external-events/creating-a-scheduling-goal-with-external-events/)
- [Procedural Scheduling API](https://nasa-ammos.github.io/plandev-docs/scheduling-and-constraints/procedural/introduction/)
- [External events in procedural timelines](https://nasa-ammos.github.io/plandev-docs/scheduling-and-constraints/procedural/timelines/basics/external-events/)
