import type { NextConfig } from "next";
import path from "path";

const nextConfig: NextConfig = {
  // Keep Phase 1 simple; enable Cache Components later when pages are fully async-ready.
  turbopack: {
    root: path.join(__dirname),
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
