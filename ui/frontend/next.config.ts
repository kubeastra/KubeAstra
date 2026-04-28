import type { NextConfig } from "next";
import path from "path";

const nextConfig: NextConfig = {
  // Required for the Docker standalone build — produces a self-contained
  // server.js that does not need node_modules at runtime.
  output: "standalone",
  // Pin the file-tracing root to this folder. Without this, Next.js 16 walks
  // up looking for a workspace root, and Turbopack's CSS resolver follows —
  // which makes `@import "tailwindcss"` fail to resolve from ui/ instead of
  // ui/frontend/node_modules/.
  outputFileTracingRoot: path.resolve(__dirname),
};

export default nextConfig;
