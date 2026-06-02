/**
 * Reusable telecom subsystem library — Friis link-equation model, DSN ground-station configs,
 * and per-link bit-rate resources.
 *
 * <p><strong>Status: experimental, not currently consumed by any example in this repo.</strong>
 * The orbiter example carries its own minimal in-tree telecom stub rather than depending on
 * this library. Geometry is mocked (hardcoded distances), antenna gain / elevation mask /
 * pointing loss are unimplemented, and degradation loss is hardcoded to 1.0. Treat any numbers
 * this library produces as illustrative. See {@code libraries/telecom/README.md} for the full
 * status writeup.
 *
 * <p>Initially derived from NASA-AMMOS/aerie-simple-model-telecom (originally a private POC).
 * See ATTRIBUTION.md at the repo root for the full directory-to-source mapping.
 */
package gov.nasa.jpl.aerie.telecom;
