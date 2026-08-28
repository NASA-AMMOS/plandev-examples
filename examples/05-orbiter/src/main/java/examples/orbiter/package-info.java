/**
 * Mars-orbiter-style mission model — integrates power, data, geometry, telecom, and radar subsystems.
 *
 * Initially derived from NASA-AMMOS/aerie-orbiter-model. Subsequently refactored to import
 * {@code libraries/{power,data,geometry}} rather than carry its own copies of that code. The
 * radar model, equipment-level PEL, and SPICE-driven event activities are orbiter-specific
 * additions on top. (Telecom is still a local stub — {@code libraries/telecom} is experimental.)
 * See ATTRIBUTION.md at the repo root for the full directory-to-source mapping.
 */
@MissionModel(model = Mission.class)
@WithMappers(BasicValueMappers.class)
@WithMappers(CommonValueMappers.class)
@WithConfiguration(Configuration.class)
//
// Activity Types
//
// Geometry
@WithActivityType(Apoapsis.class)
@WithActivityType(Periapsis.class)
@WithActivityType(EnterOccultation.class)
@WithActivityType(ExitOccultation.class)
@WithActivityType(SpacecraftEnterEclipse.class)
@WithActivityType(SpacecraftExitEclipse.class)
@WithActivityType(AddPeriapsis.class)
@WithActivityType(AddApoapsis.class)
@WithActivityType(AddOccultations.class)
@WithActivityType(AddSpacecraftEclipses.class)
// Power
@WithActivityType(SolarArrayDeployment.class)
// Data (from libraries/data)
@MissionModel.WithActivityType(ChangeDataGenerationRate.class)
@MissionModel.WithActivityType(DeleteData.class)
@MissionModel.WithActivityType(GenerateData.class)
@MissionModel.WithActivityType(PlaybackData.class)
@MissionModel.WithActivityType(ReprioritizeData.class)
// Downlink
@WithActivityType(Downlink.class)
// Radar
@WithActivityType(Radar_Off.class)
@WithActivityType(Radar_On.class)
@WithActivityType(ChangeRadarDataMode.class)
@WithActivityType(TakeRadarObservation.class)

@WithMetadata(name = "unit", annotation = gov.nasa.ammos.plandev.contrib.metadata.Unit.class)
@WithSubsystem("geometry")
@WithSubsystem("power")
@WithSubsystem("data")
@WithSubsystem("telecom")
@WithSubsystem("radar")
package examples.orbiter;

import gov.nasa.ammos.plandev.contrib.serialization.rulesets.BasicValueMappers;
import gov.nasa.ammos.plandev.merlin.framework.annotations.MissionModel;
import gov.nasa.ammos.plandev.merlin.framework.annotations.MissionModel.WithActivityType;
import gov.nasa.ammos.plandev.merlin.framework.annotations.MissionModel.WithMetadata;
import gov.nasa.ammos.plandev.merlin.framework.annotations.MissionModel.WithSubsystem;
import gov.nasa.ammos.plandev.merlin.framework.annotations.MissionModel.WithConfiguration;
import gov.nasa.ammos.plandev.merlin.framework.annotations.MissionModel.WithMappers;
import gov.nasa.ammos.plandev.data.activities.*;
import gov.nasa.ammos.plandev.data.mappers.CommonValueMappers;
import examples.orbiter.geometry.activities.atomic.*;
import examples.orbiter.geometry.activities.spawner.AddApoapsis;
import examples.orbiter.geometry.activities.spawner.AddOccultations;
import examples.orbiter.geometry.activities.spawner.AddPeriapsis;
import examples.orbiter.geometry.activities.spawner.AddSpacecraftEclipses;
import examples.orbiter.power.activities.SolarArrayDeployment;
import examples.orbiter.radar.ChangeRadarDataMode;
import examples.orbiter.radar.TakeRadarObservation;
import examples.orbiter.telecom.Downlink;
import examples.orbiter.radar.Radar_Off;
import examples.orbiter.radar.Radar_On;
