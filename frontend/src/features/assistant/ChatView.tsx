import { ArrowLeft, ArrowUp, History, Plus } from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  useAsk,
  useConversation,
  useConversations,
  useDeleteConversation,
} from "@/api/assistant";
import type { AssistantAnswer } from "@/api/types";
import { AnswerBlock } from "@/features/assistant/AnswerBlock";
import { HistoryDrawer } from "@/features/assistant/HistoryDrawer";

const SUGGESTIONS = [
  "Can I afford a R15,000 holiday in December?",
  "What is my emergency fund worth in months?",
  "How long until my car loan is paid off?",
];

/** design-system.md §9: generation feedback is specific, and the two-stage boundary
 * between computing and narrating is made visible while the reader waits. These are the
 * two stages, in order — not a generic spinner.
 *
 * Worded for the person waiting, not for us. What they need to know is that the numbers
 * come first and the words are written over them; which module is running is our concern.
 */
const STAGES = ["Working out your numbers", "Putting it in words"] as const;

function PendingIndicator() {
  const [stage, setStage] = useState(0);

  useEffect(() => {
    const timer = window.setTimeout(() => setStage(1), 900);
    return () => window.clearTimeout(timer);
  }, []);

  return (
    <p aria-live="polite" className="text-body text-content-secondary">
      {STAGES[stage]}…
    </p>
  );
}

/** One question and its answer. The question is a bubble because it is speech; the answer
 * is a panel because it is evidence. That asymmetry is deliberate — an answer here is a
 * table of computed figures, and dressing it as chatter would undersell what it is.
 */
function Turn({ question, children }: { question: string; children?: ReactNode }) {
  return (
    <article className="flex flex-col gap-3">
      <div className="flex justify-end">
        <p className="max-w-[min(42rem,85%)] rounded-2xl rounded-br-md bg-surface-sunken px-4 py-3 text-body">
          {question}
        </p>
      </div>
      {children ? (
        <div className="max-w-[min(48rem,95%)] rounded-2xl rounded-bl-md border border-rule bg-surface-raised p-4 shadow-1 sm:p-5">
          {children}
        </div>
      ) : null}
    </article>
  );
}

