"use client";

export function Empty({
  icon,
  title,
  description,
}: {
  icon?: React.ReactNode;
  title: string;
  description?: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-center">
      {icon && <div className="mb-4 text-zinc-700">{icon}</div>}
      <h3 className="text-sm font-medium text-zinc-400 mb-1">{title}</h3>
      {description && (
        <p className="text-xs text-zinc-600 max-w-xs">{description}</p>
      )}
    </div>
  );
}
