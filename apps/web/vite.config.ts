import { createHash } from "node:crypto";

import react from "@vitejs/plugin-react";
import type { Connect } from "vite";
import { defineConfig } from "vitest/config";

const LOOPBACK = new Set(["127.0.0.1", "localhost", "::1"]);
const REACT_PREAMBLE_HASH = createHash("sha256")
  .update(react.preambleCode.replace("__BASE__", "/"))
  .digest("base64");

function localUrl(value: string, name: string): URL {
  const url = new URL(value);
  if (url.protocol !== "http:" || !LOOPBACK.has(url.hostname)) {
    throw new Error(
      `${name} must be a loopback HTTP URL for local development.`,
    );
  }
  return url;
}

function configMiddleware(): Connect.NextHandleFunction {
  return (request, response, next) => {
    if (request.url !== "/config.json") {
      next();
      return;
    }
    const supabase = localUrl(
      process.env.WEB_LOCAL_SUPABASE_URL ?? "http://127.0.0.1:54321",
      "WEB_LOCAL_SUPABASE_URL",
    );
    response.setHeader("Cache-Control", "no-store");
    response.setHeader("Content-Type", "application/json; charset=utf-8");
    response.end(
      JSON.stringify({
        apiBaseUrl: "/api/v1",
        supabaseUrl: supabase.origin,
        supabaseAnonKey:
          process.env.WEB_LOCAL_SUPABASE_ANON_KEY ??
          "public-local-key-required",
        buildVersion: "0.13.0",
      }),
    );
  };
}

export default defineConfig(() => {
  const backend = localUrl(
    process.env.WEB_LOCAL_BACKEND_PROXY ?? "http://127.0.0.1:8000",
    "WEB_LOCAL_BACKEND_PROXY",
  );
  const supabase = localUrl(
    process.env.WEB_LOCAL_SUPABASE_URL ?? "http://127.0.0.1:54321",
    "WEB_LOCAL_SUPABASE_URL",
  );
  const devCsp = [
    "default-src 'self'",
    "base-uri 'none'",
    `connect-src 'self' ${supabase.origin} ws://127.0.0.1:* ws://localhost:*`,
    "font-src 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    "img-src 'self' data:",
    "object-src 'none'",
    `script-src 'self' 'sha256-${REACT_PREAMBLE_HASH}'`,
    "style-src 'self'",
    "worker-src 'none'",
  ].join("; ");
  return {
    plugins: [
      react(),
      {
        name: "runtime-public-config",
        configureServer(server) {
          server.middlewares.use(configMiddleware());
        },
      },
    ],
    build: {
      manifest: true,
      sourcemap: false,
      target: "es2022",
      outDir: "dist",
      emptyOutDir: true,
    },
    server: {
      headers: {
        "Content-Security-Policy": devCsp,
        "Permissions-Policy":
          "camera=(), geolocation=(), microphone=(), payment=(), usb=()",
        "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
      },
      proxy: {
        "/api": { target: backend.origin, changeOrigin: false },
        "/health": { target: backend.origin, changeOrigin: false },
      },
    },
    test: {
      environment: "jsdom",
      setupFiles: ["./tests/setup.ts"],
      include: [
        "src/**/*.test.ts",
        "src/**/*.test.tsx",
        "tests/**/*.test.ts",
        "tests/**/*.test.tsx",
      ],
      exclude: ["tests/e2e/**", "node_modules/**", "dist/**"],
      clearMocks: true,
      restoreMocks: true,
    },
  };
});
