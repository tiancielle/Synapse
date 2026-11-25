import type { Metadata } from "next";

import ServerView from "@/components/ServerView";

export const metadata: Metadata = { title: "Mail" };

export default function MailPage() {
  return <ServerView server="mail" />;
}
