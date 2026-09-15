import { ScenarioList, VehiclePurchaseForm } from "@/features/scenarios";

export function Scenarios() {
  return (
    <div className="flex flex-col gap-8">
      <h1 className="text-title">Scenarios</h1>
      <ScenarioList />
      <section className="flex flex-col gap-4">
        <h2 className="text-title">New vehicle purchase scenario</h2>
        <VehiclePurchaseForm />
      </section>
    </div>
  );
}
