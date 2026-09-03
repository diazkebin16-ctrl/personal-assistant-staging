import { useEffect, useState } from "react";

export type Connectivity = "ONLINE" | "OFFLINE";

export function useConnectivity(): Connectivity {
  const [state, setState] = useState<Connectivity>(() =>
    navigator.onLine ? "ONLINE" : "OFFLINE",
  );
  useEffect(() => {
    const online = () => setState("ONLINE");
    const offline = () => setState("OFFLINE");
    globalThis.addEventListener("online", online);
    globalThis.addEventListener("offline", offline);
    return () => {
      globalThis.removeEventListener("online", online);
      globalThis.removeEventListener("offline", offline);
    };
  }, []);
  return state;
}
