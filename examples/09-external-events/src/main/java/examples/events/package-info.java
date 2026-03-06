@MissionModel(model = Mission.class)
@MissionModel.WithMappers(CommonValueMappers.class)
@MissionModel.WithMappers(BasicValueMappers.class)
@MissionModel.WithConfiguration(Configuration.class)

@MissionModel.WithActivityType(TakePicture.class)
@MissionModel.WithActivityType(Downlink.class)

// Data library activities (available since Mission implements DataMissionModel)
@MissionModel.WithActivityType(GenerateData.class)
@MissionModel.WithActivityType(PlaybackData.class)
@MissionModel.WithActivityType(DeleteData.class)

package examples.events;

import examples.events.activities.Downlink;
import examples.events.activities.TakePicture;
import gov.nasa.jpl.aerie.contrib.serialization.rulesets.BasicValueMappers;
import gov.nasa.jpl.aerie.data.activities.DeleteData;
import gov.nasa.jpl.aerie.data.activities.GenerateData;
import gov.nasa.jpl.aerie.data.activities.PlaybackData;
import gov.nasa.jpl.aerie.data.mappers.CommonValueMappers;
import gov.nasa.jpl.aerie.merlin.framework.annotations.MissionModel;
