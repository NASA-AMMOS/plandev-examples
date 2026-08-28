package examples.orbiter.spice;

import gov.nasa.ammos.plandev.geometry.spice.SpiceUtils;
import spice.basic.SpiceErrorException;

import java.nio.file.Path;

/**
 * Thin wrapper around {@link SpiceUtils} for backward compatibility.
 * The actual SPICE initialization logic lives in the geometry library.
 */
public class Spice {

  public static void initialize(String metaKernelPath) {
    final Path kernelDir = Path.of(metaKernelPath).getParent();

    try {
      SpiceUtils.initialize(kernelDir);
    } catch (SpiceErrorException e) {
      throw new IllegalStateException(
              "Failed to initialize SPICE from "
                      + kernelDir.toAbsolutePath()
                      + ". Ensure SPICE_DIRECTORY points to a mounted kernel directory.",
              e);
    }
  }

}



