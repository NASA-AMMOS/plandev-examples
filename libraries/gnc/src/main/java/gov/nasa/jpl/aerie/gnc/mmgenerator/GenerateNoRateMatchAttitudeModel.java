package gov.nasa.jpl.aerie.gnc.mmgenerator;

import gov.nasa.jpl.aerie.gnc.functions.AttitudeNotAvailableException;
import gov.nasa.jpl.aerie.gnc.interfaces.Observer;
import gov.nasa.jpl.aerie.gnc.interfaces.Orientation;
import gov.nasa.jpl.aerie.gnc.interfaces.Target;
import org.apache.commons.math3.geometry.euclidean.threed.Rotation;
import org.apache.commons.math3.geometry.euclidean.threed.RotationConvention;
import gov.nasa.jpl.time.Duration;
import gov.nasa.jpl.time.Time;
import org.apache.commons.math3.geometry.euclidean.threed.Vector3D;

import java.util.SortedMap;
import java.util.TreeMap;


public class GenerateNoRateMatchAttitudeModel extends GenerateAttitudeModel{
    private final Duration sampleRateForTurns;

    /**
     * GenerateNoRateMatchAttitudeModel contains the getOrientations method and
     * the methods that support this method. This allows for an attitude
     * profile to be generated that does not initially match the rates of the
     * initial and final frames. This means that there will be a rate
     * discontinuity at the end of the turn which will not accurately depict
     * the physical characteristics of a slew.
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
     */

    public GenerateNoRateMatchAttitudeModel(Vector3D angularVelocityLimit, Vector3D angularAccelerationLimit, Duration stepSize, Duration sampleRateForTurns){
        super(angularVelocityLimit, angularAccelerationLimit, stepSize);
        this.sampleRateForTurns = sampleRateForTurns;
    }

    /**
     * getOrientations returns a time ordered map of orientations that describe
     * a slew from an initial orientation to an orientation that fulfills
     * another set of primary and secondary constraints at the end of the slew.
     * This method does not do a rate matching step. Returns attitudes until
     * override duration is over, no matter when large slew finished
     */

    @Override
    public SortedMap<Time, Orientation> getOrientations(Time turnStart, Orientation fromOrientation, Observer primaryObserver, Target primaryTarget, Observer secondaryObserver, Target secondaryTarget, Duration override) throws AttitudeNotAvailableException {

        Rotation spacecraftToRelativeTurnStart = fromOrientation.getRotation();

        // Find the end time of the turn
        Duration interval = new Duration("00:00:01");
        double[] times = new double[0];
        Vector3D angularAcceleration = null;

        for (Duration offset = new Duration("00:00:00"); offset.lessThanOrEqualTo(override); offset = offset.add(interval)) {

            // Get the spacecraft orientation at the end of the turn
            Rotation spacecraftToRelativeTurnEnd = getOrientation(turnStart.add(offset), primaryObserver, primaryTarget, secondaryObserver, secondaryTarget).getRotation();

            // Get axis and angle from the rotation defining the
            // orientation at the end of the turn relative to the
            // beginning of the turn
            Rotation spacecraftTurnStartToTurnEnd = spacecraftToRelativeTurnStart.applyTo(spacecraftToRelativeTurnEnd.applyInverseTo(Rotation.IDENTITY));

            double turnAngle = spacecraftTurnStartToTurnEnd.getAngle();
            Vector3D turnAxis = spacecraftTurnStartToTurnEnd.getAxis(RotationConvention.FRAME_TRANSFORM);

            // Find the rate vectors based off spacecraft limits
            Vector3D angularVelocity = findConstantRateVector(turnAxis, angularVelocityLimit);
            angularAcceleration = findConstantRateVector(turnAxis, angularAccelerationLimit);

            // Find the durations associated with the turn
            // (times contains {burnTime, coastTime, totalTurnTime})
            times = findTurnTimes(turnAngle, angularVelocity.getNorm(), angularAcceleration.getNorm());
            if (times[2] <= offset.totalSeconds()) {
                break;
            }
        }
        // If the time it takes to complete a turn is more than the
        // alotted turn length then throw exception
        if (times[2] > override.totalSeconds()){
            throw new AttitudeNotAvailableException("Allocated time " + override.toString(6) +
                    " is smaller than time it will take to complete turn with allowed rates and accelerations: " + Duration.fromSeconds(times[2]).toString(6) + " . " +
                    "This behavior is undefined because the target attitude may be moving after the end of the allocation, which would not be accounted for in the turn. " +
                    "To fix, either increase the turn allocation duration or increase the allowed angular rates and accelerations.");
        }

        // Determine the orientations during spin up,
        // coast, and spin down and return

        // This is organized as spin up (burn), coast, spin down (burn)
        // (uses kinematics to find angle based off of current angular
        // acceleration and velocity at that time step)
        double burnTime = times[0];
        double coastTime = times[1];
        double currentTime = 0;
        double theta;

        // Calculate each phase's time step
        double burnTimeStep = (int) (burnTime/sampleRateForTurns.totalSeconds());
        double remainder1 = burnTime%sampleRateForTurns.totalSeconds()+coastTime%sampleRateForTurns.totalSeconds();
        double remainder2 = burnTime%sampleRateForTurns.totalSeconds()*2+coastTime%sampleRateForTurns.totalSeconds();
        double coastTimeStep = 0;
        if ( coastTime > 0.0 ) {
            coastTimeStep = (int) (coastTime/sampleRateForTurns.totalSeconds());
        }
        int extraCoastStep = (int) (remainder1/sampleRateForTurns.totalSeconds());
        int extraBurnStep = (int) ((remainder2-(extraCoastStep*sampleRateForTurns.totalSeconds()))/sampleRateForTurns.totalSeconds());

        // Initialize and set first value of map
        SortedMap<Time, Orientation> orientations = new TreeMap<>();
        orientations.put(turnStart, new Orientation(spacecraftToRelativeTurnStart, null));

        // Spin up orientations
        for ( int i=1; i<=burnTimeStep; i++ ) {
            currentTime = sampleRateForTurns.totalSeconds() * (double) (i);
            theta = 0.5 * angularAcceleration.getNorm() *  currentTime*currentTime ;
            orientations.put(turnStart.add(Duration.fromSeconds(currentTime)), new Orientation(new Rotation(angularAcceleration.normalize(), theta, RotationConvention.VECTOR_OPERATOR).applyTo(spacecraftToRelativeTurnStart)));
        }
        double theta_a = 0.5 * angularAcceleration.getNorm() *  burnTime*burnTime;
        double currentBurnTime = currentTime;

        // Coast orientations (if a coast exists)
        if ( coastTime > 0.0 ) {
            for ( int i=1; i<=coastTimeStep+extraCoastStep; i++ ) {
                currentTime = currentBurnTime + sampleRateForTurns.totalSeconds() * (double) (i);
                theta = theta_a + (angularAcceleration.getNorm()*burnTime)*(currentTime- burnTime);
                orientations.put(turnStart.add(Duration.fromSeconds(currentTime)), new Orientation(new Rotation(angularAcceleration.normalize(), theta, RotationConvention.VECTOR_OPERATOR).applyTo(spacecraftToRelativeTurnStart)));
            }
        }
        double theta_b = theta_a+(angularAcceleration.getNorm()*burnTime)*(coastTime);
        currentBurnTime = currentTime;

        // Spin down orientations
        for ( int i=1; i<=burnTimeStep+extraBurnStep; i++ ) {
            currentTime = currentBurnTime + sampleRateForTurns.totalSeconds() * (double) (i);
            double omega = angularAcceleration.getNorm()*burnTime - 0.5*angularAcceleration.getNorm()*(currentTime-(burnTime + coastTime));
            theta = theta_b + (currentTime-(burnTime + coastTime))*omega;
            orientations.put(turnStart.add(Duration.fromSeconds(currentTime)), new Orientation(new Rotation(angularAcceleration.normalize(), theta, RotationConvention.VECTOR_OPERATOR).applyTo(spacecraftToRelativeTurnStart)));
        }

        // Turn is complete, now track for the remaining time
        while(currentTime < override.totalSeconds()) {
            orientations.put(turnStart.add(Duration.fromSeconds(currentTime)).add(sampleRateForTurns), getOrientation(turnStart.add(Duration.fromSeconds(currentTime)).add(sampleRateForTurns), primaryObserver, primaryTarget, secondaryObserver, secondaryTarget));
            currentTime += sampleRateForTurns.totalSeconds();
        }

        return makeQuaternionScalarComponentPositive(orientations);
    }


