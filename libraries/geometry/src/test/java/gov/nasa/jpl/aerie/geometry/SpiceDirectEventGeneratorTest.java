package gov.nasa.jpl.aerie.geometry;

import gov.nasa.jpl.aerie.geometry.directspicecalls.SpiceDirectEventGenerator;
import gov.nasa.jpl.aerie.geometry.directspicecalls.SpiceDirectTimeDependentStateCalculator;
import gov.nasa.jpl.aerie.geometry.globals.Window;
import gov.nasa.jpl.aerie.geometry.interfaces.GeometryInformationNotAvailableException;
import gov.nasa.jpl.aerie.geometry.spice.SpiceConstants;
import gov.nasa.jpl.aerie.geometry.spice.SpiceUtils;
import gov.nasa.jpl.aerie.geometry.spiceinterpolation.Body;
import gov.nasa.jpl.time.Duration;
import gov.nasa.jpl.time.Time;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;
import org.junit.jupiter.api.TestInstance.Lifecycle;
import spice.basic.SpiceErrorException;

import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.fail;

/**
 * Tests for {@link SpiceDirectEventGenerator} — occultation/eclipse window detection,
 * periapsis/apoapsis times, and conjunctions — against MATLAB reference values from
 * {@code test_mro_geom.m}. Reference window: 2024-01-02T00–04:00 UTC, MRO + Mars.
 */
@TestInstance(Lifecycle.PER_CLASS)
public class SpiceDirectEventGeneratorTest {

  static SpiceDirectTimeDependentStateCalculator stateCalculatorCaching;
  static SpiceDirectEventGenerator eventGenerator;

  private final String sc_id = "-74";
  private final String target = "MARS";
  private final String abcorr = "CN";

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

