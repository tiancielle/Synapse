import type { Metadata } from "next";

import ServerView from "@/components/ServerView";

export const metadata: Metadata = { title: "GitHub" };

export default function GithubPage() {
  return <ServerView server="github" />;
}
