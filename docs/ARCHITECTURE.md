# Data flow

1. The browser extension or export script writes attempt history to
   `localStorage`.
2. The dashboard reads a pasted or uploaded JSON blob on the client.
3. `data-processor.ts` normalizes attempts, computes per-question accuracy, and
   feeds Recharts components.
4. Optional server routes persist nothing by default; the app is designed for
   offline-first analytics on exported snapshots.
