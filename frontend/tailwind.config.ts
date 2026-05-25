import type { Config } from "tailwindcss";
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        customer: { 50: "#eff6ff", 500: "#3b82f6", 700: "#1d4ed8" },
        agent: { 50: "#ecfdf5", 500: "#10b981", 700: "#047857" },
        assist: { 50: "#f5f3ff", 500: "#8b5cf6", 700: "#6d28d9" },
      },
      fontFamily: {
        sans: ["Inter", "PingFang SC", "Microsoft YaHei", "sans-serif"],
        mono: ["JetBrains Mono", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};
export default config;
