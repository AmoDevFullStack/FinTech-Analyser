import { Sparkles } from "lucide-react";

import type { AssistantFigure } from "@/api/types";
import { Chip } from "@/components/Chip";
import { figureSourceLabel } from "@/features/assistant/figureSources";

/** ADR-002 and design-system.md §9: the figures are authoritative and the narration is
 * presentation. So the figures render FIRST and always, and the prose renders after them,
 * marked as generated. The useful part of an answer never depends on a model being up.
 */
function FigureRow({ figure }: { figure: AssistantFigure }) {
  return (
    <li className="flex items-baseline justify-between gap-4 py-3">
      <div className="flex flex-col gap-0.5">
        <span className="text-body">{figure.label}</span>
        <span className="text-caption text-content-tertiary">
          from {figureSourceLabel(figure.source)}
        </span>
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

export interface AnswerBlockProps {
  supported: boolean;
  answer: string | null;
  narrationAvailable: boolean;
  figures: AssistantFigure[];
  clarification?: string | null;
  assumptions?: Record<string, string>;
}

export function AnswerBlock({
  supported,
  answer,
  narrationAvailable,
  figures,
  clarification,
  assumptions,
}: AnswerBlockProps) {
  const hasAssumptions = assumptions !== undefined && Object.keys(assumptions).length > 0;

  return (
    <div className="flex flex-col gap-4">
      {clarification ? <p className="text-body">{clarification}</p> : null}

      {!supported ? (
        <div className="flex flex-col gap-2">
          <Chip>Not modelled</Chip>
          <p className="text-body text-content-secondary">{answer}</p>
        </div>
      ) : null}

      {figures.length > 0 ? (
        <ul className="flex flex-col divide-y divide-rule">
          {figures.map((figure) => (
            <FigureRow key={`${figure.label}-${figure.source}`} figure={figure} />
          ))}
        </ul>
      ) : null}

      {supported && figures.length > 0 ? (
        narrationAvailable && answer ? (
          <div className="flex flex-col gap-2 rounded-lg bg-surface-sunken p-4">
            <span className="inline-flex items-center gap-1.5 text-caption text-content-secondary">
              <Sparkles size={13} strokeWidth={2} aria-hidden="true" />
              Written from the figures above
            </span>
            <p className="text-body">{answer}</p>
          </div>
        ) : (
          <p className="text-caption text-content-tertiary">
            The written explanation is unavailable right now. Every number above is worked
            out from your own records, so the answer is complete without it.
          </p>
        )
      ) : null}

      {/* No figures at all — e.g. a greeting. There is nothing for the figures-only
          caption above to point at, so a bare reply (model-written or the deterministic
          fallback) is the whole answer. */}
      {supported && figures.length === 0 && answer ? (
        narrationAvailable ? (
          <div className="flex flex-col gap-2 rounded-lg bg-surface-sunken p-4">
            <span className="inline-flex items-center gap-1.5 text-caption text-content-secondary">
              <Sparkles size={13} strokeWidth={2} aria-hidden="true" />
              Written for you
            </span>
            <p className="text-body">{answer}</p>
          </div>
        ) : (
          <p className="text-body text-content-secondary">{answer}</p>
        )
      ) : null}

      {hasAssumptions ? (
        <div className="flex flex-col gap-1">
          <span className="text-label text-content-secondary">Assumptions</span>
          <ul className="text-caption text-content-tertiary">
            {Object.entries(assumptions).map(([key, value]) => (
              <li key={key}>
                {key.replace(/_/g, " ")}: {value}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
