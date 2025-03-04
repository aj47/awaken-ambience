import type { NextConfig } from 'next';

const config: NextConfig = {
  output: 'export',
  images: {
    unoptimized: true
  },
  eslint: {
    ignoreDuringBuilds: true,
  },
  typescript: {
    ignoreBuildErrors: true,
  },
};

export default config;
