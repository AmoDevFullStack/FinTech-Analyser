import { ForecastAccuracyView, ForecastView } from "@/features/forecast";

export function Forecast() {
  return (
    <div className="flex flex-col gap-8">
      <h1 className="text-title">Forecast</h1>
      <ForecastView />
      <ForecastAccuracyView />
    </div>
  );
}
