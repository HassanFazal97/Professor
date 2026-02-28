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
        "tutor-blue": "#0066CC",
        "tutor-green": "#00AA00",
        "tutor-red": "#FF0000",
      },
    },
  },
  plugins: [],
};

export default config;
