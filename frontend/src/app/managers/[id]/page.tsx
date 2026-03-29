"use client";

import { use } from "react";
import { Shell } from "@/components/Shell";
import { ManagerReviewView } from "@/components/managers/ManagerReviewView";

export default function ManagerReviewPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  return (
    <Shell>
      <ManagerReviewView managerId={id} />
    </Shell>
  );
}
