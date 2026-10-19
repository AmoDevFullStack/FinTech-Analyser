import { ArrowDownRight, ArrowRight, ArrowUpRight } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { useMonthlySummary } from "@/api/transactions";
import type { MonthMetric, MonthMetricChange, MonthReport } from "@/api/types";
import { Card } from "@/components/Card";
import { Chip } from "@/components/Chip";
import { EmptyState } from "@/components/EmptyState";
import { MoneyText } from "@/components/MoneyText";
import { formatRateAsPercent, isNegative, isZeroFigure } from "@/lib/money";

/** The figures shown, in the order a person reads a month: what came in, what went out by
 * kind, then the two totals. Exhaustive over the metrics the server sends, so a metric
 * added there without a label here is a build error rather than a blank row. */
const METRIC_LABELS: Record<MonthMetric, string> = {
  income: "Money in",
  essential: "Essentials",
  discretionary: "Day-to-day",
  saving: "Put away",
  debt_service: "Debt payments",
  spending: "Total out",
  net: "Left over",
};

const METRIC_ORDER: MonthMetric[] = [
  "income",
  "essential",
  "discretionary",
  "saving",
  "debt_service",
  "spending",
  "net",
];

/** `2026-07` to `July 2026`.
 *
 * A lookup rather than `new Date(Number(year), Number(month) - 1)`: the lint rule that
 * keeps `Number()` out of this tree exists because narrowing an API string to a number is
 * how a figure gets quietly mangled, and a month label is not worth an exception to it. A
 * table is also immune to the off-by-one that a zero-indexed month argument invites.
 */
const MONTH_NAMES: Record<string, string> = {
  "01": "January",
  "02": "February",
  "03": "March",
  "04": "April",
  "05": "May",
  "06": "June",
  "07": "July",
  "08": "August",
  "09": "September",
  "10": "October",
  "11": "November",
  "12": "December",
};

function monthLabel(month: string): string {
  const [year, index] = month.split("-");
  const name = MONTH_NAMES[index];
  return name ? `${name} ${year}` : month;
}

function Direction({ change }: { change: MonthMetricChange }) {
  if (isZeroFigure(change.change)) {
    return <ArrowRight size={14} strokeWidth={2} aria-label="unchanged" />;
  }
  return isNegative(change.change) ? (
    <ArrowDownRight size={14} strokeWidth={2} aria-label="lower than last month" />
  ) : (
    <ArrowUpRight size={14} strokeWidth={2} aria-label="higher than last month" />
  );
}

function ChangeRow({ metric, change }: { metric: MonthMetric; change: MonthMetricChange }) {
  return (
    <tr className="border-b border-rule last:border-0">
      <th scope="row" className="py-2 pr-3 text-left text-body font-normal">
        {METRIC_LABELS[metric]}
      </th>
      <td className="py-2 pr-3 text-right text-caption text-content-tertiary">
        <MoneyText value={change.previous} size="body" />
      </td>
      <td className="py-2 pr-3 text-center text-content-tertiary">
        <Direction change={change} />
      </td>
      <td className="py-2 pr-3 text-right text-body">
        <MoneyText value={change.current} size="body" />
      </td>
      <td className="py-2 text-right text-caption text-content-tertiary">
        <MoneyText value={change.change} size="body" />
        {/* No percentage where last month was zero. The server sends null rather than a
            zero, because "up from nothing" has no percentage and showing 0% would read as
            "no change". */}
        {change.percentage_change !== null && !isZeroFigure(change.change) ? (
          <span className="ml-2">{formatRateAsPercent(change.percentage_change)}</span>
        ) : null}
      </td>
    </tr>
  );
}

