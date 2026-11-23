import { useMemo, useState } from "react";

import type { DisruptionKind } from "../api/types";
import { injectDisruption } from "../store/controls";
import { useRailStore } from "../store/useRailStore";
import { DISRUPTION_LABELS } from "../utils/labels";
import { buildSegments } from "../utils/layout";
import { Button } from "./ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "./ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";

export type InjectKind = Extract<DisruptionKind, "fog" | "signal_failure" | "block_closure" | "late_departure">;

const DEFAULT_MINUTES: Record<InjectKind, number> = { fog: 60, signal_failure: 30, block_closure: 45, late_departure: 20 };
const BLURB: Record<InjectKind, string> = {
  fog: "Slows trains to 60% on the chosen stretch.",
  signal_failure: "Trains crawl at 30% speed through the chosen section.",
  block_closure: "Trains cannot enter the section until it reopens.",
  late_departure: "Holds one train at its origin before it departs.",
};
const NETWORK = "*";

interface Props {
  kind: InjectKind | null;
  onClose: () => void;
}

/** Parameters for one injected disruption: duration and where (or which train). */
export function InjectDialog({ kind, onClose }: Props) {
  const network = useRailStore((s) => s.network);
  const snapshot = useRailStore((s) => s.snapshot);
  const [minutes, setMinutes] = useState<number | null>(null);
  const [target, setTarget] = useState<string>("");
  const [busy, setBusy] = useState(false);

  const segments = useMemo(() => (network ? buildSegments(network.blocks) : []), [network]);
  const waiting = useMemo(() => (snapshot?.trains ?? []).filter((t) => t.status === "not_started"), [snapshot]);

  const isTrain = kind === "late_departure";
  const allowNetwork = kind === "fog";
  const duration = minutes ?? (kind ? DEFAULT_MINUTES[kind] : 30);
  const chosen = target || (allowNetwork ? NETWORK : "");
  const canSubmit = kind !== null && !busy && duration > 0 && chosen !== "";

  const close = () => {
    setMinutes(null);
    setTarget("");
    onClose();
  };

  const submit = async () => {
    if (!kind) return;
    let target_ids: string[] = [];
    if (isTrain) target_ids = [chosen];
    else if (chosen !== NETWORK) target_ids = segments.find((s) => s.id === chosen)?.blocks.map((b) => b.id) ?? [];
    setBusy(true);
    const ok = await injectDisruption({ kind, duration_min: duration, target_ids });
    setBusy(false);
    if (ok) close();
  };

  return (
    <Dialog open={kind !== null} onOpenChange={(open) => !open && close()}>
      <DialogContent>
        <div>
          <DialogTitle>Inject {kind ? DISRUPTION_LABELS[kind].toLowerCase() : ""}</DialogTitle>
          <DialogDescription>{kind ? BLURB[kind] : ""} Takes effect now.</DialogDescription>
        </div>

        <label className="grid gap-1 text-xs text-muted">
          {isTrain ? "Train (not departed yet)" : "Where"}
          <Select value={chosen} onValueChange={setTarget}>
            <SelectTrigger aria-label={isTrain ? "Train" : "Location"}>
              <SelectValue placeholder={isTrain ? "Choose a train" : "Choose a section"} />
            </SelectTrigger>
            <SelectContent>
              {allowNetwork && <SelectItem value={NETWORK}>Whole network</SelectItem>}
              {isTrain
                ? waiting.map((t) => (
                    <SelectItem key={t.id} value={t.id}>
                      <span className="font-mono">{t.id}</span> {t.name}
                    </SelectItem>
                  ))
                : segments.map((s) => (
                    <SelectItem key={s.id} value={s.id}>
                      {s.from} - {s.to} ({s.line} line)
                    </SelectItem>
                  ))}
            </SelectContent>
          </Select>
          {isTrain && waiting.length === 0 && <span className="text-warn">Every train has already left its origin.</span>}
        </label>

        <label className="grid gap-1 text-xs text-muted">
          {isTrain ? "Lateness (minutes)" : "Duration (minutes)"}
          <input
            type="number"
            min={5}
            max={isTrain ? 60 : 120}
            value={duration}
            onChange={(e) => setMinutes(Number(e.target.value))}
            className="h-9 rounded-md border border-border bg-bg px-3 font-mono text-sm text-text focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/70"
          />
        </label>

        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={close}>
            Cancel
          </Button>
          <Button variant="warn" disabled={!canSubmit} onClick={() => void submit()}>
            Inject
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
