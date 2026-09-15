import { Link } from "react-router-dom";

import { LoginForm } from "@/features/auth";

export function Login() {
  return (
    <div className="mx-auto flex max-w-sm flex-col gap-6 pt-16">
      <h1 className="text-title">Log in</h1>
      <LoginForm />
      <p className="text-body text-content-secondary">
        No account? <Link to="/register" className="text-accent">Register</Link>
      </p>
    </div>
  );
}
