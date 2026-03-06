package gov.nasa.jpl.aerie.gnc.ck;

import gov.nasa.jpl.aerie.gnc.functions.AttitudeNotAvailableException;
import gov.nasa.jpl.aerie.gnc.interfaces.ADCModel;
import gov.nasa.jpl.aerie.gnc.interfaces.Observer;
import gov.nasa.jpl.aerie.gnc.interfaces.Orientation;
import gov.nasa.jpl.aerie.gnc.interfaces.Target;
import gov.nasa.jpl.time.Duration;
import gov.nasa.jpl.time.Time;
import org.apache.commons.math3.geometry.euclidean.threed.Rotation;
import org.apache.commons.math3.geometry.euclidean.threed.Vector3D;
import spice.basic.CSPICE;
import spice.basic.IDCodeNotFoundException;
import spice.basic.SpiceErrorException;

import java.util.SortedMap;
import java.util.TreeMap;

public class CKAttitudeModel implements ADCModel {
    private final String scBaseFrame;
    private final String relativeFrame;
    private final Duration sampleRateForTurns;
    private final boolean angularVelocityInCK;

    public CKAttitudeModel(String scBaseFrame, String relativeFrame, Duration sampleRateForTurns, boolean angularVelocityInCK){
        this.scBaseFrame = scBaseFrame;
        this.relativeFrame = relativeFrame;
        this.sampleRateForTurns = sampleRateForTurns;
        this.angularVelocityInCK = angularVelocityInCK;
    }

    @Override
    public Orientation getOrientation(Time et, Observer primaryObserver, Target primaryTarget, Observer secondaryObserver, Target secondaryTarget) throws AttitudeNotAvailableException{
        int scCode;
        double[][] rotationMatrix = new double[3][3];
        double[] angularVelocity = new double[3];
        double[] clkout = new double[1];
        boolean[] found = new boolean[1];

        try {
            scCode = CSPICE.bods2c(scBaseFrame);

            if(angularVelocityInCK){
                CSPICE.ckgpav(scCode, CSPICE.scencd(scCode/1000, CSPICE.sce2s(scCode/1000, et.toET())), Duration.MICROSECOND_DURATION.getTics(), relativeFrame, rotationMatrix, angularVelocity, clkout, found);
            } else {
                CSPICE.ckgp(scCode, CSPICE.scencd(scCode / 1000, CSPICE.sce2s(scCode / 1000, et.toET())), Duration.MICROSECOND_DURATION.getTics(), relativeFrame, rotationMatrix, clkout, found);
            }
            Rotation rotation = new Rotation(rotationMatrix,1E-3).revert();
            // Have the scalar term of the quaternion always be positive
            if (rotation.getQ0() < 0){
                rotation = new Rotation(rotation.getQ0()*-1, rotation.getQ1()*-1, rotation.getQ2()*-1, rotation.getQ3()*-1, false);
            }
            if(angularVelocityInCK) {
                return new Orientation(rotation, new Vector3D(angularVelocity));
            }
            else{
                return new Orientation(rotation);
            }
        } catch (SpiceErrorException | IDCodeNotFoundException e) {
            throw new AttitudeNotAvailableException("Could not transform from " + scBaseFrame + " to " + relativeFrame + " at " + et.toString() + ". Likely this time is outside of the loaded CK bounds. Full error:\n" + e);
        }
    }

    /**
     * See comment for ADCModel getOrientations. Returns attitudes until override duration is over, no matter when large slew finished
     */
    @Override
    public SortedMap<Time, Orientation> getOrientations(Time turnStart, Orientation fromOrientation, Observer primaryObserver, Target primaryTarget, Observer secondaryObserver, Target secondaryTarget, Duration override) throws AttitudeNotAvailableException{

        SortedMap<Time, Orientation> orientations = new TreeMap<>();

        for(Time t = turnStart; t.lessThanOrEqualTo(turnStart.add(override)); t = t.add(sampleRateForTurns)){
            orientations.put(t, getOrientation(t, primaryObserver, primaryTarget, secondaryObserver, secondaryTarget));
        }

        return orientations;
    }

    @Override
    public void setRateAndAccelLimits(Vector3D angularVelocityLimit, Vector3D angularAccelerationLimit){
    }
}
