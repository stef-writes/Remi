"use client";

import { use } from "react";
import { ManagerReviewView } from "@/components/managers/ManagerReviewView";

export default function ManagerReviewPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  return <ManagerReviewView managerId={id} />;
}
