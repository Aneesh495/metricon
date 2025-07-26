import { useId, useState, type ReactNode } from "react";
import {
  AlertCircle,
  Check,
  ChevronDown,
  ChevronUp,
  Copy,
  Download,
  Loader2,
} from "lucide-react";
import { downloadJSON, number, percentage } from "../lib/format";
import type { Interval } from "../api/contracts";

export function Panel({
  title,
  eyebrow,
  description,
  action,
  children,
  className = "",
}: {
  title: string;
  eyebrow?: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      <header className="panel-header">
        <div>
          {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
          <h2>{title}</h2>
          {description ? <p className="muted">{description}</p> : null}
        </div>
        {action}
      </header>
      {children}
    </section>
  );
}

export function Notice({
  children,
  tone = "info",
}: {
  children: ReactNode;
  tone?: "info" | "warning" | "danger" | "success";
}) {
  return (
    <div
      className={`notice ${tone}`}
      role={tone === "danger" ? "alert" : "status"}
    >
      <AlertCircle size={16} aria-hidden="true" />
      <div>{children}</div>
    </div>
  );
}

export function Empty({
  title,
  children,
  action,
}: {
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-orbit" aria-hidden="true">
        <span />
        <span />
        <span />
      </div>
      <p className="eyebrow">An honest starting point</p>
      <h2>{title}</h2>
      <p>{children}</p>
      {action}
    </div>
  );
}

export function Loading({
  label = "Reading committed data",
}: {
  label?: string;
}) {
  return (
    <div className="loading" role="status">
      <Loader2 className="spin" size={18} />
      {label}
    </div>
  );
}

export function ErrorState({
  error,
  retry,
}: {
  error: unknown;
  retry?: () => void;
}) {
  const message = error instanceof Error ? error.message : String(error);
  return (
    <Notice tone="danger">
      <strong>Request failed.</strong> {message}
      {retry ? (
        <button className="text-button" onClick={retry}>
          Retry
        </button>
      ) : null}
    </Notice>
  );
}

export function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: ReactNode;
  hint?: string;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
      {hint ? <small>{hint}</small> : null}
    </label>
  );
}

export function CheckField({
  label,
  checked,
  onChange,
  hint,
}: {
  label: string;
  checked: boolean;
  onChange: (value: boolean) => void;
  hint?: string;
}) {
  const id = useId();
  return (
    <div className="check-field">
      <input
        id={id}
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
      />
      <label htmlFor={id}>
        {label}
        {hint ? <small>{hint}</small> : null}
      </label>
    </div>
  );
}

export function Metric({
  label,
  value,
  detail,
  accent = false,
}: {
  label: string;
  value: string;
  detail: ReactNode;
  accent?: boolean;
}) {
  return (
    <div className={`metric ${accent ? "accent" : ""}`}>
      <p>{label}</p>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  );
}

export function IntervalBar({
  value,
  label,
}: {
  value: Interval;
  label?: string;
}) {
  if (value.estimate === null || value.lower === null || value.upper === null)
    return <span className="muted">Unknown, n = 0</span>;
  return (
    <div
      className="interval-wrap"
      title={`${label ?? "Observed accuracy"}: ${percentage(value.estimate)}; ${percentage(value.lower)} to ${percentage(value.upper)}, n=${value.n}`}
    >
      <span className="interval-label">
        {percentage(value.estimate)} <small>n={number(value.n)}</small>
      </span>
      <div
        className="interval-track"
        role="img"
        aria-label={`95 percent Wilson interval from ${percentage(value.lower)} to ${percentage(value.upper)}`}
      >
        <div
          className="interval-band"
          style={{
            left: `${value.lower * 100}%`,
            width: `${(value.upper - value.lower) * 100}%`,
          }}
        />
        <div
          className="interval-dot"
          style={{ left: `${value.estimate * 100}%` }}
        />
      </div>
    </div>
  );
}

export function Pagination({
  offset,
  limit,
  total,
  onChange,
}: {
  offset: number;
  limit: number;
  total: number;
  onChange: (value: number) => void;
}) {
  return (
    <div className="pagination">
      <span>
        {total
          ? `${number(offset + 1)} to ${number(Math.min(total, offset + limit))} of ${number(total)}`
          : "No eligible rows"}
      </span>
      <div>
        <button
          className="secondary"
          disabled={offset === 0}
          onClick={() => onChange(Math.max(0, offset - limit))}
        >
          Previous
        </button>
        <button
          className="secondary"
          disabled={offset + limit >= total}
          onClick={() => onChange(offset + limit)}
        >
          Next
        </button>
      </div>
    </div>
  );
}

export function Inspector({
  value,
  title = "Inspect artifact",
  initiallyOpen = false,
}: {
  value: unknown;
  title?: string;
  initiallyOpen?: boolean;
}) {
  const [open, setOpen] = useState(initiallyOpen);
  const [copied, setCopied] = useState(false);
  const text = JSON.stringify(value, null, 2);
  async function copy() {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 2000);
  }
  return (
    <div className="inspector">
      <div className="inspector-toolbar">
        <button
          className="text-button"
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
        >
          {open ? <ChevronUp size={16} /> : <ChevronDown size={16} />} {title}
        </button>
        <div>
          <button
            className="icon-button"
            aria-label="Copy JSON"
            onClick={() => void copy()}
          >
            {copied ? <Check size={16} /> : <Copy size={16} />}
          </button>
          <button
            className="icon-button"
            aria-label="Download JSON"
            onClick={() => downloadJSON(value, "metricon-artifact.json")}
          >
            <Download size={16} />
          </button>
        </div>
      </div>
      {open ? <pre>{text}</pre> : null}
    </div>
  );
}

export function Tag({
  children,
  tone = "",
}: {
  children: ReactNode;
  tone?: string;
}) {
  return <span className={`tag ${tone}`}>{children}</span>;
}
