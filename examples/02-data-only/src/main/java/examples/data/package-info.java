/**
 * Data-only example mission model — exercises {@code libraries/data}.
 *
 * Initially derived from NASA-AMMOS/aerie-simple-model-data (the {@code demo/} subdir).
 * See ATTRIBUTION.md at the repo root for the full directory-to-source mapping.
 */
@MissionModel(model = Mission.class)
@MissionModel.WithMappers(CommonValueMappers.class)
@MissionModel.WithMappers(BasicValueMappers.class)
@MissionModel.WithConfiguration(Configuration.class)
@MissionModel.WithMetadata(name = "unit", annotation = gov.nasa.jpl.aerie.contrib.metadata.Unit.class)

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
