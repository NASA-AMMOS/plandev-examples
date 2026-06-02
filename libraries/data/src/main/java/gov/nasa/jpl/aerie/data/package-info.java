/**
 * Reusable data subsystem library — multi-bin onboard storage with prioritized playback.
 *
 * Initially derived from NASA-AMMOS/aerie-simple-model-data ({@code model/} subdir).
 * See ATTRIBUTION.md at the repo root for the full directory-to-source mapping.
 */
@MissionModel.WithMappers(CommonValueMappers.class)
@MissionModel.WithMappers(BasicValueMappers.class)


package gov.nasa.jpl.aerie.data;

import gov.nasa.jpl.aerie.contrib.serialization.rulesets.BasicValueMappers;
import gov.nasa.jpl.aerie.merlin.framework.annotations.MissionModel;
import gov.nasa.jpl.aerie.data.activities.*;

import gov.nasa.jpl.aerie.data.mappers.CommonValueMappers;
