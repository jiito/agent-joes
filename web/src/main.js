import "./styles.css";

const app = document.querySelector("#app");

app.innerHTML = `
  <div class="min-h-screen bg-white text-neutral-950">
    <div class="mx-auto flex min-h-screen max-w-6xl flex-col px-6 py-6 sm:px-8 lg:px-10">
      <header class="flex items-center justify-between py-2">
        <a href="/" class="text-base font-semibold tracking-[-0.03em]">Agent Joes</a>
        <a href="#details" class="text-sm text-neutral-500 transition hover:text-neutral-900">About</a>
      </header>

      <main class="flex flex-1 flex-col items-center justify-center text-center">
        <div class="max-w-3xl">
          <p class="mb-5 text-sm font-medium text-neutral-500">Meal planning assistant</p>
          <h1 class="mx-auto max-w-4xl text-5xl font-semibold tracking-[-0.06em] sm:text-6xl md:text-7xl">
            Simple meal plans, grounded in real Trader Joe&apos;s products.
          </h1>
          <p class="mx-auto mt-6 max-w-2xl text-base leading-7 text-neutral-500 sm:text-lg">
            Agent Joes helps turn a goal, ingredient, or weeknight constraint into a practical plan you can actually shop for.
          </p>

          <div class="mt-10 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <a
              href="#details"
              class="inline-flex min-h-[48px] items-center justify-center rounded-full bg-neutral-950 px-6 text-sm font-medium text-white transition hover:bg-neutral-800"
            >
              Learn more
            </a>
            <a
              href="#details"
              class="inline-flex min-h-[48px] items-center justify-center rounded-full border border-neutral-200 px-6 text-sm font-medium text-neutral-700 transition hover:border-neutral-300 hover:text-neutral-950"
            >
              Current surfaces
            </a>
          </div>

          <p class="mt-4 text-xs text-neutral-400">
            Currently available through a Python app, terminal UI, and SMS webhook.
          </p>
        </div>
      </main>

      <section id="details" class="border-t border-neutral-200 py-6">
        <div class="flex flex-col gap-3 text-sm text-neutral-500 sm:flex-row sm:items-center sm:justify-between">
          <p>Built for lightweight meal planning with product search, recipe assistance, and texting.</p>
          <div class="flex items-center justify-center gap-4 sm:justify-end">
            <span>CLI</span>
            <span>TUI</span>
            <span>SMS</span>
          </div>
        </div>
      </section>
    </div>
  </div>
`;
