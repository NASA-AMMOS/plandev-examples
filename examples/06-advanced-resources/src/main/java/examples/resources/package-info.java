@MissionModel(model = Mission.class)
@WithMappers(BasicValueMappers.class)
@WithConfiguration(Configuration.class)

@WithActivityType(StartInstrument.class)
@WithActivityType(StopInstrument.class)
@WithActivityType(ResetTimer.class)

package examples.resources;

import examples.resources.activities.StartInstrument;
import examples.resources.activities.StopInstrument;
import examples.resources.activities.ResetTimer;
import gov.nasa.jpl.aerie.contrib.serialization.rulesets.BasicValueMappers;
import gov.nasa.jpl.aerie.merlin.framework.annotations.MissionModel;
import gov.nasa.jpl.aerie.merlin.framework.annotations.MissionModel.WithActivityType;
import gov.nasa.jpl.aerie.merlin.framework.annotations.MissionModel.WithConfiguration;
import gov.nasa.jpl.aerie.merlin.framework.annotations.MissionModel.WithMappers;
