import { TriangleAlert } from "lucide-react";

/**
 * Plain-language limits of the results. Always visible at the top of the Compare tab.
 * The CP-SAT vs priority-rule numbers are quoted from docs/RESULTS.md section 3 (20 seeds, ML delay model).
 */
export function CaveatPanel() {
  return (
    <aside className="rounded-xl border border-warn/40 bg-warn/[0.07] p-4" aria-label="How to read these results">
      <div className="flex items-start gap-3">
        <TriangleAlert className="mt-0.5 h-5 w-5 shrink-0 text-warn" aria-hidden="true" />
        <div className="min-w-0">
          <h2 className="text-title font-semibold text-text">Read this before the numbers</h2>
          <ul className="mt-2 grid gap-x-8 gap-y-1.5 text-body text-text/90 xl:grid-cols-2">
            <li>
              <strong className="font-semibold text-warn">Synthetic data, simulation only.</strong> The corridor, the timetable, the delays and the
              disruptions are generated. Nothing here is measured on real railways.
            </li>
            <li>
              <strong className="font-semibold text-warn">The gains are modest.</strong> Over 20 seeds, with the delay model in the loop, the CP-SAT
              optimizer beats the priority rule by about 0.4 / 0.7 / 0.5 min of average delay (low / medium / high disruption), roughly 2-5%. At
              high disruption the weighted delay and punctuality are not reliably different. Without the delay model it is no better than the
              priority rule. Punctuality and throughput barely move.
            </li>
            <li className="xl:col-span-2">
              <strong className="font-semibold text-warn">&ldquo;Saves X min&rdquo; on a recommendation is a prediction, not a result.</strong> It is
              the optimizer&rsquo;s own estimate and overstates the real gain: over 24 test days the claimed savings were about 1.4 times what was
              actually gained against no control.
            </li>
          </ul>
        </div>
      </div>
    </aside>
  );
}
