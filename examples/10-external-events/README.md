# 10 - External Events

Demonstrates how to schedule activities in response to external events — a key real-world workflow where missions schedule operations around DSN ground contacts, orbital events, or other externally-defined windows.

## What's in this example

**Mission model**: Uses the [03-power-and-data](../03-power-and-data/) model. This example contains only the scheduling goal — no duplicated model code.

**Scheduling goal**:

| Goal | What it does |
|---|---|
| `ScheduleDownlinksDuringContacts` | Places a one-hour `Downlink` at the start of each external-event provided `DSNContact` window |

**Example external event data** (in `src/main/resources/`):

| File | Description |
|---|---|
| `dsn_contact_schema.json` | Defines the `DSNContact` event type and `DSNSchedule` source type |
| `dsn_contact_source.json` | Contains three example DSN contacts spanning January 1–2, 2025 |

## How to use

1. Build and upload the `03-power-and-data` mission model.
2. Create a plan that includes January 1–2, 2025, the period covered by the example contacts.
3. Go to the External Sources page and upload `dsn_contact_schema.json` as an external event schema. This defines the `DSNContact` event type and `DSNSchedule` source type.
4. Upload `dsn_contact_source.json` as an external event source. Its events belong to the `DSNSchedule Default` derivation group.
5. Open the plan’s External Sources panel, select Manage Derivation Groups, and associate `DSNSchedule Default` with the plan.
6. Confirm that the three `DSNContact` events now appear on the plan timeline.
7. Add one or more `TakePicture` or `GenerateData` activities so the spacecraft has data to downlink.
8. Build and upload this example’s procedure JAR.
9. Run `ScheduleDownlinksDuringContacts` to add a one-hour `Downlink` at the beginning of each contact window.
10. Simulate the plan. Each `Downlink` turns on telecom power and spawns a `PlaybackData` activity to transfer stored data.

## Key API

```java
// Query external events by event type
var contactQuery = new EventQuery(null, "DSNContact", null);
for (var contact : plan.events(contactQuery).collect()) {
    plan.create(new NewDirective(
        new AnyDirective(Map.of("durationHours", SerializedValue.of(1))),
        "Downlink", "Downlink",
        new DirectiveStart.Absolute(contact.getInterval().start)));
}
plan.commit();
```

## Build

```bash
# Build the mission model (from example 03)
./gradlew :examples:03-power-and-data:build

# Build the procedure JAR
./gradlew :examples:10-external-events:build
```
