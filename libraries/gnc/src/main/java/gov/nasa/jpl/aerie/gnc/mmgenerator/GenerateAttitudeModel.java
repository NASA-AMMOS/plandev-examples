package gov.nasa.jpl.aerie.gnc.mmgenerator;

import gov.nasa.jpl.aerie.gnc.functions.AttitudeNotAvailableException;
import gov.nasa.jpl.aerie.gnc.interfaces.ADCModel;
import gov.nasa.jpl.aerie.gnc.interfaces.Observer;
import gov.nasa.jpl.aerie.gnc.interfaces.Orientation;
import gov.nasa.jpl.aerie.gnc.interfaces.Target;
import gov.nasa.jpl.time.Duration;
import gov.nasa.jpl.time.Time;
import org.apache.commons.math3.geometry.euclidean.threed.Rotation;
import org.apache.commons.math3.geometry.euclidean.threed.RotationConvention;
import org.apache.commons.math3.geometry.euclidean.threed.Vector3D;

import java.util.Map;
import java.util.Objects;
import java.util.SortedMap;


public abstract class GenerateAttitudeModel implements ADCModel{
    protected Vector3D angularVelocityLimit;
    protected Vector3D angularAccelerationLimit;
    protected Duration stepSize;

    /**
     * GenerateAttitudeModel contains the methods needed to generate attitude
     * based off of targets and observers. These methods are used by to
     * generate profiles that consider the initial rate matching step and that
     * do not consider this step. This consists of the getOrientation method
     * that returns an instantaneous orientation and methods that support
     * getOrientation.
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
     */

    public GenerateAttitudeModel(Vector3D angularVelocityLimit, Vector3D angularAccelerationLimit, Duration stepSize){
        this.angularVelocityLimit = angularVelocityLimit;
        this.angularAccelerationLimit = angularAccelerationLimit;
        this.stepSize = stepSize;
    }

    // both subclasses share the same instantaneous orientation method
    @Override
    public Orientation getOrientation(Time et, Observer primaryObserver, Target primaryTarget, Observer secondaryObserver, Target secondaryTarget) {

        // Find the direction of the primary and secondary targets at the time given
        Vector3D primaryTargetDirection = primaryTarget.getPointing(et);
        Vector3D secondaryTargetDirection = secondaryTarget.getPointing(et);

        Rotation totalRotation = getTotalRotation(primaryTargetDirection, secondaryTargetDirection, primaryObserver, secondaryObserver);

        // Find a rough angular velocity of the total rotation by doing a forward finite differencing
        primaryTargetDirection = primaryTarget.getPointing(et.add(stepSize));
        secondaryTargetDirection = secondaryTarget.getPointing(et.add(stepSize));

        Rotation totalRotationPerturbed = getTotalRotation(primaryTargetDirection, secondaryTargetDirection, primaryObserver, secondaryObserver);
        Rotation dRotation = (totalRotation.revert().applyTo(totalRotationPerturbed)).revert();
        Vector3D rotationRate = totalRotationPerturbed.applyTo(dRotation.getAxis(RotationConvention.FRAME_TRANSFORM)).scalarMultiply(dRotation.getAngle()/stepSize.totalSeconds());

        return new Orientation(totalRotation, rotationRate);

    }

    /**
     * getOrientations is specified based on whether the frame rate matching
     * step is included or it is ignored.
     */

    @Override
    public abstract SortedMap<Time, Orientation> getOrientations(Time turnStart, Orientation fromOrientation, Observer primaryObserver, Target primaryTarget, Observer secondaryObserver, Target secondaryTarget, Duration override) throws AttitudeNotAvailableException ;

    /**
     * setRatesandAccels allows the user to change the limits that are
     * allowable by the spacecraft structure even after the class is
     * already instantiated
     *
     * @param angularVelocityLimit Maximum allowable angular velocity vector
     *                             represented in the body frame
     *
     * @param angularAccelerationLimit Maximum allowable angular acceleration
     *                                 vector represented in the body frame
     */

    @Override
    public void setRateAndAccelLimits(Vector3D angularVelocityLimit, Vector3D angularAccelerationLimit){
        this.angularVelocityLimit = angularVelocityLimit;
        this.angularAccelerationLimit = angularAccelerationLimit;
    }

//     *************** getOrientation Supporting Methods ***************

    /**
     * getTotalRotation does most of the work to determine the attitude of the
     * spacecraft with respect to the relative frame. This work is put into a
     * method because it must all be done twicec to determine an estimate of
     * the instantaneous rotation rate at the given time
     *
     * @param primaryTargetDirection Unit Vector3D of the direction of the primary target
     *
     * @param secondaryTargetDirection Unit Vector3D of the direction of the secondary target
     *
     * @param primaryObserver Primary observer in the spacecraft-fixed frame
     *
     * @param secondaryObserver Secondary observer in the spacecraft-fixed frame
     */

