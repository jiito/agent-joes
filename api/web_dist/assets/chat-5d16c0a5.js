import"./styles-04314243.js";const m=["Plan three easy vegetarian dinners for this week.","What should I make with tofu, broccoli, and rice?","Give me a Trader Joe's dinner under $25 for two."],x=[{role:"assistant",content:"This test page sends the same kind of single-turn request as the SMS agent. Ask for a recipe, a short meal plan, or ideas built around Trader Joe's ingredients."}],n={messages:[...x],loading:!1},f=document.querySelector("#app");f.innerHTML=`
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
`;const o=document.querySelector("#messages"),h=document.querySelector("#chat-form"),s=document.querySelector("#chat-input"),g=document.querySelector("#status"),b=document.querySelector("#send-button"),u=document.querySelector("#quick-prompts");function l(e){return e.replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#39;")}function y(e){return l(e).replaceAll(`
`,"<br />")}function v(e){g.textContent=e}function w(){u.innerHTML=m.map(e=>`
        <button
          type="button"
          data-prompt="${l(e)}"
          class="rounded-full border border-neutral-200 px-4 py-2 text-sm text-neutral-600 transition hover:border-neutral-300 hover:text-neutral-950"
        >
          ${l(e)}
        </button>
      `).join("")}function r(){o.innerHTML=n.messages.map(e=>{const t=e.role==="user";return`
        <article class="flex ${t?"justify-end":"justify-start"}">
          <div class="${t?"bg-neutral-950 text-white":"bg-neutral-100 text-neutral-900"} max-w-[85%] rounded-3xl px-5 py-4 text-sm leading-6 sm:text-base">
            ${y(e.content)}
          </div>
        </article>
      `}).join(""),o.scrollTop=o.scrollHeight}function c(e){n.loading=e,b.disabled=e,s.disabled=e,v(e?"Thinking...":"")}async function d(e){const t=e.trim();if(!(!t||n.loading)){n.messages.push({role:"user",content:t}),r(),s.value="",c(!0);try{const a=await fetch("/api/chat",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({message:t})}),i=await a.json().catch(()=>({}));if(!a.ok){const p=i.detail||"The agent did not return a reply.";throw new Error(p)}n.messages.push({role:"assistant",content:i.reply||"The agent returned an empty reply."}),r()}catch(a){n.messages.push({role:"assistant",content:`Request failed: ${a instanceof Error?a.message:"Unknown error."}`}),r()}finally{c(!1),s.focus()}}}h.addEventListener("submit",async e=>{e.preventDefault(),await d(s.value)});u.addEventListener("click",async e=>{const t=e.target.closest("[data-prompt]");t instanceof HTMLButtonElement&&(s.value=t.dataset.prompt||"",await d(s.value))});w();r();s.focus();
