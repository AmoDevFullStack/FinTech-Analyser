import { useMutation } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { AssistantAnswer } from "@/api/types";

/** Every ask re-runs the whole pipeline server-side: figures are never carried forward
 * from conversation history, because the underlying position may have changed
 * (specs/ai-cfo.md). There is deliberately no client-side cache of an answer for that
 * reason — this is a mutation, not a query.
 */
export function useAsk() {
  return useMutation({
    mutationFn: ({ question, conversationId }: { question: string; conversationId?: string }) =>
      api.post<AssistantAnswer>("/assistant/ask", {
        question,
        conversation_id: conversationId,
      }),
  });
}
