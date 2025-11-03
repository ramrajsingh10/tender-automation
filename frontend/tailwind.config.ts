import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/app/**/*.{js,ts,jsx,tsx,mdx}", "./src/components/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        background: "#f8fafc",
        foreground: "#0f172a",
        border: "#d4dbe8",
        muted: {
          DEFAULT: "#e2e8f0",
          foreground: "#64748b",
        },
        primary: {
          DEFAULT: "#2563eb",
          foreground: "#f8fafc",
        },
        accent: {
          DEFAULT: "#f97316",
          foreground: "#fff7ed",
        },
        success: {
          DEFAULT: "#22c55e",
          foreground: "#ecfdf5",
        },
        warning: {
          DEFAULT: "#facc15",
          foreground: "#422006",
        },
        surface: {
          DEFAULT: "#ffffff",
          foreground: "#0f172a",
        },
        card: {
          DEFAULT: "#ffffff",
          foreground: "#0f172a",
        },
      },
      fontFamily: {
        sans: ["var(--font-sans)", "sans-serif"],
      },
      boxShadow: {
        card: "0 24px 40px -24px rgba(15, 23, 42, 0.25)",
        subtle: "0 12px 24px -16px rgba(15, 23, 42, 0.15)",
      },
      backgroundImage: {
        "hero-gradient": "linear-gradient(135deg, rgba(37, 99, 235, 0.18), rgba(79, 70, 229, 0.24))",
      },
    },
  },
  plugins: [],
};

export default config;
