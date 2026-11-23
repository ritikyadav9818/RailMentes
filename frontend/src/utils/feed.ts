/** Turns conflicts + recommendations from a snapshot into the cards of the alerts feed. */
import type { Conflict, Recommendation, Severity } from "../api/types";

export const SEVERITY_RANK: Record<Severity, number> = { low: 0, medium: 1, high: 2, critical: 3 };

export interface FeedItem {
  /** stable React key: the first conflict's id (or the recommendation id when its conflict is gone) */
  key: string;
  conflicts: Conflict[];
  recommendation: Recommendation | null;
  severity: Severity;
  /** earliest predicted conflict time (scenario minute) */
  timeMin: number;
}

export interface Feed {
  /** still needs attention (open conflicts and their recommendations), most severe first */
  active: FeedItem[];
  /** recommendations that were applied or ignored and whose conflicts are gone, newest first */
  handled: FeedItem[];
}

function maxSeverity(conflicts: Conflict[]): Severity {
  return conflicts.reduce<Severity>((best, c) => (SEVERITY_RANK[c.severity] > SEVERITY_RANK[best] ? c.severity : best), "low");
}

function makeItem(key: string, conflicts: Conflict[], recommendation: Recommendation | null): FeedItem {
  return {
    key,
    conflicts,
    recommendation,
    severity: maxSeverity(conflicts),
    timeMin: conflicts.length > 0 ? Math.min(...conflicts.map((c) => c.time_min)) : 0,
  };
}

export function compareItems(a: FeedItem, b: FeedItem): number {
  return SEVERITY_RANK[b.severity] - SEVERITY_RANK[a.severity] || a.timeMin - b.timeMin || a.key.localeCompare(b.key);
}

export function buildFeed(conflicts: Conflict[], recommendations: Recommendation[]): Feed {
  const byId = new Map(conflicts.map((c) => [c.id, c]));
  const claimed = new Set<string>();
  const active: FeedItem[] = [];
  const handled: FeedItem[] = [];

  for (const rec of recommendations) {
    const live = rec.conflict_ids.map((id) => byId.get(id)).filter((c): c is Conflict => c !== undefined);
    const isOpen = rec.status === "proposed" || rec.status === "undone";
    if (live.length === 0 && isOpen) continue; // conflict gone: the backend drops it too
    live.forEach((c) => claimed.add(c.id));
    // keyed by its first conflict, so a card keeps its identity when a recommendation arrives for it
    const item = makeItem(live.length > 0 ? live[0].id : rec.id, live, rec);
    (live.length > 0 ? active : handled).push(item);
  }
  for (const c of conflicts) {
    if (!claimed.has(c.id)) active.push(makeItem(c.id, [c], null));
  }
  active.sort(compareItems);
  handled.reverse();
  return { active, handled: handled.slice(0, 5) };
}
