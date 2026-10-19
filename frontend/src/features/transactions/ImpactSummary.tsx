import { AlertTriangle, ArrowDownRight, ArrowRight, ArrowUpRight, Repeat } from "lucide-react";

import type { MetricChange, SpendingInsight } from "@/api/types";
import { Card } from "@/components/Card";
import { Chip } from "@/components/Chip";
import { MoneyText } from "@/components/MoneyText";
import { formatDate } from "@/lib/dates";
import { asMoney, asRate, formatMonths, formatRateAsPercent, isZeroFigure } from "@/lib/money";

import {
  IMPACT_METRIC_LABELS,
  IMPACT_METRIC_ORDER,
  PAYMENT_METHOD_LABELS,
  SPENDING_PURPOSE_LABELS,
} from "./spendingLabels";

/** Render a figure in the unit the server said it was in.
 *
 * The unit travels with each change for exactly this reason — nothing here has to infer
 * from a metric's name whether 0.12 is twelve cents, twelve percent, or a tenth of a
 * month, and a metric added server-side renders correctly without a change here.
 */
function Figure({ value, unit }: { value: string; unit: MetricChange["unit"] }) {
  if (unit === "money") return <MoneyText value={asMoney(value)} size="body" />;
  if (unit === "rate") return <>{formatRateAsPercent(asRate(value), { places: 1 })}</>;
  return <>{formatMonths(value)} months</>;
}

function DirectionIcon({ delta }: { delta: string }) {
  if (delta.startsWith("-")) {
    return <ArrowDownRight size={14} strokeWidth={2} aria-label="down" />;
  }
  if (isZeroFigure(delta)) {
    return <ArrowRight size={14} strokeWidth={2} aria-label="unchanged" />;
  }
  return <ArrowUpRight size={14} strokeWidth={2} aria-label="up" />;
}

function ChangeRow({ change }: { change: MetricChange }) {
  return (
    <tr className="border-b border-rule last:border-0">
      <th scope="row" className="py-2 pr-3 text-left text-body font-normal">
        {IMPACT_METRIC_LABELS[change.name] ?? change.name}
      </th>
      <td className="py-2 pr-3 text-right text-caption text-content-tertiary">
        <Figure value={change.before} unit={change.unit} />
      </td>
      <td className="py-2 pr-3 text-center text-content-tertiary">
        <DirectionIcon delta={change.delta} />
      </td>
      <td className="py-2 text-right text-body">
        <Figure value={change.after} unit={change.unit} />
      </td>
    </tr>
  );
}

/**
 * What an import or a manual entry was, and what it changes.
 *
 * Shown before the commit as well as after it. The two are the same component on the same
 * payload shape on purpose: a preview that renders differently from the result is a
 * preview a user learns not to trust.
 */
export function ImpactSummary({
  insight,
  heading,
}: {
  insight: SpendingInsight;
  heading: string;
}) {
  const changes = IMPACT_METRIC_ORDER.map((name) =>
    insight.impact.changes.find((change) => change.name === name),
  ).filter((change): change is MetricChange => change !== undefined);

  const moved = changes.filter((change) => change.is_material);
  const newCommitments = insight.commitments.filter((commitment) => commitment.is_new);

  return (
    <Card>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-title">{heading}</h2>
        {insight.period_start && insight.period_end ? (
          <span className="text-caption text-content-tertiary">
            {formatDate(insight.period_start)} – {formatDate(insight.period_end)} ·{" "}
            {insight.months_covered} {insight.months_covered === 1 ? "month" : "months"}
          </span>
        ) : null}
      </div>

      {/* Stated rather than assumed. A six-month statement adds six months of rent, and a
          reader comparing "before" and "after" needs to know both sides are per month. */}
      <p className="text-caption text-content-tertiary">
        Figures are monthly averages over the period covered.
      </p>

      {moved.length === 0 ? (
        <p className="text-body text-content-secondary">
          Nothing in this file moves a monthly figure.
        </p>
      ) : (
        <table className="w-full border-collapse text-body">
          <caption className="sr-only">
            Monthly figures before and after these transactions
          </caption>
          <thead>
            <tr className="border-b border-rule text-left text-label text-content-secondary">
              <th scope="col" className="py-2 pr-3">
                Figure
              </th>
              <th scope="col" className="py-2 pr-3 text-right">
                Now
              </th>
              <th scope="col" className="py-2 pr-3 text-center">
                <span className="sr-only">Direction</span>
              </th>
              <th scope="col" className="py-2 text-right">
                After
              </th>
            </tr>
          </thead>
          <tbody>
            {moved.map((change) => (
              <ChangeRow key={change.name} change={change} />
            ))}
          </tbody>
        </table>
      )}

      {newCommitments.length > 0 ? (
        <section className="flex flex-col gap-2">
          <h3 className="text-label text-content-secondary">New standing commitments</h3>
          {/* Surfaced separately from the recurring-series view, which needs three
              occurrences before it will call something a series. A debit order is a
              standing arrangement on its first appearance. */}
          <ul className="flex flex-col gap-1">
            {newCommitments.map((commitment) => (
              <li key={commitment.label} className="flex items-baseline justify-between gap-3">
                <span className="flex min-w-0 items-center gap-2">
                  <Repeat size={14} strokeWidth={2} aria-hidden="true" />
                  <span className="truncate text-body">{commitment.merchant ?? commitment.label}</span>
                  <Chip>{PAYMENT_METHOD_LABELS[commitment.method]}</Chip>
                  <Chip>{SPENDING_PURPOSE_LABELS[commitment.purpose]}</Chip>
                </span>
                <MoneyText value={asMoney(commitment.monthly_amount)} size="body" />
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {insight.by_purpose.length > 0 ? (
        <section className="flex flex-col gap-2">
          <h3 className="text-label text-content-secondary">What the money went to</h3>
          <ul className="flex flex-col gap-1">
            {insight.by_purpose.slice(0, 8).map((group) => (
              <li key={group.key} className="flex items-baseline justify-between gap-3">
                <span className="text-body">
                  {SPENDING_PURPOSE_LABELS[
                    group.key as keyof typeof SPENDING_PURPOSE_LABELS
                  ] ?? group.label}
                  <span className="pl-2 text-caption text-content-tertiary">
                    {group.count} {group.count === 1 ? "payment" : "payments"}
                  </span>
                </span>
                <MoneyText value={asMoney(group.monthly_average)} size="body" />
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {insight.rows_needing_review > 0 ? (
        <p className="flex items-center gap-2 text-caption text-content-secondary">
          <AlertTriangle size={14} strokeWidth={2} aria-hidden="true" />
          {insight.rows_needing_review}{" "}
          {insight.rows_needing_review === 1 ? "payment was" : "payments were"} not
          recognised and will need a category.
        </p>
      ) : null}

      {insight.affected.length > 0 ? (
        <details className="text-caption text-content-secondary">
          <summary className="cursor-pointer">What else this changes</summary>
          <ul className="flex flex-col gap-1 pt-2">
            {insight.affected.map((area) => (
              <li key={`${area.area}-${area.effect}`}>
                <span className="text-content">{area.area.replace(/_/g, " ")}</span>{" "}
                {area.effect} — {area.detail}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </Card>
  );
}
