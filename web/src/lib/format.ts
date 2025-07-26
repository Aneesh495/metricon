export function number(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || !Number.isFinite(value))
    return "Unknown";
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: digits,
  }).format(value);
}
export function percentage(
  value: number | null | undefined,
  digits = 1,
): string {
  return value === null || value === undefined
    ? "Unknown"
    : `${number(value * 100, digits)}%`;
}
export function hash(value: string | undefined | null, length = 12): string {
  return value ? value.slice(0, length) : "No version";
}
export function bytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 ** 2) return `${number(value / 1024, 1)} KB`;
  if (value < 1024 ** 3) return `${number(value / 1024 ** 2, 1)} MB`;
  return `${number(value / 1024 ** 3, 1)} GB`;
}
export function date(value: number): string {
  return new Date(value * 1000).toLocaleString();
}
export function downloadJSON(value: unknown, filename: string): void {
  const objectURL = URL.createObjectURL(
    new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }),
  );
  const link = document.createElement("a");
  link.href = objectURL;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(objectURL);
}
export function parseObject(
  text: string,
  label: string,
): Record<string, unknown> {
  const value: unknown = JSON.parse(text);
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new Error(`${label} must be a JSON object`);
  return value as Record<string, unknown>;
}
