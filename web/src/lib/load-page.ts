import { z } from "zod";

const reloadToken = new URLSearchParams(window.location.search).get(
  "_workbench_reload",
);
const ModuleSchema = z.object({
  file: z.string().regex(/^assets\/[A-Za-z0-9._-]+\.js$/),
  isDynamicEntry: z.literal(true),
});

export async function loadPage<T>(
  page: string,
  load: () => Promise<T>,
): Promise<T> {
  try {
    return await load();
  } catch (error) {
    if (!reloadToken) throw error;
    const response = await fetch("/manifest.json", { cache: "no-store" });
    if (!response.ok) throw error;
    const manifest = z.record(z.unknown()).parse(await response.json());
    const entry = ModuleSchema.parse(manifest[`src/pages/${page}.tsx`]);
    const recovered: Record<string, unknown> = await import(
      /* @vite-ignore */ `/${entry.file}?workbench_reload=${encodeURIComponent(reloadToken)}`
    );
    if (typeof recovered[page] !== "function") throw error;
    return recovered as T;
  }
}
