package gov.nasa.ammos.plandev.geometry.resources;

import gov.nasa.ammos.plandev.contrib.serialization.mappers.DoubleValueMapper;
import gov.nasa.ammos.plandev.contrib.streamline.core.Resource;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.Registrar;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.Discrete;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.monads.DiscreteResourceMonad;
import org.apache.commons.math3.geometry.euclidean.threed.Rotation;
import org.apache.commons.math3.geometry.euclidean.threed.Vector3D;

import static gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.monads.DiscreteResourceMonad.map;

/**
 * Utility methods for registering Vector3D and Rotation resources with an Aerie Registrar.
 * Extracted from the original GenericGeometryResources class for reuse by GNC and other subsystems.
 */
public class GeometryRegistrarUtils {

  private static final DoubleValueMapper dvm = new DoubleValueMapper();

  public static void registerVector(Registrar registrar, String name, Resource<Discrete<Vector3D>> r) {
    registrar.discrete(name + "_X", map(r, v -> v == null ? null : v.getX()), dvm);
    registrar.discrete(name + "_Y", map(r, v -> v == null ? null : v.getY()), dvm);
    registrar.discrete(name + "_Z", map(r, v -> v == null ? null : v.getZ()), dvm);
    registrar.discrete(name + "_magnitude", map(r, v -> v == null ? null : Math.sqrt(v.getX() * v.getX() + v.getY() * v.getY() + v.getZ() * v.getZ())), dvm);
  }

  public static void registerRotation(Registrar registrar, String name, Resource<Discrete<Rotation>> rotationResource) {
    registrar.discrete(name + ".Q0", DiscreteResourceMonad.map(rotationResource, Rotation::getQ0), dvm);
    registrar.discrete(name + ".Q1", DiscreteResourceMonad.map(rotationResource, Rotation::getQ1), dvm);
    registrar.discrete(name + ".Q2", DiscreteResourceMonad.map(rotationResource, Rotation::getQ2), dvm);
    registrar.discrete(name + ".Q3", DiscreteResourceMonad.map(rotationResource, Rotation::getQ3), dvm);
  }
}
