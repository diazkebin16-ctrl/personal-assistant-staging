import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { BackendClient } from "./api/client";
import { createAuthGateway } from "./auth/authGateway";
import { loadRuntimeConfig } from "./config";
import { ConversationController } from "./conversation/controller";
import { SessionController } from "./session/sessionController";
import "./styles.css";

async function bootstrap() {
  const config = await loadRuntimeConfig();
  const auth = createAuthGateway(config);
  let client: BackendClient | null = null;
  let conversations: ConversationController | null = null;
  const session = new SessionController(auth, {
    onClear: () => {
      client?.abortAll();
      conversations?.clear();
    },
  });
  client = new BackendClient({
    baseUrl: config.apiBaseUrl,
    tokenProvider: () => session.getToken(),
    onAuthenticationRequired: () => session.expire(),
  });
  conversations = new ConversationController(client);
  const root = document.getElementById("root");
  if (!root) throw new Error("Application root is unavailable.");
  createRoot(root).render(
    <StrictMode>
      <App client={client} conversations={conversations} session={session} />
    </StrictMode>,
  );
}

bootstrap().catch(() => {
  const root = document.getElementById("root");
  if (root) {
    const main = document.createElement("main");
    main.className = "fatal-error";
    const heading = document.createElement("h1");
    heading.textContent = "Personal Assistant is unavailable";
    const message = document.createElement("p");
    message.textContent =
      "Secure configuration could not be loaded. Try again later.";
    main.append(heading, message);
    root.replaceChildren(main);
  }
});
