import type { NextConfig } from "next";

const BACKEND = process.env.BACKEND_URL || "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  // drei <Html> portals double-unmount under StrictMode (dev-only warning with React 19)
  reactStrictMode: false,
  // pitch setup: one Chrome window, one login per host (localhost / 127.0.0.1 / student.localhost)
  allowedDevOrigins: ["127.0.0.1", "*.localhost"],
  // no "N" dev badge on the projector
  devIndicators: false,
  // single-container deploys: the backend is internal, so expose its generated files and the MCP endpoint here
  async rewrites() {
    return [
      { source: "/outbox/:path*", destination: `${BACKEND}/outbox/:path*` },
      { source: "/mcp", destination: `${BACKEND}/mcp` },
      // Gemini Enterprise: A2A agent, its card and the MCP connector live at the secret /g/<secret>/ path
      { source: "/g/:path*", destination: `${BACKEND}/g/:path*` },
    ];
  },
};

export default nextConfig;
