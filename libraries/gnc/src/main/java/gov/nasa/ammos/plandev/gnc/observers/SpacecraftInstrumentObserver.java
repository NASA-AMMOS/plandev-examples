package gov.nasa.ammos.plandev.gnc.observers;

import gov.nasa.ammos.plandev.gnc.functions.AttitudeFunctions;
import gov.nasa.ammos.plandev.gnc.interfaces.Observer;
import org.apache.commons.math3.geometry.euclidean.threed.Vector3D;
import spice.basic.CSPICE;
import spice.basic.IDCodeNotFoundException;
import spice.basic.NameNotFoundException;
import spice.basic.SpiceErrorException;

import java.util.Objects;

public class SpacecraftInstrumentObserver implements Observer {
    private final String instrumentSpiceName;
    private final String obsBody;

    /**
     * The SpacecraftInstrumentObserver takes in an instrument's defined
     * SPICE name and the name of the body it is associated with. This
     * should be used when the observer is an instrument defined in SPICE.
     * The output of getPointing is the instrument boresight in the
     * spacecraft frame. SpacecraftInstrumentObserver can be used as a
     * primary or secondary observer.
     *
     * EX: The spacecraft antenna is defined by SPICE in a frame kernel.
     * This is the observer in targeting the direction of the Earth for
     * communications.
     *
     * @param instrumentSpiceName Instrument name defined in SPICE by a
     *                            kernel
     * @param obsBody SPICE defined string of the observing body
     */

    public SpacecraftInstrumentObserver(String instrumentSpiceName, String obsBody){
        this.instrumentSpiceName = instrumentSpiceName;
        this.obsBody = obsBody;
    }

    @Override
    public String getName() {
        return "SpacecraftInstrumentObserver," + instrumentSpiceName;
    }

    @Override
    public Vector3D getPointing() {

        // Get the spacecraft frame from the inputted string
        int spacecraftID;
        String spacecraftFrame = null;
        try {
            spacecraftID = CSPICE.bods2c(obsBody);
            spacecraftFrame = CSPICE.bodc2n(spacecraftID * 1000);
        } catch (SpiceErrorException | IDCodeNotFoundException | NameNotFoundException spiceErrorException) {
            spiceErrorException.printStackTrace();
        }

        // Get the observer in the spacecraft frame
        double[] observerVector = new double[3];
        try {
            CSPICE.getfov(CSPICE.bods2c(instrumentSpiceName), new String[1], new String[1], observerVector, new int[1], new double[12]);
        } catch (SpiceErrorException | IDCodeNotFoundException err) {
            err.printStackTrace();
        }
        // Make unit vector if not already
        Vector3D observerInItsFrame = new Vector3D(observerVector);

        // Rotate unit vector out the observer frame and into the spacecraft frame
        try {
            return Objects.requireNonNull(AttitudeFunctions.getFixedFrameRotationWithSpice(instrumentSpiceName, spacecraftFrame)).applyTo(observerInItsFrame).normalize();
        } catch (SpiceErrorException e) {
            e.printStackTrace();
        }
        return null;
    }
}
