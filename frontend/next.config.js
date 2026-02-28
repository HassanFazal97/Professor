/** @type {import('next').NextConfig} */
const nextConfig = {
  // tldraw uses ES modules that Next.js needs to transpile
  transpilePackages: ["@tldraw/tldraw", "@tldraw/editor"],

  // Disable strict mode in dev to avoid double-render issues with canvas
  reactStrictMode: false,

  webpack: (config) => {
    // Required for tldraw's worker files
    config.resolve.fallback = {
      ...config.resolve.fallback,
      fs: false,
    };
    return config;
  },
};

module.exports = nextConfig;
