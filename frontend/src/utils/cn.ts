import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

/** The custom type scale from tailwind.config.ts; tailwind-merge must know these are font sizes, not colours. */
const twMerge = extendTailwindMerge({
  extend: { classGroups: { "font-size": [{ text: ["micro", "caption", "body", "title", "display"] }] } },
});

/** Join class names and resolve Tailwind conflicts (shadcn convention). */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
