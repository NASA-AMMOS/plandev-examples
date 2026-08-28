package gov.nasa.ammos.plandev.gnc.secondary;

import gov.nasa.ammos.plandev.gnc.interfaces.Target;
import gov.nasa.jpl.time.Time;
import org.apache.commons.math3.geometry.euclidean.threed.Rotation;
import org.apache.commons.math3.geometry.euclidean.threed.RotationConvention;
import org.apache.commons.math3.geometry.euclidean.threed.Vector3D;

import java.util.Objects;

public class CustomSecondaryTarget implements Target {
    private final Vector3D customTarget;
    private final Target primaryTarget;
    private final double offset;

    /**
     * ********************POINTS IN AN INERTIAL DIRECTION*********************
     * ***********************(OR AS CLOSE AS POSSIBLE)************************
     *
     * The CustomSecondaryTarget takes in the Vector3D version of a custom
     * vector, observing body's name, the frame the spacecraft's orientation
     * is relative to, and the rotation axis that the secondary rotation occurs
     * about. This should be used when the primary constraint is already
     * satisfied and the desired secondary target is a vector rather than a
     * plane. The output is the unit Vector3D that defines the plane normal to
     * the rotation axis and the secondary target. The ultimate goal in
     * targeting a vector instead of a plane for secondary targeting is to
     * get the projection of the target and observer on the plane of
     * rotation. This is done in two steps the first of which is done in
     * getPointing() and the second of which is done directly after the call
     * to getPointing. This is to be used strictly as a secondary target.
     *
     * EX: Primary pointing having an antenna pointed at the Earth and
     * getting the instrument (observer) to point in another direction (or as
     * close as possible)
     *
     * @param customTarget Vector3D version of a custom target vector (assumed
     *                     to be inertial)
     *
     * @param primaryTarget The effective secondary rotation axis
     *
     * @param offset Angle in degrees that the nominal solution is rotated by about the
     *               primary rotation axis (counter-clockwise is positive when
     *               the primary rotation axis is pointed towards the viewer)
     */

    public CustomSecondaryTarget(Vector3D customTarget, Target primaryTarget, double offset){
        this.customTarget = customTarget;
        this.primaryTarget = primaryTarget;
        this.offset = offset;
    }

    /**
     * Constructor with no 'offset' input assumes offset angle is 0
     */
    public CustomSecondaryTarget(Vector3D customTarget, Target primaryTarget){
        this(customTarget, primaryTarget, 0.0);
    }

    @Override
    public Vector3D getPointing(Time et) {

        // Get the direction of the target relative to the observing body
        Vector3D secondaryTargetDirection = getPosition(et).normalize();

        // Rotate the previous vector by the offset angle about the
        // primary target
        Rotation offsetRotation = new Rotation(primaryTarget.getPointing(et), Math.toRadians(offset), RotationConvention.VECTOR_OPERATOR);

        // Return the vector normal to the plane that contains the
        // target and the axis of rotation. Taking the cross product of
        // this returned vector with the rotation axis would then give the
        // target projected on the plane of rotation. The projected observer
        // can then be rotated to align with the projected target.
        return offsetRotation.applyTo(Vector3D.crossProduct(primaryTarget.getPointing(et), Objects.requireNonNull(secondaryTargetDirection)));

    }

    public Vector3D getPosition(Time et){
        return customTarget;
    }

    public Vector3D getVelocity(Time et){
        return new Vector3D(0.0, 0.0, 0.0);
    }

    @Override
    public String getName(){
        return "CustomSecondaryTarget," + customTarget.toString() + "," + offset;
    }
}
