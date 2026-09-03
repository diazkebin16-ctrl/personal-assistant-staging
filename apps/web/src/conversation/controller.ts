import type {
  AssistantResponse,
  Conversation,
  ConversationMessage,
  UUID,
} from "../api/contracts";
import type { BackendClient, LogicalMessage } from "../api/client";
import { ApiError, classifyTransportError } from "../api/errors";

export type ConversationViewState = Readonly<{
  selectedId: UUID | null;
  conversation: Conversation | null;
  messages: readonly ConversationMessage[];
  pending: LogicalMessage | null;
  error: ApiError | null;
}>;

export class ConversationController {
  readonly #client: BackendClient;
  #state: ConversationViewState = Object.freeze({
    selectedId: null,
    conversation: null,
    messages: [],
    pending: null,
    error: null,
  });
  #epoch = 0;
  #inFlight: Promise<AssistantResponse | null> | null = null;
  #loadController: AbortController | null = null;
  readonly #listeners = new Set<(state: ConversationViewState) => void>();

  constructor(client: BackendClient) {
    this.#client = client;
  }

  get state(): ConversationViewState {
    return this.#state;
  }

  subscribe(listener: (state: ConversationViewState) => void): () => void {
    this.#listeners.add(listener);
    listener(this.#state);
    return () => this.#listeners.delete(listener);
  }

  async select(conversation: Conversation): Promise<void> {
    this.#epoch += 1;
    const epoch = this.#epoch;
    this.#loadController?.abort();
    const controller = new AbortController();
    this.#loadController = controller;
    this.#set({
      selectedId: conversation.id,
      conversation,
      messages: [],
      pending: null,
      error: null,
    });
    try {
      const messages = await this.#client.listMessages(
        conversation.id,
        controller.signal,
      );
      if (epoch !== this.#epoch || this.#state.selectedId !== conversation.id)
        return;
      this.#set({ ...this.#state, messages });
    } catch (error) {
      if (controller.signal.aborted || epoch !== this.#epoch) return;
      this.#set({ ...this.#state, error: classifyTransportError(error) });
    }
  }

  send(
    content: string,
    online = navigator.onLine,
  ): Promise<AssistantResponse | null> {
    if (!online) {
      const error = new ApiError(
        "NETWORK_OFFLINE",
        "The assistant is unavailable while you are offline.",
      );
      this.#set({ ...this.#state, error });
      return Promise.reject(error);
    }
    const conversation = this.#state.conversation;
    if (!conversation) {
      return Promise.reject(
        new ApiError("VALIDATION_ERROR", "Select a conversation first."),
      );
    }
    if (this.#inFlight) return this.#inFlight;
    const logical = this.#client.createLogicalMessage(conversation, content);
    return this.#dispatch(logical);
  }

  retry(): Promise<AssistantResponse | null> {
    if (this.#inFlight) return this.#inFlight;
    const logical = this.#state.pending;
    if (!logical) {
      return Promise.reject(
        new ApiError("VALIDATION_ERROR", "There is no retryable message."),
      );
    }
    return this.#dispatch(logical);
  }

  clear(): void {
    this.#epoch += 1;
    this.#loadController?.abort();
    this.#inFlight = null;
    this.#set({
      selectedId: null,
      conversation: null,
      messages: [],
      pending: null,
      error: null,
    });
  }

  #dispatch(logical: LogicalMessage): Promise<AssistantResponse | null> {
    const epoch = this.#epoch;
    this.#set({ ...this.#state, pending: logical, error: null });
    const operation = this.#client
      .sendLogicalMessage(logical)
      .then((response) => {
        if (
          epoch !== this.#epoch ||
          this.#state.selectedId !== logical.conversationId
        )
          return null;
        const messages = [
          ...this.#state.messages,
          response.user_message,
          response.assistant_message,
        ];
        this.#set({
          selectedId: response.conversation.id,
          conversation: response.conversation,
          messages,
          pending: null,
          error: null,
        });
        return response;
      })
      .catch((error: unknown) => {
        const classified = classifyTransportError(error);
        if (
          epoch === this.#epoch &&
          this.#state.selectedId === logical.conversationId
        ) {
          const retryable =
            classified.category === "NETWORK_OFFLINE" ||
            classified.category === "TIMEOUT" ||
            classified.category === "SERVER_UNAVAILABLE";
          this.#set({
            ...this.#state,
            pending: retryable ? logical : null,
            error: classified,
          });
        }
        throw classified;
      })
      .finally(() => {
        if (this.#inFlight === operation) this.#inFlight = null;
      });
    this.#inFlight = operation;
    return operation;
  }

  #set(state: ConversationViewState): void {
    this.#state = Object.freeze(state);
    for (const listener of this.#listeners) listener(this.#state);
  }
}
