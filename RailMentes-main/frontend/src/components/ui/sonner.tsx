import { Toaster as Sonner } from "sonner";

/** Toasts styled with the control-room tokens (shadcn "sonner" component). */
export function Toaster() {
  return (
    <Sonner
      theme="dark"
      position="bottom-right"
      toastOptions={{
        classNames: {
          toast: "!bg-panel !border-border !text-text",
          description: "!text-muted",
          actionButton: "!bg-accent !text-bg",
        },
      }}
    />
  );
}
