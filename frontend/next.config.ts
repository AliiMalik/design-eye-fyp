import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Emits .next/standalone so the runtime image ships without node_modules.
  output: "standalone",
  images: {
    // Heatmaps and mockups are served by the API's /storage mount.
    remotePatterns: [
      { protocol: "http", hostname: "localhost", port: "8000", pathname: "/storage/**" },
      { protocol: "http", hostname: "api", port: "8000", pathname: "/storage/**" },
      { protocol: "https", hostname: "res.cloudinary.com", pathname: "/**" },
    ],
  },
};

export default nextConfig;
