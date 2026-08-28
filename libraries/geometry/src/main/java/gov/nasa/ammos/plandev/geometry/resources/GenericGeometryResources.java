package gov.nasa.ammos.plandev.geometry.resources;

import gov.nasa.ammos.plandev.contrib.serialization.mappers.*;
import gov.nasa.ammos.plandev.contrib.streamline.core.MutableResource;
import gov.nasa.ammos.plandev.contrib.streamline.core.Resource;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.Registrar;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.Discrete;
import gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.monads.DiscreteResourceMonad;
import gov.nasa.ammos.plandev.geometry.spiceinterpolation.Body;
import org.apache.commons.math3.geometry.euclidean.threed.Rotation;
import org.apache.commons.math3.geometry.euclidean.threed.Vector3D;

import java.util.*;

import static gov.nasa.ammos.plandev.contrib.metadata.UnitRegistrar.withUnit;
import static gov.nasa.ammos.plandev.contrib.streamline.core.MutableResource.resource;
import static gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.Discrete.discrete;
import static gov.nasa.ammos.plandev.contrib.streamline.modeling.discrete.monads.DiscreteResourceMonad.map;

public class GenericGeometryResources {

  public static final double FLOAT_EPSILON = 0.0001;
  private static Map<String, Body> bodyObjects;
  private static String[] bodies;
  private static List<String> earthSpacecraftBodies;
  private static List<String> altitudeBodies;
  private static List<String> illuminationBodies;
  private static List<String> raDecBodies;
  private static List<String> subSolarBodies;
  private static List<String> subSCBodies;
  private static List<String> betaAngleBodies;
  private static List<String> orbitParameterBodies;

  //private static String[] cartesian = new String[]{"x","y","z"};
  private static String[] illumAngles = new String[]{"phase","incidence","emission"};
  private static String[] raDecIndices = new String[]{"Ra", "Dec"};
  //private static String[] latLonCoordinates = new String[]{"latitude","longitude", "radius"};
  private static String[] subSCIndices = new String[]{"dist","latitude","longitude","radius","LST"};

  public static Map<String, String> ComplexRepresentativeStation = new HashMap<>();
  static{
    ComplexRepresentativeStation.put("Goldstone", "DSS-24");
    ComplexRepresentativeStation.put("Canberra", "DSS-36");
    ComplexRepresentativeStation.put("Madrid", "DSS-54");
  }

  public MutableResource<Discrete<Double>> upleg_time;
  public MutableResource<Discrete<Double>> downleg_time;
  public MutableResource<Discrete<Double>> spacecraftDeclination;
  public MutableResource<Discrete<Double>> spacecraftRightAscension;
  public Map<String, MutableResource<Discrete<Vector3D>>> BODY_POS_ICRF;
  public Map<String, MutableResource<Discrete<Vector3D>>> BODY_VEL_ICRF;
  public Map<String, MutableResource<Discrete<Double>>> SpacecraftBodyRange;
  public Map<String, MutableResource<Discrete<Double>>> SpacecraftBodySpeed;
  public Map<String, MutableResource<Discrete<Double>>> SunSpacecraftBodyAngle;
  public Map<String, MutableResource<Discrete<Double>>> SunBodySpacecraftAngle;
  public Map<String, MutableResource<Discrete<Double>>> BodyHalfAngleSize;

  public Map<String, MutableResource<Discrete<Double>>> BetaAngleByBody;

  public Map<String, MutableResource<Discrete<Double>>> EarthSpacecraftBodyAngle;

  public MutableResource<Discrete<Double>> EarthSunProbeAngle;

  public Map<String, MutableResource<Discrete<Double>>> SpacecraftAltitude;

  public Map<String, Map<String, MutableResource<Discrete<Double>>>> IlluminationAnglesByBody;

  public Map<String, Map<String, MutableResource<Discrete<Double>>>> EarthRaDecByBody;

  public Map<String, MutableResource<Discrete<Double>>> EarthRaDeltaWithSCByBody;

  public Map<String, MutableResource<Discrete<Vector3D>>> BodySubSolarPoint;
  public Map<String, Map<String, MutableResource<Discrete<Double>>>> BodySubSCPoint;

