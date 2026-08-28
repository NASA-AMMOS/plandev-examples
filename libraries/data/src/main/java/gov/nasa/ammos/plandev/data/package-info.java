/**
 * Reusable data subsystem library — multi-bin onboard storage with prioritized playback.
 *
 * Initially derived from NASA-AMMOS/aerie-simple-model-data ({@code model/} subdir).
 * See ATTRIBUTION.md at the repo root for the full directory-to-source mapping.
 */
@MissionModel.WithMappers(CommonValueMappers.class)
@MissionModel.WithMappers(BasicValueMappers.class)


package gov.nasa.ammos.plandev.data;

import gov.nasa.ammos.plandev.contrib.serialization.rulesets.BasicValueMappers;
import gov.nasa.ammos.plandev.merlin.framework.annotations.MissionModel;
import gov.nasa.ammos.plandev.data.activities.*;

import gov.nasa.ammos.plandev.data.mappers.CommonValueMappers;
