import { ArrowDownRight, ArrowRight, ArrowUpRight } from "lucide-react";

import { useMonthlySummary } from "@/api/transactions";
import type { MonthMetric, MonthMetricChange, MonthReport, Position } from "@/api/types";
import { Card } from "@/components/Card";
import { EmptyState } from "@/components/EmptyState";
import { MoneyText } from "@/components/MoneyText";
import { asMoney, isNegative, isZeroFigure } from "@/lib/money";

/** The four figures this region shows, and the month metric behind each.
 *
 * "Remaining" is the month's `net`, which is income less *everything* that went out —
 * savings and debt payments included, not only the two columns beside it. The caption
 * below the figures says so, because four numbers that visibly do not add up are worse
 * than a sentence explaining why they do not.
 */
const COLUMNS: { label: string; metric: MonthMetric }[] = [
  { label: "Income", metric: "income" },
  { label: "Essential", metric: "essential" },
  { label: "Discretionary", metric: "discretionary" },
  { label: "Remaining", metric: "net" },
];

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

/** How this figure moved since last month. No colour: direction is carried by the arrow
 * and the sign, because whether "more" is good depends on the row — more income and more
 * discretionary spending point the same way on screen and opposite ways in life. */
function Delta({ change }: { change: MonthMetricChange }) {
  if (isZeroFigure(change.change)) {
    return (
      <span className="inline-flex items-center gap-1 text-caption text-content-tertiary">
        <ArrowRight size={12} strokeWidth={2} aria-hidden="true" />
        Same as last month
      </span>
    );
  }

  const Icon = isNegative(change.change) ? ArrowDownRight : ArrowUpRight;
  return (
    <span className="inline-flex items-center gap-1 text-caption text-content-tertiary">
      <Icon size={12} strokeWidth={2} aria-hidden="true" />
      <MoneyText value={change.change} size="body" />
    </span>
  );
}

function MonthFigures({ report, isCurrentMonth }: { report: MonthReport; isCurrentMonth: boolean }) {
  return (
    <>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {COLUMNS.map(({ label, metric }) => {
          const change = report.changes[metric];
          return (
            <div key={metric} className="flex flex-col gap-1">
              <span className="text-label text-content-secondary">{label}</span>
              <MoneyText value={report.totals[metric]} />
              {change ? <Delta change={change} /> : null}
            </div>
          );
        })}
      </div>

      <p className="text-caption text-content-tertiary">
        {isCurrentMonth
          ? `${monthLabel(report.month)} so far`
          : `${monthLabel(report.month)} — the most recent month with activity`}
        {report.previous_month ? `, against ${monthLabel(report.previous_month)}` : ""}.
        Remaining is what is left after savings and debt payments as well.
      </p>
    </>
  );
}

/** Region 2 — this month's cash flow, rendered as a flow, not a pie chart, per
 * specs/dashboard.md.
 *
 * The figures are the calendar month's own totals, from `GET /transactions/months`, with
 * the change from the month before under each. `position.monthly_*` are the stored
 * snapshot's monthly averages over the user's history, which is a different question from
 * the one this card's title asks — and reads as R0,00 on an account whose snapshot has not
 * caught up. The snapshot is still what decides whether there is anything to show at all,
 * and still what is rendered if the month query has nothing.
 */
export function CashFlowRegion({ position }: { position: Position }) {
  const months = useMonthlySummary();
  const reports = months.data?.data ?? [];

  // The newest month that actually has transactions, not simply the newest month. A user
  // whose last statement ended in July is looking at an empty September, and four zeros
  // under a heading is a worse answer than July's figures with July's name on them.
  const shown =
    [...reports].reverse().find((report) => report.transaction_count > 0) ?? reports.at(-1);
  const isCurrentMonth = shown !== undefined && shown.month === reports.at(-1)?.month;

  if (position.monthly_income === null) {
    return (
      <Card>
        <h2 className="text-title">This month&apos;s cash flow</h2>
        <EmptyState message="No transaction history yet." />
      </Card>
    );
  }

  return (
    <Card>
      <h2 className="text-title">This month&apos;s cash flow</h2>

      {shown ? (
        <MonthFigures report={shown} isCurrentMonth={isCurrentMonth} />
      ) : (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <div className="flex flex-col gap-1">
            <span className="text-label text-content-secondary">Income</span>
            <MoneyText value={asMoney(position.monthly_income)} />
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-label text-content-secondary">Essential</span>
            <MoneyText value={asMoney(position.monthly_essential!)} />
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-label text-content-secondary">Discretionary</span>
            <MoneyText value={asMoney(position.monthly_discretionary!)} />
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-label text-content-secondary">Remaining</span>
            <MoneyText value={asMoney(position.projected_cash_flow!)} />
          </div>
        </div>
      )}
    </Card>
  );
}
