import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { Position } from "@/api/types";

/** Query key mirrors the resource, per docs/frontend.md §5. The dashboard issues exactly
 * this one query, per specs/dashboard.md.
 */
export function usePosition() {
  return useQuery({
    queryKey: ["position"],
    queryFn: () => api.get<Position>("/position"),
  });
}

export function useCaptureSnapshot() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<{ snapshot_id: string; captured_at: string }>("/position/snapshot"),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["position"] }),
  });
}
