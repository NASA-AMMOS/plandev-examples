package gov.nasa.jpl.aerie.gnc.functions;

import gov.nasa.jpl.aerie.gnc.interfaces.Orientation;
import gov.nasa.jpl.time.Time;
import org.apache.commons.math3.geometry.euclidean.threed.Rotation;
import org.apache.commons.math3.geometry.euclidean.threed.Vector3D;
import org.apache.commons.math3.util.FastMath;
import spice.basic.CSPICE;
import spice.basic.SpiceErrorException;

import java.io.File;
import java.util.Map;
import java.util.SortedMap;


public class AttitudeFunctions {

    public AttitudeFunctions() {
    }

    /**
     *
     * @param scRotation Rotation between spacecraft fixed frame and reference frame
     * @param fixedFrameRotation Rotation between spacecraft fixed frame and boresight of interest
     * @param target Vector in reference frame from SC to target
     * @param scDeviceVector Vector in device frame (could be instrument or structure)
     * @return Angle between boresight and vector to target, in degrees
     */
    public static double angleBetweenObjectAndVector(Rotation scRotation, Rotation fixedFrameRotation, Vector3D target, Vector3D scDeviceVector){
        Vector3D referenceToInstrument = scRotation.applyTo(fixedFrameRotation.applyTo(scDeviceVector));
        return FastMath.toDegrees(Vector3D.angle(referenceToInstrument,target));
    }

    /**
     *
     * @param scRotation Rotation between spacecraft fixed frame and reference frame
     * @param fixedFrameRotation Rotation between spacecraft fixed frame and boresight of interest
     * @param target Vector in reference frame from SC to target
     * @return Angle between boresight and vector to target, in degrees
     */
    public static double angleBetweenObjectAndBoresight(Rotation scRotation, Rotation fixedFrameRotation, Vector3D target){
        return angleBetweenObjectAndVector(scRotation, fixedFrameRotation,target,new Vector3D(0,0,1));
    }

    public static Rotation getFixedFrameRotationWithSpice(String fromFrame, String toFrame) throws SpiceErrorException{
        return new Rotation(CSPICE.pxform(fromFrame,toFrame,0),1E-3);
    }

    /**
     * Generates a CK file with a single type 3 segment (interpolating time-tagged quaternions). Deletes file with exact name if it exists before writing out new file.
     * @param attitudesAtTimes maps of Times to the Rotation at that time
     * @param fileName Desired filename (including .bc extension)
     * @param scID NAIF integer ID for the spacecraft (just used for time conversion)
     * @param instrumentID NAIF integer ID for the 'instrument' that the rotation goes to (if spacecraft is desired, multiply scID by 1000)
     * @param referenceFrame String of the frame that the rotation turns from, that the quaternions are relative to (Ex. J2000)
     * @param shouldAngularVelocityBeWritten Boolean that determines if angular velocity information is available to be written
     * @throws SpiceErrorException if any input quaternion has magnitude zero, if the reference frame cannot be found, or other reasons (see ckw03_c)
     */
    public static void writeCK(SortedMap<Time, Orientation> attitudesAtTimes, String fileName, int scID, int instrumentID, String referenceFrame, boolean shouldAngularVelocityBeWritten) throws SpiceErrorException{
        new File(fileName).delete();
        int handle = CSPICE.ckopn(fileName, "CK_file", 5000);
        double[] q = new double[4*attitudesAtTimes.size()];
        double[] av = new double[3*attitudesAtTimes.size()];
        double[] sclkd = new double[attitudesAtTimes.size()];
        int i = 0;
        for(Map.Entry<Time, Orientation> entry : attitudesAtTimes.entrySet()){
            sclkd[i] = CSPICE.sce2c(scID, entry.getKey().toET());
            Rotation quat = entry.getValue().getRotation();
            q[4 * i]   = quat.getQ0();
            q[4 * i + 1] = quat.getQ1();
            q[4 * i + 2] = quat.getQ2();
            q[4 * i + 3] = quat.getQ3();
            if (shouldAngularVelocityBeWritten){
                if(!entry.getValue().isRotationRateDefined()){
                    throw new RuntimeException("Flag to write angular velocities to CK is on, but angular velocities not available in attitudeAtTimes at time " + entry.getKey());
                }
                Vector3D rotationRate = entry.getValue().getRotationRate();
                av[3 * i]   = rotationRate.getX();
                av[3 * i + 1]   = rotationRate.getY();
                av[3 * i + 2]   = rotationRate.getZ();
            }
            i++;
        }
        CSPICE.ckw03(handle, sclkd[0], sclkd[sclkd.length-1], instrumentID, referenceFrame, shouldAngularVelocityBeWritten, "Blackbird Generated CKernel", sclkd.length, sclkd, q, av, 1, new double[] {sclkd[0]});
        CSPICE.ckcls(handle);
    }

    /**
     * Returns the position and velocity of a target object relative to an observing object in expressed in a relative frame
     * @param target String of SPICE recognized object for which the state is desired
     * @param et Time that the state is desired at
     * @param frame The frame that the state is expressed relative to (ex. "J2000")
     * @param correction String of the light time correction specification (ex. "LT+S")
     * @param observer String of SPICE recognized object for which the state is desired with respect to
     */
    public static double[] getState(String target, Time et, String frame, String correction, String observer){
        // Use SPICE call to find an array of the target's position and velocity
        // relative to the observing body
        double[] targetRelative = new double[6];
        double[] lightTimeDelay = new double[1];
        try {
            CSPICE.spkezr(target, et.toET(), frame, correction, observer, targetRelative, lightTimeDelay);
        } catch (SpiceErrorException er) {
            er.printStackTrace();
        }
        return targetRelative;
    }
}
