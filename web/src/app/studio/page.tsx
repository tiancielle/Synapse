import type { Metadata } from "next";

import Chat from "@/components/Chat";

export const metadata: Metadata = { title: "Studio de l'agent" };

export default function StudioPage() {
  return <Chat />;
}
