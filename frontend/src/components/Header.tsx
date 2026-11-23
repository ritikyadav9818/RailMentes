import { FlaskConical, Loader2, Radio, TriangleAlert } from "lucide-react";

import { useRailStore, type Connection } from "../store/useRailStore";
import { ControlBar } from "./ControlBar";
import { SimClock } from "./SimClock";
import { Badge } from "./ui/badge";

const BADGES: Record<Connection, { tone: "ok" | "warn" | "neutral"; label: string }> = {
  online: { tone: "ok", label: "Live" },
  connecting: { tone: "neutral", label: "Connecting..." },
  reconnecting: { tone: "warn", label: "Reconnecting" },
  offline_demo: { tone: "warn", label: "Offline demo data" },
};

/** Where the numbers on screen come from: live backend, last data while reconnecting, or bundled demo data. */
export function ConnectionBadge() {
  const connection = useRailStore((s) => s.connection);
  const { tone, label } = BADGES[connection];
  const Icon = connection === "online" ? Radio : connection === "connecting" ? Loader2 : TriangleAlert;
  return (
    <Badge
      tone={tone}
      className="min-w-[7.5rem] justify-center"
      role="status"
      title={
        connection === "offline_demo"
          ? "The backend is not reachable. Showing a bundled sample frame; it will switch to live data when the backend starts."
          : connection === "reconnecting"
            ? "Connection lost. The last live frame stays on screen until the backend answers again."
            : undefined
      }
    >
      {connection === "online" ? (
        <span className="live-dot relative mr-0.5 h-1.5 w-1.5 rounded-full bg-ok" aria-hidden="true" />
      ) : (
        <Icon className={connection === "connecting" ? "h-3 w-3 animate-spin" : "h-3 w-3"} />
      )}
      {label}
    </Badge>
  );
}

/** Logo mark: two rails running into the distance. */
function Logo() {
  return (
    <svg width="28" height="28" viewBox="0 0 32 32" aria-hidden="true" className="shrink-0">
      <defs>
        <linearGradient id="logo-bg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#16324a" />
          <stop offset="1" stopColor="#0a131d" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="8" fill="url(#logo-bg)" stroke="#38bdf8" strokeOpacity="0.45" />
      <path d="M8 23h16M10.5 23l3-13h5l3 13M12.3 17h7.4" stroke="#38bdf8" strokeWidth="2.2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** Top bar: brand, run controls, clock and the data-source chips. */
export function Header() {
  return (
    <header className="glass-strong z-20 mx-2 mt-2 flex min-h-[3.25rem] shrink-0 flex-wrap items-center gap-x-4 gap-y-2 rounded-xl px-3 py-2">
      <div className="flex items-center gap-2.5">
        <Logo />
        <div className="leading-tight">
          <h1 className="font-mono text-title font-semibold tracking-wide text-text">RailMentes</h1>
          <p className="hidden text-micro tracking-normal text-muted 2xl:block">AI-powered train traffic control</p>
        </div>
      </div>
      <div className="lg:border-l lg:border-white/10 lg:pl-4">
        <ControlBar />
      </div>
      <div className="ml-auto flex items-center gap-3">
        <SimClock />
        <Badge tone="accent" title="Fictional network, generated timetables and disruptions. Not real Indian Railways data.">
          <FlaskConical className="h-3 w-3" />
          Synthetic data
        </Badge>
        <ConnectionBadge />
      </div>
    </header>
  );
}
