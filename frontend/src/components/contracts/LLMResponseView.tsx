"use client";

export function LLMResponseView({ data }: { data: unknown }) {
  const text = typeof data === "string" ? data : JSON.stringify(data, null, 2);

  return (
    <div className="rounded-xl border border-zinc-700/50 p-6 bg-zinc-800/30">
      <div className="flex items-center gap-2 mb-3">
        <div className="h-2 w-2 rounded-full bg-violet-400" />
        <span className="text-xs font-medium text-violet-400 uppercase tracking-wide">
          Agent Response
        </span>
      </div>
      <div className="prose prose-invert prose-sm max-w-none">
        <pre className="whitespace-pre-wrap text-zinc-200 text-sm leading-relaxed font-sans">
          {text}
        </pre>
      </div>
    </div>
  );
}
