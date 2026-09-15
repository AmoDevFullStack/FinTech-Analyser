import { Card } from "@/components/Card";
import { EmptyState } from "@/components/EmptyState";
import { asMoney } from "@/lib/money";
import { MoneyText } from "@/components/MoneyText";
import type { Position } from "@/api/types";

/** Region 1 — the three anchor figures. See specs/dashboard.md. */
export function PositionRegion({ position }: { position: Position }) {
  if (position.net_worth === null) {
    return <EmptyState message="Position not yet available — no account data recorded." />;
  }

  return (
    <div className="grid grid-cols-1 gap-6 sm:grid-cols-3">
      <Card>
        <span className="text-label text-content-secondary">Net worth</span>
        <MoneyText value={asMoney(position.net_worth)} size="position" />
      </Card>
      <Card>
        <span className="text-label text-content-secondary">Liquid savings</span>
        <MoneyText value={asMoney(position.liquid_savings!)} size="position" />
      </Card>
      <Card>
        <span className="text-label text-content-secondary">Total debt</span>
        <MoneyText value={asMoney(position.total_debt!)} size="position" />
      </Card>
    </div>
  );
}
