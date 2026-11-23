import * as DialogPrimitive from "@radix-ui/react-dialog";
import { CornerDownLeft, Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { pauseSimulation, replaySameScenario, resetSimulation, startGuidedDemo, startSimulation, commitStrategy } from "../store/controls";
import { useRailStore } from "../store/useRailStore";
import { useUiStore } from "../store/useUiStore";
import { cn } from "../utils/cn";
import { buildCommands, filterCommands, type CommandActions } from "../utils/commands";
import { Dialog } from "./ui/dialog";

/** Real implementations of the palette's actions. */
export function useCommandActions(): CommandActions {
  return useMemo<CommandActions>(
    () => ({
      start: () => void startSimulation(),
      pause: () => void pauseSimulation(),
      reset: () => void resetSimulation(),
      setStrategy: (strategy) => {
        useRailStore.getState().updateSettings({ strategy });
        void commitStrategy();
      },
      inject: (kind) => useUiStore.getState().setInjectKind(kind),
      setTab: (tab) => useUiStore.getState().setTab(tab),
      replay: (strategy) => void replaySameScenario(strategy),
      demo: () => void startGuidedDemo(),
      openHelp: () => useUiStore.getState().setHelpOpen(true),
      toggleAlerts: () => useUiStore.getState().toggleAlerts(),
      toggleTrain: () => useUiStore.getState().toggleTrain(),
    }),
    [],
  );
}

/** Ctrl+K command palette: type to filter, arrows to move, Enter to run, Esc to close. */
export function CommandPalette() {
  const open = useUiStore((s) => s.paletteOpen);
  const setOpen = useUiStore((s) => s.setPaletteOpen);
  const live = useRailStore((s) => s.dataSource === "live");
  const running = useRailStore((s) => s.snapshot?.running ?? false);
  const strategy = useRailStore((s) => s.snapshot?.strategy ?? s.settings.strategy);
  const actions = useCommandActions();
  const [query, setQuery] = useState("");
  const [index, setIndex] = useState(0);
  const listRef = useRef<HTMLUListElement>(null);

  const commands = useMemo(() => buildCommands({ live, running, strategy, actions }), [live, running, strategy, actions]);
  const results = useMemo(() => filterCommands(commands, query), [commands, query]);

  useEffect(() => {
    if (open) {
      setQuery("");
      setIndex(0);
    }
  }, [open]);
  useEffect(() => setIndex(0), [query]);
  useEffect(() => {
    listRef.current?.querySelector<HTMLElement>("[aria-selected=true]")?.scrollIntoView({ block: "nearest" });
  }, [index]);

  const run = (i: number) => {
    const cmd = results[i];
    if (!cmd || !cmd.enabled) return;
    setOpen(false);
    cmd.run();
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setIndex((i) => Math.min(results.length - 1, i + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setIndex((i) => Math.max(0, i - 1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      run(index);
    }
  };

  let lastSection = "";
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/60 data-[state=open]:animate-in data-[state=open]:fade-in-0" />
        <DialogPrimitive.Content
          className="glass-strong fixed left-1/2 top-[14%] z-50 w-[calc(100%-2rem)] max-w-xl -translate-x-1/2 overflow-hidden rounded-xl data-[state=open]:animate-in data-[state=open]:fade-in-0"
          aria-describedby={undefined}
        >
          <DialogPrimitive.Title className="sr-only">Command palette</DialogPrimitive.Title>
          <div className="flex items-center gap-2 border-b border-white/10 px-3">
            <Search className="h-4 w-4 shrink-0 text-muted" aria-hidden="true" />
            <input
              autoFocus
              role="combobox"
              aria-expanded="true"
              aria-controls="palette-list"
              aria-activedescendant={results[index] ? `cmd-${results[index].id}` : undefined}
              aria-label="Type a command"
              placeholder="Type a command: start, strategy, inject fog, compare ..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={onKeyDown}
              className="h-11 w-full bg-transparent text-body text-text placeholder:text-muted focus:outline-none"
            />
            <kbd className="rounded border border-white/15 px-1.5 font-mono text-micro tracking-normal text-muted">Esc</kbd>
          </div>
          <ul ref={listRef} id="palette-list" role="listbox" aria-label="Commands" className="max-h-[22rem] overflow-y-auto p-1.5">
            {results.length === 0 && (
              <li className="px-3 py-6 text-center text-body text-muted" role="presentation">
                No command matches &ldquo;{query}&rdquo;.
              </li>
            )}
            {results.map((cmd, i) => {
              const heading = cmd.section !== lastSection && query === "";
              lastSection = cmd.section;
              return (
                <li key={cmd.id} role="presentation">
                  {heading && <div className="micro-label px-2.5 pb-1 pt-2">{cmd.section}</div>}
                  <div
                    id={`cmd-${cmd.id}`}
                    role="option"
                    aria-selected={i === index}
                    aria-disabled={!cmd.enabled}
                    onMouseMove={() => setIndex(i)}
                    onClick={() => run(i)}
                    className={cn(
                      "flex cursor-pointer items-center gap-3 rounded-md px-2.5 py-2 text-body",
                      i === index ? "bg-accent/15 text-text" : "text-text/90",
                      !cmd.enabled && "cursor-not-allowed opacity-40",
                    )}
                  >
                    <span className="min-w-0 flex-1 truncate">{cmd.title}</span>
                    {!cmd.enabled && <span className="text-caption text-muted">{cmd.id.startsWith("strategy.") || cmd.id.startsWith("replay.") ? "current or offline" : "offline"}</span>}
                    {cmd.shortcut && <kbd className="rounded border border-white/15 px-1.5 font-mono text-micro tracking-normal text-muted">{cmd.shortcut}</kbd>}
                    {i === index && cmd.enabled && <CornerDownLeft className="h-3.5 w-3.5 text-accent" aria-hidden="true" />}
                  </div>
                </li>
              );
            })}
          </ul>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </Dialog>
  );
}
