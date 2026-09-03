import { createReadStream, promises as fs } from "node:fs";
import { createServer } from "node:http";
import { extname, resolve, sep } from "node:path";
import { Readable } from "node:stream";
import { fileURLToPath } from "node:url";

import {
  buildSecurityHeaders,
  isTrustedMutationOrigin,
  publicRuntimeConfig,
  validatedOrigin,
} from "./security.mjs";

const ROOT = resolve(fileURLToPath(new URL("../dist", import.meta.url)));
const PORT = Number.parseInt(process.env.PORT ?? "3000", 10);
const HOST = process.env.HOST ?? "127.0.0.1";
const publicOrigin = validatedOrigin(
  process.env.WEB_PUBLIC_ORIGIN,
  "WEB_PUBLIC_ORIGIN",
);
const backendOrigin = validatedOrigin(
  process.env.WEB_BACKEND_ORIGIN,
  "WEB_BACKEND_ORIGIN",
);
const runtimeConfig = publicRuntimeConfig({
  supabaseUrl: process.env.WEB_SUPABASE_URL,
  supabaseAnonKey: process.env.WEB_SUPABASE_ANON_KEY,
});
const securityHeaders = buildSecurityHeaders({
  supabaseOrigin: runtimeConfig.supabaseUrl,
  enableHsts: process.env.WEB_ENABLE_HSTS === "true",
});

const MIME = Object.freeze({
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".ico": "image/x-icon",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".webmanifest": "application/manifest+json",
  ".woff2": "font/woff2",
});

function applyHeaders(response, extra = {}) {
  for (const [name, value] of Object.entries({
    ...securityHeaders,
    ...extra,
  })) {
    response.setHeader(name, value);
  }
}

async function collectBody(request, maxBytes = 1_048_576) {
  const chunks = [];
  let total = 0;
  for await (const chunk of request) {
    total += chunk.length;
    if (total > maxBytes) throw new Error("REQUEST_TOO_LARGE");
    chunks.push(chunk);
  }
  return Buffer.concat(chunks);
}

async function proxyApi(request, response, url) {
  const method = request.method ?? "GET";
  const mutating = !["GET", "HEAD", "OPTIONS"].includes(method);
  if (
    mutating &&
    !isTrustedMutationOrigin(request.headers.origin, publicOrigin)
  ) {
    applyHeaders(response, {
      "Content-Type": "application/json; charset=utf-8",
    });
    response.writeHead(403);
    response.end(
      JSON.stringify({
        error: { code: "FORBIDDEN", message: "Request origin denied." },
      }),
    );
    return;
  }
  const headers = new Headers({ Accept: "application/json" });
  for (const name of ["authorization", "content-type", "x-request-id"]) {
    const value = request.headers[name];
    if (typeof value === "string") headers.set(name, value);
  }
  const body = mutating ? await collectBody(request) : undefined;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 20_000);
  try {
    const upstream = await fetch(
      `${backendOrigin}${url.pathname}${url.search}`,
      {
        method,
        headers,
        redirect: "manual",
        signal: controller.signal,
        ...(body === undefined ? {} : { body }),
      },
    );
    const safeHeaders = {};
    for (const name of ["content-type", "www-authenticate", "x-request-id"]) {
      const value = upstream.headers.get(name);
      if (value) safeHeaders[name] = value;
    }
    applyHeaders(response, safeHeaders);
    response.writeHead(upstream.status);
    if (method === "HEAD" || !upstream.body) response.end();
    else Readable.fromWeb(upstream.body).pipe(response);
  } catch {
    applyHeaders(response, {
      "Content-Type": "application/json; charset=utf-8",
    });
    response.writeHead(502);
    response.end(
      JSON.stringify({
        error: { code: "SERVER_UNAVAILABLE", message: "Backend unavailable." },
      }),
    );
  } finally {
    clearTimeout(timeout);
  }
}

async function serveStatic(request, response, url) {
  if (request.method !== "GET" && request.method !== "HEAD") {
    applyHeaders(response, { Allow: "GET, HEAD" });
    response.writeHead(405).end();
    return;
  }
  let relative = decodeURIComponent(url.pathname).replace(/^\/+/, "");
  if (!relative || !extname(relative)) relative = "index.html";
  let file = resolve(ROOT, relative);
  if (file !== ROOT && !file.startsWith(`${ROOT}${sep}`)) {
    applyHeaders(response);
    response.writeHead(404).end();
    return;
  }
  try {
    const stat = await fs.stat(file);
    if (!stat.isFile()) throw new Error("NOT_FILE");
  } catch {
    file = resolve(ROOT, "index.html");
  }
  const type = MIME[extname(file)] ?? "application/octet-stream";
  applyHeaders(response, {
    "Content-Type": type,
    "Cache-Control": file.endsWith("index.html")
      ? "no-store"
      : "public, max-age=31536000, immutable",
  });
  response.writeHead(200);
  if (request.method === "HEAD") response.end();
  else createReadStream(file).pipe(response);
}

const server = createServer(async (request, response) => {
  try {
    const url = new URL(request.url ?? "/", publicOrigin);
    if (url.pathname === "/config.json") {
      if (request.method !== "GET") {
        applyHeaders(response, { Allow: "GET" });
        response.writeHead(405).end();
        return;
      }
      applyHeaders(response, {
        "Cache-Control": "no-store",
        "Content-Type": "application/json; charset=utf-8",
      });
      response.writeHead(200).end(JSON.stringify(runtimeConfig));
      return;
    }
    if (
      url.pathname.startsWith("/api/") ||
      url.pathname.startsWith("/health/")
    ) {
      await proxyApi(request, response, url);
      return;
    }
    await serveStatic(request, response, url);
  } catch {
    if (!response.headersSent) applyHeaders(response);
    response.writeHead(response.headersSent ? 500 : 400).end();
  }
});

server.listen(PORT, HOST, () => {
  process.stdout.write(`Personal Assistant Web listening on ${HOST}:${PORT}\n`);
});

function shutdown() {
  server.close(() => process.exit(0));
}

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);
