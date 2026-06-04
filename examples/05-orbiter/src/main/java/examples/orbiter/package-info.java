/**
 * Mars-orbiter-style mission model — integrates power, data, geometry, telecom, and radar subsystems.
 *
 * Initially derived from NASA-AMMOS/aerie-orbiter-model. Subsequently refactored to import
 * {@code libraries/{power,data,geometry,telecom}} rather than carry its own copies of that code.
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
// Data
@MissionModel.WithActivityType(ChangeDataGenerationRate.class)
@MissionModel.WithActivityType(DeleteData.class)
@MissionModel.WithActivityType(FilterData.class)
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

// @WithMetadata(name = "unit", annotation = gov.nasa.jpl.aerie.contrib.metadata.Unit.class) // for unit support
package examples.orbiter;

import gov.nasa.jpl.aerie.contrib.serialization.rulesets.BasicValueMappers;
import gov.nasa.jpl.aerie.merlin.framework.annotations.MissionModel;
import gov.nasa.jpl.aerie.merlin.framework.annotations.MissionModel.WithActivityType;
import gov.nasa.jpl.aerie.merlin.framework.annotations.MissionModel.WithConfiguration;
import gov.nasa.jpl.aerie.merlin.framework.annotations.MissionModel.WithMappers;
import examples.orbiter.data.activities.*;
import examples.orbiter.data.mappers.CommonValueMappers;
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
