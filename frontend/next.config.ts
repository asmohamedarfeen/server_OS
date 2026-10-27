import type { NextConfig } from "next";
const config: NextConfig = {
  outputFileTracingRoot: process.cwd(),
  experimental: { proxyTimeout: 3_600_000 },
  async rewrites() {
    return [{ source: "/api/:path*", destination: "http://backend:8000/api/:path*" }];
  },
};
export default config;
