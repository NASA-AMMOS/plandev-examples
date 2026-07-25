package gov.nasa.jpl.coverModel;

import gov.nasa.jpl.resource.*;
import gov.nasa.jpl.time.Duration;
import gov.nasa.jpl.time.Time;

import java.util.Arrays;

/**
 * Conformance probe: one resource of EVERY Blackbird resource type.
 *
 * This exists so the PlanDev adapter's type coverage is verifiable rather than assumed. The demo
 * `powermodel` only declares Double/Integer/String, and Blackbird's own exampleAdaptation has no
 * BooleanResource or Sum*Resource -- so those paths were untested by construction, and two of them
 * were silently broken (a resource would register in PlanDev with a schema and then have NO
 * segments at all).
 *
 * Expected PlanDev ValueSchema for each is asserted by check_coverage.py.
 */
public class Res extends ResourceDeclaration {
    // --- scalar types ---
    public static DoubleResource   Dbl    = new DoubleResource(1.5, "cover");
    public static IntegerResource  Int    = new IntegerResource(7, "cover", "");
    public static StringResource   StrEnum = new StringResource(
        Arrays.asList(new String[]{"Off", "On", "Degraded"}));           // -> variant
    public static StringResource   StrFree = new StringResource("anything", "cover");  // -> string
    public static BooleanResource  Bool   = new BooleanResource(false, "cover");
    public static DurationResource Dur    = new DurationResource(new Duration("00:00:30"), "cover");
    public static TimeResource     Tim    = new TimeResource(new Time("2024-001T00:00:00"), "cover");

    // --- linear / integrating: these must produce a NON-ZERO rate in PlanDev ---
    public static DoubleResource      Ramp   = new DoubleResource(0.0, "cover", "", "linear");
    public static IntegratingResource Integ  = new IntegratingResource(Ramp, Duration.ONE_SECOND);

    // --- derived (sum) resources ---
    public static SumDoubleResource  SumDbl = new SumDoubleResource(Dbl, Ramp, "cover");
    public static SumIntegerResource SumInt = new SumIntegerResource(Int, Int, "cover");

    // --- arrayed (flattened by the adapter to Name.Index) ---
    public static ArrayedResource<DoubleResource> Vec =
        new ArrayedResource<DoubleResource>(new String[]{"x", "y"}) {};
}
