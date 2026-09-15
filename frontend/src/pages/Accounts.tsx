import { AccountList, CreateAccountForm } from "@/features/accounts";

export function Accounts() {
  return (
    <div className="flex flex-col gap-8">
      <h1 className="text-title">Accounts</h1>
      <CreateAccountForm />
      <AccountList />
    </div>
  );
}
