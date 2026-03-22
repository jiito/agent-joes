import "./styles.css";

const quickPrompts = [
  "Plan three easy vegetarian dinners for this week.",
  "What should I make with tofu, broccoli, and rice?",
  "Give me a Trader Joe's dinner under $25 for two.",
];

const initialMessages = [
  {
    role: "assistant",
    content:
      "This test page sends the same kind of single-turn request as the SMS agent. Ask for a recipe, a short meal plan, or ideas built around Trader Joe's ingredients.",
  },
];

const state = {
  messages: [...initialMessages],
  loading: false,
};

const app = document.querySelector("#app");

app.innerHTML = `
  <div class="min-h-screen bg-white text-neutral-950">
    <div class="mx-auto flex min-h-screen max-w-6xl flex-col px-6 py-6 sm:px-8 lg:px-10">
      <header class="flex items-center justify-between py-2">
        <a href="/" class="text-base font-semibold tracking-[-0.03em]">Agent Joes</a>
        <nav class="flex items-center gap-5 text-sm text-neutral-500">
          <a href="/" class="transition hover:text-neutral-900">Home</a>
          <span class="text-neutral-900">Test chat</span>
        </nav>
      </header>

      <main class="flex flex-1 items-center py-8">
        <div class="mx-auto flex w-full max-w-4xl flex-1 flex-col rounded-[28px] border border-neutral-200 bg-white shadow-[0_24px_80px_rgba(0,0,0,0.06)]">
          <section class="border-b border-neutral-200 px-6 py-5 sm:px-8">
            <p class="text-sm font-medium text-neutral-500">Meal planning assistant</p>
            <h1 class="mt-2 text-3xl font-semibold tracking-[-0.05em] sm:text-4xl">
              Test the agent before using SMS.
            </h1>
            <p class="mt-3 max-w-2xl text-sm leading-6 text-neutral-500 sm:text-base">
              Each message is sent like a fresh text to the backend agent, so this is a lightweight preview of the SMS experience rather than a long-running chat session.
            </p>
          </section>

          <section class="border-b border-neutral-200 px-6 py-4 sm:px-8">
            <div class="flex flex-wrap gap-2" id="quick-prompts"></div>
          </section>

          <section class="flex-1 space-y-4 overflow-y-auto px-6 py-6 sm:px-8" id="messages"></section>

          <form class="border-t border-neutral-200 px-6 py-5 sm:px-8" id="chat-form">
            <label class="sr-only" for="chat-input">Message</label>
            <div class="flex flex-col gap-3 sm:flex-row sm:items-end">
              <textarea
                id="chat-input"
                rows="3"
                placeholder="Ask for a dinner plan, recipe idea, or Trader Joe's shopping suggestion."
                class="min-h-[112px] flex-1 resize-none rounded-3xl border border-neutral-200 px-5 py-4 text-base text-neutral-950 outline-none transition focus:border-neutral-400"
              ></textarea>
              <button
                type="submit"
                id="send-button"
                class="inline-flex min-h-[52px] items-center justify-center rounded-full bg-neutral-950 px-6 text-sm font-medium text-white transition hover:bg-neutral-800 disabled:cursor-not-allowed disabled:bg-neutral-300"
              >
                Send
              </button>
            </div>
            <p id="status" class="mt-3 text-sm text-neutral-500"></p>
          </form>
        </div>
      </main>
    </div>
  </div>
`;

const messagesEl = document.querySelector("#messages");
const formEl = document.querySelector("#chat-form");
const inputEl = document.querySelector("#chat-input");
const statusEl = document.querySelector("#status");
const sendButtonEl = document.querySelector("#send-button");
const quickPromptsEl = document.querySelector("#quick-prompts");

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatMessage(value) {
  return escapeHtml(value).replaceAll("\n", "<br />");
}

function setStatus(message) {
  statusEl.textContent = message;
}

function renderQuickPrompts() {
  quickPromptsEl.innerHTML = quickPrompts
    .map(
      (prompt) => `
        <button
          type="button"
          data-prompt="${escapeHtml(prompt)}"
          class="rounded-full border border-neutral-200 px-4 py-2 text-sm text-neutral-600 transition hover:border-neutral-300 hover:text-neutral-950"
        >
          ${escapeHtml(prompt)}
        </button>
      `
    )
    .join("");
}

function renderMessages() {
  messagesEl.innerHTML = state.messages
    .map((message) => {
      const isUser = message.role === "user";
      return `
        <article class="flex ${isUser ? "justify-end" : "justify-start"}">
          <div class="${isUser ? "bg-neutral-950 text-white" : "bg-neutral-100 text-neutral-900"} max-w-[85%] rounded-3xl px-5 py-4 text-sm leading-6 sm:text-base">
            ${formatMessage(message.content)}
          </div>
        </article>
      `;
    })
    .join("");
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function setLoading(loading) {
  state.loading = loading;
  sendButtonEl.disabled = loading;
  inputEl.disabled = loading;
  setStatus(loading ? "Thinking..." : "");
}

async function sendMessage(message) {
  const trimmed = message.trim();
  if (!trimmed || state.loading) {
    return;
  }

  state.messages.push({ role: "user", content: trimmed });
  renderMessages();
  inputEl.value = "";
  setLoading(true);

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ message: trimmed }),
    });

    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const errorMessage = payload.detail || "The agent did not return a reply.";
      throw new Error(errorMessage);
    }

    state.messages.push({
      role: "assistant",
      content: payload.reply || "The agent returned an empty reply.",
    });
    renderMessages();
  } catch (error) {
    state.messages.push({
      role: "assistant",
      content: `Request failed: ${error instanceof Error ? error.message : "Unknown error."}`,
    });
    renderMessages();
  } finally {
    setLoading(false);
    inputEl.focus();
  }
}

formEl.addEventListener("submit", async (event) => {
  event.preventDefault();
  await sendMessage(inputEl.value);
});

quickPromptsEl.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-prompt]");
  if (!(button instanceof HTMLButtonElement)) {
    return;
  }
  inputEl.value = button.dataset.prompt || "";
  await sendMessage(inputEl.value);
});

renderQuickPrompts();
renderMessages();
inputEl.focus();
