import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  // drei <Html> portals double-unmount under StrictMode (dev-only warning with React 19)
  reactStrictMode: false,
};

export default nextConfig;
