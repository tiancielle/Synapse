import type { Metadata } from "next";

import ServerView from "@/components/ServerView";

export const metadata: Metadata = { title: "Calendrier" };

export default function CalendarPage() {
  return <ServerView server="calendar" />;
}
