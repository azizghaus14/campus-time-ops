import type { NextConfig } from "next";

const BACKEND = process.env.BACKEND_URL || "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  // drei <Html> portals double-unmount under StrictMode (dev-only warning with React 19)
  reactStrictMode: false,
  // single-container deploys: the backend is internal, so expose its generated files and the MCP endpoint here
  async rewrites() {
    return [
      { source: "/outbox/:path*", destination: `${BACKEND}/outbox/:path*` },
      { source: "/mcp", destination: `${BACKEND}/mcp` },
    ];
  },
};

export default nextConfig;