    stateCalculatorCaching = new SpiceDirectTimeDependentStateCalculator(bodies, true);
    eventGenerator         = new SpiceDirectEventGenerator(bodies);
  }

  @Test
  public void testGetOccultations() {
    // MATLAB reference eclipse windows (Sun-Mars occultations).
    List<Window> eclipseRef = new ArrayList<>();
    eclipseRef.add(new Window(Time.fromET(757430442.38465), Time.fromET(757432124.34934)));
    eclipseRef.add(new Window(Time.fromET(757437175.76832), Time.fromET(757438857.55937)));

    List<Window> occultRef = new ArrayList<>();
    occultRef.add(new Window(Time.fromET(757430137.20259), Time.fromET(757432111.62785)));
    occultRef.add(new Window(Time.fromET(757436869.74876), Time.fromET(757438845.00248)));

    List<Window> dssRef = new ArrayList<>();
    dssRef.add(new Window(Time.fromET(757425669.18394), Time.fromET(757426589.34433)));
    dssRef.add(new Window(Time.fromET(757431344.33722), Time.fromET(757433319.47216)));
    dssRef.add(new Window(Time.fromET(757438076.76388), Time.fromET(757440052.72965)));

    try {
      List<Window> eclipseGot = eventGenerator.getOccultations(
          new Time("2024-01-02T00:00:00"), new Time("2024-01-02T04:00:00"),
          new Duration("0:1:0"), sc_id, "SUN", target, "CN", true, false, false);
      assertSameWindowListsToWithin(eclipseRef, eclipseGot, new Duration("00:00:20"));

      List<Window> occultGot = eventGenerator.getOccultations(
          new Time("2024-01-02T00:00:00"), new Time("2024-01-02T04:00:00"),
          new Duration("0:1:0"), sc_id, "EARTH", target, "CN", true, false, false);
      assertSameWindowListsToWithin(occultRef, occultGot, new Duration("00:00:20"));

      List<Window> dssGot = eventGenerator.getOccultations(
          new Time("2024-01-02T00:00:00"), new Time("2024-01-02T04:00:00"),
          new Duration("0:1:0"), "DSS-24", sc_id, target, "CN", true, true, false);
      assertSameWindowListsToWithin(dssRef, dssGot, new Duration("00:00:20"));
    } catch (GeometryInformationNotAvailableException e) {
      e.printStackTrace();
      fail();
    }
  }

  @Test
  public void testGetPeriapses() {
    List<Time> ref = new ArrayList<>();
    ref.add(Time.fromET(757426028.12514));
    ref.add(Time.fromET(757432784.65443));
    ref.add(Time.fromET(757439542.14604));
    try {
      List<Time> got = eventGenerator.getPeriapses(
          new Time("2024-01-02T00:00:00"), new Time("2024-01-02T04:00:00"),
          new Duration("0:5:00"), sc_id, target, 10000, abcorr);
      assertSameTimeListsToWithin(ref, got, new Duration("00:00:06"));
    } catch (GeometryInformationNotAvailableException e) {
      e.printStackTrace();
      fail();
    }
  }

  @Test
  public void testGetApoapses() {
    List<Time> ref = new ArrayList<>();
    ref.add(Time.fromET(757429409.47531));
    ref.add(Time.fromET(757436175.16261));
    try {
      List<Time> got = eventGenerator.getApoapses(
          new Time("2024-01-02T00:00:00"), new Time("2024-01-02T04:00:00"),
          new Duration("0:5:00"), sc_id, target, 0, abcorr);
      assertSameTimeListsToWithin(ref, got, new Duration("00:00:03"));
    } catch (GeometryInformationNotAvailableException e) {
      e.printStackTrace();
      fail();
    }
  }

  @Test
  public void testGetConjunctions() {
    // Mars had a solar conjunction on 7 Nov 2023 21:14 — covered by 2023-07-01 to 2024-01-02.
    try {
      List<Window> conjunctions = eventGenerator.getConjunctions(
          new Time("2023-180T00:00:00"), new Time("2024-001T00:00:00"),
          new Duration("1:0:0"), "EARTH", "MARS", "SUN", "CN", 3.0);
      assertEquals(1, conjunctions.size());
      assertTrue(new Duration("19T20:26:00").equalToWithin(
          conjunctions.get(0).getDuration(), Duration.HOUR_DURATION));
    } catch (GeometryInformationNotAvailableException e) {
      e.printStackTrace();
      fail();
    }
  }

  // ---- Helpers (same approach as the upstream test) ----

  private void assertSameTimeListsToWithin(List<Time> t1, List<Time> t2, Duration tolerance) {
    if (t1.size() != t2.size()) {
      System.out.println("Time lists not same size:");
      for (int i = 0; i < Integer.max(t1.size(), t2.size()); i++) {
        System.out.println(printTimePair(
            i < t1.size() ? t1.get(i) : null,
            i < t2.size() ? t2.get(i) : null));
      }
      fail();
    }

    int firstDiff = -1;
    Duration sumDiff = Duration.ZERO_DURATION;
    Duration maxDiff = Duration.ZERO_DURATION;
    for (int j = 0; j < t1.size(); j++) {
      Duration diff = t1.get(j).absoluteDifference(t2.get(j));
      if (diff.greaterThan(tolerance)) {
        firstDiff = j;
        sumDiff = sumDiff.add(diff);
      }
      maxDiff = Duration.max(maxDiff, diff);
    }
    if (firstDiff != -1) {
      System.out.println("Two time lists differ. First difference outside tolerance at line " + firstDiff);
      System.out.println("Max difference is: " + maxDiff.toString(3));
      System.out.println("Average difference is: " + sumDiff.divide(t1.size()).toString(3));
      for (int i = 0; i < Integer.max(t1.size(), t2.size()); i++) {
        System.out.println(printTimePair(
            i < t1.size() ? t1.get(i) : null,
            i < t2.size() ? t2.get(i) : null));
      }
      fail();
    }
    assertTrue(true);
  }

  private void assertSameWindowListsToWithin(List<Window> w1, List<Window> w2, Duration tolerance) {
    if (w1.size() != w2.size()) {
      System.out.println("Window lists not same size:");
      for (int i = 0; i < Integer.max(w1.size(), w2.size()); i++) {
        System.out.println(printWindowPair(
            i < w1.size() ? w1.get(i) : null,
            i < w2.size() ? w2.get(i) : null));
      }
      fail();
    }

    int firstDiff = -1;
    Duration sumDiff = Duration.ZERO_DURATION;
    Duration maxDiff = Duration.ZERO_DURATION;
    for (int j = 0; j < w1.size(); j++) {
      Duration startDiff = w1.get(j).getStart().absoluteDifference(w2.get(j).getStart());
      Duration endDiff   = w1.get(j).getEnd().absoluteDifference(w2.get(j).getEnd());
      if (startDiff.greaterThan(tolerance) || endDiff.greaterThan(tolerance)) {
        firstDiff = j;
        sumDiff = sumDiff.add(startDiff).add(endDiff);
      }
      maxDiff = Duration.max(maxDiff, startDiff, endDiff);
    }
    if (firstDiff != -1) {
      System.out.println("Two window lists differ. First difference outside tolerance at line " + firstDiff);
      System.out.println("Max difference is: " + maxDiff.toString(3));
      System.out.println("Average difference is: " + sumDiff.divide(2 * w1.size()).toString(3));
      for (int i = 0; i < Integer.max(w1.size(), w2.size()); i++) {
        System.out.println(printWindowPair(
            i < w1.size() ? w1.get(i) : null,
            i < w2.size() ? w2.get(i) : null));
      }
      fail();
    }
    assertTrue(true);
  }

  private String printTimePair(Time t1, Time t2) {
    StringBuilder out = new StringBuilder();
    out.append(t1 != null ? t1.toUTC(3) + "   " : String.join("", Collections.nCopies(24, " ")));
    if (t2 != null) out.append(t2.toUTC(3));
    return out.toString();
  }

  private String printWindowPair(Window w1, Window w2) {
    StringBuilder out = new StringBuilder();
    if (w1 != null) {
      out.append("[").append(w1.getStart().toUTC(3)).append(",").append(w1.getEnd().toUTC(3)).append("]   ");
    } else {
      out.append(String.join("", Collections.nCopies(48, " ")));
    }
    if (w2 != null) {
      out.append("[").append(w2.getStart().toUTC(3)).append(",").append(w2.getEnd().toUTC(3)).append("]");
    }
    return out.toString();
  }
}
