package gov.nasa.ammos.plandev.gnc.primary;

import gov.nasa.ammos.plandev.gnc.interfaces.Target;
import gov.nasa.jpl.time.Time;
import org.apache.commons.math3.geometry.euclidean.threed.Rotation;
import org.apache.commons.math3.geometry.euclidean.threed.Vector3D;
import spice.basic.CSPICE;
import spice.basic.SpiceErrorException;

import static gov.nasa.ammos.plandev.gnc.functions.AttitudeFunctions.getState;

public class AheadCrossNadirPrimaryTarget implements Target {
    private final String centerBody;
    private final String obsBody;
    private final String relativeFrame;
    private final double aheadOffsetAngle;
    private final double crossOffsetAngle;

    /**
     * ************POINTS OFFSET FROM THE SPICE DEFINED CENTER BODY************
     *
     * The AheadCrossNadirPrimaryTarget takes in the body the observer is orbiting,
     * the observing body, the frame that the spacecraft's orientation is
     * relative to, and the two offset angles. This should be used when you
     * don't want to point directly downwards at a body's center. The output
     * is the unit Vector3D that implements the offset angles and is
     * represented in the relative frame. This is to be used strictly as a
     * primary target.
     *
     * EX: An off nadir target would be targeted by an instrument observer
     * getting a variation in surface mapping
     *
     * @param centerBody SPICE defined string of the body that is being
     *                   orbited by the observing body
     *
     * @param obsBody SPICE defined string of the observing body
     *
     * @param relativeFrame SPICE defined string of the frame that the
     *                      spacecraft's orientation is being defined
     *                      relative to
     *
     * @param aheadOffsetAngle Angle in degrees that is associated with an
     *                         azimuth angle (rotation about z-axis)
     *                         representation of off nadir pointing with
     *                         x-axis pointing nadir, y-axis pointing in
     *                         the along track direction, and z-axis
     *                         pointing normal.
     *
     * @param crossOffsetAngle  Angle in degrees that is associated with an
     *                          elevation angle (rotation about x-axis)
     *                          representation of off nadir pointing with
     *                          x-axis pointing nadir, y-axis pointing in
     *                          the along track direction, and z-axis
     *                          pointing normal.
     */


    public AheadCrossNadirPrimaryTarget(String centerBody, String obsBody, String relativeFrame, double aheadOffsetAngle, double crossOffsetAngle){
        this.centerBody = centerBody;
        this.obsBody = obsBody;
        this.relativeFrame = relativeFrame;
        this.aheadOffsetAngle = aheadOffsetAngle;
        this.crossOffsetAngle = crossOffsetAngle;

    }

    @Override
    public Vector3D getPointing(Time et) {

        // Offset angles can be thought of as azimuth and elevation and we
        // want to convert these to rectangular coordinates in ACN frame
        // ((0,0) angles corresponds with x-axis in rectangular,
        //  (90,0) angles corresponds with y-axis in rectangular,
        //  (0, 90) angles corresponds with z axis in rectangular)
        double xACN = Math.cos(Math.toRadians(crossOffsetAngle))*Math.cos(Math.toRadians(aheadOffsetAngle));
        double yACN = Math.cos(Math.toRadians(crossOffsetAngle))*Math.sin(Math.toRadians(aheadOffsetAngle));
        double zACN = Math.sin(Math.toRadians(crossOffsetAngle));

        // Convert from ACN frame to LVLH (just a switch of the order)
        @SuppressWarnings("SuspiciousNameCombination") Vector3D offsetTargetLVLH = new Vector3D(yACN, zACN, xACN);

        // We need to convert from LVLH to our relative frame so the
        // representation of these axes is needed in the relative frame
        // and this uses the observing body's position and velocity
        // relative to the body it is orbiting
        double[] state = new double[6];
        try {
            CSPICE.spkezr(obsBody, et.toET(), relativeFrame, "LT+S", centerBody, state, new double[1]);
        } catch (SpiceErrorException e) {
            e.printStackTrace();
        }
        Vector3D nadir = new Vector3D(state[0],state[1],state[2]).normalize().scalarMultiply(-1);
        Vector3D oppositeOrbitMomentum = new Vector3D(state[0], state[1], state[2]).crossProduct(new Vector3D(state[3], state[4], state[5])).normalize().scalarMultiply(-1);
        double[] yLVLHAxisInRelativeFrame = oppositeOrbitMomentum.toArray();
        double[] zLVLHAxisInRelativeFrame = nadir.toArray();
        double[] xLVLHAxisInRelativeFrame = Vector3D.crossProduct(oppositeOrbitMomentum,nadir).toArray();

        // Create rotation matrix from LVLH to relative frame using basis
        // vectors
        double[][] lvlhToRelative = {xLVLHAxisInRelativeFrame, yLVLHAxisInRelativeFrame, zLVLHAxisInRelativeFrame};

        // Return the unit vector of the primary target (taking into
        // account offsets) represented in the relative frame
        return new Rotation(lvlhToRelative,0.1).applyInverseTo(offsetTargetLVLH).normalize();

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
    public String getName() {
        return "AheadCrossNadirPrimaryTarget," + centerBody + "," + aheadOffsetAngle + "," + crossOffsetAngle;
    }
}
