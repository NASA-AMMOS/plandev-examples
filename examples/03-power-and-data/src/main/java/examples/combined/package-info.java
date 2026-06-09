@MissionModel(model = Mission.class)
@MissionModel.WithMappers(CommonValueMappers.class)
@MissionModel.WithMappers(BasicValueMappers.class)
@MissionModel.WithConfiguration(Configuration.class)
@MissionModel.WithMetadata(name = "unit", annotation = gov.nasa.jpl.aerie.contrib.metadata.Unit.class)

@MissionModel.WithActivityType(TakePicture.class)
@MissionModel.WithActivityType(Downlink.class)
@MissionModel.WithActivityType(Calibrate.class)
@MissionModel.WithActivityType(ThrowDuringSim.class)
@MissionModel.WithActivityType(StressResourceProfile.class)

// Data library activities (available since Mission implements DataMissionModel)
@MissionModel.WithActivityType(GenerateData.class)
@MissionModel.WithActivityType(PlaybackData.class)
@MissionModel.WithActivityType(DeleteData.class)
@MissionModel.WithActivityType(ReprioritizeData.class)
@MissionModel.WithActivityType(ChangeDataGenerationRate.class)

package examples.combined;

import examples.combined.activities.Calibrate;
import examples.combined.activities.Downlink;
import examples.combined.activities.StressResourceProfile;
import examples.combined.activities.TakePicture;
import examples.combined.activities.ThrowDuringSim;
import gov.nasa.jpl.aerie.contrib.serialization.rulesets.BasicValueMappers;
import gov.nasa.jpl.aerie.data.activities.ChangeDataGenerationRate;
import gov.nasa.jpl.aerie.data.activities.DeleteData;
import gov.nasa.jpl.aerie.data.activities.GenerateData;
import gov.nasa.jpl.aerie.data.activities.PlaybackData;
import gov.nasa.jpl.aerie.data.activities.ReprioritizeData;
import gov.nasa.jpl.aerie.data.mappers.CommonValueMappers;
import gov.nasa.jpl.aerie.merlin.framework.annotations.MissionModel;
