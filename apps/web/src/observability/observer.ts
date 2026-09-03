export type WebObservation = Readonly<{
  requestId: string;
  route: string;
  latencyMs: number;
  statusCategory: string;
  retryCount: number;
  buildVersion: "0.13.0";
  conversationId?: string;
}>;

export type WebObserver = (event: WebObservation) => void;

export const silentObserver: WebObserver = () => undefined;

export function safeObservation(input: WebObservation): WebObservation {
  return Object.freeze({ ...input });
}
