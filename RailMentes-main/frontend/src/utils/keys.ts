/** True if a key press should be left alone because the user is typing or a modifier is held. */
export function ignoreShortcut(e: KeyboardEvent): boolean {
  if (e.ctrlKey || e.metaKey || e.altKey) return true;
  const el = e.target instanceof HTMLElement ? e.target : null;
  if (!el) return false;
  return el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName) || el.closest("[role=dialog], [role=listbox], [role=menu]") !== null;
}
