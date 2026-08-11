import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // `standalone` exists for the self-hosted path: .zscripts/build.sh requires
  // .next/standalone/server.js and fails the build without it. Vercel builds
  // its own output format and does not want a standalone bundle, so skip it
  // there. VERCEL=1 is set automatically in every Vercel build environment.
  output: process.env.VERCEL ? undefined : "standalone",
  /* config options here */
  typescript: {
    ignoreBuildErrors: true,
  },
  reactStrictMode: false,
  // Hide the floating Next.js dev badge in the corner.
  devIndicators: false,
};

export default nextConfig;
