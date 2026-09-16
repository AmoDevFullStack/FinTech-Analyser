import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import type {
  AssistantAnswer,
  AssistantConversation,
  AssistantConversationSummary,
} from "@/api/types";

/** Every ask re-runs the whole pipeline server-side: figures are never carried forward
 * from conversation history, because the underlying position may have changed
 * (specs/ai-cfo.md). There is deliberately no client-side cache of an answer for that
 * reason — this is a mutation, not a query.
 */
export function useAsk() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ question, conversationId }: { question: string; conversationId?: string }) =>
      api.post<AssistantAnswer>("/assistant/ask", {
        question,
        conversation_id: conversationId,
      }),
    onSuccess: (answer) => {
      // The transcript is server-owned, so the list and the open thread are refetched
      // rather than patched client-side.
      queryClient.invalidateQueries({ queryKey: ["assistant", "conversations"] });
      if (answer.conversation_id) {
        queryClient.invalidateQueries({
          queryKey: ["assistant", "conversation", answer.conversation_id],
        });
      }
    },
  });
}

export function useConversations() {
  return useQuery({
    queryKey: ["assistant", "conversations"],
    queryFn: () => api.get<{ data: AssistantConversationSummary[] }>("/assistant/conversations"),
    select: (response) => response.data,
  });
}

export function useConversation(conversationId: string | undefined) {
  return useQuery({
    queryKey: ["assistant", "conversation", conversationId],
    queryFn: () => api.get<AssistantConversation>(`/assistant/conversations/${conversationId}`),
    enabled: Boolean(conversationId),
  });
}
