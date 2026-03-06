@MissionModel(model = Mission.class)
@MissionModel.WithMappers(CommonValueMappers.class)
@MissionModel.WithMappers(BasicValueMappers.class)
@MissionModel.WithConfiguration(Configuration.class)

@MissionModel.WithActivityType(ChangeDataGenerationRate.class)
@MissionModel.WithActivityType(DeleteData.class)
@MissionModel.WithActivityType(GenerateData.class)
@MissionModel.WithActivityType(PlaybackData.class)
@MissionModel.WithActivityType(ReprioritizeData.class)

@MissionModel.WithActivityType(SetPlaybackDataRate.class)
@MissionModel.WithActivityType(SetMaxVolume.class)

package examples.data;

import gov.nasa.jpl.aerie.contrib.serialization.rulesets.BasicValueMappers;
import gov.nasa.jpl.aerie.merlin.framework.annotations.MissionModel;
import examples.data.activities.*;
import gov.nasa.jpl.aerie.data.activities.*;
import gov.nasa.jpl.aerie.data.mappers.CommonValueMappers;
