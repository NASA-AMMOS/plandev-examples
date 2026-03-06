package gov.nasa.jpl.aerie.gnc.secondary;

import gov.nasa.jpl.aerie.gnc.interfaces.Target;
import gov.nasa.jpl.time.Time;
import org.apache.commons.math3.geometry.euclidean.threed.Rotation;
import org.apache.commons.math3.geometry.euclidean.threed.RotationConvention;
import org.apache.commons.math3.geometry.euclidean.threed.Vector3D;

import static gov.nasa.jpl.aerie.gnc.functions.AttitudeFunctions.getState;

public class BodyPlaneSecondaryTarget implements Target {
    private final String bodyName;
    private final String obsBody;
    private final String relativeFrame;
    private final Target primaryTarget;
    private final double offset;
    private final boolean observersNormal;

    /**
     * ***********POINTS IN THE PLANE NORMAL TO A SPICE DEFINED BODY***********
     * ***********************(OR AS CLOSE AS POSSIBLE)************************
     *
     * The BodyPlaneSecondaryTarget takes in the target body's name,
     * observing body's name, and the frame the spacecraft's orientation is
     * relative to. This should be used when the target is a plane rather
     * than a vector. This plane must be defined by a vector that is normal
     * to the plane and points in the direction of a SPICE defined body. The
     * output is the unit Vector3D that is normal to the targeted plane in
     * the relative frame. This is to be used strictly as a secondary target.
     * (NOTE: This does the same thing as BodyCenterTarget but it is used to
     * define a target plane rather than a target vector)
     *
     * ----Offset secondary pointing only works if observersNormal is TRUE-----
     *
     * EX: The plane normal to the sun direction would be targeted by the
     * spacecraft y-axis for Power Steering.
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
     *
     * @param observersNormal Boolean that tells whether the primary and
     *                        secondary observer are normal to each other
     *
     */
    public BodyPlaneSecondaryTarget(String bodyName, String obsBody, String relativeFrame, Target primaryTarget, double offset, boolean observersNormal){
        this.bodyName = bodyName;
        this.obsBody = obsBody;
        this.relativeFrame = relativeFrame;
        this.primaryTarget = primaryTarget;
        this.offset = offset;
        this.observersNormal = observersNormal;
    }

    /**
     * Constructor without 'offset' and 'observersNormal' assumes a 0 offset, which mean we don't need to assume
     * anything about relative orientation of primary and secondary observers
     */
    public BodyPlaneSecondaryTarget(String bodyName, String obsBody, String relativeFrame, Target primaryTarget) {
        this(bodyName, obsBody, relativeFrame, primaryTarget, 0.0, false);
    }

    @Override
    public Vector3D getPointing(Time et) {

        if(observersNormal) {
            // Project the secondary target onto the plane normal to the
            // primary target
            Vector3D secTargetProjectedOnPrimaryPlane = Vector3D.crossProduct(Vector3D.crossProduct(primaryTarget.getPointing(et).normalize(), getPosition(et).normalize()).normalize(), primaryTarget.getPointing(et).normalize()).normalize();
            // Rotate the previous vector by the offset angle about the
            // primary target
            Rotation offsetRotation = new Rotation(primaryTarget.getPointing(et), Math.toRadians(offset), RotationConvention.FRAME_TRANSFORM);
            return offsetRotation.revert().applyTo(secTargetProjectedOnPrimaryPlane);
        }else{
            if(Math.abs(offset) < 1e-6) {
                return getPosition(et).normalize();
            }
            else {
                throw new RuntimeException("BodyPlaneSecondaryTarget can only be called with a non-zero offset if the primary and secondary observer are normal to each other");
            }
        }
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
        return "BodyPlaneSecondaryTarget," + bodyName + "," + offset;
    }
}
