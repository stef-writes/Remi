"use client";

const SUGGESTIONS = [
  "How is Marcus doing this month?",
  "Which properties have the most turnover?",
  "Are any leases expiring soon that I should know about?",
  "Compare my managers on occupancy",
  "What's changed since my last upload?",
];

export function SessionEmptyState({
  onSend,
  connected,
  streaming,
  mode,
}: {
  onSend: (text: string) => void;
  connected: boolean;
  streaming: boolean;
  mode: "ask" | "agent";
}) {
  return (
    <div className="flex-1 flex items-center justify-center">
      <div className="flex flex-col items-center space-y-8 py-16">
        <div className="text-center space-y-2">
          <h2 className="text-lg font-semibold text-zinc-200">
            What would you like to know?
          </h2>
          <p className="text-sm text-zinc-500 max-w-md">
            Ask about your managers, properties, leases, or finances.
            {mode === "agent" &&
              " In deep dive mode, REMI can run its own analysis and find patterns in your data."}
          </p>
        </div>

        <div className="w-full max-w-md space-y-1.5">
          {SUGGESTIONS.map((q) => (
            <button
              key={q}
              onClick={() => onSend(q)}
              disabled={!connected || streaming}
              className="w-full text-left px-4 py-2.5 rounded-xl border border-zinc-800/40 text-sm text-zinc-400 hover:text-zinc-200 hover:border-zinc-700 hover:bg-zinc-800/30 transition-all disabled:opacity-40"
            >
              {q}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
