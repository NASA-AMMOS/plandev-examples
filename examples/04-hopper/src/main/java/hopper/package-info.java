@MissionModel(model = Mission.class)
@WithMappers(CommonValueMappers.class)
@WithMappers(BasicValueMappers.class)
@WithConfiguration(Configuration.class)
@WithMetadata(name = "unit", annotation = gov.nasa.ammos.plandev.contrib.metadata.Unit.class)
@WithSubsystem("mobility")
@WithSubsystem("payload")
@WithSubsystem("telecom")
@WithSubsystem("data")

@WithActivityType(PerformHop.class)
@WithActivityType(TakePicture.class)
@WithActivityType(Downlink.class)
@WithActivityType(PlaybackData.class)
@WithActivityType(DeleteData.class)

package hopper;

import hopper.activities.PerformHop;
import hopper.activities.TakePicture;
import hopper.activities.Downlink;
import gov.nasa.ammos.plandev.data.activities.PlaybackData;
import gov.nasa.ammos.plandev.data.activities.DeleteData;
import gov.nasa.ammos.plandev.contrib.serialization.rulesets.BasicValueMappers;
import gov.nasa.ammos.plandev.data.mappers.CommonValueMappers;
import gov.nasa.ammos.plandev.merlin.framework.annotations.MissionModel;
import gov.nasa.ammos.plandev.merlin.framework.annotations.MissionModel.WithActivityType;
import gov.nasa.ammos.plandev.merlin.framework.annotations.MissionModel.WithConfiguration;
import gov.nasa.ammos.plandev.merlin.framework.annotations.MissionModel.WithMappers;
import gov.nasa.ammos.plandev.merlin.framework.annotations.MissionModel.WithMetadata;
import gov.nasa.ammos.plandev.merlin.framework.annotations.MissionModel.WithSubsystem;

