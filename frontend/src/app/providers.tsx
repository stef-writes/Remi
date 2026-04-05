"use client";

import type { ReactNode } from "react";
import { TooltipProvider } from "@/components/ui/Tooltip";

export function Providers({ children }: { children: ReactNode }) {
  return <TooltipProvider>{children}</TooltipProvider>;
}
