// frontend/next.config.mjs
const nextConfig = {
  reactStrictMode: true,
  // Produce a self-contained server.js + minimal node_modules in .next/standalone.
  // Cuts production image size by ~70% vs. shipping full node_modules.
  output: "standalone",
};
export default nextConfig;
