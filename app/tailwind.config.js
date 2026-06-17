/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#040810",
          900: "#080c18",
          800: "#0c1220",
          700: "#0f1629",
          600: "#141e36",
          500: "#1e2d4a",
          400: "#2a3f60",
        },
        neural: {
          DEFAULT: "#22d3ee",
          dim: "#0891b2",
          glow: "#67e8f9",
          muted: "#164e63",
        },
      },
      animation: {
        "pulse-slow": "pulse 3s ease-in-out infinite",
        "fade-up": "fadeUp 0.4s ease-out both",
        "fade-in": "fadeIn 0.3s ease-out both",
        "card-in": "cardIn 0.35s cubic-bezier(0.34,1.56,0.64,1) both",
      },
      keyframes: {
        fadeUp: {
          from: { opacity: "0", transform: "translateY(16px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        fadeIn: {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        cardIn: {
          from: { opacity: "0", transform: "scale(0.92) translateY(12px)" },
          to: { opacity: "1", transform: "scale(1) translateY(0)" },
        },
      },
    },
  },
  plugins: [],
};
