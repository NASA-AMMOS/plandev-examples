package gov.nasa.ammos.plandev.data.mappers;

import gov.nasa.ammos.plandev.merlin.framework.Result;
import gov.nasa.ammos.plandev.merlin.framework.ValueMapper;
import gov.nasa.ammos.plandev.merlin.protocol.types.SerializedValue;
import gov.nasa.ammos.plandev.merlin.protocol.types.ValueSchema;
import gov.nasa.ammos.plandev.data.utils.Instants;

import java.time.Instant;
import java.util.function.Function;

public class InstantValueMapper implements ValueMapper<Instant> {

  @Override
  public ValueSchema getValueSchema() {
    return ValueSchema.STRING;
  }

  @Override
  public Result<Instant, String> deserializeValue(SerializedValue serializedValue) {
    return serializedValue
        .asString()
        .map(
            (Function<String, Result<Instant, String>>)
                (String x) -> Result.success(Instant.from(Instants.parseFromDOYString(x))))
        .orElseGet(() -> Result.failure("Expected real number, got " + serializedValue.toString()));
  }

  @Override
  public SerializedValue serializeValue(Instant value) {
    return SerializedValue.of(Instants.formatToDOYString(value));
  }
}
