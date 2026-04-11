import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/**/*.{js,ts,jsx,tsx,mdx}"
  ],
  theme: {
    extend: {
      colors: {
        ink: "#0f1a1f",
        sand: "#f7f1e6",
        ember: "#c95a3d",
        tide: "#2b6170",
        moss: "#5f7b4b",
        brass: "#b78d3d"
      },
      boxShadow: {
        card: "0 24px 80px rgba(15, 26, 31, 0.12)"
      },
      backgroundImage: {
        "hero-radial": "radial-gradient(circle at top left, rgba(201,90,61,0.22), transparent 34%), radial-gradient(circle at 80% 20%, rgba(43,97,112,0.24), transparent 30%), linear-gradient(180deg, #f7f1e6 0%, #f0e6d5 100%)"
      }
    }
  },
  plugins: []
};

export default config;
