/**
 * Runtime configuration for the OpenMCT host page, read by index.html.
 *
 * The URLs are SAME-ORIGIN paths that host/server.mjs proxies to PlanDev — this
 * sidesteps CORS entirely (the browser only talks to this host). Point the
 * proxy at a different backend with env vars when starting the server:
 *   PLANDEV_HASURA_URL=...  PLANDEV_GATEWAY_LOGIN_URL=...  npm start
 */
window.PLANDEV_CONFIG = {
  graphqlUrl: '/api/graphql',
  // AUTH is server-side: the host (server.mjs) logs in with PLANDEV_SERVICE_USER and
  // injects the token + PLANDEV_ROLE on every GraphQL call, so nothing auth-related
  // belongs here — the browser holds no token and can't pick a role.
  healthUrl: '/api/health',
  // Base URL of the PlanDev (Aerie) UI, used for "Open in PlanDev" backlinks in
  // the inspector. Leave '' to hide the link; e.g. 'http://localhost:3000'.
  planDevUiUrl: 'http://localhost:3000',
  namespace: 'plandev',
  // Floor (ms) for zero-duration activity spans so they show as Gantt bars.
  // 0 keeps instantaneous events as point markers; try 600000 (10 min) for a
  // denser-looking demo at full-plan zoom.
  minActivityDurationMs: 0,
};
