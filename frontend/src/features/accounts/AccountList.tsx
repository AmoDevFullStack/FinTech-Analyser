import { useAccounts } from "@/api/accounts";
import { EmptyState } from "@/components/EmptyState";

import { AccountRow } from "./AccountRow";

export function AccountList() {
  const { data: accounts, isLoading } = useAccounts();

  if (isLoading) return <EmptyState message="Loading accounts…" />;
  if (!accounts || accounts.length === 0) {
    return <EmptyState message="No accounts yet. Add one to get started." />;
  }

  return (
    <div className="flex flex-col gap-4">
      {accounts.map((account) => (
        <AccountRow key={account.id} account={account} />
      ))}
    </div>
  );
}
