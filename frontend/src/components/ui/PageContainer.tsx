import { type ReactNode } from "react";

export function PageContainer({
  wide,
  children,
}: {
  wide?: boolean;
  children: ReactNode;
}) {
  return (
    <div className="h-full overflow-y-auto">
      <div
        className={`${wide ? "max-w-7xl" : "max-w-6xl"} mx-auto px-4 sm:px-6 lg:px-8 py-6 sm:py-8 space-y-6`}
      >
        {children}
      </div>
    </div>
  );
}
