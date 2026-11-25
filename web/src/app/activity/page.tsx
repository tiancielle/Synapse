import type { Metadata } from "next";

import ActivityView from "@/components/ActivityView";

export const metadata: Metadata = { title: "Observatoire" };

export default function ActivityPage() {
  return <ActivityView />;
}
