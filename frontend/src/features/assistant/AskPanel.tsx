import { useState } from "react";

import { useAsk } from "@/api/assistant";
import type { AssistantFigure } from "@/api/types";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { Chip } from "@/components/Chip";

const FIELD_CLASS =
  "w-full rounded border border-rule bg-surface px-3 py-2 text-body text-content focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent";

/** ADR-002: the figures are authoritative and the narration is presentation. This panel
 * renders the figures FIRST and always, and the narration only if the provider produced
 * one — so the useful part of the answer never depends on a model being available.
 */
function FigureRow({ figure }: { figure: AssistantFigure }) {
  return (
    <li className="flex items-baseline justify-between gap-4 py-2">
      <div className="flex flex-col gap-0.5">
        <span className="text-body">{figure.label}</span>
        <span className="text-caption text-content-tertiary">from {figure.source}</span>
      </div>
      <span className="font-ui text-figure tabular-nums">
        {figure.unit === "rand" ? "R" : ""}
        {figure.value}
        {figure.unit === "months" ? " months" : ""}
        {figure.unit === "points" ? " / 100" : ""}
      </span>
    </li>
  );
}

export function AskPanel() {
  const [question, setQuestion] = useState("");
  const [conversationId, setConversationId] = useState<string | undefined>();
  const ask = useAsk();
  const answer = ask.data;

  return (
    <Card>
      <h2 className="text-title">Ask about your money</h2>

      <form
        className="flex flex-col gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          if (!question.trim()) return;
          ask.mutate(
            { question, conversationId },
            { onSuccess: (result) => setConversationId(result.conversation_id ?? undefined) },
          );
        }}
      >
        <label className="flex flex-col gap-1 text-label text-content-secondary">
          Question
          <input
            className={FIELD_CLASS}
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="Can I afford a R15,000 holiday in December?"
          />
        </label>
        <div>
          <Button type="submit" variant="primary" disabled={ask.isPending}>
            {ask.isPending ? "Working…" : "Ask"}
          </Button>
        </div>
      </form>

      {ask.isError ? (
        <p className="text-body text-signal-critical">
          Could not answer that: {(ask.error as Error).message}
        </p>
      ) : null}

      {answer ? (
        <div className="flex flex-col gap-4 border-t border-rule pt-4">
          {answer.clarification ? (
            <p className="text-body">{answer.clarification}</p>
          ) : null}

          {!answer.supported ? (
            <>
              <Chip>Not supported</Chip>
              <p className="text-body text-content-secondary">{answer.answer}</p>
            </>
          ) : null}

          {answer.figures.length > 0 ? (
            <ul className="flex flex-col divide-y divide-rule">
              {answer.figures.map((figure) => (
                <FigureRow key={`${figure.label}-${figure.source}`} figure={figure} />
              ))}
            </ul>
          ) : null}

          {answer.supported && answer.figures.length > 0 ? (
            answer.narration_available ? (
              <p className="text-body">{answer.answer}</p>
            ) : (
              <p className="text-caption text-content-tertiary">
                Figures only — no narration is available. Every number above was computed
                by the named engine, so the answer is complete without it.
              </p>
            )
          ) : null}

          {answer.based_on?.assumptions &&
          Object.keys(answer.based_on.assumptions).length > 0 ? (
            <div className="flex flex-col gap-1">
              <span className="text-label text-content-secondary">Assumptions</span>
              <ul className="text-caption text-content-tertiary">
                {Object.entries(answer.based_on.assumptions).map(([key, value]) => (
                  <li key={key}>
                    {key.replace(/_/g, " ")}: {value}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}
    </Card>
  );
}
