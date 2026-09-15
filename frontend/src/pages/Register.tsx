import { Link } from "react-router-dom";

import { RegisterForm } from "@/features/auth";

export function Register() {
  return (
    <div className="mx-auto flex max-w-sm flex-col gap-6 pt-16">
      <h1 className="text-title">Create your account</h1>
      <RegisterForm />
      <p className="text-body text-content-secondary">
        Already have an account? <Link to="/login" className="text-accent">Log in</Link>
      </p>
    </div>
  );
}
