package gov.nasa.ammos.plandev.geometry.spiceinterpolation;

import com.google.gson.*;

import gov.nasa.ammos.plandev.contrib.streamline.modeling.Registrar;
import gov.nasa.jpl.time.Duration;
import gov.nasa.jpl.time.EpochRelativeTime;
import gov.nasa.jpl.time.Time;
import gov.nasa.ammos.plandev.geometry.globals.AbsoluteClock;
import gov.nasa.ammos.plandev.geometry.globals.JPLTimeConvertUtility;
import gov.nasa.ammos.plandev.geometry.globals.Window;
import gov.nasa.ammos.plandev.geometry.resources.GenericGeometryResources;

import java.util.*;

import static gov.nasa.ammos.plandev.merlin.framework.ModelActions.spawn;
import static gov.nasa.ammos.plandev.geometry.config.ConfigObject.jsonObjHasKey;
import static gov.nasa.ammos.plandev.geometry.config.RecursiveConfigAccess.getArbitraryJSON;

public class SpiceResourcePopulater {
  private Window[] dataGaps;
  private Duration paddingAroundDataGaps;
  private JsonObject bodiesJsonObject;
  private HashMap<String, Body> bodies;
  private GenericGeometryCalculator geoCalc;

  private AbsoluteClock absClock;

  /**
   * @param geoCalc The geometry calculator to use
   * @param absoluteClock The absolute clock for time conversion
   * @param dataGaps Array of windows representing data gaps
   * @param paddingAroundDataGaps Duration of padding around data gaps
   * @param resourceAnchorClass The class whose package contains default_geometry_config.json
   */
  public SpiceResourcePopulater(GenericGeometryCalculator geoCalc, AbsoluteClock absoluteClock, Window[] dataGaps, Duration paddingAroundDataGaps, Class<?> resourceAnchorClass) {
    Bodies bodiesObj = new Bodies(resourceAnchorClass);
    this.bodiesJsonObject = bodiesObj.getBodiesJson();
    this.bodies = bodiesObj.getBodiesMap();
    this.geoCalc = geoCalc;
    this.absClock = absoluteClock;
    this.geoCalc.setBodies(this.bodies);
    this.dataGaps = dataGaps;
    this.paddingAroundDataGaps = paddingAroundDataGaps;
  }

  public void setDataGaps(Window[] newGaps, Duration newPadding) {
    dataGaps = newGaps;
    paddingAroundDataGaps = newPadding;
  }

  public void calculateTimeDependentInformation(){
    for(Body body : bodies.values()){
      List<CalculationPeriod> calculationPeriods = getCalculationPeriods(body.getName(), "Trajectory");
      for(CalculationPeriod calculationPeriod : calculationPeriods) {
        BodyGeometryGenerator bodyGeoGenerator = new BodyGeometryGenerator(
          absClock, geoCalc.getResources(), JPLTimeConvertUtility.jplTimeFromUTCInstant(absClock.now()), body.getName(),
          calculationPeriod.getThreshold(), calculationPeriod.getMinTimeStep(), calculationPeriod.getMaxTimeStep(), "", geoCalc, bodies);
        spawn(bodyGeoGenerator::model);
      }
    }
  }

  public HashMap<String, Body> getBodies(){
    return bodies;
  }

  private static Window[] getWindowsWithData(Time begin, Time end, Window[] gaps, Duration paddingAroundDataGaps){
    // potentially need to splice up calculation window into multiple smaller windows to cut out around periods where SPKs or other input files don't have relevant information
    List<Window> paddedWindowsWithData = new ArrayList<>();
    Window[] unpaddedWindowsWithData = Window.and(new Window[]{new Window(begin, end)}, Window.not(gaps, begin, end));
    for(Window w : unpaddedWindowsWithData){
      paddedWindowsWithData.add(new Window(
        w.getStart().equals(begin) ? w.getStart() : w.getStart().add(paddingAroundDataGaps),
        w.getEnd().equals(end)     ? w.getEnd()   : w.getEnd().subtract(paddingAroundDataGaps)
      ));
    }
    return paddedWindowsWithData.toArray(new Window[paddedWindowsWithData.size()]);
  }

  public List<CalculationPeriod> getCalculationPeriods(String bodyname, String geometryType){
    List<CalculationPeriod> toReturn = new ArrayList<>();
    List<String> indices = Arrays.asList("bodies", bodyname, geometryType, "calculationPeriods");
    JsonElement calculationPeriods = getArbitraryJSON(bodiesJsonObject, indices);
    if(calculationPeriods != null) {
      for (JsonElement period : calculationPeriods.getAsJsonArray()) {
        JsonObject periodStruct = period.getAsJsonObject();
        for (Window dataWindow : getWindowsWithData(EpochRelativeTime.getAbsoluteOrRelativeTime(periodStruct.get("begin").getAsString()), EpochRelativeTime.getAbsoluteOrRelativeTime(periodStruct.get("end").getAsString()), dataGaps, paddingAroundDataGaps)) {
          Duration minTimeStep = jsonObjHasKey(periodStruct, "minTimeStep") ? new Duration(periodStruct.get("minTimeStep").getAsString()) : Duration.SECOND_DURATION;
          Duration maxTimeStep = jsonObjHasKey(periodStruct, "maxTimeStep") ? new Duration(periodStruct.get("maxTimeStep").getAsString()) : Duration.DAY_DURATION;
          double threshold =     jsonObjHasKey(periodStruct, "threshold")   ? periodStruct.get("threshold").getAsDouble() : 0.0;

          toReturn.add(new CalculationPeriod(new Time(dataWindow.getStart()), new Time(dataWindow.getEnd()),
            minTimeStep, maxTimeStep, threshold));
        }
      }
    }
    return toReturn;
  }

}
