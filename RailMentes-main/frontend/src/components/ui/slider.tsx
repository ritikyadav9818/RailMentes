import * as SliderPrimitive from "@radix-ui/react-slider";
import * as React from "react";

import { cn } from "../../utils/cn";

const Slider = React.forwardRef<
  React.ElementRef<typeof SliderPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof SliderPrimitive.Root>
>(({ className, ...props }, ref) => (
  <SliderPrimitive.Root ref={ref} className={cn("relative flex h-5 w-full touch-none select-none items-center", className)} {...props}>
    <SliderPrimitive.Track className="relative h-1.5 w-full grow overflow-hidden rounded-full bg-border">
      <SliderPrimitive.Range className="absolute h-full bg-accent" />
    </SliderPrimitive.Track>
    <SliderPrimitive.Thumb className="block h-4 w-4 rounded-full border-2 border-accent bg-bg shadow-[0_0_10px_-1px_rgb(56_189_248_/_0.7)] transition-[transform,box-shadow] hover:scale-110 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/70 disabled:pointer-events-none" />
  </SliderPrimitive.Root>
));
Slider.displayName = "Slider";

export { Slider };
