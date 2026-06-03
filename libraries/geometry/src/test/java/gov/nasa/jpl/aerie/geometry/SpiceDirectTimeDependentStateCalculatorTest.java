package gov.nasa.jpl.aerie.geometry;

import gov.nasa.jpl.aerie.geometry.directspicecalls.SpiceDirectTimeDependentStateCalculator;
import gov.nasa.jpl.aerie.geometry.interfaces.GeometryInformationNotAvailableException;
import gov.nasa.jpl.aerie.geometry.returnedobjects.IlluminationAngles;
import gov.nasa.jpl.aerie.geometry.returnedobjects.LatLonCoord;
import gov.nasa.jpl.aerie.geometry.returnedobjects.RADec;
import gov.nasa.jpl.aerie.geometry.returnedobjects.SubPointInformation;
import gov.nasa.jpl.aerie.geometry.spice.SpiceConstants;
import gov.nasa.jpl.aerie.geometry.spice.SpiceUtils;
import gov.nasa.jpl.aerie.geometry.spiceinterpolation.Body;
import gov.nasa.jpl.time.Time;
import org.apache.commons.math3.geometry.euclidean.threed.Vector3D;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;
import org.junit.jupiter.api.TestInstance.Lifecycle;
import spice.basic.SpiceErrorException;

import java.util.HashMap;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.fail;

/**
 * Tests for {@link SpiceDirectTimeDependentStateCalculator} against MATLAB reference
 * values (from {@code test_mro_geom.m}) at a fixed epoch. Reference epoch:
 * 2024-01-02T00:00:00 UTC, spacecraft MRO (-74), target MARS.
 *
 * <p>Requires the SPICE kernel set in [spice-kernels/](../../../../../../../spice-kernels/);
 * see {@link SpiceConstants}.
 */
@TestInstance(Lifecycle.PER_CLASS)
public class SpiceDirectTimeDependentStateCalculatorTest {

  static SpiceDirectTimeDependentStateCalculator stateCalculatorNoCaching;
  static SpiceDirectTimeDependentStateCalculator stateCalculatorCaching;

  private final Time t = new Time("2024-01-02T00:00:00");
  private final String sc_id = "-74";   // MRO
  private final String target = "MARS";
  private final String abcorr = "LT+S";

  @BeforeAll
  static void beforeAll() {
    try {
      SpiceUtils.initialize(SpiceConstants.VERSIONED_KERNELS_ROOT_DIRECTORY);
    } catch (SpiceErrorException e) {
      throw new RuntimeException("Failed to initialize SPICE kernels", e);
    }

    Body mars  = new Body("MARS",  499, "IAU_MARS",  0.17);
    Body earth = new Body("EARTH", 399, "IAU_EARTH", 0.30);
    Body sun   = new Body("SUN",   10,  "IAU_SUN",   1.0);
    HashMap<String, Body> bodies = new HashMap<>();
    bodies.put("MARS",  mars);
    bodies.put("EARTH", earth);
    bodies.put("SUN",   sun);

    stateCalculatorCaching   = new SpiceDirectTimeDependentStateCalculator(bodies, true);
    stateCalculatorNoCaching = new SpiceDirectTimeDependentStateCalculator(bodies, false);
  }

  @Test
  public void testGetState() {
    try {
      Vector3D[][] calcs = {
          stateCalculatorCaching.getState(t, sc_id, target, abcorr),
          stateCalculatorCaching.getState(t, sc_id, target, abcorr),
          stateCalculatorNoCaching.getState(t, sc_id, target, abcorr),
      };
      // MATLAB reference (test_mro_geom.m): position 834.60108, -720.70159, 3459.16649 km
      for (Vector3D[] calc : calcs) {
        assertEquals( 834.60108, calc[0].getX(), 0.001);
        assertEquals(-720.70159, calc[0].getY(), 0.001);
        assertEquals(3459.16649, calc[0].getZ(), 0.001);
      }
    } catch (GeometryInformationNotAvailableException e) {
      fail();
    }
  }

