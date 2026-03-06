package gov.nasa.jpl.aerie.gnc.interfaces;

import gov.nasa.jpl.time.Time;
import org.apache.commons.math3.geometry.euclidean.threed.Vector3D;

/**
 * A Target is an object that an Observer can be oriented towards, and it provides three vectors: a pointing vector,
 * a target position vector, and a target velocity vector. Pointing and position are required separately because
 * for some target subclasses, the spacecraft is not supposed to directly point towards the position of the target.
 * Different implementations of ADCModel may require one or the other to fully resolve attitude.
 */

public interface Target {

    /**
     * @param et The time at which the pointing is desired
     *
     * @return a unit Vector3D in the direction of the target for primary targets,
     *
     *                    in the direction of the target with offset, if present,
     *                    for secondary plane targets,
     *
     *                    in the direction of the vector normal to the plane that
     *                    contains the primary target and secondary target direction
     *                    for secondary point targets
     *
     * Notes: For primary targets this return vector is simply the direction
     *        specified by the specific implementation getPosition, because for the primary targets this
     *        position is the vector that is intended to be aligned with the observer body-fixed vector.
     *
     *        The two different types of secondary targets are
     *        targeting a vector or targeting a plane normal to a vector. Plane targeting pointing returns the
     *        direction of the vector normal to the targeted plane and vector targeting returns the vector normal
     *        to the plane containing the primary target vector and the secondary target vector. This is because
     *        typically the cross product is immediately taken outside of the getPointing() method
     *        which is then the actual vector that is desired to be aligned with the secondary observer.
     */
    Vector3D getPointing(Time et);

    /**
     * @param et The time at which the position of the target relative to the
     *           observer is desired
     *
     * @return a Vector3D from the observer to the target for primary targets (km),
     *
     *                    from the observer to the notional target without offset
     *                    for secondary targets (km)
     *
     *  Notes: For the secondary targets getPosition() returns the position of notional target with no offset angle.
     *         (Examples are: the position of the Earth for BodyCenterSecondaryTarget, the position of the Sun
     *         for BodyPlaneSecondaryTarget, or the position of the body of gravitation for
     *         OrbitPlaneSecondaryTarget). Because of the potential rotational offset and due to cross-product process
     *         in typical generation implementations, secondary targets do not necessarily output the same
     *         thing for getPointing() and getPosition().
     */
    Vector3D getPosition(Time et);

    /**
     * @param et The time at which the velocity of the target relative to the
     *           observer is desired
     *
     * @return a Vector3D describing the velocity of the subject of getPosition()
     *         relative to the observer, no matter whether a primary or secondary target (km/s)
     */
    Vector3D getVelocity(Time et);

    /**
     * @return The name of the target
     */
    String getName();
}
