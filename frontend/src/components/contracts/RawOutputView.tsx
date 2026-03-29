"use client";

export function RawOutputView({
  data,
  contract,
}: {
  data: unknown;
  contract: string | null;
}) {
  const text =
    typeof data === "string" ? data : JSON.stringify(data, null, 2);

  return (
    <div className="rounded-xl border border-zinc-700/50 p-6 bg-zinc-900/50">
      {contract && (
        <span className="inline-block px-2 py-0.5 text-xs font-mono rounded bg-zinc-700/50 text-zinc-400 mb-3">
          {contract}
        </span>
      )}
      <pre className="text-sm text-zinc-300 whitespace-pre-wrap overflow-x-auto font-mono">
        {text}
      </pre>
    </div>
  );
}
