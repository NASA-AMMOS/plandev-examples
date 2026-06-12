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
    return proxy(HASURA_URL, req, res);
  }
  if (pathname === '/api/auth/login') {
    return proxy(GATEWAY_LOGIN_URL, req, res);
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
  console.log(`  proxy /api/graphql     → ${HASURA_URL}`);
  console.log(`  proxy /api/auth/login  → ${GATEWAY_LOGIN_URL}`);
});
