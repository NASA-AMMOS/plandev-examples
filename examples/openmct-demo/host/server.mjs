/**
 * Zero-dependency host server for the PlanDev × OpenMCT demo.
 *
 *   • serves the host page + bundled plugin from host/
 *   • serves OpenMCT core from node_modules/openmct/dist at /openmct/
 *   • proxies /api/graphql     → PlanDev Hasura  (sidesteps CORS)
 *   • proxies /api/auth/login  → PlanDev gateway
 *
 * Override the proxy targets per deployment:
 *   PLANDEV_HASURA_URL=http://host:8080/v1/graphql \
 *   PLANDEV_GATEWAY_LOGIN_URL=http://host:9000/auth/login \
 *   PORT=8888 npm start
 */
import { createReadStream, existsSync, statSync } from 'node:fs';
import { createServer, request as httpRequest } from 'node:http';
import { request as httpsRequest } from 'node:https';
import { dirname, extname, join, normalize, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const HOST_DIR = HERE;
const OPENMCT_DIST = resolve(HERE, '..', 'node_modules', 'openmct', 'dist');

const PORT = Number(process.env.PORT ?? 8888);
const HASURA_URL = process.env.PLANDEV_HASURA_URL ?? 'http://localhost:8080/v1/graphql';
const GATEWAY_LOGIN_URL =
  process.env.PLANDEV_GATEWAY_LOGIN_URL ?? 'http://localhost:9000/auth/login';
// PlanDev liveness check for the OpenMCT URLIndicator. Defaults to Hasura's
// /healthz (200 "OK" when up), derived from the Hasura origin.
const HEALTH_URL =
  process.env.PLANDEV_HEALTH_URL ?? new URL('/healthz', HASURA_URL).toString();

// SERVER-SIDE AUTH. The host logs in once with PLANDEV_SERVICE_USER and injects
// `Authorization` + a pinned `x-hasura-role` on every proxied GraphQL request — so the
// browser never logs in, holds a token, or picks a role. The plugin sends no
// credentials, so this proxy is the single auth point. The default user works with
// AUTH_TYPE=none; set a real PLANDEV_SERVICE_USER / PLANDEV_SERVICE_PASSWORD for an
// auth-enabled PlanDev, and PLANDEV_ROLE for a role the account is allowed.
const SERVICE_USER = process.env.PLANDEV_SERVICE_USER ?? 'openmct-demo';
const SERVICE_PASSWORD = process.env.PLANDEV_SERVICE_PASSWORD ?? '';
const SERVICE_ROLE = process.env.PLANDEV_ROLE ?? 'viewer';

const MIME = {
  '.css': 'text/css; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.ico': 'image/x-icon',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.map': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.ttf': 'font/ttf',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
};

function proxy(targetUrl, req, res) {
  const url = new URL(targetUrl);
  const transport = url.protocol === 'https:' ? httpsRequest : httpRequest;
  const options = {
    headers: { ...req.headers, host: url.host },
    hostname: url.hostname,
    method: req.method,
    path: url.pathname + url.search,
    port: url.port || (url.protocol === 'https:' ? 443 : 80),
  };
  const proxyReq = transport(options, proxyRes => {
    res.writeHead(proxyRes.statusCode ?? 502, proxyRes.headers);
    proxyRes.pipe(res);
  });
  proxyReq.on('error', err => {
    res.writeHead(502, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: `Proxy to ${targetUrl} failed: ${err.message}` }));
  });
  req.pipe(proxyReq);
}

let serviceToken = null;

/** Logs in once with the service account and caches the JWT; `force` re-logs in. */
async function serviceLogin(force = false) {
  if (serviceToken && !force) {
    return serviceToken;
  }
  const res = await fetch(GATEWAY_LOGIN_URL, {
    body: JSON.stringify({ password: SERVICE_PASSWORD, username: SERVICE_USER }),
    headers: { 'Content-Type': 'application/json' },
    method: 'POST',
  });
  if (!res.ok) {
    throw new Error(`service login failed (${res.status})`);
  }
  const json = await res.json();
  serviceToken = json.token ?? json.ssoToken;
  if (!serviceToken) {
    throw new Error('service login returned no token');
  }
  return serviceToken;
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on('data', chunk => chunks.push(chunk));
    req.on('end', () => resolve(Buffer.concat(chunks)));
    req.on('error', reject);
  });
}

/**
 * Proxies a GraphQL request with the server's service token + pinned role, so the
 * browser sends no credentials and can't choose its role. Re-logs in once on a 401.
 */
async function graphqlServerAuth(req, res) {
  try {
    const body = await readBody(req);
    const send = token =>
      fetch(HASURA_URL, {
        body,
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
          'x-hasura-role': SERVICE_ROLE,
        },
        method: 'POST',
      });
    let upstream = await send(await serviceLogin());
    if (upstream.status === 401) {
      upstream = await send(await serviceLogin(true));
    }
    const text = await upstream.text();
    res.writeHead(upstream.status, { 'Content-Type': 'application/json' });
    res.end(text);
  } catch (err) {
    res.writeHead(502, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: `PlanDev service-auth proxy failed: ${err.message}` }));
  }
}

function serveStatic(filePath, res) {
  if (!existsSync(filePath) || !statSync(filePath).isFile()) {
    res.writeHead(404, { 'Content-Type': 'text/plain' });
    res.end('Not found');
    return;
  }
  res.writeHead(200, { 'Content-Type': MIME[extname(filePath)] ?? 'application/octet-stream' });
  createReadStream(filePath).pipe(res);
}

/** Resolves a URL path to a file within `baseDir`, blocking path traversal. */
function safeJoin(baseDir, urlPath) {
  const target = normalize(join(baseDir, urlPath));
  return target.startsWith(baseDir) ? target : null;
}

const server = createServer((req, res) => {
  const pathname = decodeURIComponent(new URL(req.url ?? '/', 'http://localhost').pathname);

  if (pathname === '/api/graphql') {
    return graphqlServerAuth(req, res); // injects the service token + pinned role
  }
  if (pathname === '/api/health') {
    return proxy(HEALTH_URL, req, res);
  }

  if (pathname === '/' || pathname === '/index.html') {
    return serveStatic(join(HOST_DIR, 'index.html'), res);
  }
  if (pathname.startsWith('/openmct/')) {
    const file = safeJoin(OPENMCT_DIST, pathname.slice('/openmct/'.length));
    return file ? serveStatic(file, res) : res.writeHead(403).end();
  }
  const file = safeJoin(HOST_DIR, pathname);
  return file ? serveStatic(file, res) : res.writeHead(403).end();
});

server.listen(PORT, () => {
  if (!existsSync(join(OPENMCT_DIST, 'openmct.js'))) {
    console.warn(`⚠  OpenMCT dist not found at ${OPENMCT_DIST}. Run "npm install" first.`);
  }
  console.log(`PlanDev × OpenMCT host:  http://localhost:${PORT}`);
  console.log(`  proxy /api/graphql     → ${HASURA_URL}  (server-auth as "${SERVICE_USER}", role ${SERVICE_ROLE})`);
  console.log(`  service login          → ${GATEWAY_LOGIN_URL}`);
  console.log(`  proxy /api/health      → ${HEALTH_URL}`);
});
