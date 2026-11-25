import type { Metadata } from "next";

import ApprovalsView from "@/components/ApprovalsView";

export const metadata: Metadata = { title: "Approbations" };

export default function ApprovalsPage() {
  return <ApprovalsView />;
}
