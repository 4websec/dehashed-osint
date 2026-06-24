// Redaction reveal + copy-on-reveal. Event-delegated so it survives HTMX swaps.
// Sensitive values (passwords, hashes) render as amber redaction bars; clicking
// one is a deliberate gesture to expose real leaked PII. A copy control appears
// only once a value is revealed.
document.addEventListener("click", (e) => {
  const redact = e.target.closest(".redact");
  if (redact) {
    const revealed = redact.classList.toggle("revealed");
    redact.setAttribute("aria-pressed", revealed ? "true" : "false");
    redact.setAttribute(
      "aria-label",
      revealed ? "Hide value" : "Reveal redacted value"
    );
    // The copy control is a sibling within the same cell/wrapper (.pwcell or td).
    const copy = redact.parentElement
      ? redact.parentElement.querySelector(".copy")
      : null;
    if (copy) copy.hidden = !revealed;
    return;
  }

  const copy = e.target.closest(".copy");
  if (copy) {
    const val = copy.getAttribute("data-copy") || "";
    navigator.clipboard.writeText(val).then(() => {
      const prev = copy.textContent;
      copy.textContent = "copied";
      setTimeout(() => {
        copy.textContent = prev;
      }, 1200);
    });
  }
});
