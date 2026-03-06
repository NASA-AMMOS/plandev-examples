package examples.power;

import examples.power.activities.TurnOnTelecom;
import examples.power.generated.activities.TurnOnTelecomMapper;
import org.junit.jupiter.api.Test;

class TurnOnTelecomTest {
    private final TurnOnTelecomMapper mapper;

    public TurnOnTelecomTest() {
        this.mapper = new TurnOnTelecomMapper();
    }

    @Test
    public void testDefaultSerializationDoesNotThrow() {
        this.mapper.getInputType().getArguments(new TurnOnTelecom());
    }
}
