package gov.nasa.jpl.aerie.gnc.secondary;

import gov.nasa.jpl.aerie.gnc.interfaces.Target;
import gov.nasa.jpl.time.Time;
import org.apache.commons.math3.geometry.euclidean.threed.Vector3D;

import static gov.nasa.jpl.aerie.gnc.functions.AttitudeFunctions.getState;

public class OrbitPlaneSecondaryTarget implements Target {
    private final String centerBody;
    private final String obsBody;
    private final String relativeFrame;

    /**
     * ***********************POINTS IN THE ORBIT PLANE************************
     * ***********************(OR AS CLOSE AS POSSIBLE)************************
     *
     * The OrbitPlaneSecondaryTarget takes in the body that is being
     * orbited around, the orbiting (observing) body, and the frame that
     * the spacecraft's orientation is relative to. This should be used
     * when you want to get some observer to be aligned within the orbital
     * plane. The output is the unit vector3D that is normal to the
     * targeted plane in the relative frame. This is to be used strictly
     * as a secondary target.
     *
     * EX: Gravity gradient torque reduction by aligning the spacecraft
     * solar panel axis (observer) with the orbital plane (target)
     *
     * @param centerBody SPICE defined string of the body that is being
     *                   orbited by the observing body
     *
     * @param obsBody SPICE defined string of the observing body
     *
     * @param relativeFrame SPICE defined string of the frame that the
     *                      spacecraft's orientation is being defined
     *                      relative to
     */

    public OrbitPlaneSecondaryTarget(String centerBody, String obsBody, String relativeFrame){
        this.centerBody = centerBody;
        this.obsBody = obsBody;
        this.relativeFrame = relativeFrame;

    }

    @Override
    public Vector3D getPointing(Time et) {
        // Cross the position and velocity of the observing body and make
        // a unit vector
        return Vector3D.crossProduct(getPosition(et), getVelocity(et)).normalize();
    }

    public Vector3D getPosition(Time et){
        double[] state = getState(centerBody, et, relativeFrame, "LT+S", obsBody);
        return new Vector3D(state[0], state[1], state[2]);
    }

    public Vector3D getVelocity(Time et){
        double[] state = getState(centerBody, et, relativeFrame, "LT+S", obsBody);
        return new Vector3D(state[3], state[4], state[5]);
    }

    @Override
    public String getName(){
        return "OrbitPlaneSecondaryTarget," + centerBody;
    }
}
