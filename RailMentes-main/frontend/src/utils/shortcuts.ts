/** Keyboard shortcuts shown in the help dialog (the handlers live next to the features they control). */
export interface ShortcutGroup {
  title: string;
  items: { keys: string[]; label: string }[];
}

export const SHORTCUT_GROUPS: ShortcutGroup[] = [
  {
    title: "Everywhere",
    items: [
      { keys: ["Ctrl", "K"], label: "Open the command palette" },
      { keys: ["?"], label: "Show this help" },
      { keys: ["1"], label: "Map tab" },
      { keys: ["2"], label: "Time-distance tab" },
      { keys: ["3"], label: "Compare tab" },
      { keys: ["Space"], label: "Start or pause the simulation" },
      { keys: ["["], label: "Show or hide the alerts panel" },
      { keys: ["]"], label: "Show or hide the train panel" },
      { keys: ["Esc"], label: "Close the train panel or a dialog" },
    ],
  },
  {
    title: "Map",
    items: [
      { keys: ["+"], label: "Zoom in" },
      { keys: ["-"], label: "Zoom out" },
      { keys: ["0"], label: "Fit the corridor to the screen" },
      { keys: ["F"], label: "Fit the corridor to the screen" },
      { keys: ["Wheel"], label: "Zoom about the cursor" },
      { keys: ["Drag"], label: "Pan" },
    ],
  },
  {
    title: "Time-distance graph",
    items: [
      { keys: ["Wheel"], label: "Zoom" },
      { keys: ["Drag"], label: "Pan" },
      { keys: ["Click"], label: "Select a train (same as the map)" },
    ],
  },
];
