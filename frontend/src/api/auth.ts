import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { User } from "@/api/types";

export function useCurrentUser() {
  return useQuery({
    queryKey: ["auth", "me"],
    queryFn: () => api.get<User>("/auth/me"),
    retry: false,
  });
}

export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: { email: string; password: string }) =>
      api.post<User>("/auth/login", data),
    onSuccess: (user) => queryClient.setQueryData(["auth", "me"], user),
  });
}

export function useRegister() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: { email: string; password: string; full_name: string }) =>
      api.post<User>("/auth/register", data),
    onSuccess: (user) => queryClient.setQueryData(["auth", "me"], user),
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<void>("/auth/logout"),
    onSuccess: () => queryClient.setQueryData(["auth", "me"], null),
  });
}
