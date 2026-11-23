import { animate, useReducedMotion } from "framer-motion";
import { useEffect, useRef } from "react";

interface Props {
  value: number;
  decimals?: number;
  className?: string;
}

/**
 * A number that counts to its new value. The text is written straight into the DOM while it
 * counts, so React does not re-render every frame. With reduced motion it just changes.
 */
export function AnimatedNumber({ value, decimals = 0, className }: Props) {
  const ref = useRef<HTMLSpanElement>(null);
  const shown = useRef(value);
  const first = useRef(value.toFixed(decimals)); // never changes, so React never overwrites the animated text
  const reduced = useReducedMotion();

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (reduced || shown.current === value) {
      el.textContent = value.toFixed(decimals);
      shown.current = value;
      return;
    }
    const controls = animate(shown.current, value, {
      duration: 0.7,
      ease: [0.16, 1, 0.3, 1],
      onUpdate: (v) => {
        shown.current = v;
        el.textContent = v.toFixed(decimals);
      },
      onComplete: () => {
        shown.current = value;
        el.textContent = value.toFixed(decimals);
      },
    });
    return () => controls.stop();
  }, [value, decimals, reduced]);

  return (
    <span ref={ref} className={className}>
      {first.current}
    </span>
  );
}
