import { motion } from "framer-motion";
import { ChevronsLeft, ChevronsRight, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "./ui/button";

/** Width of a collapsed panel (px). */
export const RAIL_WIDTH = 46;

interface ToggleProps {
  side: "left" | "right";
  onToggle: () => void;
  shortcut: string;
  label: string;
}

/** The small chevron button in a panel header. */
export function PanelCollapseButton({ side, onToggle, shortcut, label }: ToggleProps) {
  const Icon = side === "left" ? ChevronsLeft : ChevronsRight;
  return (
    <Button size="icon" variant="ghost" className="h-7 w-7 shrink-0" onClick={onToggle} aria-label={`Collapse ${label}`} title={`Collapse ( ${shortcut} )`}>
      <Icon className="h-4 w-4" />
    </Button>
  );
}

interface Props extends ToggleProps {
  open: boolean;
  /** open width in px */
  width: number;
  icon: LucideIcon;
  /** label shown on the collapsed rail */
  railTitle: string;
  railBadge?: ReactNode;
  /** extra content on the collapsed rail, under the icon */
  railExtra?: ReactNode;
  ariaLabel: string;
  /** grow from zero width when it appears (a panel that comes and goes); false = only fade and slide in */
  growIn?: boolean;
  children: ReactNode;
}

/**
 * A floating glass side panel that collapses to a slim rail. The state lives in the caller
 * (see useUiStore), so it is remembered. The inner box keeps its width while the outer one
 * animates, so text does not re-wrap during the transition. A panel that is always there
 * (`growIn={false}`) does not animate its width on first load, so the map does not re-fit while starting up.
 */
export function SidePanel({ side, open, width, icon: Icon, railTitle, railBadge, railExtra, ariaLabel, shortcut, onToggle, label, growIn = true, children }: Props) {
  const from = side === "left" ? -24 : 24;
  return (
    <motion.aside
      aria-label={ariaLabel}
      className="glass-strong relative h-full shrink-0 overflow-hidden rounded-xl"
      initial={{ width: growIn ? 0 : open ? width : RAIL_WIDTH, opacity: 0, x: from }}
      animate={{ width: open ? width : RAIL_WIDTH, opacity: 1, x: 0 }}
      exit={{ width: 0, opacity: 0, x: from }}
      transition={{ type: "spring", stiffness: 360, damping: 38, mass: 0.9 }}
    >
      {open ? (
        <motion.div
          key="open"
          className="flex h-full flex-col"
          style={{ width }}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.2, delay: 0.08 }}
        >
          {children}
        </motion.div>
      ) : (
        <div key="rail" className="flex h-full flex-col items-center gap-3 py-3" style={{ width: RAIL_WIDTH }}>
          <button
            type="button"
            onClick={onToggle}
            aria-label={`Expand ${label}`}
            title={`Expand ( ${shortcut} )`}
            className="group relative flex h-8 w-8 items-center justify-center rounded-md text-muted transition-colors hover:bg-white/[0.07] hover:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/70"
          >
            <Icon className="h-[18px] w-[18px]" />
            {railBadge}
          </button>
          {railExtra}
          <span className="micro-label mt-1 [text-orientation:mixed] [writing-mode:vertical-rl]">{railTitle}</span>
          <kbd className="mt-auto rounded border border-white/10 px-1.5 py-0.5 font-mono text-micro text-muted">{shortcut}</kbd>
        </div>
      )}
    </motion.aside>
  );
}
