import { X } from "lucide-react";
import type { RefObject } from "react";

import type { AssistantConversationSummary } from "@/api/types";

/** Past conversations, opened over the thread rather than beside it — ChatView keeps its
 * full-height surface (docs/frontend.md §7, ADR-009's pattern applied to this page's own
 * drawer) instead of losing width to a permanent sidebar.
 */
export function HistoryDrawer({
  open,
  onClose,
  panelRef,
  conversations,
  activeConversationId,
  onSelect,
}: {
  open: boolean;
  onClose: () => void;
  panelRef: RefObject<HTMLDivElement>;
  conversations: AssistantConversationSummary[] | undefined;
  activeConversationId: string | undefined;
  onSelect: (id: string) => void;
}) {
  if (!open) return null;

  return (
    <>
      <div
        className="fixed inset-0 z-40 bg-scrim transition-opacity duration-150"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label="Conversation history"
        className="fixed inset-y-0 right-0 z-50 flex w-[min(22rem,85vw)] animate-drawer-in-right flex-col gap-2 border-l border-rule bg-surface-raised p-4 shadow-3"
      >
        <div className="flex items-center justify-between pb-2">
          <span className="text-label text-content-secondary">History</span>
          <button
            type="button"
            aria-label="Close history"
            onClick={onClose}
            className="inline-flex h-11 w-11 items-center justify-center rounded-full text-content-secondary transition-colors duration-150 hover:bg-surface-sunken focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          >
            <X size={20} strokeWidth={2} aria-hidden="true" />
          </button>
        </div>

        {!conversations || conversations.length === 0 ? (
          <p className="text-body text-content-tertiary">No conversations yet.</p>
        ) : (
          <ul className="flex flex-col gap-1 overflow-y-auto">
            {conversations.map((conversation) => {
              const isActive = conversation.id === activeConversationId;
              return (
                <li key={conversation.id}>
                  <button
                    type="button"
                    onClick={() => onSelect(conversation.id)}
                    className={`flex min-h-[44px] w-full flex-col items-start justify-center rounded-lg px-3 py-1.5 text-left transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${
                      isActive
                        ? "bg-surface-sunken text-accent"
                        : "text-content hover:bg-surface-sunken"
                    }`}
                  >
                    <span className="line-clamp-1 text-body font-medium">
                      {conversation.title || "Untitled conversation"}
                    </span>
                    <span className="text-caption text-content-tertiary">
                      {formatShortDate(conversation.started_at)}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </>
  );
}

function formatShortDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-ZA", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}
