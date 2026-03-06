package gov.nasa.jpl.aerie.geometry.spice;

import spice.basic.CSPICE;

public class SpiceUtils {

  /**
   * Initialize CSPICE for entire model.  This includes loading in
   * any required kernels.
   * <p>
   * Kernels are bookkept in the meta kernel file determined by the
   * SpiceConstants.NAIF_META_KERNEL_PATH environment
   */
  public static void initialize() throws Exception {
    CSPICE.kclear();

    CSPICE.furnsh(SpiceConstants.NAIF_META_KERNEL_PATH);
  }

  public static String getToolkitVersion() throws Exception {
    String version = "TOOLKIT";
    version = CSPICE.tkvrsn(version);

    return version;
  }


  /**
   * Input should be a Spice 3D point describing the location of the object on the
   * target body (lat/lon/elevation).
   * <p>
   * This routine will determine if it is illuminated and return true/false
   *
   * @return
   * @throws Exception
   */
  public static boolean isLatLonIlluminated(double [] latLonPoint) throws Exception {
    // convert lat/lon/radii to Cartesian points
//    double [] latLonPoint = new double []{90.0d, 0.0d, 1736.482d};

    double [] spoint = CSPICE.latrec(latLonPoint[0], latLonPoint[1], latLonPoint[2]);
    return isIlluminated(spoint);

  }


  public static boolean isIlluminated(double [] spoint) throws Exception {

    double et = CSPICE.str2et(SpiceConstants.DEFAULT_ET);
    double[] ssolpt = new double[3];
    double[] trgepc = new double[3]; // Target surface point epoch.
    double[] srfvec = new double[3];
    double sslphs = 0.00d;
    double sslsol = 0.00d;
    double sslemi = 0.00d;

    // this is the input for the method
//    double[] spoint = new double[]{90.00d, 0.00d, 0.00d};
    double[] angles = new double[3];
    boolean[] visibl = new boolean[3];
    boolean[] lit = new boolean[3];

    CSPICE.illumf(SpiceConstants.NAIF_ILLUM_METHOD[0],
      SpiceConstants.NAIF_MOON_NAME,
      SpiceConstants.NAIF_SUN_NAME,
      et,
      "IAU_MOON",
      SpiceConstants.NAIF_ABCORR_STRATEGY,
      SpiceConstants.NAIF_SUN_NAME,
      spoint,
      trgepc,
      srfvec,
      angles,
      visibl,
      lit);

    for (int i=0; i<3; i++)
      System.out.println("angles " + i + ": " + angles[i]);

    System.out.println("visibl: " + visibl[0]);
    System.out.println("lit: " + lit[0]);

    return lit[0];
  }

  /**
   * Prints the output of spkezr for debugging purposes
   *
   * @param sv
   * @param lt
   */
  public static void printStateVector(double[] sv, double[] lt) {
    System.out.println("x: " + sv[0] + "\tVx: " + sv[3]);
    System.out.println("y: " + sv[1] + "\tVy: " + sv[4]);
    System.out.println("z: " + sv[2] + "\tVz: " + sv[5]);

    System.out.println("Light Time: " + lt[0]);

  }

}
