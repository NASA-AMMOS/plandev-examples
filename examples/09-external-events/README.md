# 09 - External Events

Demonstrates how to schedule activities in response to external events — a key real-world workflow where missions schedule operations around DSN ground contacts, orbital events, or other externally-defined windows.

## What's in this example

**Mission model**: Spacecraft with power and data subsystems, TakePicture and Downlink activities.

**Scheduling goal**:

| Goal | What it does |
|---|---|
| `ScheduleDownlinksDuringContacts` | Queries DSN contact external events and schedules a Downlink at each contact window |

**Example data** (in `src/main/resources/`):

| File | Description |
|---|---|
| `dsn-contacts-example.json` | Sample DSN ground station pass windows (3 contacts across 2 days) |

## How to use

1. Upload the JAR to Aerie and create a plan
2. Upload the DSN contact data as external events (event group: `DSNContacts`)
3. Run the `ScheduleDownlinksDuringContacts` goal
4. The goal automatically places Downlink activities during each DSN pass

## Key API

```java
// Query external events by group name
EventQuery contactQuery = new EventQuery("DSNContacts", null, null);
for (var contact : plan.events(contactQuery)) {
    plan.create("Downlink",
        new DirectiveStart.Absolute(contact.getInterval().start),
        Map.of("durationHours", SerializedValue.of(1)));
}
plan.commit();
```

## Build

```bash
./gradlew :examples:09-external-events:build
```
