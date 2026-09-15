import { AskPanel } from "@/features/assistant";

export function Assistant() {
  return (
    <div className="flex flex-col gap-8">
      <h1 className="text-title">Ask</h1>
      <p className="text-body text-content-secondary">
        Answers are computed by the same engines the rest of this product uses. The figures
        are the answer; any prose is a description of them.
      </p>
      <AskPanel />
    </div>
  );
}
