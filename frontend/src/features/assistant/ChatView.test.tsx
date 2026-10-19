import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AssistantAnswer, AssistantConversation } from "@/api/types";
import { ChatView } from "@/features/assistant/ChatView";

const mutate = vi.fn();
const deleteMutate = vi.fn();
const useConversationsMock = vi.fn();
const useConversationMock = vi.fn();

vi.mock("@/api/assistant", () => ({
  useAsk: () => ({ mutate, isPending: false, isError: false, error: null }),
  useConversations: () => useConversationsMock(),
  useConversation: (conversationId: string | undefined) => useConversationMock(conversationId),
  useDeleteConversation: () => ({ mutate: deleteMutate, isPending: false }),
}));

function answer(overrides: Partial<AssistantAnswer> = {}): AssistantAnswer {
  return {
    supported: true,
    answer: "Your emergency fund covers 0.90 months of spending.",
    narration_available: true,
    figures: [
      {
        label: "Emergency fund after",
        value: "0.90",
        unit: "months",
        source: "emergency_fund_engine",
        result_id: null,
      },
    ],
    based_on: {},
    clarification: null,
    capability: "affordability",
    conversation_id: "0192f0c1-0000-7000-8000-000000000001",
    ...overrides,
  };
}

function send(question: string, result: AssistantAnswer) {
  mutate.mockImplementation((_vars, options) => options.onSuccess(result));
  fireEvent.change(screen.getByLabelText("Question"), { target: { value: question } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
}

describe("ChatView", () => {
  beforeEach(() => {
    mutate.mockReset();
    deleteMutate.mockReset();
    useConversationsMock.mockReset().mockReturnValue({ data: [] });
    useConversationMock.mockReset().mockReturnValue({ data: undefined });
    render(
      <MemoryRouter>
        <ChatView />
      </MemoryRouter>,
    );
  });

  it("offers openers before anything has been asked", () => {
    expect(screen.getByRole("heading", { name: "What do you want to know?" })).toBeVisible();
    expect(
      screen.getByRole("button", { name: "What is my emergency fund worth in months?" }),
    ).toBeVisible();
  });

  it("renders the question and the figures it was answered with", () => {
    send("What is my emergency fund worth in months?", answer());

    expect(screen.getByText("What is my emergency fund worth in months?")).toBeVisible();
    expect(screen.getByText("Emergency fund after")).toBeVisible();
    // The module name is kept on the wire for provenance and never shown — see
    // features/assistant/figureSources.ts.
    expect(screen.getByText("from your emergency fund")).toBeVisible();
    expect(screen.queryByText(/emergency_fund_engine/)).not.toBeInTheDocument();
  });

  /** design-system.md §9 and ADR-002: prose is disclosed as generated, and the figures
   * stand without it when no provider answered.
   */
  it("marks narration as written over the figures rather than as a figure", () => {
    send("What is my emergency fund worth in months?", answer());

    expect(screen.getByText("Written from the figures above")).toBeVisible();
  });

  it("still renders the figures when no narration is available", () => {
    send(
      "What is my emergency fund worth in months?",
      answer({ answer: null, narration_available: false }),
    );

    expect(screen.getByText("Emergency fund after")).toBeVisible();
    expect(screen.getByText(/written explanation is unavailable/)).toBeVisible();
    expect(screen.queryByText("Written from the figures above")).not.toBeInTheDocument();
  });

  it("sends on Enter and keeps Shift+Enter for a line break", () => {
    const composer = screen.getByLabelText("Question");

    fireEvent.change(composer, { target: { value: "Can I afford a holiday?" } });
    fireEvent.keyDown(composer, { key: "Enter", shiftKey: true });
    expect(mutate).not.toHaveBeenCalled();

    fireEvent.keyDown(composer, { key: "Enter" });
    expect(mutate).toHaveBeenCalledWith(
      expect.objectContaining({ question: "Can I afford a holiday?" }),
      expect.anything(),
    );
  });

  it("renders a small-talk reply with no figures and no missing-explanation caption", () => {
    send(
      "hi",
      answer({
        answer: "Hi! I can help with affordability check, spending analysis — ask me about any of those.",
        narration_available: false,
        figures: [],
        capability: "small_talk",
      }),
    );

    expect(screen.getByText(/Hi! I can help with/)).toBeVisible();
    expect(screen.queryByText(/written explanation is unavailable/)).not.toBeInTheDocument();
    expect(screen.queryByText("Not modelled")).not.toBeInTheDocument();
  });

  it("badges a narrated small-talk reply the same as any other narration", () => {
    send(
      "hello there",
      answer({
        answer: "Hey! Ask me about your net worth, debt, or goals any time.",
        narration_available: true,
        figures: [],
        capability: "small_talk",
      }),
    );

    expect(screen.getByText("Written for you")).toBeVisible();
  });

  it("states what cannot be modelled rather than approximating", () => {
    send(
      "Should I buy bitcoin?",
      answer({
        supported: false,
        answer: "That is not something this system models.",
        narration_available: false,
        figures: [],
      }),
    );

    expect(screen.getByText("Not modelled")).toBeVisible();
    expect(screen.getByText("That is not something this system models.")).toBeVisible();
  });
});

function renderChatView() {
  render(
    <MemoryRouter>
      <ChatView />
    </MemoryRouter>,
  );
}

function conversationFixture(
  overrides: Partial<AssistantConversation> = {},
): AssistantConversation {
  return {
    id: "conv-2",
    title: "Net worth check",
    started_at: "2026-09-10T09:00:00Z",
    messages: [
      {
        id: "m1",
        asked_at: "2026-09-10T09:00:01Z",
        question: "What is my net worth?",
        answer: null,
        capability: "position_query",
        supported: true,
        narration_available: false,
        figures: [],
      },
    ],
    ...overrides,
  };
}

describe("ChatView history", () => {
  beforeEach(() => {
    mutate.mockReset();
    useConversationsMock.mockReset();
    useConversationMock.mockReset().mockReturnValue({ data: undefined });
  });

  it("opens the history drawer and lists past conversations", () => {
    useConversationsMock.mockReturnValue({
      data: [
        { id: "conv-1", title: "Can I afford a holiday?", started_at: "2026-09-01T10:00:00Z" },
        { id: "conv-2", title: "Net worth check", started_at: "2026-09-10T09:00:00Z" },
      ],
    });
    renderChatView();

    fireEvent.click(screen.getByRole("button", { name: "History" }));

    expect(screen.getByRole("dialog", { name: "Conversation history" })).toBeVisible();
    expect(screen.getByText("Can I afford a holiday?")).toBeVisible();
    expect(screen.getByText("Net worth check")).toBeVisible();
  });

  it("switches to the selected conversation and closes the drawer", () => {
    useConversationsMock.mockReturnValue({
      data: [{ id: "conv-2", title: "Net worth check", started_at: "2026-09-10T09:00:00Z" }],
    });
    useConversationMock.mockImplementation((conversationId: string | undefined) =>
      conversationId === "conv-2" ? { data: conversationFixture() } : { data: undefined },
    );
    renderChatView();

    fireEvent.click(screen.getByRole("button", { name: "History" }));
    fireEvent.click(screen.getByText("Net worth check"));

    expect(screen.getByText("What is my net worth?")).toBeVisible();
    expect(screen.queryByRole("dialog", { name: "Conversation history" })).not.toBeInTheDocument();
  });

  it("asks before deleting a conversation, and does nothing if you keep it", () => {
    useConversationsMock.mockReturnValue({
      data: [{ id: "conv-2", title: "Net worth check", started_at: "2026-09-10T09:00:00Z" }],
    });
    renderChatView();

    fireEvent.click(screen.getByRole("button", { name: "History" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete Net worth check" }));

    expect(deleteMutate).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Keep" }));
    expect(deleteMutate).not.toHaveBeenCalled();
    expect(screen.getByText("Net worth check")).toBeVisible();
  });

  it("deletes the conversation once confirmed", () => {
    useConversationsMock.mockReturnValue({
      data: [{ id: "conv-2", title: "Net worth check", started_at: "2026-09-10T09:00:00Z" }],
    });
    renderChatView();

    fireEvent.click(screen.getByRole("button", { name: "History" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete Net worth check" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    expect(deleteMutate).toHaveBeenCalledWith("conv-2");
  });

  it("leaves no deleted thread on screen when the open one is the one deleted", () => {
    useConversationsMock.mockReturnValue({
      data: [{ id: "conv-2", title: "Net worth check", started_at: "2026-09-10T09:00:00Z" }],
    });
    useConversationMock.mockImplementation((conversationId: string | undefined) =>
      conversationId === "conv-2" ? { data: conversationFixture() } : { data: undefined },
    );
    renderChatView();

    fireEvent.click(screen.getByRole("button", { name: "History" }));
    fireEvent.click(screen.getByText("Net worth check"));
    expect(screen.getByText("What is my net worth?")).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "History" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete Net worth check" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    expect(screen.queryByText("What is my net worth?")).not.toBeInTheDocument();
  });

  it("says there is no history yet when the list is empty", () => {
    useConversationsMock.mockReturnValue({ data: [] });
    renderChatView();

    fireEvent.click(screen.getByRole("button", { name: "History" }));

    expect(screen.getByText("No conversations yet.")).toBeVisible();
  });
});
