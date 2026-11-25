import type { Metadata } from "next";

import SettingsView from "@/components/SettingsView";

export const metadata: Metadata = { title: "Réglages" };

export default function SettingsPage() {
  return <SettingsView />;
}
