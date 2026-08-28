package gov.nasa.ammos.plandev.gnc;

import gov.nasa.ammos.plandev.contrib.streamline.modeling.Registrar;
import gov.nasa.ammos.plandev.gnc.functions.AttitudeFunctions;
import gov.nasa.ammos.plandev.merlin.framework.junit.MerlinExtension;
import org.apache.commons.math3.geometry.euclidean.threed.Rotation;
import org.apache.commons.math3.geometry.euclidean.threed.RotationConvention;
import org.apache.commons.math3.geometry.euclidean.threed.Vector3D;
import org.apache.commons.math3.util.FastMath;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;
import org.junit.jupiter.api.TestInstance.Lifecycle;
import org.junit.jupiter.api.extension.ExtendWith;

import static gov.nasa.ammos.plandev.contrib.streamline.core.Resources.currentValue;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertSame;

/**
 * Tests for the GNC library — {@link GncDataModel} state and {@link AttitudeFunctions}
 * pointing math. SPICE-backed pieces (CK file I/O, {@code getFixedFrameRotationWithSpice})
 * are not covered here.
 */
@ExtendWith(MerlinExtension.class)
@TestInstance(Lifecycle.PER_CLASS)
public class GncTest {

  private final GncDataModel gnc;

  public GncTest(gov.nasa.ammos.plandev.merlin.framework.Registrar registrar) {
    this.gnc = new GncDataModel(new Registrar(registrar, Registrar.ErrorBehavior.Throw));
  }

  // ---- GncDataModel defaults ----

  @Test
  void testDefaultRotationIsIdentity() {
    assertEquals(Rotation.IDENTITY.getQ0(), currentValue(gnc.rotation).getQ0(), 1e-12);
    assertEquals(Rotation.IDENTITY.getQ1(), currentValue(gnc.rotation).getQ1(), 1e-12);
    assertEquals(Rotation.IDENTITY.getQ2(), currentValue(gnc.rotation).getQ2(), 1e-12);
    assertEquals(Rotation.IDENTITY.getQ3(), currentValue(gnc.rotation).getQ3(), 1e-12);
  }

  @Test
  void testDefaultStateIsRestful() {
    assertEquals(Vector3D.ZERO, currentValue(gnc.RotationRate));
    assertEquals(0.0, currentValue(gnc.PointingRotationAngle), 1e-12);
    assertFalse(currentValue(gnc.IsSlewing));
  }

  @Test
  void testObserverForStringMapsCardinalAxes() {
    assertSame(GncDataModel.X,     GncDataModel.observerForString("X"));
    assertSame(GncDataModel.Y,     GncDataModel.observerForString("Y"));
    assertSame(GncDataModel.Z,     GncDataModel.observerForString("Z"));
    assertSame(GncDataModel.NEG_X, GncDataModel.observerForString("-X"));
    assertSame(GncDataModel.NEG_Y, GncDataModel.observerForString("MINUS_Y"));
    assertSame(GncDataModel.NEG_Z, GncDataModel.observerForString("NEG_Z"));
  }

  // ---- AttitudeFunctions pointing math ----

  @Test
  void testAngleToTargetAlongBoresightIsZero() {
    // No rotation, boresight = +Z, target = +Z -> 0 deg.
    Vector3D targetAlongZ = new Vector3D(0, 0, 100);
    double angle = AttitudeFunctions.angleBetweenObjectAndBoresight(
        Rotation.IDENTITY, Rotation.IDENTITY, targetAlongZ);
    assertEquals(0.0, angle, 1e-9);
  }

  @Test
  void testAngleToTargetPerpendicularToBoresightIs90() {
    // No rotation, boresight = +Z, target = +X -> 90 deg.
    Vector3D targetAlongX = new Vector3D(100, 0, 0);
    double angle = AttitudeFunctions.angleBetweenObjectAndBoresight(
        Rotation.IDENTITY, Rotation.IDENTITY, targetAlongX);
    assertEquals(90.0, angle, 1e-9);
  }

  @Test
  void testAngleToAntiparallelTargetIs180() {
    // No rotation, boresight = +Z, target = -Z -> 180 deg.
    Vector3D targetAlongNegZ = new Vector3D(0, 0, -100);
    double angle = AttitudeFunctions.angleBetweenObjectAndBoresight(
        Rotation.IDENTITY, Rotation.IDENTITY, targetAlongNegZ);
    assertEquals(180.0, angle, 1e-9);
  }

  @Test
  void testRotatingSpacecraftReorientsBoresight() {
    // Rotate spacecraft 90 deg about +X. Boresight (originally +Z) now points along -Y.
    // A target along -Y should be in view (0 deg); a target along +Z should be 90 deg off.
    Rotation rotateAboutXBy90 = new Rotation(
        Vector3D.PLUS_I, FastMath.toRadians(90), RotationConvention.VECTOR_OPERATOR);

    double angleToNegY = AttitudeFunctions.angleBetweenObjectAndBoresight(
        rotateAboutXBy90, Rotation.IDENTITY, new Vector3D(0, -1, 0));
    assertEquals(0.0, angleToNegY, 1e-9);

    double angleToZ = AttitudeFunctions.angleBetweenObjectAndBoresight(
        rotateAboutXBy90, Rotation.IDENTITY, Vector3D.PLUS_K);
    assertEquals(90.0, angleToZ, 1e-9);
  }
}
