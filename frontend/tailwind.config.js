/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#1f1a17",
        paper: "#f6f1ea",
        accent: "#8a4b2d",
        muted: "#6b5f57",
      },
      fontFamily: {
        display: ['"Fraunces"', "Georgia", "serif"],
        sans: ['"IBM Plex Sans"', "Segoe UI", "sans-serif"],
      },
    },
  },
  plugins: [],
};
