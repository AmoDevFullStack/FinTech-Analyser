import { LogIn } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { useLogin } from "@/api/auth";
import { ApiError } from "@/api/client";
import { Button } from "@/components/Button";

export function LoginForm() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const login = useLogin();
  const navigate = useNavigate();

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    login.mutate(
      { email, password },
      { onSuccess: () => navigate("/") },
    );
  }

  return (
    <form onSubmit={handleSubmit} className="flex max-w-sm flex-col gap-4">
      <label className="flex flex-col gap-1">
        <span className="text-label text-content-secondary">Email</span>
        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="h-11 rounded-md border border-rule bg-surface-raised px-3 text-body"
        />
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-label text-content-secondary">Password</span>
        <input
          type="password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="h-11 rounded-md border border-rule bg-surface-raised px-3 text-body"
        />
      </label>
      {login.isError ? (
        <p className="text-body text-signal-critical">
          {login.error instanceof ApiError ? login.error.message : "Login failed."}
        </p>
      ) : null}
      <Button type="submit" variant="primary" icon={LogIn} disabled={login.isPending}>
        {login.isPending ? "Logging in…" : "Log in"}
      </Button>
    </form>
  );
}
