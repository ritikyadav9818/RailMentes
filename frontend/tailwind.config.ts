import type { Config } from "tailwindcss";
import animate from "tailwindcss-animate";

// Control-room palette: layered dark surfaces, one cool accent, amber = warning, red = critical.
// `major` sits between warn and crit on the delay scale (see src/utils/delay.ts).
// Surfaces get lighter with elevation: bg < panel < raised.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#070b10",
        panel: "#0f161f",
        raised: "#16202c",
        border: "#223041",
        text: "#dbe4ee",
        muted: "#8a9bb0",
        accent: "#38bdf8",
        warn: "#f5a524",
        major: "#fb7c2d",
        crit: "#f04438",
        ok: "#34d399",
      },
      fontFamily: {
        sans: ["Inter Variable", "Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono Variable", "JetBrains Mono", "Consolas", "monospace"],
      },
      // type scale: micro labels, captions, body, emphasis, display numbers
      fontSize: {
        micro: ["10px", { lineHeight: "14px", letterSpacing: "0.08em" }],
        caption: ["11px", { lineHeight: "16px" }],
        body: ["13px", { lineHeight: "19px" }],
        title: ["15px", { lineHeight: "20px" }],
        display: ["26px", { lineHeight: "28px" }],
      },
      boxShadow: {
        glass: "0 8px 30px -8px rgb(0 0 0 / 0.6), 0 1px 0 0 rgb(255 255 255 / 0.04) inset",
        glow: "0 0 0 1px rgb(56 189 248 / 0.35), 0 0 24px -4px rgb(56 189 248 / 0.35)",
      },
    },
  },
  plugins: [animate],
} satisfies Config;
