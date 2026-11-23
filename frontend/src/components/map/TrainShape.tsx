import type { TrainCategory } from "../../api/types";

/** Half-size of the largest marker in px; viewBoxes around a TrainShape should be a bit larger. */
export const TRAIN_RADIUS = 12;

/** Marker outline per train type: premium diamond, express triangle, passenger circle, freight square. */
export function TrainShape({ category, color }: { category: TrainCategory; color: string }) {
  const common = { fill: color, stroke: "#070b10", strokeWidth: 2, strokeLinejoin: "round" as const };
  switch (category) {
    case "premium":
      return <polygon points="0,-12 10.5,0 0,12 -10.5,0" {...common} />;
    case "express":
      return <polygon points="0,-11 11,8.5 -11,8.5" {...common} />;
    case "freight":
      return <rect x={-7.5} y={-7.5} width={15} height={15} rx={2.2} {...common} />;
    default:
      return <circle r={8.5} {...common} />;
  }
}
