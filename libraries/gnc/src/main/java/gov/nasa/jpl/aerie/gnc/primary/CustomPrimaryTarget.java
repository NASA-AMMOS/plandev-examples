package gov.nasa.jpl.aerie.gnc.primary;

import gov.nasa.jpl.aerie.gnc.interfaces.Target;
import gov.nasa.jpl.time.Time;
import org.apache.commons.math3.geometry.euclidean.threed.Vector3D;

public class CustomPrimaryTarget implements Target {
    private final Vector3D customTarget;

    /**
     * ********************POINTS IN AN INERTIAL DIRECTION*********************
     *
     * The CustomTarget takes in the Vector3D version of a custom vector,
     * already assumed to be in the frame the spacecraft's orientation is
     * relative to. This could be used when pulling values from a CSV thrust
     * vector file. The output is a unit Vector3D pointing in the direction
     * of the custom vector. This is to be used strictly as a primary target.
     *
     * EX: Aligning the thruster (observer) with an intended thrusting
     * direction (target)
     *
     * @param customTarget Vector3D version of a custom target vector (assumed
     *                     to be in the frame the spacecraft's orientation is
     *                     relative to)
     */

    public CustomPrimaryTarget(Vector3D customTarget){
        this.customTarget = customTarget;
    }

    @Override
    public Vector3D getPointing(Time et) {
        // Return the unit vector of the target direction
        return customTarget.normalize();
    }

    public Vector3D getPosition(Time et){
        return customTarget;
    }

    public Vector3D getVelocity(Time et){
        return new Vector3D(0.0, 0.0, 0.0);
    }

    @Override
    public String getName() {
        return "CustomPrimaryTarget," + customTarget.toString();
    }
}