  @Test
  public void testGetRange() {
    try {
      double[] calcs = {
          stateCalculatorCaching.getRange(t, sc_id, target, abcorr),
          stateCalculatorCaching.getRange(t, sc_id, target, abcorr),
          stateCalculatorNoCaching.getRange(t, sc_id, target, abcorr),
      };
      // MATLAB reference: 3630.67522 km
      for (double calc : calcs) assertEquals(3630.67522, calc, 0.001);
    } catch (GeometryInformationNotAvailableException e) {
      fail();
    }
  }

  @Test
  public void testGetSpeed() {
    try {
      double[] calcs = {
          stateCalculatorCaching.getSpeed(t, sc_id, target, abcorr),
          stateCalculatorCaching.getSpeed(t, sc_id, target, abcorr),
          stateCalculatorNoCaching.getSpeed(t, sc_id, target, abcorr),
      };
      // MATLAB reference: 3.44354 km/s
      for (double calc : calcs) assertEquals(3.44354, calc, 0.001);
    } catch (GeometryInformationNotAvailableException e) {
      fail();
    }
  }

  @Test
  public void testGetSpacecraftAltitude() {
    try {
      double[] calcs = {
          stateCalculatorCaching.getSpacecraftAltitude(t, sc_id, target, abcorr, false),
          stateCalculatorCaching.getSpacecraftAltitude(t, sc_id, target, abcorr, false),
          stateCalculatorNoCaching.getSpacecraftAltitude(t, sc_id, target, abcorr, false),
      };
      // MATLAB reference: 252.27442 km
      for (double calc : calcs) assertEquals(252.27442, calc, 0.001);
    } catch (GeometryInformationNotAvailableException e) {
      fail();
    }
  }

  @Test
  public void testGetSunBodySpacecraftAngle() {
    try {
      double[] calcs = {
          stateCalculatorCaching.getSunBodySpacecraftAngle(t, sc_id, "EARTH", abcorr),
          stateCalculatorCaching.getSunBodySpacecraftAngle(t, sc_id, "EARTH", abcorr),
          stateCalculatorNoCaching.getSunBodySpacecraftAngle(t, sc_id, "EARTH", abcorr),
      };
      // MATLAB reference: 13.01936 deg
      for (double calc : calcs) assertEquals(13.01936, calc, 0.001);
    } catch (GeometryInformationNotAvailableException e) {
      fail();
    }
  }

  @Test
  public void testGetSunSpacecraftBodyAngle() {
    try {
      double[] calcs = {
          stateCalculatorCaching.getSunSpacecraftBodyAngle(t, sc_id, "EARTH", abcorr),
          stateCalculatorCaching.getSunSpacecraftBodyAngle(t, sc_id, "EARTH", abcorr),
          stateCalculatorNoCaching.getSunSpacecraftBodyAngle(t, sc_id, "EARTH", abcorr),
      };
      // MATLAB reference: 8.60335 deg
      for (double calc : calcs) assertEquals(8.60335, calc, 0.001);
    } catch (GeometryInformationNotAvailableException e) {
      fail();
    }
  }

  @Test
  public void testGetEarthSpacecraftBodyAngle() {
    try {
      double[] calcs = {
          stateCalculatorCaching.getEarthSpacecraftBodyAngle(t, sc_id, target, abcorr),
          stateCalculatorCaching.getEarthSpacecraftBodyAngle(t, sc_id, target, abcorr),
          stateCalculatorNoCaching.getEarthSpacecraftBodyAngle(t, sc_id, target, abcorr),
      };
      // MATLAB reference: 77.57672 deg
      for (double calc : calcs) assertEquals(77.57672, calc, 0.001);
    } catch (GeometryInformationNotAvailableException e) {
      fail();
    }
  }

  @Test
  public void testGetEarthSunProbeAngle() {
    try {
      double[] calcs = {
          stateCalculatorCaching.getEarthSunProbeAngle(t, sc_id, abcorr),
          stateCalculatorCaching.getEarthSunProbeAngle(t, sc_id, abcorr),
          stateCalculatorNoCaching.getEarthSunProbeAngle(t, sc_id, abcorr),
      };
      // MATLAB reference: 158.37732 deg
      for (double calc : calcs) assertEquals(158.37732, calc, 0.001);
    } catch (GeometryInformationNotAvailableException e) {
      fail();
    }
  }

