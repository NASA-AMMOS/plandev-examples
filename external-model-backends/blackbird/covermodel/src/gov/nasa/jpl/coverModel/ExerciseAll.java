package gov.nasa.jpl.coverModel;

import gov.nasa.jpl.activity.Activity;
import gov.nasa.jpl.time.Duration;
import gov.nasa.jpl.time.Time;

import static gov.nasa.jpl.coverModel.Res.*;

/**
 * Drives every resource in {@link Res} through at least two distinct values, so each one produces
 * real segments (not just an initial sample) and the linear resources produce a measurable slope.
 *
 * Ramp is stepped 0 -> 100 across the activity so a correct adapter must emit a NON-ZERO rate:
 * PlanDev's RealDynamics is value = initial + rate*elapsedSeconds.
 */
public class ExerciseAll extends Activity {
    private final Duration dur;

    public ExerciseAll(Time t, Duration d) {
        super(t, d);
        this.dur = d;
        setDuration(d);
    }

    public void model() {
        Duration half = dur.divide(2);

        // first half: flip everything off its initial value
        Dbl.set(2.5);
        Int.set(42);
        StrEnum.set("On");
        StrFree.set("running");
        Bool.set(true);
        Dur.set(new Duration("01:00:00"));
        Tim.set(new Time("2024-100T12:00:00"));
        Ramp.set(0.0);
        Vec.get("x").set(1.0);
        Vec.get("y").set(-1.0);

        waitFor(half);

        // second half: ramp climbs, discretes change again
        Ramp.set(100.0);
        Bool.set(false);
        StrEnum.set("Degraded");
        Int.set(43);
        Vec.get("x").set(2.0);
        Rgb_.set(new Rgb(9, 8, 7));

        waitFor(half);
    }
}
