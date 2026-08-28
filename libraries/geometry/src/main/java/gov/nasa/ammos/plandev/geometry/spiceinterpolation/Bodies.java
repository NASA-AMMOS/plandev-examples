package gov.nasa.ammos.plandev.geometry.spiceinterpolation;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

import java.io.IOException;
import java.io.InputStreamReader;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

import static gov.nasa.ammos.plandev.geometry.config.ConfigObject.jsonObjHasKey;

public class Bodies {

  private JsonObject bodiesJsonObject;
  private HashMap<String, Body> bodies;

  /**
   * The resourceAnchorClass parameter is used to locate the default_geometry_config.json resource.
   * In the original code, this was hardcoded to Mission.class. Now it must be provided by the caller
   * (typically the Mission class or any class whose package contains the JSON resource).
   */
  private final Class<?> resourceAnchorClass;

  public Bodies(Class<?> resourceAnchorClass) {
    this.resourceAnchorClass = resourceAnchorClass;
    this.bodiesJsonObject = parseBodiesFromJson();
    this.bodies = initializeAllBodiesFromJson(this.bodiesJsonObject);
  }

  public HashMap<String, Body> getBodiesMap(){
    return bodies;
  }

  public JsonObject getBodiesJson(){
    return bodiesJsonObject;
  }

  private JsonObject parseBodiesFromJson() {
    try (
      var in = Objects.requireNonNull(resourceAnchorClass.getResourceAsStream("default_geometry_config.json"), "default_geometry_config.json not found");
      var reader = new InputStreamReader(in)
    ) {
      return JsonParser.parseReader(reader).getAsJsonObject();
    } catch (IOException e) {
      throw new RuntimeException(e);
    }
  }

  public HashMap<String, Body> initializeAllBodiesFromJson(JsonObject bodiesJson){
    HashMap<String, Body> toReturn = new HashMap<>();
    JsonObject jsonObject = bodiesJson.get("bodies").getAsJsonObject();

    Set<Map.Entry<String, JsonElement>> entrySet = jsonObject.entrySet();
    for(Map.Entry<String, JsonElement> entry : entrySet){
      JsonObject body = entry.getValue().getAsJsonObject();
      if(jsonObjHasKey(body, "Trajectory")) {
        JsonObject trajectory = body.get("Trajectory").getAsJsonObject();
        String spacecraftFrame = trajectory.has("spacecraftFrame") && !trajectory.get("spacecraftFrame").isJsonNull()
          ? trajectory.get("spacecraftFrame").getAsString() : null;
        toReturn.put(entry.getKey(), new Body(entry.getKey(),
          body.get("NaifID").getAsInt(),
          body.get("NaifFrame").getAsString(),
          body.get("Albedo").getAsDouble(),
          getIfNonNull(trajectory, "calculateAltitude"),
          getIfNonNull(trajectory, "calculateEarthSpacecraftBodyAngle"),
          getIfNonNull(trajectory, "calculateSubSCInformation"),
          getIfNonNull(trajectory, "calculateRaDec"),
          getIfNonNull(trajectory, "calculateIlluminationAngles"),
          getIfNonNull(trajectory, "calculateSubSolarInformation"),
          getIfNonNull(trajectory, "calculateLST"),
          getIfNonNull(trajectory, "calculateBetaAngle"),
          getIfNonNull(trajectory, "calculateOrbitParameters"),
          getIfNonNull(trajectory, "useDSK"),
          getIfNonNull(trajectory, "calculateAttitude"),
          spacecraftFrame));
      }
      else{
        toReturn.put(entry.getKey(), new Body(entry.getKey(),
          body.get("NaifID").getAsInt(),
          body.get("NaifFrame").getAsString(),
          body.get("Albedo").getAsDouble()
        ));
      }
    }

    return toReturn;
  }

  private boolean getIfNonNull(JsonObject obj, String key){
    return obj.get(key) != null && !obj.get(key).isJsonNull() ? obj.get(key).getAsBoolean() : false;
  }

}
