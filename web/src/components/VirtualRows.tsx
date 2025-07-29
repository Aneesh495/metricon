import { useRef, useState, type ReactNode } from "react";

export function VirtualRows<T>({
  rows,
  columns,
  render,
  rowKey,
  label,
}: {
  rows: T[];
  columns: string[];
  render: (row: T) => ReactNode;
  rowKey: (row: T) => string;
  label: string;
}) {
  const viewport = useRef<HTMLDivElement>(null);
  const [top, setTop] = useState(0);
  const [expanded, setExpanded] = useState(false);
  const rowHeight = 76;
  const visible = expanded
    ? rows
    : rows.slice(
        Math.max(0, Math.floor(top / rowHeight) - 3),
        Math.floor(top / rowHeight) + 12,
      );
  const start = expanded ? 0 : Math.max(0, Math.floor(top / rowHeight) - 3);
  function move(key: string) {
    if (!viewport.current) return;
    const amount =
      key === "PageDown"
        ? 380
        : key === "PageUp"
          ? -380
          : key === "ArrowDown"
            ? 76
            : key === "ArrowUp"
              ? -76
              : 0;
    if (key === "Home") viewport.current.scrollTop = 0;
    else if (key === "End")
      viewport.current.scrollTop = rows.length * rowHeight;
    else viewport.current.scrollTop += amount;
  }
  return (
    <>
      <button
        className="text-button"
        onClick={() => setExpanded((value) => !value)}
      >
        {expanded ? "Use virtual table" : "Show full accessible page table"}
      </button>
      <div
        className="table-scroll"
        style={{ maxHeight: expanded ? undefined : 440, overflow: "auto" }}
        ref={viewport}
        tabIndex={0}
        aria-label={label}
        onScroll={(event) => setTop(event.currentTarget.scrollTop)}
        onKeyDown={(event) => {
          if (
            [
              "ArrowDown",
              "ArrowUp",
              "PageDown",
              "PageUp",
              "Home",
              "End",
            ].includes(event.key)
          ) {
            event.preventDefault();
            move(event.key);
          }
        }}
      >
        <table aria-rowcount={rows.length + 1}>
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={column} scope="col">
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {!expanded && start > 0 ? (
              <tr aria-hidden="true">
                <td
                  colSpan={columns.length}
                  style={{ height: start * rowHeight, padding: 0 }}
                />
              </tr>
            ) : null}
            {visible.map((row, index) => (
              <tr
                key={rowKey(row)}
                aria-rowindex={start + index + 2}
                style={{ height: rowHeight }}
              >
                {render(row)}
              </tr>
            ))}
            {!expanded && start + visible.length < rows.length ? (
              <tr aria-hidden="true">
                <td
                  colSpan={columns.length}
                  style={{
                    height: (rows.length - start - visible.length) * rowHeight,
                    padding: 0,
                  }}
                />
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </>
  );
}
