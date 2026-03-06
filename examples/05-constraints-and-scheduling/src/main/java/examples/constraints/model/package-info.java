@MissionModel(model = Mission.class)
@MissionModel.WithMappers(CommonValueMappers.class)
@MissionModel.WithMappers(BasicValueMappers.class)
@MissionModel.WithConfiguration(Configuration.class)

@MissionModel.WithActivityType(TakePicture.class)
@MissionModel.WithActivityType(Downlink.class)
@MissionModel.WithActivityType(Calibrate.class)

// Data library activities
@MissionModel.WithActivityType(GenerateData.class)
@MissionModel.WithActivityType(PlaybackData.class)
@MissionModel.WithActivityType(DeleteData.class)

package examples.constraints.model;

import examples.constraints.model.activities.Calibrate;
import examples.constraints.model.activities.Downlink;
import examples.constraints.model.activities.TakePicture;
import gov.nasa.jpl.aerie.contrib.serialization.rulesets.BasicValueMappers;
import gov.nasa.jpl.aerie.data.activities.DeleteData;
import gov.nasa.jpl.aerie.data.activities.GenerateData;
import gov.nasa.jpl.aerie.data.activities.PlaybackData;
import gov.nasa.jpl.aerie.data.mappers.CommonValueMappers;
import gov.nasa.jpl.aerie.merlin.framework.annotations.MissionModel;
