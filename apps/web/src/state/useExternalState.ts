import { useSyncExternalStore } from "react";

export function useExternalState<T>(source: {
  subscribe(listener: (state: T) => void): () => void;
  readonly state: T;
}): T {
  return useSyncExternalStore(
    (onChange) => source.subscribe(() => onChange()),
    () => source.state,
    () => source.state,
  );
}
