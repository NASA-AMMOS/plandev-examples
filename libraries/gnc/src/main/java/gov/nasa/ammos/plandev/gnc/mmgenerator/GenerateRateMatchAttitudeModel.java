package gov.nasa.ammos.plandev.gnc.mmgenerator;

import gov.nasa.ammos.plandev.gnc.functions.AttitudeNotAvailableException;
import gov.nasa.ammos.plandev.gnc.interfaces.Observer;
import gov.nasa.ammos.plandev.gnc.interfaces.Orientation;
import gov.nasa.ammos.plandev.gnc.interfaces.Target;
import gov.nasa.jpl.time.Duration;
import gov.nasa.jpl.time.Time;
import org.apache.commons.math3.geometry.euclidean.threed.Rotation;
import org.apache.commons.math3.geometry.euclidean.threed.RotationConvention;
import org.apache.commons.math3.geometry.euclidean.threed.Vector3D;

import java.util.SortedMap;
import java.util.TreeMap;


public class GenerateRateMatchAttitudeModel extends GenerateAttitudeModel {
    private final Duration sampleRateForTurns;
    private final boolean throwExceptionIfTurnLongerThanOverride;
    private final boolean truncateMapWhenTurnPhaseFinishes;

    /**
     * GenerateRateMatchAttitudeModel contains the getOrientations method. This
     * method allows for an attitude profile to be generated that does the
     * initial rate match step for the initial and final frames. This means
     * that there will be no rate discontinuity at the end of the turn.
     *
     * @param angularVelocityLimit Maximum allowable angular velocity vector
     *                             represented in the body frame
     *
     * @param angularAccelerationLimit Maximum allowable angular acceleration
     *                                 vector represented in the body frame
     *
     * @param stepSize The duration used for forward finite differencing to
     *                 obtain the approximation of the frame rotation rate at
     *                 the given time
     *
     * @param sampleRateForTurns The duration between each orientation that is
     *                           included in the returned map
     *
     * @param throwExceptionIfTurnLongerThanOverride If true, throw an exception if turn phase is calculated
     *                                               to go longer than start + override parameter in getOrientations
     *
     * @param truncateMapWhenTurnPhaseFinishes If true, the map returned from getOrientations will only include
     *                                         attitudes during the turn phase, not the track phase. If false, attitudes
     *                                         will be included in the return map between the end of the turn and
     *                                         start + override, which will be tracking the destination targets
     */

    public GenerateRateMatchAttitudeModel(Vector3D angularVelocityLimit, Vector3D angularAccelerationLimit, Duration stepSize, Duration sampleRateForTurns, boolean throwExceptionIfTurnLongerThanOverride, boolean truncateMapWhenTurnPhaseFinishes){
        super(angularVelocityLimit, angularAccelerationLimit, stepSize);
        this.sampleRateForTurns = sampleRateForTurns;
        this.throwExceptionIfTurnLongerThanOverride = throwExceptionIfTurnLongerThanOverride;
        this.truncateMapWhenTurnPhaseFinishes = truncateMapWhenTurnPhaseFinishes;
    }

    /**
     * Calls other constructor, but passes true to throwExceptionIfTurnLongerThanOverride and false to truncateMapWhenTurnPhaseFinishes
     * @param angularVelocityLimit
     * @param angularAccelerationLimit
     * @param stepSize
     * @param sampleRateForTurns
     */
    public GenerateRateMatchAttitudeModel(Vector3D angularVelocityLimit, Vector3D angularAccelerationLimit, Duration stepSize, Duration sampleRateForTurns){
        this(angularVelocityLimit, angularAccelerationLimit, stepSize, sampleRateForTurns, true, false);
    }


