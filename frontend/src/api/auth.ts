import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import { clearTokens, refreshToken, storeTokens, type TokenPair } from "@/api/tokens";
import type { User } from "@/api/types";

/** Register and login return the user with the JWT pair alongside. The cookie arrives on
 * the same response; a client holds whichever it can. */
interface AuthenticatedUser extends User {
  tokens: TokenPair;
}

function adopt(response: AuthenticatedUser): User {
  const { tokens, ...user } = response;
  storeTokens(tokens);
  return user;
}

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
      api.post<AuthenticatedUser>("/auth/login", data).then(adopt),
    onSuccess: (user) => queryClient.setQueryData(["auth", "me"], user),
  });
}

export function useRegister() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: { email: string; password: string; full_name: string }) =>
      api.post<AuthenticatedUser>("/auth/register", data).then(adopt),
    onSuccess: (user) => queryClient.setQueryData(["auth", "me"], user),
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    // The refresh token is sent so the server can revoke it — it cannot work out which of
    // a user's tokens belongs to this tab on its own. See backend/app/api/v1/auth.py.
    mutationFn: () => api.post<void>("/auth/logout", { refresh_token: refreshToken() }),
    onSettled: () => {
      // onSettled, not onSuccess: a logout that failed on the network still has to clear
      // this browser. Leaving a usable token behind because the request timed out is the
      // one outcome a user pressing "log out" is not expecting.
      clearTokens();
      queryClient.setQueryData(["auth", "me"], null);
      queryClient.clear();
    },
  });
}
