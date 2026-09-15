import { Plus } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { useCreateScenario } from "@/api/scenarios";
import { Button } from "@/components/Button";

/** The worked example from specs/scenarios.md is the default seed: R350,000 vehicle,
 * R50,000 deposit, 11.75% over 72 months.
 */
export function VehiclePurchaseForm() {
  const [name, setName] = useState("New vehicle");
  const [purchasePrice, setPurchasePrice] = useState("350000.00");
  const [deposit, setDeposit] = useState("50000.00");
  const [annualRate, setAnnualRate] = useState("0.1175");
  const [termMonths, setTermMonths] = useState(72);
  const [insuranceMonthly, setInsuranceMonthly] = useState("850.00");
  const [fuelMonthly, setFuelMonthly] = useState("1800.00");
  const [maintenanceMonthly, setMaintenanceMonthly] = useState("450.00");
  const create = useCreateScenario();
  const navigate = useNavigate();

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    create.mutate(
      {
        name,
        assumptions: {
          purchase_price: purchasePrice,
          deposit,
          annual_rate: annualRate,
          term_months: termMonths,
          insurance_monthly: insuranceMonthly,
          fuel_monthly: fuelMonthly,
          maintenance_monthly: maintenanceMonthly,
        },
      },
      { onSuccess: (scenario) => navigate(`/scenarios/${scenario.id}`) },
    );
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <label className="flex flex-col gap-1">
        <span className="text-label text-content-secondary">Scenario name</span>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="h-11 max-w-sm rounded-md border border-rule bg-surface-raised px-3 text-body"
        />
      </label>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        <Field label="Purchase price" value={purchasePrice} onChange={setPurchasePrice} />
        <Field label="Deposit" value={deposit} onChange={setDeposit} />
        <Field label="Annual rate" value={annualRate} onChange={setAnnualRate} />
        <label className="flex flex-col gap-1">
          <span className="text-label text-content-secondary">Term (months)</span>
          <input
            type="number"
            min={1}
            step={1}
            value={termMonths}
            onChange={(e) => setTermMonths(e.target.valueAsNumber)}
            className="h-11 rounded-md border border-rule bg-surface-raised px-3 text-body"
          />
        </label>
        <Field label="Insurance / month" value={insuranceMonthly} onChange={setInsuranceMonthly} />
        <Field label="Fuel / month" value={fuelMonthly} onChange={setFuelMonthly} />
        <Field
          label="Maintenance / month"
          value={maintenanceMonthly}
          onChange={setMaintenanceMonthly}
        />
      </div>
      <Button
        type="submit"
        variant="primary"
        icon={Plus}
        disabled={create.isPending}
        className="w-fit"
      >
        {create.isPending ? "Creating…" : "Create scenario"}
      </Button>
    </form>
  );
}

function Field({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-label text-content-secondary">{label}</span>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-11 rounded-md border border-rule bg-surface-raised px-3 text-body"
      />
    </label>
  );
}