    /**
     * getOrientations returns a time ordered map of orientations that describe
     * a slew from an initial orientation to an orientation that fulfills
     * another set of primary and secondary constraints at the end of the slew.
     *
     * This method includes the initial step of matching the initial and final
     * frame's rates. Important! This step assumes constant rates! Also the
     * limit for angular velocity is assumed to be the same across all three
     * spacecraft axes!
     */
    public SortedMap<Time, Orientation> getOrientations(Time turnStart, Orientation fromOrientation, Observer primaryObserver, Target primaryTarget, Observer secondaryObserver, Target secondaryTarget, Duration override) throws AttitudeNotAvailableException {

        // ****** Currently assumes both to and from frames are rotating at a constant rate*********
        // (This is an okay assumption because the difference in rates are very small, with a rate
        // matching step that takes less than 10 sec at the specified allowable body rates)

        // Notation: rotation CX_Y = qYX = rotationYToX
        //           A is the frame the turn is coming from (can be at anytime though)
        //           B is the frame the turn is going to (can be at anytime though)
        //           Beg(Beginning)/Curr(Current) denotes the time that the rotation refers to
        //           Start is synonymous with from frame and target is synonymous with to frame

        if(!fromOrientation.isRotationRateDefined()){
            throw new AttitudeNotAvailableException("In order to use the rate matching attitude generating model, a fromOrientation with angular velocities defined must be provided");
        }

        // Get the rotations and rotation rates of from (A) and to (B) frames at the initial time
        Rotation rotationABegToRel = fromOrientation.getRotation();
        Vector3D rotationRateABegToRel = fromOrientation.getRotationRate();

        Duration dt = new Duration("00:00:01");
        Rotation rotationBBegToRel = getOrientation(turnStart, primaryObserver, primaryTarget, secondaryObserver, secondaryTarget).getRotation();
        Rotation rotationBBegPertToRel = getOrientation(turnStart.add(dt), primaryObserver, primaryTarget, secondaryObserver, secondaryTarget).getRotation();
        Rotation rotationBBegToBBegPert = (rotationBBegToRel.revert().applyTo(rotationBBegPertToRel)).revert();
        Vector3D rotationRateBBegToRel = rotationBBegPertToRel.applyTo(rotationBBegToBBegPert.getAxis(RotationConvention.FRAME_TRANSFORM)).scalarMultiply(rotationBBegToBBegPert.getAngle()/dt.totalSeconds());

        // Determine the ratematch rotation and associated axis and angle
        Rotation rotationBToABeg = rotationABegToRel.revert().applyTo(rotationBBegToRel);
        Vector3D rotationRateABegToBBeg = rotationRateABegToRel.subtract(rotationBToABeg.applyTo(rotationRateBBegToRel));

        // Protect against a dividing by a zero norm
        Vector3D turnAxisRateMatch;
        if (rotationRateABegToBBeg.getNorm() != 0) {
            turnAxisRateMatch = rotationRateABegToBBeg.normalize();
        } else {
            turnAxisRateMatch = new Vector3D(1.0, 0.0, 0.0);
        }

        // Use kinematics and the allowable spacecraft rates to determine the rotation from the end of rate matching to
        // the target frame
        double accelerationRateMatch = new Vector3D(turnAxisRateMatch.getX() * angularAccelerationLimit.getX(), turnAxisRateMatch.getY() * angularAccelerationLimit.getY(), turnAxisRateMatch.getZ() * angularAccelerationLimit.getZ()).getNorm();
        double durationRateMatch = rotationRateABegToBBeg.getNorm() / accelerationRateMatch;
        double angleRateMatch = 0.5 * accelerationRateMatch * durationRateMatch * durationRateMatch;
        Rotation rotationABegToARateMatch = new Rotation(turnAxisRateMatch, angleRateMatch, RotationConvention.FRAME_TRANSFORM);
        Rotation rotationARateMatchToB = (rotationABegToARateMatch.applyTo(rotationBToABeg)).revert();

        // Determine the axis and angle from the previous rotation and protect against zero norm again
        double thetaWholeTurn = rotationARateMatchToB.getAngle();
        Vector3D turnAxis;
        if (thetaWholeTurn != 0) {
            turnAxis = rotationARateMatchToB.getAxis(RotationConvention.FRAME_TRANSFORM);
        } else {
            turnAxis = new Vector3D(1.0, 0.0, 0.0);
        }

        // Based off the turn axis and the allowable spaceccraft rates determine the acceleration of the turn after
        // ratematching is finished
        double acceleration = new Vector3D(turnAxis.getX() * angularAccelerationLimit.getX(), turnAxis.getY() * angularAccelerationLimit.getY(), turnAxis.getZ() * angularAccelerationLimit.getZ()).getNorm();

        // Use kinematics, the turn angle, and acceleration to determine the times for the acceleration, coast, and
        // deceleration phases (if condition for the case where there is no coast phase)
        double timeCoastBeg;
        double timeDecelBeg;
        double timeEnd;

        // Assumes that each axis has the same limit for angular velocity
        double angularVelocityLimitMag = angularVelocityLimit.getX();
        if (Math.sqrt(thetaWholeTurn / acceleration) < angularVelocityLimitMag / acceleration) {
            timeCoastBeg = durationRateMatch + Math.sqrt(thetaWholeTurn / acceleration);
            timeDecelBeg = timeCoastBeg;
            timeEnd = timeDecelBeg + Math.sqrt(thetaWholeTurn / acceleration);
        } else {
            timeCoastBeg = durationRateMatch + angularVelocityLimitMag / acceleration;
            timeDecelBeg = timeCoastBeg + (thetaWholeTurn - acceleration * (angularVelocityLimitMag / acceleration) * (angularVelocityLimitMag / acceleration)) / angularVelocityLimitMag;
            timeEnd = timeDecelBeg + angularVelocityLimitMag / acceleration;
        }

        if(throwExceptionIfTurnLongerThanOverride && timeEnd > override.totalSeconds()){
            throw new AttitudeNotAvailableException("Turn starting at " + turnStart.toString() + " with destination (" +
                    primaryObserver.getName() + " to " + primaryTarget.getName() + " and " + secondaryObserver.getName() +
                    " to " + secondaryTarget.getName() + ") is estimated to take " + timeEnd +
                    " seconds, longer than the allocated " + override.totalSeconds() + " seconds");
        }

        // Loop through each interval of time using the above information to calculate the spacecraft attitude
        SortedMap<Time, Orientation> orientations = new TreeMap<>();
        for(int t = 0; t <= override.totalSeconds(); t = (int)(t+sampleRateForTurns.totalSeconds())) {

            Rotation rotationBCurrToRel = getOrientation(turnStart.add(Duration.fromSeconds(t)), primaryObserver, primaryTarget, secondaryObserver, secondaryTarget).getRotation();

            Rotation rotationSCToRel;
            double angleBetweenTurnEndAndCoastEnd = 0.5 * acceleration * (timeEnd - timeDecelBeg) * (timeEnd - timeDecelBeg);
            // Ratematch Phase
            if(t < durationRateMatch){
                double theta = 0.5 * accelerationRateMatch * (durationRateMatch * durationRateMatch - (t - durationRateMatch) * (t - durationRateMatch));
                Rotation rotationABegToSC = new Rotation(turnAxisRateMatch, theta, RotationConvention.FRAME_TRANSFORM);
                Rotation rotationBCurrToSC = rotationABegToSC.applyTo(rotationBToABeg).applyTo(rotationBBegToRel.revert()).applyTo(rotationBCurrToRel);
                rotationSCToRel = rotationBCurrToRel.applyTo(rotationBCurrToSC.revert());
            // Acceleration Phase
            }else if(t >= durationRateMatch && t < timeCoastBeg){
                double theta =  angleBetweenTurnEndAndCoastEnd + angularVelocityLimitMag * (timeDecelBeg-timeCoastBeg) + 0.5 * acceleration * (((timeCoastBeg - durationRateMatch) * (timeCoastBeg - durationRateMatch)) - ((t - durationRateMatch) * (t - durationRateMatch)));
                Rotation rotationBCurrToSC = new Rotation(turnAxis, theta, RotationConvention.FRAME_TRANSFORM).revert();
                rotationSCToRel = rotationBCurrToRel.applyTo(rotationBCurrToSC.revert());
            // Coast Phase
            }else if(t >= timeCoastBeg && t < timeDecelBeg){
                double theta = angleBetweenTurnEndAndCoastEnd + angularVelocityLimitMag * (timeDecelBeg - t);
                Rotation rotationBCurrToSC = new Rotation(turnAxis, theta, RotationConvention.FRAME_TRANSFORM).revert();
                rotationSCToRel = rotationBCurrToRel.applyTo(rotationBCurrToSC.revert());
            // Deceleration Phase
            }else if(t >= timeDecelBeg && t < timeEnd){
                double theta = 0.5 * acceleration * (timeEnd - t) * (timeEnd - t);
                Rotation rotationBCurrToSC = new Rotation(turnAxis, theta, RotationConvention.FRAME_TRANSFORM).revert();
                rotationSCToRel = rotationBCurrToRel.applyTo(rotationBCurrToSC.revert());
            // Track Phase: depending on truncateMapWhenTurnPhaseFinishes, either return just the turn or continue adding tracking until override
            }else{
                if(truncateMapWhenTurnPhaseFinishes) {
                    orientations.put(turnStart.add(Duration.fromSeconds(t)), new Orientation(rotationBCurrToRel));
                    return makeQuaternionScalarComponentPositive(orientations);
                }
                else{
                    rotationSCToRel = rotationBCurrToRel;
                }
            }
            orientations.put(turnStart.add(Duration.fromSeconds(t)), new Orientation(rotationSCToRel));
        }

        return makeQuaternionScalarComponentPositive(orientations);
    }
}
