package gov.nasa.ammos.plandev.geometry.spice;

import gov.nasa.ammos.plandev.spice.SpiceLoader;
import spice.basic.CSPICE;
import spice.basic.SpiceErrorException;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class SpiceUtils {

  private static boolean nativeLoaded = false;

  /**
   * Load the native SPICE library (JNISpice). Safe to call multiple times.
   */
  public static void loadNativeLibrary() {
    if (!nativeLoaded) {
      SpiceLoader.loadSpice();
      nativeLoaded = true;
    }
  }

  /**
   * Initialize CSPICE by loading all kernel files from a directory.
   * <p>
   * Loads the native SPICE library if not already loaded, clears any
   * previously loaded kernels, then loads all kernel files (.bsp, .tls,
   * .tpc, .bpc, .tf, .ck) from the given directory. This avoids issues
   * with meta kernel PATH_VALUES being relative to the process working
   * directory.
   * <p>
   * Falls back to loading the meta kernel file if no individual kernel
   * files are found in the directory.
   *
   * @param kernelDir path to the directory containing SPICE kernel files
   */
  public static void initialize(Path kernelDir) throws SpiceErrorException {
    loadNativeLibrary();
    CSPICE.kclear();

    if (kernelDir != null && Files.isDirectory(kernelDir)) {
      try {
        var kernelFiles = Files.list(kernelDir)
            .filter(p -> {
              String name = p.getFileName().toString().toLowerCase();
              return name.endsWith(".bsp") || name.endsWith(".tls") ||
                     name.endsWith(".tpc") || name.endsWith(".bpc") ||
                     name.endsWith(".tf") || name.endsWith(".ck");
            })
            .sorted()
            .toList();

        if (!kernelFiles.isEmpty()) {
          for (Path kernel : kernelFiles) {
            CSPICE.furnsh(kernel.toString());
          }
          return;
        }
      } catch (IOException e) {
        // Fall through to meta kernel
      }
    }

    // Fallback: try loading meta kernel from the directory
    Path metaKernel = kernelDir != null
        ? kernelDir.resolve("latest_meta_kernel.tm")
        : Path.of(SpiceConstants.NAIF_META_KERNEL_PATH);
    CSPICE.furnsh(metaKernel.toString());
  }

  /**
   * Initialize CSPICE using the default kernel directory from SPICE_DIRECTORY env var.
   */
  public static void initialize() throws SpiceErrorException {
    initialize(SpiceConstants.VERSIONED_KERNELS_ROOT_DIRECTORY);
  }

  public static String getToolkitVersion() throws SpiceErrorException {
    return CSPICE.tkvrsn("TOOLKIT");
  }

}
