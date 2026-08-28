package examples.orbiter.spice;

import gov.nasa.ammos.plandev.geometry.spice.SpiceUtils;
import spice.basic.SpiceErrorException;

import java.nio.file.Path;

/**
 * Thin wrapper around {@link SpiceUtils} for backward compatibility.
 * The actual SPICE initialization logic lives in the geometry library.
 */
public class Spice {

  public static void initialize(String metaKernelPath) throws SpiceErrorException {
    Path kernelDir = Path.of(metaKernelPath).getParent();
    SpiceUtils.initialize(kernelDir);
  }

}



