import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        "kia-blue": "#004AAD",
        "kia-black": "#000000",
        "kia-cream": "#FBF8EF",
        "kia-warm": "#E5E2D9",
        "kia-lime": "#E4FFC2",
        "kia-gray": "#6A5E63",
        // legacy aliases
        "tutor-blue": "#004AAD",
        "tutor-green": "#00AA00",
        "tutor-red": "#FF0000",
      },
      fontFamily: {
        heading: ["var(--font-heading)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
