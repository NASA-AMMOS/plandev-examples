@MissionModel(model = Mission.class)
@WithMappers(BasicValueMappers.class)
@WithMappers(CustomValueMappers.class)
@WithConfiguration(Configuration.class)

// Comment out SolarArrayDeployment when using RTG model
@WithActivityType(SolarArrayDeployment.class)
@WithActivityType(TurnOnCamera.class)
@WithActivityType(TurnOnTelecom.class)
@WithActivityType(ChangeGNCState.class)
@WithActivityType(Drive.class)

package examples.power;

import examples.power.activities.ChangeGNCState;
import examples.power.activities.Drive;
import examples.power.activities.SolarArrayDeployment;
import examples.power.activities.TurnOnTelecom;
import examples.power.activities.TurnOnCamera;
import gov.nasa.jpl.aerie.contrib.serialization.rulesets.BasicValueMappers;
import gov.nasa.jpl.aerie.merlin.framework.annotations.MissionModel;
import gov.nasa.jpl.aerie.merlin.framework.annotations.MissionModel.WithActivityType;
import gov.nasa.jpl.aerie.merlin.framework.annotations.MissionModel.WithConfiguration;
import gov.nasa.jpl.aerie.merlin.framework.annotations.MissionModel.WithMappers;
