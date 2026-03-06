package gov.nasa.jpl.aerie.gnc.interfaces;

import gov.nasa.jpl.aerie.gnc.functions.AttitudeNotAvailableException;
import gov.nasa.jpl.time.Duration;
import gov.nasa.jpl.time.Time;
import org.apache.commons.math3.geometry.euclidean.threed.Vector3D;

import java.util.SortedMap;

public interface ADCModel {

    /**
     * getOrientation uses primary and secondary pointing constraints in the
     * form of targets and observers at a given time to return the orientation
     * of the spacecraft with respect to the specified reference frame.
     *
     * @param et The time at which the orientation of the spacecraft is desired
     *
     * @param primaryObserver The observer on the spacecraft that must be
     *                        aligned with the primary target
     *
     * @param primaryTarget The target in the spacecraft's environment that
     *                      the primary observer must align with
     *
     * @param secondaryObserver The observer on the spacecraft that is
     *                          aligned with the secondary target while also
     *                          fulfilling the primary constraints
     *
     * @param secondaryTarget The target in the spacecraft's environment that
     *                       the secondary observer must align with while also
     *                        fulfilling the primary constraints
     *
     * @return An Orientation object that contains a Rotation and a rotation rate
     *                       of the spacecraft with respect to the reference frame
     */
    Orientation getOrientation(Time et, Observer primaryObserver, Target primaryTarget, Observer secondaryObserver, Target secondaryTarget) throws AttitudeNotAvailableException;

    /**
     * getOrientations returns a Time-ordered map of orientations that describe
     * a slew from an initial orientation to an orientation that fulfills
     * another set of primary and secondary constraints at the end of the slew.
     *
     * @param start Time at which the slew begins
     *
     * @param fromOrientation Orientation at the beginning of the slew
     *
     * @param primaryObserver The observer on the spacecraft that must be
     *                        aligned with the primary target
     *
     * @param primaryTarget The target in the spacecraft's environment that
     *                      the primary observer must align with
     *
     * @param secondaryObserver The observer on the spacecraft that is
     *                          aligned with the secondary target while also
     *                          fulfilling the primary constraints
     *
     * @param secondaryTarget The target in the spacecraft's environment that
     *                        the secondary observer must align with while also
     *                        fulfilling the primary constraints
     *
     * @param override Maximum allowable duration of the turn
     *
     * @return A SortedMap containing (Time, Orientation) pairs that make up the
     *                        turn profile. The last entry of the map is either the
     *                        first instant the spacecraft can be assumed to be at the end attitude,
     *                        or it is the orientation after override Duration no matter when
     *                        the Turn ended inside that window, depending on the implementation
     *
     */
    SortedMap<Time, Orientation> getOrientations(Time start, Orientation fromOrientation, Observer primaryObserver, Target primaryTarget, Observer secondaryObserver, Target secondaryTarget, Duration override)  throws AttitudeNotAvailableException;

    /**
     * Sets angular rate and acceleration limits partway through the simulation if desired - future calculations will use the new limits
     *
     * @param angularVelocityLimit Maximum allowable angular velocity vector
     *                             represented in the body frame, in rad/s
     *
     * @param angularAccelerationLimit Maximum allowable angular acceleration
     *                                 vector represented in the body frame, in rad/s^2
     */
    void setRateAndAccelLimits(Vector3D angularVelocityLimit, Vector3D angularAccelerationLimit);
}