    private Rotation getTotalRotation(Vector3D primaryTargetDirection, Vector3D secondaryTargetDirection, Observer primaryObserver, Observer secondaryObserver){

        // Find the first rotation that puts the primary observer on the primary target
        Rotation primaryRotation = getRotation(primaryObserver.getPointing(), primaryTargetDirection);

        if (secondaryObserver == null || secondaryObserver.equals(primaryObserver)) {
          if (primaryRotation.getQ0() < 0){
            primaryRotation = new Rotation(primaryRotation.getQ0()*-1, primaryRotation.getQ1()*-1,
              primaryRotation.getQ2()*-1, primaryRotation.getQ3()*-1, false);
          }
          return primaryRotation;
        }

        // To find the second rotation you must first get the secondary observer in
        // the spacecraft frame that has been rotated by the primary rotation
        Vector3D secondaryObserverIntermediateFrame =  primaryRotation.applyTo(secondaryObserver.getPointing());

        // Then you need to get the projection of the previous vector onto the plane
        // normal to the secondary rotation axis
        Vector3D normal = Vector3D.crossProduct(Objects.requireNonNull(secondaryObserverIntermediateFrame), primaryTargetDirection);
        Vector3D secondaryObserverProjected = Vector3D.crossProduct(primaryTargetDirection, normal).normalize();

        // Find the second rotation that puts the projected observer on the secondary target (the
        // secondary target is now the direction normal to the rotation axis and target direction
        // for plane targeting and for vector targeting it is now the target projected on the plane
        // normal to the rotation axis)
        Rotation secondaryRotation = getRotation(secondaryObserverProjected, secondaryTargetDirection.crossProduct(primaryTargetDirection).normalize());


        // ***************************** Needed For plane targeting *******************************
        // If the secondary rotation axis (primary target) is not in the plane normal to the
        // secondary observer (plane targeting) or is not normal to the secondary target  (vector
        // targeting) we must take the secondary observer in the intermediate frame and rotate it by
        // the secondary rotation to get it into the final frame
        Vector3D secondaryObserverGuess = secondaryRotation.applyTo(secondaryObserverIntermediateFrame);

        // Then we rotate the previous vector about the rotation axis until it is most normal
        // to the the secondary target direction for plane targeting (for directional
        // targeting the secondary rotation is already correct)
        Vector3D optimizedTarget = optimizeSecondaryTarget(secondaryObserverGuess, primaryTargetDirection, secondaryTargetDirection);

        // Get the previous vector's projection onto the plane normal to the rotation axis
        normal = Vector3D.crossProduct(Objects.requireNonNull(optimizedTarget), primaryTargetDirection);
        Vector3D optimizedTargetProjection = Vector3D.crossProduct(primaryTargetDirection, normal).normalize();

        // Find the  second rotation that puts the secondary observer on the optimized secondary target
        secondaryRotation = getRotation(secondaryObserverProjected, optimizedTargetProjection);
        // ****************************************************************************************


        // Combine primary and secondary rotations
        Rotation totalRotation = secondaryRotation.applyTo(primaryRotation);

        // Make sure the first term of the quaternion always is positive (convention)
        if (totalRotation.getQ0() < 0){
            totalRotation = new Rotation(totalRotation.getQ0()*-1, totalRotation.getQ1()*-1, totalRotation.getQ2()*-1, totalRotation.getQ3()*-1, false);
        }
        return totalRotation;
    }

    /**
     * getRotation uses an observer vector in the spacecraft frame and a target
     * vector in a relative frame and the rotation that aligns these vectors is
     * returned
     *
     * @param observerSpacecraftFrame The observer on the spacecraft that must be
     *                                aligned with the primary target
     *
     * @param targetRelativeFrame The target in the spacecraft's environment that
     *                            the primary observer must align with
     *
     */

    private Rotation getRotation(Vector3D observerSpacecraftFrame, Vector3D targetRelativeFrame){

        // Find angle between the observer vector and the target vector
        // then find the axis of rotation by taking the cross product of
        // these two vectors
        double angleOfSeparation = Vector3D.angle(observerSpacecraftFrame, targetRelativeFrame);
        Vector3D rotationAxis = Vector3D.crossProduct(observerSpacecraftFrame, targetRelativeFrame);
        Rotation rotation = new Rotation(rotationAxis, angleOfSeparation, RotationConvention.VECTOR_OPERATOR);

        // Angle will always output as positive but sometimes should be
        // negative so test to see which one is right
        return testRotationDirection(observerSpacecraftFrame, targetRelativeFrame, rotation);
    }

    /**
     * testRotationDirection determines if the rotation from getRotation is the
     * correct rotation. If the rotation is incorrect the angle of the rotation
     * is negated, otherwise the original rotation is returned.
     *
     * @param observer The observer on the spacecraft that must be aligned with
     *                the primary target
     *
     * @param target The target in the spacecraft's environment that the
     *               primary observer must align with
     *
     * @param rotation The rotation that aligns the observer and target vectors
     *
     */

