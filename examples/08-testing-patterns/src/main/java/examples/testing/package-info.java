@MissionModel(model = Mission.class)
@WithMappers(BasicValueMappers.class)
@WithConfiguration(Configuration.class)

@WithActivityType(DrainBattery.class)
@WithActivityType(CollectData.class)

package examples.testing;

import gov.nasa.jpl.aerie.contrib.serialization.rulesets.BasicValueMappers;
import gov.nasa.jpl.aerie.merlin.framework.annotations.MissionModel;
import gov.nasa.jpl.aerie.merlin.framework.annotations.MissionModel.WithActivityType;
import gov.nasa.jpl.aerie.merlin.framework.annotations.MissionModel.WithConfiguration;
import gov.nasa.jpl.aerie.merlin.framework.annotations.MissionModel.WithMappers;
