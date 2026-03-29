"use client";

import type { ProfileView } from "@/lib/types";

export function ProfileViewComponent({ data }: { data: ProfileView }) {
  return (
    <div className="rounded-xl border border-zinc-700/50 overflow-hidden">
      <div className="px-6 py-4 border-b border-zinc-700/50">
        <p className="text-xs font-medium text-zinc-500 uppercase tracking-wide">
          {data.entity_type}
        </p>
        <h3 className="text-xl font-bold text-zinc-100 mt-1">{data.title}</h3>
        <p className="text-sm text-zinc-400">{data.entity_id}</p>
      </div>
      <div className="divide-y divide-zinc-800/50">
        {data.sections.map((section, i) => (
          <div key={i} className="px-6 py-4">
            <h4 className="text-sm font-semibold text-zinc-300 mb-3">
              {section.heading}
            </h4>
            <dl className="grid grid-cols-2 gap-x-8 gap-y-2">
              {section.fields.map((field, j) => (
                <div key={j}>
                  <dt className="text-xs text-zinc-500">{field.label}</dt>
                  <dd className="text-sm text-zinc-200">
                    {String(field.value ?? "—")}
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        ))}
      </div>
    </div>
  );
}
