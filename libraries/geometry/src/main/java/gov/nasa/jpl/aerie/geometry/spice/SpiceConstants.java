package gov.nasa.jpl.aerie.geometry.spice;

import java.nio.file.Path;

public class SpiceConstants {
  public static final Path VERSIONED_KERNELS_ROOT_DIRECTORY = Path.of(System.getenv().getOrDefault("SPICE_DIRECTORY", "spice/kernels"));
  public static final String NAIF_TLS_KERNEL_PATH = VERSIONED_KERNELS_ROOT_DIRECTORY.toString() + "/naif0012.tls";
  public static final String NAIF_BSP_KERNEL_PATH = VERSIONED_KERNELS_ROOT_DIRECTORY.toString() + "/de440s.bsp";
  public static final String NAIF_TPC_KERNEL_PATH = VERSIONED_KERNELS_ROOT_DIRECTORY.toString() + "/pck00011.tpc";
  public static final String NAIF_META_KERNEL_PATH = VERSIONED_KERNELS_ROOT_DIRECTORY.toString() + "/latest_meta_kernel.tm";
  public static final String NAIF_MOON_NAME = "MOON";
  public static final String NAIF_EARTH_NAME = "EARTH";
  public static final String NAIF_SUN_NAME = "SUN";
  public static final String NAIF_FRAME_NAME = "J2000";// strategies are: "NONE", "LT", "LT+S", "CN", "CN+S"
  public static final String NAIF_ABCORR_STRATEGY = "LT+S";

  // 2 possible methods
  //    "Near Point/Ellipsoid"
  //    "DSK/Nadir/Unprioritized"
  public static final String [] NAIF_SUBPT_METHOD = new String [] {"Near Point/Ellipsoid", "DSK/Nadir/Unprioritized"};
  public static final String [] NAIF_ILLUM_METHOD = new String [] {"ELLIPSOID", "DSK/UNPRIORITIZED/SURFACES"};
  public static final String DEFAULT_ET = "JAN 1 2015 12:00:00";
}
