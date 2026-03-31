"use client";

export default function Error({
  error: _error,
  reset,
}: {
  error: Error;
  reset: () => void;
}) {
  return (
    <div className="h-full flex items-center justify-center">
      <div className="text-center space-y-3">
        <p className="text-sm text-error">Something went wrong</p>
        <button
          onClick={reset}
          className="text-xs text-accent hover:underline"
        >
          Try again
        </button>
      </div>
    </div>
  );
}
