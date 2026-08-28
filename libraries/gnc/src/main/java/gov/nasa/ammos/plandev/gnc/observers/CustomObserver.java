package gov.nasa.ammos.plandev.gnc.observers;

import gov.nasa.ammos.plandev.gnc.interfaces.Observer;
import org.apache.commons.math3.geometry.euclidean.threed.Vector3D;


public class CustomObserver implements Observer {
    private final Vector3D observerSpacecraftFrame;

    /**
     * A CustomObserver takes in a known vector defined in the spacecraft
     * frame. This should be used when the observing direction is easily
     * expressed as a vector in the spacecraft frame. CustomObserver can be
     * used as a primary or secondary observer.
     *
     * EX: The spacecraft solar panel axis is a known observer in the
     * spacecraft frame. This is the observer in targeting the plane
     * normal to the sun for Power Steering.
     *
     * @param observerSpacecraftFrame Known Vector3D defined in the
     *                                spacecraft frame
     */

    public CustomObserver(Vector3D observerSpacecraftFrame){
        this.observerSpacecraftFrame = observerSpacecraftFrame;
    }

    @Override
    public String getName() {
        return "CustomObserver," + observerSpacecraftFrame.toString();
    }

    @Override
    public Vector3D getPointing() {
        // Return the unit vector of the observer direction
        return observerSpacecraftFrame.normalize();
    }
}