    private Rotation testRotationDirection(Vector3D observer, Vector3D target, Rotation rotation){

        double tolerance = 10E-8;

        // Rotate the observer vector by the angle between the two vectors
        Vector3D testCorrectDirection = rotation.applyTo(observer);

        // See if the target lines up with the rotated observer vector and
        // if it doesn't make the angle of rotation negative
        if (target.subtract(testCorrectDirection).getNorm() >= tolerance) {
            rotation = new Rotation(rotation.getAxis(RotationConvention.VECTOR_OPERATOR), -rotation.getAngle(), RotationConvention.VECTOR_OPERATOR);
        }

        return rotation;

    }

    /**
     * optimizeSecondaryTarget is required when the primary and secondary
     * observer vectors in the spacecraft frame are not orthogonal to each
     * other. This method aligns the secondary observer and target as much
     * as possible while still adhering to the primary constraints.
     *
     * @param initialTargetGuess The target vector initial guess that is then
     *                           iterated upon to more closely align the
     *                           secondary target and observer
     *
     * @param rotationAxis The rotation axis the the initialTargetGuess is spun
     *                     about
     *
     * @param targetRelative The secondary target represented in the relative
     *                       frame
     *
     */

    public Vector3D optimizeSecondaryTarget(Vector3D initialTargetGuess, Vector3D rotationAxis, Vector3D targetRelative){

        // Spins the initial target guess about the rotation axis while
        // checking the angle between it and the actual target (Sun,
        // momentum vector). Returns the target vector when this angle
        // is closest to 90 degrees.
        Vector3D coarseTargetResult = iterateAboutRotationAxis(initialTargetGuess, rotationAxis, targetRelative, 1, 180, 1);
        return iterateAboutRotationAxis(coarseTargetResult, rotationAxis, targetRelative, 0.1, 1, 0.1);

    }

    /**
     * iterateAboutRotationAxis is the method that actually performs successive
     * rotations to determine the most optimal pointing based and the primary
     * and secondary constraints.
     *
     * @param targetGuess The target vector initial guess that is then
     *                           iterated upon to more closely align the
     *                           secondary target and observer
     *
     * @param rotationAxis The rotation axis the the initialTargetGuess is spun
     *                     about
     *
     * @param targetRelative The secondary target represented in the relative
     *                       frame
     *
     * @param start The starting fraction of a full rotation
     *
     * @param end The ending fraction of a full rotation
     *
     * @param stepSize The step size used to increment each successive rotation
     *
     */

    public Vector3D iterateAboutRotationAxis(Vector3D targetGuess, Vector3D rotationAxis, Vector3D targetRelative, double start, double end, double stepSize){
        // The goal here is to rotate the guess about the rotation
        // axis and look at the dot product between the new guess and
        // the true target direction and find the guess where the
        // dot product is smallest (target and guess are perpendicular)

        double minDotProduct = Math.abs(targetGuess.dotProduct(targetRelative));
        Vector3D optimizedTarget = targetGuess;

        // Start rotating increasing direction, if dot product increases stop
        // and then start rotating the opposite direction. The minimum for the
        // dotProduct is guaranteed to be in the direction in which it is
        // decreasing from the beginning
        for (double signOperator = 1; signOperator >= -1; signOperator = signOperator-2) {
            for (double i = start; i <= end; i = i + stepSize) {

                double rotatedAngle = signOperator * i * (Math.PI / 180);
                Vector3D newTargetGuess = new Rotation(rotationAxis, rotatedAngle, RotationConvention.VECTOR_OPERATOR).applyTo(targetGuess);
                double newDotProduct = Math.abs(newTargetGuess.dotProduct(targetRelative));

                if (i == start && newDotProduct > minDotProduct) {
                    break;
                }
                if (newDotProduct < minDotProduct) {
                    minDotProduct = newDotProduct;
                    optimizedTarget = newTargetGuess;
                } else {
                    return optimizedTarget;
                }
            }
        }

        return optimizedTarget;
    }

///     *************** getOrientations Supporting Method ***************

    /**
     * makeQuaternionScalarComponentPositive makes sure that the rotation for
     * each orientation abides by the convention of the scalar component of
     * the quaternion being positive
     *
     * @param orientations Map of orientations with their associated times
     *
     */

    public SortedMap<Time, Orientation> makeQuaternionScalarComponentPositive(SortedMap<Time, Orientation> orientations){
        // NOTE: For some reason the turn negates the entire quaternion
        // when the first element passes through zero. This is not
        // an issue because although the quaternions are different,
        // they represent the same rotation
        for (Map.Entry<Time, Orientation> entry : orientations.entrySet()) {
            if (entry.getValue().getRotation().getQ0() < 0){
                Rotation rotation = entry.getValue().getRotation();
                entry.setValue(new Orientation(new Rotation(rotation.getQ0()*-1, rotation.getQ1()*-1, rotation.getQ2()*-1, rotation.getQ3()*-1, false)));
            }
        }
         return orientations;
    }
}
