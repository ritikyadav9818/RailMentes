import { Maximize, Minus, Plus } from "lucide-react";
import { useEffect, useRef } from "react";

import type { CameraController } from "../../utils/camera";
import { Button } from "../ui/button";

/** Zoom out / in and fit-to-screen, with the current zoom (100% = whole corridor in view). */
export function MapToolbar({ controller }: { controller: CameraController }) {
  const label = useRef<HTMLSpanElement>(null);

  useEffect(
    () =>
      controller.subscribe((cam, _size, fitK) => {
        if (label.current) label.current.textContent = `${Math.round((cam.k / fitK) * 100)}%`;
      }),
    [controller],
  );

  return (
    <div className="glass-strong flex flex-col items-center gap-0.5 rounded-lg p-1" role="toolbar" aria-label="Map zoom">
      <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => controller.zoomBy(1.5)} aria-label="Zoom in" title="Zoom in ( + )">
        <Plus className="h-4 w-4" />
      </Button>
      <span ref={label} className="w-10 py-0.5 text-center font-mono text-micro tracking-normal text-muted" aria-live="off">
        100%
      </span>
      <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => controller.zoomBy(1 / 1.5)} aria-label="Zoom out" title="Zoom out ( - )">
        <Minus className="h-4 w-4" />
      </Button>
      <span className="my-1 h-px w-5 bg-white/10" aria-hidden="true" />
      <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => controller.fit()} aria-label="Fit to screen" title="Fit to screen ( 0 )">
        <Maximize className="h-4 w-4" />
      </Button>
    </div>
  );
}
