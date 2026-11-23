import { useUiStore } from "../store/useUiStore";
import { SHORTCUT_GROUPS } from "../utils/shortcuts";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "./ui/dialog";

/** Keyboard shortcut cheat sheet, opened with ? or from the command palette. */
export function HelpDialog() {
  const open = useUiStore((s) => s.helpOpen);
  const setOpen = useUiStore((s) => s.setHelpOpen);
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="max-w-lg">
        <div>
          <DialogTitle>Keyboard shortcuts</DialogTitle>
          <DialogDescription>Shortcuts are ignored while you type in a field.</DialogDescription>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          {SHORTCUT_GROUPS.map((group) => (
            <section key={group.title} className={group.title === "Everywhere" ? "sm:col-span-2" : undefined} aria-label={group.title}>
              <h3 className="micro-label mb-1.5">{group.title}</h3>
              <dl className="grid grid-cols-[auto_1fr] items-center gap-x-4 gap-y-1.5">
                {group.items.map((item) => (
                  <div key={`${item.keys.join("+")}-${item.label}`} className="contents">
                    <dt className="flex gap-1">
                      {item.keys.map((k) => (
                        <kbd key={k} className="min-w-[1.5rem] rounded border border-white/15 bg-white/5 px-1.5 text-center font-mono text-caption text-text">
                          {k}
                        </kbd>
                      ))}
                    </dt>
                    <dd className="text-body text-muted">{item.label}</dd>
                  </div>
                ))}
              </dl>
            </section>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}
