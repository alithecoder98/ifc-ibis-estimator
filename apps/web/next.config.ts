import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Lean, self-contained server bundle (.next/standalone), only for the Docker build
  // (apps/web/Dockerfile sets DOCKER_BUILD=1). Standalone output makes Next.js mirror
  // the pnpm virtual store with symlinks, which needs Windows Developer Mode to create
  // without elevation - unconditionally enabling it broke plain `pnpm build` on Windows.
  output: process.env.DOCKER_BUILD === "1" ? "standalone" : undefined,
  // The floating "N" dev-mode indicator is a useful default elsewhere, but it
  // sits on top of real UI in every corner screenshot/demo of this app - off
  // by request. Next.js only ever renders it in `next dev` regardless.
  devIndicators: false,
};

export default nextConfig;
