"use client";

import type { TableView } from "@/lib/types";

export function TableViewComponent({ data }: { data: TableView }) {
  const columns = data.columns.length > 0
    ? data.columns
    : Object.keys(data.rows[0] ?? {}).map((k) => ({
        key: k,
        label: k.charAt(0).toUpperCase() + k.slice(1),
        data_type: "string",
        sortable: false,
      }));

  return (
    <div className="rounded-xl border border-zinc-700/50 overflow-hidden">
      <div className="px-6 py-4 border-b border-zinc-700/50">
        <h3 className="text-lg font-semibold text-zinc-100">{data.title}</h3>
        <p className="text-sm text-zinc-400 mt-0.5">
          {data.total_count || data.rows.length} records
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-700/50 bg-zinc-800/50">
              {columns.map((col) => (
                <th
                  key={col.key}
                  className="px-6 py-3 text-left font-medium text-zinc-400 uppercase tracking-wide text-xs"
                >
                  {col.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800/50">
            {data.rows.map((row, i) => (
              <tr
                key={i}
                className="hover:bg-zinc-800/30 transition-colors"
              >
                {columns.map((col) => (
                  <td key={col.key} className="px-6 py-3 text-zinc-200">
                    {String(row[col.key] ?? "")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
