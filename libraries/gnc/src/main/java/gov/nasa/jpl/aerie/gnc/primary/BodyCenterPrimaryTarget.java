package gov.nasa.jpl.aerie.gnc.primary;

import gov.nasa.jpl.aerie.gnc.interfaces.Target;
import gov.nasa.jpl.time.Time;
import org.apache.commons.math3.geometry.euclidean.threed.Vector3D;

import static gov.nasa.jpl.aerie.gnc.functions.AttitudeFunctions.getState;

public class BodyCenterPrimaryTarget implements Target {
    private final String bodyName;
    private final String obsBody;
    private final String relativeFrame;

    /**
     * **********************POINTS AT SPICE DEFINED BODY**********************
     *
     * The BodyCenterPrimaryTarget takes in the target body's name, observing
     * body's name, and the frame the spacecraft's orientation is relative
     * to. This should be used when the target is a body that has its
     * ephemeris defined in a kernel. The output is a unit Vector3D of the
     * target body's direction relative to the observing body in the
     * relative frame. This is to be used strictly as a primary target.
     * (NOTE: This does the same thing as BodyNormalPlaneSecondaryTarget
     * but it is used to define a target vector rather than a target plane)
     *
     * EX: The Earth's ephemeris is loaded in a kernel. The Earth is the
     * target of the observer (antenna) on the spacecraft.
     *
     * @param bodyName SPICE defined string of the target body
     *
     * @param obsBody SPICE defined string of the observing body
     *
     * @param relativeFrame SPICE defined string of the frame that
     *                      the spacecraft's orientation is being
     *                      defined relative to
     */

    public BodyCenterPrimaryTarget(String bodyName, String obsBody, String relativeFrame){
        this.bodyName = bodyName;
        this.obsBody = obsBody;
        this.relativeFrame = relativeFrame;

    }

    @Override
    public Vector3D getPointing(Time et) {
        // Get unit vector of position of target relative to observer
        return getPosition(et).normalize();
    }

    public Vector3D getPosition(Time et){
        double[] state = getState(bodyName, et, relativeFrame, "LT+S", obsBody);
        return new Vector3D(state[0], state[1], state[2]);
    }

    public Vector3D getVelocity(Time et){
        double[] state = getState(bodyName, et, relativeFrame, "LT+S", obsBody);
        return new Vector3D(state[3], state[4], state[5]);
    }

    @Override
    public String getName() {
        return "BodyCenterPrimaryTarget," + bodyName;
    }

}
