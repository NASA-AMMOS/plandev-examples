# 10 - External Events

Demonstrates how to schedule activities in response to external events — a key real-world workflow where missions schedule operations around DSN ground contacts, orbital events, or other externally-defined windows.

## What's in this example

**Mission model**: Uses the [03-power-and-data](../03-power-and-data/) model. This example contains only the scheduling goal — no duplicated model code.

**Scheduling goal**:

| Goal | What it does |
|---|---|
| `ScheduleDownlinksDuringContacts` | Queries DSN contact external events and schedules a Downlink at each contact window |

**Example data** (in `src/main/resources/`):

| File | Description |
|---|---|
| `dsn-contacts-example.json` | Sample DSN ground station pass windows (3 contacts across 2 days) |

## How to use

1. Upload the `03-power-and-data` model JAR to PlanDev and create a plan
2. Upload the DSN contact data as external events (event type: `DSNContact`)
3. Upload this example's procedure JAR and run the `ScheduleDownlinksDuringContacts` goal
4. The goal automatically places Downlink activities during each DSN pass

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