export function ChatView() {
  const navigate = useNavigate();
  const [conversationId, setConversationId] = useState<string | undefined>();
  const [draft, setDraft] = useState("");
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null);
  const [liveAnswer, setLiveAnswer] = useState<{
    question: string;
    answer: AssistantAnswer;
  } | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);

  const ask = useAsk();
  const conversations = useConversations();
  const deleteConversation = useDeleteConversation();
  const thread = useConversation(conversationId);
  const endRef = useRef<HTMLDivElement>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const historyButtonRef = useRef<HTMLButtonElement>(null);
  const historyPanelRef = useRef<HTMLDivElement>(null);

  // Same Escape-closes / focus-returns contract as the primary nav drawer
  // (components/Layout.tsx, design-system.md §11).
  useEffect(() => {
    if (!historyOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setHistoryOpen(false);
        historyButtonRef.current?.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    historyPanelRef.current?.querySelector<HTMLElement>("a, button")?.focus();
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [historyOpen]);

  const storedMessages = useMemo(() => thread.data?.messages ?? [], [thread.data]);

  // The live answer is dropped as soon as the server transcript contains that turn, so a
  // question is never rendered twice while the refetch lands.
  const liveIsStored = useMemo(
    () =>
      liveAnswer !== null &&
      storedMessages.some((message) => message.question === liveAnswer.question),
    [liveAnswer, storedMessages],
  );

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [storedMessages.length, pendingQuestion, liveAnswer]);

  const submit = (question: string) => {
    const trimmed = question.trim();
    if (!trimmed || ask.isPending) return;
    setDraft("");
    setPendingQuestion(trimmed);
    ask.mutate(
      { question: trimmed, conversationId },
      {
        onSuccess: (result) => {
          setPendingQuestion(null);
          setLiveAnswer({ question: trimmed, answer: result });
          if (result.conversation_id) setConversationId(result.conversation_id);
        },
        onError: () => setPendingQuestion(null),
      },
    );
    composerRef.current?.focus();
  };

  const isEmpty = storedMessages.length === 0 && !pendingQuestion && !liveAnswer;

  return (
    <div className="flex h-[100dvh] flex-col bg-surface font-ui text-content">
      <header className="sticky top-0 z-10 border-b border-rule bg-glass backdrop-blur-xl backdrop-saturate-150 [@media(prefers-reduced-transparency:reduce)]:bg-surface-raised [@media(prefers-reduced-transparency:reduce)]:backdrop-blur-none">
        <div className="mx-auto flex h-16 w-full max-w-3xl items-center gap-3 px-4">
          <button
            type="button"
            aria-label="Back"
            onClick={() => navigate(-1)}
            className="inline-flex h-11 w-11 items-center justify-center rounded-full border border-rule bg-surface-raised transition-colors duration-150 hover:bg-surface-sunken focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          >
            <ArrowLeft size={20} strokeWidth={2} aria-hidden="true" />
          </button>
          <div className="flex flex-col">
            <h1 className="text-title">Ask</h1>
            {conversations.data && conversations.data.length > 0 ? (
              <button
                type="button"
                onClick={() => setHistoryOpen(true)}
                className="w-fit text-caption text-accent underline-offset-2 hover:underline"
              >
                {conversations.data.length} conversation{conversations.data.length === 1 ? "" : "s"}
              </button>
            ) : (
              <span className="text-caption text-content-tertiary">New conversation</span>
            )}
          </div>
          <div className="ml-auto flex items-center gap-2">
            <button
              ref={historyButtonRef}
              type="button"
              aria-label="History"
              aria-expanded={historyOpen}
              onClick={() => setHistoryOpen((open) => !open)}
              className="inline-flex h-11 w-11 items-center justify-center rounded-full border border-rule bg-surface-raised text-content transition-colors duration-150 hover:bg-surface-sunken focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            >
              <History size={20} strokeWidth={2} aria-hidden="true" />
            </button>
            <button
              type="button"
              onClick={() => {
                setConversationId(undefined);
                setLiveAnswer(null);
                setPendingQuestion(null);
                setHistoryOpen(false);
                composerRef.current?.focus();
              }}
              className="inline-flex h-11 items-center gap-2 rounded-full border border-rule bg-surface-raised px-4 text-label transition-colors duration-150 hover:bg-surface-sunken focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            >
              <Plus size={16} strokeWidth={2} aria-hidden="true" />
              New
            </button>
          </div>
        </div>
      </header>

      <HistoryDrawer
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        panelRef={historyPanelRef}
        conversations={conversations.data}
        activeConversationId={conversationId}
        onSelect={(id) => {
          setConversationId(id);
          setLiveAnswer(null);
          setPendingQuestion(null);
          setHistoryOpen(false);
        }}
        isDeleting={deleteConversation.isPending}
        onDelete={(id) => {
          deleteConversation.mutate(id);
          // The open thread cannot survive its own deletion. Reset to a new one rather
          // than leaving the view pointed at an id the server no longer has.
          if (id === conversationId) {
            setConversationId(undefined);
            setLiveAnswer(null);
            setPendingQuestion(null);
          }
        }}
      />

      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-6">
          {isEmpty ? (
            <div className="flex flex-col gap-4 pt-8">
              <h2 className="text-figure-lg">What do you want to know?</h2>
              <p className="text-body text-content-secondary">
                Every answer is worked out from the same figures you see everywhere else in
                the app. The figures are the answer; the words are there to describe them.
              </p>
              <ul className="flex flex-col gap-2 pt-2">
                {SUGGESTIONS.map((suggestion) => (
                  <li key={suggestion}>
                    <button
                      type="button"
                      onClick={() => submit(suggestion)}
                      className="min-h-[44px] w-full rounded-xl border border-rule bg-surface-raised px-4 py-3 text-left text-body transition-colors duration-150 hover:bg-surface-sunken focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                    >
                      {suggestion}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {storedMessages.map((message) => (
            <Turn key={message.id} question={message.question}>
              <AnswerBlock
                supported={message.supported}
                answer={message.answer}
                narrationAvailable={message.narration_available}
                figures={message.figures}
              />
            </Turn>
          ))}

          {liveAnswer && !liveIsStored ? (
            <Turn question={liveAnswer.question}>
              <AnswerBlock
                supported={liveAnswer.answer.supported}
                answer={liveAnswer.answer.answer}
                narrationAvailable={liveAnswer.answer.narration_available}
                figures={liveAnswer.answer.figures}
                clarification={liveAnswer.answer.clarification}
                assumptions={liveAnswer.answer.based_on?.assumptions}
              />
            </Turn>
          ) : null}

          {pendingQuestion ? (
            <Turn question={pendingQuestion}>
              <PendingIndicator />
            </Turn>
          ) : null}

          {ask.isError ? (
            <p className="text-body text-signal-critical">
              Could not answer that: {(ask.error as Error).message}
            </p>
          ) : null}

          <div ref={endRef} />
        </div>
      </div>

      <div className="border-t border-rule bg-surface-raised">
        <form
          className="mx-auto flex w-full max-w-3xl items-end gap-2 px-4 py-4"
          onSubmit={(event) => {
            event.preventDefault();
            submit(draft);
          }}
        >
          <label htmlFor="ask-composer" className="sr-only">
            Question
          </label>
          <textarea
            id="ask-composer"
            ref={composerRef}
            rows={1}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              // Enter sends, Shift+Enter breaks the line — the convention of every chat
              // surface the reader already uses.
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                submit(draft);
              }
            }}
            placeholder="Ask about your money"
            className="max-h-40 min-h-[44px] flex-1 resize-none rounded-2xl border border-rule bg-surface px-4 py-3 text-body text-content focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent"
          />
          <button
            type="submit"
            aria-label="Send"
            disabled={ask.isPending || !draft.trim()}
            className="inline-flex h-11 w-11 items-center justify-center rounded-full border border-rule bg-surface-raised text-content transition-colors duration-150 hover:bg-surface-sunken focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:pointer-events-none disabled:opacity-50"
          >
            <ArrowUp size={20} strokeWidth={2} aria-hidden="true" />
          </button>
        </form>
      </div>
    </div>
  );
}