  @Test
  public void testGetSubPointInformation() {
    try {
      SubPointInformation[] calcs = {
          stateCalculatorCaching.getSubPointInformation(t, sc_id, target, abcorr, false),
          stateCalculatorCaching.getSubPointInformation(t, sc_id, target, abcorr, false),
          stateCalculatorNoCaching.getSubPointInformation(t, sc_id, target, abcorr, false),
      };
      // MATLAB reference: lat -70.54205 deg, lon -162.87486 deg, radius 3378.40081 km
      for (SubPointInformation calc : calcs) {
        LatLonCoord ll = new LatLonCoord(calc.getSpoint());
        assertEquals(-70.54205,  ll.getLatitude()  * (180 / Math.PI), 0.001);
        assertEquals(-162.87486, ll.getLongitude() * (180 / Math.PI), 0.001);
        assertEquals(3378.40081, ll.getRadius(), 0.001);
      }
    } catch (GeometryInformationNotAvailableException e) {
      fail();
    }
  }

  @Test
  public void testGetIlluminationAngles() {
    try {
      IlluminationAngles[] calcs = {
          stateCalculatorCaching.getIlluminationAngles(t, sc_id, target, abcorr, false),
          stateCalculatorCaching.getIlluminationAngles(t, sc_id, target, abcorr, false),
          stateCalculatorNoCaching.getIlluminationAngles(t, sc_id, target, abcorr, false),
      };
      // MATLAB reference: phase 104.58995, incidence 104.46234, emission 0.21215 deg
      for (IlluminationAngles calc : calcs) {
        assertEquals(  0.21215, calc.getEmissionAngle(),  0.001);
        assertEquals(104.46234, calc.getIncidenceAngle(), 0.001);
        assertEquals(104.58995, calc.getPhaseAngle(),     0.001);
      }
    } catch (GeometryInformationNotAvailableException e) {
      fail();
    }
  }

  @Test
  public void testGetBetaAngle() {
    try {
      double[] calcs = {
          stateCalculatorCaching.getBetaAngle(t, sc_id, target, abcorr),
          stateCalculatorCaching.getBetaAngle(t, sc_id, target, abcorr),
          stateCalculatorNoCaching.getBetaAngle(t, sc_id, target, abcorr),
      };
      // MATLAB reference: 57.73393 deg
      for (double calc : calcs) assertEquals(57.73393, calc, 0.001);
    } catch (GeometryInformationNotAvailableException e) {
      fail();
    }
  }

  @Test
  public void testGetBodyHalfAngleSize() {
    try {
      double[] calcs = {
          stateCalculatorCaching.getBodyHalfAngleSize(t, sc_id, target, abcorr),
          stateCalculatorCaching.getBodyHalfAngleSize(t, sc_id, target, abcorr),
          stateCalculatorNoCaching.getBodyHalfAngleSize(t, sc_id, target, abcorr),
      };
      // MATLAB reference: 69.29538 deg
      for (double calc : calcs) assertEquals(69.29538, calc, 0.001);
    } catch (GeometryInformationNotAvailableException e) {
      fail();
    }
  }

  @Test
  public void testGetRADec() {
    try {
      RADec[] calcs = {
          stateCalculatorCaching.getRADec(t, "EARTH", sc_id, abcorr),
          stateCalculatorCaching.getRADec(t, "EARTH", sc_id, abcorr),
          stateCalculatorNoCaching.getRADec(t, "EARTH", sc_id, abcorr),
      };
      // MATLAB reference: RA -92.49891, Dec -23.97684 deg
      for (RADec calc : calcs) {
        assertEquals(-92.49891, calc.getRA(),  0.001);
        assertEquals(-23.97684, calc.getDec(), 0.001);
      }
    } catch (GeometryInformationNotAvailableException e) {
      fail();
    }
  }

  @Test
  public void testGetLST() {
    try {
      double[] calcs = {
          stateCalculatorCaching.getLST(t, sc_id, target, abcorr, false),
          stateCalculatorCaching.getLST(t, sc_id, target, abcorr, false),
          stateCalculatorNoCaching.getLST(t, sc_id, target, abcorr, false),
      };
      // MATLAB reference: 3.37972 (hours)
      for (double calc : calcs) assertEquals(3.37972, calc, 0.001);
    } catch (GeometryInformationNotAvailableException e) {
      fail();
    }
  }
}
