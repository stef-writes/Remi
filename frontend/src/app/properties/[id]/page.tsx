"use client";

import { use } from "react";
import { Shell } from "@/components/Shell";
import { PropertyDetailView } from "@/components/properties/PropertyDetailView";

export default function PropertyPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return (
    <Shell>
      <PropertyDetailView propertyId={id} />
    </Shell>
  );
}
