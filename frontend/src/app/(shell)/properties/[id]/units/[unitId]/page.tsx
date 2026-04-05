"use client";

import { use } from "react";
import { UnitDetailView } from "@/components/properties/UnitDetailView";

export default function UnitPage({
  params,
}: {
  params: Promise<{ id: string; unitId: string }>;
}) {
  const { id, unitId } = use(params);
  return (
    <UnitDetailView
      propertyId={decodeURIComponent(id)}
      unitId={decodeURIComponent(unitId)}
    />
  );
}
