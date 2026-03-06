package gov.nasa.jpl.aerie.geometry.spiceinterpolation;

import gov.nasa.jpl.time.Duration;
import gov.nasa.jpl.time.Time;
import gov.nasa.jpl.aerie.geometry.globals.AbsoluteClock;
import gov.nasa.jpl.aerie.geometry.globals.JPLTimeConvertUtility;
import gov.nasa.jpl.aerie.geometry.interfaces.GeometryCalculator;
import gov.nasa.jpl.aerie.geometry.interfaces.GeometryInformationNotAvailableException;
import gov.nasa.jpl.aerie.geometry.resources.GenericGeometryResources;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import static gov.nasa.jpl.aerie.merlin.framework.ModelActions.delay;

public class BodyGeometryGenerator {
  private String bodyName;
  private GeometryCalculator geoCalc;
  private VariableTimeStepGenerator stepGenerator;
  private HashMap<String, Body> bodies;
  public static PrintWriter pw;
  private FileWriter fileWriter = null;
  private boolean writeTimestepFile;

  private final AbsoluteClock absoluteClock;

  public BodyGeometryGenerator(AbsoluteClock absoluteClock, GenericGeometryResources geometryResources, Time t, String bodyName, double precision, Duration minStep, Duration maxStep, String timestepFile, GeometryCalculator geoCalc, HashMap<String, Body> bodies) {
    this.absoluteClock = absoluteClock;
    this.bodyName = bodyName;
    this.geoCalc = geoCalc;
    List<String> bodyNames = new ArrayList<>();
    bodyNames.add(bodyName);
    this.stepGenerator = new VariableTimeStepGenerator(absoluteClock, geometryResources, bodyNames, precision, minStep, maxStep, t);
    this.bodies = bodies;
    this.writeTimestepFile = timestepFile != null && !timestepFile.equals("");
  }

  public void model(){
    while (true) {
      try {
        geoCalc.calculateGeometry(bodies.get(bodyName));
      } catch (GeometryInformationNotAvailableException e) {
        e.printStackTrace();
      }
      Map.Entry<String, Time> nextTimeAndBody = stepGenerator.nextTimeToJumpToAndItsBody(bodyName);

      delay( JPLTimeConvertUtility.getDuration(
          nextTimeAndBody.getValue().minus( JPLTimeConvertUtility.nowJplTime(absoluteClock))));
    }
  }
}
