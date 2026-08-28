/**
 * Mission model for the tutorial walk-through.
 *
 * Initially derived from NASA-AMMOS/aerie-modeling-tutorial. See ATTRIBUTION.md at
 * the repo root for the full directory-to-source mapping.
 */
@MissionModel(model = Mission.class)
@WithMappers(BasicValueMappers.class)
@WithConfiguration(Configuration.class)

@WithActivityType(CollectData.class)
@WithActivityType(ChangeMagMode.class)

package tutorial;

import gov.nasa.ammos.plandev.contrib.serialization.rulesets.BasicValueMappers;
import gov.nasa.ammos.plandev.merlin.framework.annotations.ActivityType;
import gov.nasa.ammos.plandev.merlin.framework.annotations.MissionModel;
import gov.nasa.ammos.plandev.merlin.framework.annotations.MissionModel.WithActivityType;
import gov.nasa.ammos.plandev.merlin.framework.annotations.MissionModel.WithConfiguration;
import gov.nasa.ammos.plandev.merlin.framework.annotations.MissionModel.WithMappers;
