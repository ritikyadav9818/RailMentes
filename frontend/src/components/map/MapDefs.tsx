import { DELAY_COLORS, type DelayLevel } from "../../utils/delay";

const LEVELS = Object.keys(DELAY_COLORS) as DelayLevel[];

/** Shared SVG paint servers: hatch for closed blocks, glows for trains, soft fog blobs, the map grid. */
export function MapDefs() {
  return (
    <defs>
      <pattern id="hatch" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
        <rect width="7" height="7" fill="#f04438" fillOpacity="0.10" />
        <line x1="0" y1="0" x2="0" y2="7" stroke="#f04438" strokeWidth="2.2" strokeOpacity="0.75" />
      </pattern>
      <radialGradient id="fog-blob">
        <stop offset="0%" stopColor="#cbd8e6" stopOpacity="0.55" />
        <stop offset="60%" stopColor="#cbd8e6" stopOpacity="0.22" />
        <stop offset="100%" stopColor="#cbd8e6" stopOpacity="0" />
      </radialGradient>
      {LEVELS.map((level) => (
        <radialGradient id={`glow-${level}`} key={level}>
          <stop offset="0%" stopColor={DELAY_COLORS[level]} stopOpacity="0.5" />
          <stop offset="100%" stopColor={DELAY_COLORS[level]} stopOpacity="0" />
        </radialGradient>
      ))}
      <radialGradient id="station-glow">
        <stop offset="0%" stopColor="#38bdf8" stopOpacity="0.35" />
        <stop offset="100%" stopColor="#38bdf8" stopOpacity="0" />
      </radialGradient>
      {/* grid: a fine line every 50 world units, a stronger one every 250 */}
      <pattern id="grid-fine" width="50" height="50" patternUnits="userSpaceOnUse">
        <path d="M50 0H0V50" fill="none" stroke="#8fb4d8" strokeOpacity="0.045" strokeWidth="1" vectorEffect="non-scaling-stroke" />
      </pattern>
      <pattern id="grid-major" width="250" height="250" patternUnits="userSpaceOnUse">
        <path d="M250 0H0V250" fill="none" stroke="#8fb4d8" strokeOpacity="0.07" strokeWidth="1" vectorEffect="non-scaling-stroke" />
      </pattern>
    </defs>
  );
}

/** The grid itself; it lives inside the camera group so it pans and zooms with the map. */
export function MapGrid() {
  return (
    <g pointerEvents="none" aria-hidden="true">
      <rect x={-4000} y={-3000} width={9000} height={7000} fill="url(#grid-fine)" />
      <rect x={-4000} y={-3000} width={9000} height={7000} fill="url(#grid-major)" />
    </g>
  );
}
