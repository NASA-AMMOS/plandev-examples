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
  loginUrl: '/api/auth/login',
  // Any username works while PlanDev runs with AUTH_TYPE=none.
  username: 'openmct-demo',
  role: 'aerie_admin',
  namespace: 'plandev',
  // Floor (ms) for zero-duration activity spans so they show as Gantt bars.
  // 0 keeps instantaneous events as point markers; try 600000 (10 min) for a
  // denser-looking demo at full-plan zoom.
  minActivityDurationMs: 0,
};
