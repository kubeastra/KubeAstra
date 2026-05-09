"use client";

/**
 * Shareable session page — /chat/:sessionId
 *
 * When someone visits this URL, the ChatPage loads that specific session's
 * history instead of creating a new one from localStorage.
 *
 * This enables the "share investigation" flow: copy the URL from the share
 * button and send it to a teammate.
 */

import { use } from "react";
import ChatPage from "../page-client";

export default function SharedSessionPage({
  params,
}: {
  params: Promise<{ sessionId: string }>;
}) {
  const { sessionId } = use(params);
  return <ChatPage sharedSessionId={sessionId} />;
}