function MonthDetail({ report }: { report: MonthReport }) {
  const changes = METRIC_ORDER.map((metric) => [metric, report.changes[metric]] as const).filter(
    (entry): entry is [MonthMetric, MonthMetricChange] => entry[1] !== undefined,
  );

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div className="flex flex-col gap-1">
          <span className="text-label text-content-secondary">Left over in {monthLabel(report.month)}</span>
          <MoneyText value={report.totals.net} size="figure-lg" />
        </div>
        {report.cash ? (
          <div className="flex flex-col gap-1 text-right">
            <span className="text-label text-content-secondary">In the account at month end</span>
            <MoneyText value={report.cash.closing} size="figure" />
            <span className="text-caption text-content-tertiary">
              Started the month with <MoneyText value={report.cash.opening} size="body" />
            </span>
          </div>
        ) : null}
      </div>

      {changes.length === 0 ? (
        /* The earliest month the window could read. It is a real month with real figures;
           there is simply nothing before it to compare against. */
        <p className="text-body text-content-secondary">
          This is the earliest month on record, so there is nothing before it to compare with.
        </p>
      ) : (
        <table className="w-full border-collapse text-body">
          <caption className="sr-only">
            {monthLabel(report.month)} compared with{" "}
            {report.previous_month ? monthLabel(report.previous_month) : "the month before"}
          </caption>
          <thead>
            <tr className="border-b border-rule text-left text-label text-content-secondary">
              <th scope="col" className="py-2 pr-3">
                Figure
              </th>
              <th scope="col" className="py-2 pr-3 text-right">
                {report.previous_month ? monthLabel(report.previous_month) : "Before"}
              </th>
              <th scope="col" className="py-2 pr-3 text-center">
                <span className="sr-only">Direction</span>
              </th>
              <th scope="col" className="py-2 pr-3 text-right">
                {monthLabel(report.month)}
              </th>
              <th scope="col" className="py-2 text-right">
                Difference
              </th>
            </tr>
          </thead>
          <tbody>
            {changes.map(([metric, change]) => (
              <ChangeRow key={metric} metric={metric} change={change} />
            ))}
          </tbody>
        </table>
      )}

      <p className="text-caption text-content-tertiary">
        {report.transaction_count} {report.transaction_count === 1 ? "transaction" : "transactions"}
        {report.import_batch_ids.length > 0
          ? ` · from ${report.import_batch_ids.length} ${
              report.import_batch_ids.length === 1 ? "statement you uploaded" : "statements you uploaded"
            }`
          : " · all added by hand"}
      </p>
    </div>
  );
}

/**
 * One month next to the one before it, and the run of months either side.
 *
 * The transaction list answers what happened. This answers whether the month was better
 * or worse than the last one, which is the question a person actually asks of their own
 * statements — and the one this product could not answer before.
 *
 * Two figures per month, deliberately different: "left over" excludes transfers between
 * your own accounts, because moving money is neither earning nor spending it, while the
 * account balance includes everything, because that is what the bank shows.
 */
export function MonthComparison() {
  const { data, isLoading, isError } = useMonthlySummary();
  const reports = useMemo(() => data?.data ?? [], [data]);
  const [selected, setSelected] = useState<string | null>(null);

  // Default to the most recent month, and follow it when the window reloads — but leave a
  // month the reader picked alone.
  useEffect(() => {
    if (reports.length === 0) return;
    setSelected((current) =>
      current !== null && reports.some((report) => report.month === current)
        ? current
        : reports[reports.length - 1].month,
    );
  }, [reports]);

  const report = reports.find((candidate) => candidate.month === selected);

  return (
    <Card>
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="text-title">Month by month</h2>
        {reports.length > 0 ? (
          <label className="flex items-center gap-2 text-caption text-content-secondary">
            <span>Showing</span>
            <select
              className="rounded-lg border border-rule bg-surface-raised px-3 py-2 text-body"
              value={selected ?? ""}
              onChange={(event) => setSelected(event.target.value)}
            >
              {[...reports].reverse().map((candidate) => (
                <option key={candidate.month} value={candidate.month}>
                  {monthLabel(candidate.month)}
                </option>
              ))}
            </select>
          </label>
        ) : null}
      </div>

      {isLoading ? <p className="text-body text-content-secondary">Working out your months…</p> : null}
      {isError ? (
        <p className="text-body text-content-secondary">
          Your months could not be worked out just now. Try again shortly.
        </p>
      ) : null}
      {!isLoading && !isError && reports.length === 0 ? (
        <EmptyState message="Upload a statement and your months will appear here, one next to the other." />
      ) : null}

      {report ? <MonthDetail report={report} /> : null}

      {reports.length > 1 ? (
        <section className="flex flex-col gap-2">
          <h3 className="text-label text-content-secondary">Every month in view</h3>
          <ul className="flex flex-wrap gap-2">
            {reports.map((candidate) => (
              <li key={candidate.month}>
                <button
                  type="button"
                  onClick={() => setSelected(candidate.month)}
                  aria-pressed={candidate.month === selected}
                  className="rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                >
                  <Chip>
                    {monthLabel(candidate.month)} · {isNegative(candidate.totals.net) ? "short" : "left over"}{" "}
                    <MoneyText value={candidate.totals.net} size="body" />
                  </Chip>
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </Card>
  );
}
