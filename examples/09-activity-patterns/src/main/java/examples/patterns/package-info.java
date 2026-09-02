@MissionModel(model = Mission.class)
@WithMappers(BasicValueMappers.class)
@WithConfiguration(Configuration.class)

@WithActivityType(StateMachineActivity.class)
@WithActivityType(ConditionalActivity.class)
@WithActivityType(LoopedActivity.class)
@WithActivityType(ParallelActivities.class)
@WithActivityType(DelayPatterns.class)
@WithActivityType(ResourceGatedActivity.class)
@WithActivityType(DurationLimitedActivity.class)
@WithActivityType(ConfigurationDrivenActivity.class)
@WithActivityType(DiscreteVsLinearActivity.class)

package examples.patterns;

import examples.patterns.activities.StateMachineActivity;
import examples.patterns.activities.ConditionalActivity;
import examples.patterns.activities.LoopedActivity;
import examples.patterns.activities.ParallelActivities;
import examples.patterns.activities.DelayPatterns;
import examples.patterns.activities.ResourceGatedActivity;
import examples.patterns.activities.DurationLimitedActivity;
import examples.patterns.activities.ConfigurationDrivenActivity;
import examples.patterns.activities.DiscreteVsLinearActivity;
import gov.nasa.ammos.plandev.contrib.serialization.rulesets.BasicValueMappers;
import gov.nasa.ammos.plandev.merlin.framework.annotations.MissionModel;
import gov.nasa.ammos.plandev.merlin.framework.annotations.MissionModel.WithActivityType;
import gov.nasa.ammos.plandev.merlin.framework.annotations.MissionModel.WithConfiguration;
import gov.nasa.ammos.plandev.merlin.framework.annotations.MissionModel.WithMappers;