  public Map<String, MutableResource<Discrete<EclipseTypes>>> SpacecraftEclipseByBody;
  public MutableResource<Discrete<EclipseTypes>> AnySpacecraftEclipse;

  public Map<String, Map<String, MutableResource<Discrete<Boolean>>>> SpacecraftOccultationByBodyAndStation;
  public MutableResource<Discrete<Integer>> Occultation;
  public MutableResource<Discrete<Double>> FractionOfSunNotInEclipse;
  public MutableResource<Discrete<Integer>> LitOrDarkSide;

  public Map<String, MutableResource<Discrete<Double>>> orbitInclinationByBody;
  public Map<String, MutableResource<Discrete<Double>>> orbitPeriodByBody;


  public Map<String, MutableResource<Discrete<Boolean>>> Periapsis;
  public Map<String, MutableResource<Discrete<Boolean>>> Apoapsis;

  /** Spacecraft attitude quaternion (J2000 → spacecraft body frame) for bodies with calculateAttitude=true */
  public MutableResource<Discrete<Rotation>> spacecraftAttitude;

  public static DoubleValueMapper dvm = new DoubleValueMapper();
  public static BooleanValueMapper bvm = new BooleanValueMapper();
  public static IntegerValueMapper ivm = new IntegerValueMapper();

