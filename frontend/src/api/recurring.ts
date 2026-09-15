import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { RecurringSeriesRow } from "@/api/types";

export function useRecurringSeries() {
  return useQuery({
    queryKey: ["recurring"],
    queryFn: () =>
      api.get<{ data: RecurringSeriesRow[] }>("/analysis/recurring").then((r) => r.data),
  });
}
