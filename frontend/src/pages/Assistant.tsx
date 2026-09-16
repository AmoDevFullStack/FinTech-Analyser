import { ChatView } from "@/features/assistant";

/** A conversation, not a page: it owns the whole viewport and sits outside the app shell,
 * so the navigation drawer never competes with the thread. See docs/frontend.md §7.
 */
export function Assistant() {
  return <ChatView />;
}
