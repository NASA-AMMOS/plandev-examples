@MissionModel(model = Mission.class)
@WithMappers(CommonValueMappers.class)
@WithMappers(BasicValueMappers.class)
@WithConfiguration(Configuration.class)

@WithActivityType(PerformHop.class)
@WithActivityType(TakePicture.class)

package hopper;

import hopper.activities.PerformHop;
import hopper.activities.TakePicture;
import gov.nasa.jpl.aerie.contrib.serialization.rulesets.BasicValueMappers;
import gov.nasa.jpl.aerie.data.mappers.CommonValueMappers;
import gov.nasa.jpl.aerie.merlin.framework.annotations.MissionModel;
import gov.nasa.jpl.aerie.merlin.framework.annotations.MissionModel.WithActivityType;
import gov.nasa.jpl.aerie.merlin.framework.annotations.MissionModel.WithConfiguration;
import gov.nasa.jpl.aerie.merlin.framework.annotations.MissionModel.WithMappers;