    // *************** getOrientations Supporting Methods ***************

    /**
     * findConstantRateVector projects the body frame rate limit onto the turn
     * axis such that the the rate magnitude about the turn axis does not
     * violate the limit.
     *
     * @param turnAxis Vector of the turn axis
     *
     * @param limit Vector of the rate limit
     *
     */

    public Vector3D findConstantRateVector(Vector3D turnAxis, Vector3D limit){

        double x = (turnAxis.getX()*turnAxis.getX()) / (limit.getX()*limit.getX());
        double y = (turnAxis.getY()*turnAxis.getY()) / (limit.getY()*limit.getY());
        double z = (turnAxis.getZ()*turnAxis.getZ()) / (limit.getZ()*limit.getZ());

        Vector3D f = new Vector3D(x,y,z);

        double sum = Math.sqrt(f.getX() + f.getY() + f.getZ());

        double sumInv = 1.0 / sum;

        return turnAxis.scalarMultiply(sumInv);
    }

    /**
     * findTurnTimes uses the allowable angular velocity and acceleration and
     * the turn angle to determine the ramp up, coast, and ramp down durations.
     * These values are then returned as an array
     *
     * @param turnAngle Angle of rotation needed to complete the specified slew
     *
     * @param angularVelocityNorm Magnitude of angular velocity allowed about
     *                            the rotation axis
     *
     * @param angularAccelerationNorm Magnitude of angular acceleration allowed
     *                                about the rotation axis
     *
     */

    public double[] findTurnTimes(double turnAngle, double angularVelocityNorm, double angularAccelerationNorm){

        // Calculate the burn time and angle based off
        // of angular acceleration and velocity
        double burnTime = angularVelocityNorm/angularAccelerationNorm;
        double burnAngle = 0.5 * angularAccelerationNorm * (burnTime)*(burnTime);

        // Calculate coast time and therefore total time
        double coastTime = 0.0;
        double totalTurnTime;

        // No coast
        if (burnAngle >= (0.5*turnAngle)){
            burnTime = Math.sqrt(turnAngle/angularAccelerationNorm);
            totalTurnTime = 2.0*(burnTime);
            // Yes coast
        } else{
            double ang_coast = turnAngle - 2.0*burnAngle;
            coastTime = ang_coast / angularVelocityNorm;
            totalTurnTime = 2.0*(burnTime) + coastTime;
        }

        // Returns time in seconds if angularVelocity/angularAcceleration are in seconds
        return new double[] {burnTime, coastTime, totalTurnTime};
    }

}
