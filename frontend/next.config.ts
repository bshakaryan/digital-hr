import type { NextConfig } from "next";

const apiOrigin = (process.env.API_INTERNAL_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const documentologOrigin = process.env.DOCUMENTOLOG_PROXY_ORIGIN?.replace(/\/$/, "");

const config: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${apiOrigin}/api/:path*` },
      ...(documentologOrigin ? [
        { source: "/external/sign/embedded", destination: `${documentologOrigin}/external/sign/embedded` },
        { source: "/external/mock/:path*", destination: `${documentologOrigin}/external/mock/:path*` },
      ] : []),
    ];
  },
};

export default config;
