"use client";

interface Column<T> {
  key: string;
  label: string;
  render?: (row: T) => React.ReactNode;
  className?: string;
}

interface Props<T> {
  columns: Column<T>[];
  rows: T[];
  onRowClick?: (row: T) => void;
  emptyMessage?: string;
}

export function DataTable<T extends Record<string, unknown>>({
  columns,
  rows,
  onRowClick,
  emptyMessage = "No data",
}: Props<T>) {
  if (!rows.length) {
    return (
      <div className="py-12 text-center text-sm text-zinc-600">{emptyMessage}</div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-zinc-800/60">
            {columns.map((col) => (
              <th
                key={col.key}
                className={`text-left px-4 py-2.5 text-[11px] font-semibold text-zinc-500 uppercase tracking-wide ${col.className ?? ""}`}
              >
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr
              key={i}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              className={`border-b border-zinc-800/30 ${
                onRowClick ? "cursor-pointer hover:bg-zinc-800/20" : ""
              } transition-colors`}
            >
              {columns.map((col) => (
                <td key={col.key} className={`px-4 py-2.5 text-zinc-300 ${col.className ?? ""}`}>
                  {col.render ? col.render(row) : (row[col.key] != null ? String(row[col.key]) : "—")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
