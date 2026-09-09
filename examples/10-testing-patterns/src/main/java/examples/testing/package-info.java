@MissionModel(model = Mission.class)
@WithMappers(BasicValueMappers.class)
@WithConfiguration(Configuration.class)

@WithActivityType(DrainBattery.class)
@WithActivityType(CollectData.class)

package examples.testing;

import gov.nasa.ammos.plandev.contrib.serialization.rulesets.BasicValueMappers;
import gov.nasa.ammos.plandev.merlin.framework.annotations.MissionModel;
import gov.nasa.ammos.plandev.merlin.framework.annotations.MissionModel.WithActivityType;
import gov.nasa.ammos.plandev.merlin.framework.annotations.MissionModel.WithConfiguration;
import gov.nasa.ammos.plandev.merlin.framework.annotations.MissionModel.WithMappers;
