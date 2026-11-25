import type { Metadata } from "next";

import IntegrationsView from "@/components/IntegrationsView";

export const metadata: Metadata = { title: "Explorateur MCP" };

export default function IntegrationsPage() {
  return <IntegrationsView />;
}
