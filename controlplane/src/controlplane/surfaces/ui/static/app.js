// AUTON web chat — dependency-free vanilla JS.
// Talks to the same ChatEngine/SessionStore the terminal and desktop use, so the
// page hydrates from shared history on load and appends new turns as you chat.

const chat = document.getElementById("chat");
const emptyHint = document.getElementById("empty-hint");
const form = document.getElementById("composer");
const input = document.getElementById("prompt");
const send = document.getElementById("send");

/** Append a rendered message bubble and scroll it into view. */
function addMessage(role, text, { unhandled = false, pending = false } = {}) {
  if (emptyHint) emptyHint.remove();

  const el = document.createElement("div");
  el.className = `msg ${role}`;
  if (unhandled) el.classList.add("unhandled");
  if (pending) el.classList.add("pending");

  const who = document.createElement("span");
  who.className = "who";
  who.textContent = role === "user" ? "you" : "auton";
  el.append(who);

  const body = document.createElement("span");
  body.textContent = text;
  el.append(body);

  chat.append(el);
  chat.scrollTop = chat.scrollHeight;
  return el;
}

/** Load and render the persisted cross-surface conversation. */
async function hydrate() {
  try {
    const res = await fetch("/api/history");
    if (!res.ok) return;
    const turns = await res.json();
    for (const turn of turns) {
      const unhandled = turn.role === "auton" && turn.data?.handled === false;
      addMessage(turn.role, turn.text, { unhandled });
    }
  } catch {
    // First load before any backend; the empty hint stays. Non-fatal.
  }
}

async function submit(text) {
  addMessage("user", text);
  input.value = "";
  send.disabled = true;
  const thinking = addMessage("auton", "thinking…", { pending: true });

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const reply = await res.json();
    thinking.remove();
    addMessage("auton", reply.text || "(no reply)", { unhandled: !reply.handled });
  } catch (err) {
    thinking.remove();
    addMessage("auton", `Couldn't reach AUTON: ${err.message}`, { unhandled: true });
  } finally {
    send.disabled = false;
    input.focus();
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const text = input.value.trim();
  if (text) submit(text);
});

document.addEventListener("click", (event) => {
  const seed = event.target.closest(".seed");
  if (seed) submit(seed.dataset.seed);
});

hydrate();