  public GenericGeometryResources(Registrar registrar, Map<String, Body> allBodies) {
    bodyObjects = allBodies;
    bodies = Body.getNamesOfBodies(allBodies);
    earthSpacecraftBodies =  Body.getEarthSCBodies(allBodies);
    altitudeBodies = Body.getAltitudeBodies(allBodies);
    illuminationBodies = Body.getIlluminationAngleBodies(allBodies);
    raDecBodies = Body.getRaDecBodies(allBodies);
    subSolarBodies = Body.getSubSolarBodies(allBodies);
    subSCBodies = Body.getRadiatorAvoidanceBodies(allBodies);
    betaAngleBodies = Body.getBetaAngleBodies(allBodies);
    orbitParameterBodies = Body.getOrbitParameterBodies(allBodies);

    // Initialize resources
    BODY_POS_ICRF = new HashMap<>();
    BODY_VEL_ICRF = new HashMap<>();
    SpacecraftBodyRange = new HashMap<>();
    SpacecraftBodySpeed = new HashMap<>();
    SunSpacecraftBodyAngle = new HashMap<>();
    SunBodySpacecraftAngle = new HashMap<>();
    BodyHalfAngleSize = new HashMap<>();
    IlluminationAnglesByBody = new HashMap<>();
    EarthRaDecByBody = new HashMap<>();
    BodySubSCPoint = new HashMap<>();
    SpacecraftOccultationByBodyAndStation = new HashMap<>();
    SpacecraftEclipseByBody = new HashMap<>();
    BetaAngleByBody = new HashMap<>();
    EarthSpacecraftBodyAngle = new HashMap<>();
    SpacecraftAltitude = new HashMap<>();
    EarthRaDeltaWithSCByBody = new HashMap<>();
    BodySubSolarPoint = new HashMap<>();
    orbitInclinationByBody = new HashMap<>();
    orbitPeriodByBody = new HashMap<>();

    Apoapsis = new HashMap<>();
    Periapsis = new HashMap<>();

    // Non-arrayed resources
    upleg_time = resource(discrete(0.0));
    registrar.discrete("upleg_time", upleg_time, dvm);

    downleg_time = resource(discrete(0.0));
    registrar.discrete("downleg_time", downleg_time, dvm);

    spacecraftDeclination = resource(discrete(0.0));
    registrar.discrete("spacecraftDeclination", spacecraftDeclination, dvm);

    spacecraftRightAscension = resource(discrete(0.0));
    registrar.discrete("spacecraftRightAscension", spacecraftRightAscension, dvm);

    EarthSunProbeAngle = resource(discrete(0.0));
    registrar.discrete("EarthSunProbeAngle", EarthSunProbeAngle, dvm);

    AnySpacecraftEclipse = resource(discrete(EclipseTypes.NONE));
    registrar.discrete("AnySpacecraftEclipse", AnySpacecraftEclipse, new EnumValueMapper(EclipseTypes.class));

    Occultation = resource(discrete(0));
    registrar.discrete("Occultation", Occultation, ivm);

    FractionOfSunNotInEclipse = resource(discrete(1.0));
    registrar.discrete("FractionOfSunNotInEclipse", FractionOfSunNotInEclipse, dvm);

    LitOrDarkSide = resource(discrete(0));
    registrar.discrete("LitOrDarkSide", LitOrDarkSide, ivm);

    // Spacecraft attitude quaternion (identity = no rotation from J2000)
    spacecraftAttitude = resource(discrete(Rotation.IDENTITY));
    registerRotation(registrar, "spacecraftAttitude", spacecraftAttitude);

    // loop through bodies to build and register arrayed resources
    for (String body : bodies) {
      BODY_POS_ICRF.put(body, resource(discrete( new Vector3D(0.0,0.0,0.0))));
      registerVector(registrar, "BODY_POS_ICRF_" + body, BODY_POS_ICRF.get(body));

      BODY_VEL_ICRF.put(body, resource(discrete( new Vector3D(0.0,0.0,0.0))));
      registerVector(registrar, "BODY_VEL_ICRF_" + body, BODY_VEL_ICRF.get(body));

      SpacecraftBodyRange.put(body, resource(discrete(0.0)));
      registrar.discrete("SpacecraftBodyRange_" + body, SpacecraftBodyRange.get(body), withUnit("km", dvm));

      SpacecraftBodySpeed.put(body, resource(discrete(0.0)));
      registrar.discrete("SpacecraftBodySpeed_" + body, SpacecraftBodySpeed.get(body), withUnit("km/s", dvm));

      SunSpacecraftBodyAngle.put(body, resource(discrete(0.0)));
      registrar.discrete("SunSpacecraftBodyAngle_" + body, SunSpacecraftBodyAngle.get(body), withUnit("deg", dvm));

      SunBodySpacecraftAngle.put(body, resource(discrete(0.0)));
      registrar.discrete("SunBodySpacecraftAngle_" + body, SunBodySpacecraftAngle.get(body), withUnit("deg", dvm));

      BodyHalfAngleSize.put(body, resource(discrete(0.0)));
      registrar.discrete("BodyHalfAngleSize_" + body, BodyHalfAngleSize.get(body), withUnit("deg", dvm));

      if (betaAngleBodies.contains(body)) {
        BetaAngleByBody.put(body, resource(discrete(0.0)));
        registrar.discrete("BetaAngle_" + body, BetaAngleByBody.get(body), withUnit("deg", dvm));
      }

      if (earthSpacecraftBodies.contains(body)) {
        EarthSpacecraftBodyAngle.put(body, resource(discrete(0.0)));
        registrar.discrete("EarthSpacecraftAngle_" + body, EarthSpacecraftBodyAngle.get(body), withUnit("deg", dvm));
      }

      if (altitudeBodies.contains(body)) {
        SpacecraftAltitude.put(body, resource(discrete(0.0)));
        registrar.discrete("SpacecraftAltitude_" + body, SpacecraftAltitude.get(body), withUnit("km", dvm));
      }

      if (illuminationBodies.contains(body)) {
        Map<String, MutableResource<Discrete<Double>>> illumAnglesMap = new HashMap<>();
        for (String angle : illumAngles) {
          illumAnglesMap.put(angle, resource(discrete(0.0)));
          registrar.discrete("IlluminationAnglesByBody_" + body + "_" + angle,
            illumAnglesMap.get(angle), withUnit("deg", dvm));
        }
        IlluminationAnglesByBody.put(body, illumAnglesMap);
      }

      if (raDecBodies.contains(body)) {
        Map<String, MutableResource<Discrete<Double>>> EarthRaDecMap = new HashMap<>();
        for (String angle : raDecIndices) {
          EarthRaDecMap.put(angle, resource(discrete(0.0)));
          registrar.discrete("EarthRaDecByBody_" + body + "_" + angle,
            EarthRaDecMap.get(angle), withUnit("deg", dvm));
        }
        EarthRaDecByBody.put(body, EarthRaDecMap);
        EarthRaDeltaWithSCByBody.put(body, resource(discrete(0.0)));
        registrar.discrete("EarthRaDeltaWithSCByBody_" + body, EarthRaDeltaWithSCByBody.get(body), withUnit("deg", dvm));
      }

      if (subSolarBodies.contains(body)) {
        BodySubSolarPoint.put(body, resource(discrete( new Vector3D(0.0,0.0,0.0))));
        registerVector(registrar, "BodySubSolarPoint_" + body, BodySubSolarPoint.get(body));
      }

      if (subSCBodies.contains(body)) {
        Map<String, MutableResource<Discrete<Double>>> subSCMap = new HashMap<>();
        for (String index : subSCIndices) {
          subSCMap.put(index, resource(discrete(0.0)));
          registrar.discrete("subSCBodies_" + body + "_" + index,
            subSCMap.get(index), dvm);
        }
        BodySubSCPoint.put(body, subSCMap);
      }

      SpacecraftEclipseByBody.put(body, resource(discrete(EclipseTypes.NONE)));
      registrar.discrete("SpacecraftEclipseByBody_" + body,
        SpacecraftEclipseByBody.get(body), new EnumValueMapper<>(EclipseTypes.class));

      Map<String, MutableResource<Discrete<Boolean>>> occultationStationMap = new HashMap<>();
      for (Map.Entry<String,String> entry : ComplexRepresentativeStation.entrySet()) {
        occultationStationMap.put(entry.getValue(), resource(discrete(false)));
        registrar.discrete("IlluminationAnglesByBody_" + body + "_" + entry.getKey(),
          occultationStationMap.get(entry.getValue()), bvm);
      }
      SpacecraftOccultationByBodyAndStation.put(body, occultationStationMap);

      if (orbitParameterBodies.contains(body)) {
        orbitInclinationByBody.put(body, resource(discrete(0.0)));
        registrar.discrete("orbitInclinationByBody_" + body, orbitInclinationByBody.get(body), withUnit("deg", dvm));

        orbitPeriodByBody.put(body, resource(discrete(0.0)));
        registrar.discrete("orbitPeriodByBody_" + body, orbitPeriodByBody.get(body), withUnit("s", dvm));
      }

      Periapsis.put(body, resource(discrete(false)));
      registrar.discrete("Periapsis_" + body, Periapsis.get(body), bvm);

      Apoapsis.put(body, resource(discrete(false)));
      registrar.discrete("Apoapsis_" + body, Apoapsis.get(body), bvm);
    }

  }
  public static void registerVector(Registrar registrar, String name, Resource<Discrete<Vector3D>> r) {
    registrar.discrete(name + "_X", map(r, v -> v == null ? null : v.getX()), dvm);
    registrar.discrete(name + "_Y", map(r, v -> v == null ? null : v.getY()), dvm);
    registrar.discrete(name + "_Z", map(r, v -> v == null ? null : v.getZ()), dvm);
    registrar.discrete(name + "_magnitude", map(r, v -> v == null ? null : Math.sqrt(v.getX() * v.getX() + v.getY() * v.getY() + v.getZ() * v.getZ())), dvm);
  }

  public static void registerRotation(Registrar registrar, String name, Resource<Discrete<Rotation>> rotationResource) {
      registrar.discrete(name + ".Q0",  DiscreteResourceMonad.map(rotationResource, (r) -> r.getQ0()), dvm);
      registrar.discrete(name + ".Q1",  DiscreteResourceMonad.map(rotationResource, (r) -> r.getQ1()), dvm);
      registrar.discrete(name + ".Q2",  DiscreteResourceMonad.map(rotationResource, (r) -> r.getQ2()), dvm);
      registrar.discrete(name + ".Q3",  DiscreteResourceMonad.map(rotationResource, (r) -> r.getQ3()), dvm);
  }

  public static Map<String, Body> getBodies(){
    return bodyObjects;
  }


}
