import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The console is one four-step workflow (Set up → Watch → Results → Fix &
  // re-test); these are the screens it replaced, kept working for bookmarks.
  async redirects() {
    return [
      { source: "/topology", destination: "/watch", permanent: false },
      { source: "/activity", destination: "/watch", permanent: false },
      { source: "/metrics", destination: "/results", permanent: false },
      { source: "/remediation", destination: "/fix", permanent: false },
      { source: "/defenses", destination: "/fix", permanent: false },
    ];
  },
};

export default nextConfig;
