import { UserPlus } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { useRegister } from "@/api/auth";
import { ApiError } from "@/api/client";
import { Button } from "@/components/Button";

export function RegisterForm() {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const register = useRegister();
  const navigate = useNavigate();

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    register.mutate(
      { email, password, full_name: fullName },
      { onSuccess: () => navigate("/") },
    );
  }

  return (
    <form onSubmit={handleSubmit} className="flex max-w-sm flex-col gap-4">
      <label className="flex flex-col gap-1">
        <span className="text-label text-content-secondary">Full name</span>
        <input
          required
          value={fullName}
          onChange={(e) => setFullName(e.target.value)}
          className="h-11 rounded-md border border-rule bg-surface-raised px-3 text-body"
        />
      </label>
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
          minLength={8}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="h-11 rounded-md border border-rule bg-surface-raised px-3 text-body"
        />
      </label>
      {register.isError ? (
        <p className="text-body text-signal-critical">
          {register.error instanceof ApiError ? register.error.message : "Registration failed."}
        </p>
      ) : null}
      <Button type="submit" variant="primary" icon={UserPlus} disabled={register.isPending}>
        {register.isPending ? "Creating account…" : "Create account"}
      </Button>
    </form>
  );
}
