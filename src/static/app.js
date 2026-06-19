// Redaction reveal — the signature interaction.
// Sensitive values (passwords, hashes) render as amber redaction bars; clicking
// one is a deliberate gesture to expose real leaked PII. Event-delegated so it
// works for result rows that HTMX swaps in after a search.
document.addEventListener("click", (e) => {
  const btn = e.target.closest(".redact");
  if (!btn) return;
  const revealed = btn.classList.toggle("revealed");
  btn.setAttribute("aria-pressed", revealed ? "true" : "false");
  btn.setAttribute(
    "aria-label",
    revealed ? "Hide value" : "Reveal redacted value"
  );
});
