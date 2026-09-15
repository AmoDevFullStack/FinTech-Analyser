import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { AccuracyResponse, ForecastResponse } from "@/api/types";

/** `GET /forecasts/current` reads stored results and never computes (ADR-003), so an
 * absent forecast is a real state the UI must render, not an error.
 */
export function useForecast() {
  return useQuery({
    queryKey: ["forecast"],
    queryFn: () => api.get<ForecastResponse | { forecast: null }>("/forecasts/current"),
  });
}

export function useForecastAccuracy() {
  return useQuery({
    queryKey: ["forecast", "accuracy"],
    queryFn: () => api.get<AccuracyResponse>("/forecasts/accuracy"),
  });
}

export interface RefreshForecastInput {
  inflation_annual?: string;
  salary_growth_annual?: string;
  horizon_months?: number;
}

export function useRefreshForecast() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: RefreshForecastInput = {}) =>
      api.post<ForecastResponse>("/forecasts/refresh", data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["forecast"] });
      // Regenerating drives risk and recommendation evaluation server-side, so both
      // lists may have changed by the time this returns.
      queryClient.invalidateQueries({ queryKey: ["risk-flags"] });
      queryClient.invalidateQueries({ queryKey: ["recommendations"] });
      queryClient.invalidateQueries({ queryKey: ["position"] });
    },
  });
}
