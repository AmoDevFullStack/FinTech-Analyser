import {
  AddTransactionForm,
  ImportFlow,
  MonthComparison,
  TransactionList,
} from "@/features/transactions";

export function Transactions() {
  return (
    <div className="flex flex-col gap-8">
      <h1 className="text-title">Transactions</h1>
      <ImportFlow />
      <MonthComparison />
      <AddTransactionForm />
      <TransactionList />
    </div>
  );
}
