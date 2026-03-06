package gov.nasa.jpl.aerie.gnc.interfaces;

import org.apache.commons.math3.geometry.euclidean.threed.Vector3D;

/**
 * An Observer is an object that can return a 3D vector that points in the spacecraft body-fixed frame along
 * the spacecraft part which needs to be oriented to a Target
 */
public interface Observer {

    /**
     * @return the name of the Observer
     */
    String getName();

    /**
     * @return a Vector3D in the spacecraft body-fixed frame
     */
    Vector3D getPointing();
}
