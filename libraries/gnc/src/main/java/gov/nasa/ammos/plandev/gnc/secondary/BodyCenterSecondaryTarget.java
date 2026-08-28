package gov.nasa.ammos.plandev.gnc.secondary;

import gov.nasa.ammos.plandev.gnc.interfaces.Target;
import gov.nasa.jpl.time.Time;
import org.apache.commons.math3.geometry.euclidean.threed.Rotation;
import org.apache.commons.math3.geometry.euclidean.threed.RotationConvention;
import org.apache.commons.math3.geometry.euclidean.threed.Vector3D;

import java.util.Objects;

import static gov.nasa.ammos.plandev.gnc.functions.AttitudeFunctions.getState;

public class BodyCenterSecondaryTarget implements Target {
    private final String bodyName;
    private final String obsBody;
    private final String relativeFrame;
    private final Target primaryTarget;
    private final double offset;

    /**
     * ***********************POINTS AT SPICE DEFINED BODY***********************
     * ************************(OR AS CLOSE AS POSSIBLE)*************************
     *
     * The BodyCenterSecondaryTarget takes in the target body's name, observing
     * body's name, the frame the spacecraft's orientation is relative to,
     * and the rotation axis that the secondary rotation occurs about. This
     * should be used when the primary constraint is already satisfied and
     * the desired secondary target is a vector rather than a plane. The
     * output is the unit Vector3D that defines the plane normal to the
     * rotation axis and the secondary target. The ultimate goal in
     * targeting a vector instead of a plane for secondary targeting is to
     * get the projection of the target and observer on the plane of
     * rotation. This is done in two steps the first of which is done in
     * getPointing() and the second of which is done directly after the call
     * to getPointing. This is to be used strictly as a secondary target.
     *
     * EX: Primary pointing having an antenna pointed at the Earth and
     * getting the instrument (observer) to point at or as close as
     * possible at another body
     *
     * @param bodyName SPICE defined string of the target body
     *
     * @param obsBody SPICE defined string of the observing body
     *
     * @param relativeFrame SPICE defined string of the frame that
     *                      the observing body's orientation is being
     *                      defined relative to
     *
     * @param primaryTarget The effective secondary rotation axis
     *
     * @param offset Angle in degrees that the nominal solution is rotated by about the
     *               primary rotation axis (counter-clockwise is positive when
     *               the primary rotation axis is pointed towards the viewer)
     */

    public BodyCenterSecondaryTarget(String bodyName, String obsBody, String relativeFrame, Target primaryTarget, double offset){
        this.bodyName = bodyName;
        this.obsBody = obsBody;
        this.relativeFrame = relativeFrame;
        this.primaryTarget = primaryTarget;
        this.offset = offset;
    }

    /**
     * Constructor with no 'offset' input assumes offset angle is 0
     */
    public BodyCenterSecondaryTarget(String bodyName, String obsBody, String relativeFrame, Target primaryTarget) {
        this(bodyName, obsBody, relativeFrame, primaryTarget, 0);
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
        double[] state = getState(bodyName, et, relativeFrame, "LT+S", obsBody);
        return new Vector3D(state[0], state[1], state[2]);
    }

    public Vector3D getVelocity(Time et){
        double[] state = getState(bodyName, et, relativeFrame, "LT+S", obsBody);
        return new Vector3D(state[3], state[4], state[5]);
    }

    @Override
    public String getName(){
        return "BodyCenterSecondaryTarget," + bodyName + "," + offset;
    }
}
