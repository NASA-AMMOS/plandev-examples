package gov.nasa.jpl.coverModel;

import gov.nasa.jpl.resource.Resource;
import gov.nasa.jpl.time.Time;

/** A resource whose value is a custom Comparable type -- see {@link Rgb}. */
public class RgbResource extends Resource<Rgb> {
    private Rgb profile;

    public RgbResource(Rgb initial, String subsystem) {
        super(subsystem);
        this.profile = initial;
    }

    @Override
    public Rgb profile(Time t) { return profile; }
}
