"use client";

import { use } from "react";
import { PropertyDetailView } from "@/components/properties/PropertyDetailView";

export default function PropertyPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return <PropertyDetailView propertyId={id} />;
}
