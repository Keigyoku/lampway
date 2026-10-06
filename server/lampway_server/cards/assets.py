"""The shared stylesheet and lightbox every card page links (``cards/_shared/report.css`` and ``report.js``): no web font, no CDN, nothing fetched from the network.
The lightbox is written for Lampway (not a copy): every image opens full size in a ``<dialog>``, ArrowLeft / ArrowRight step through the page's images, Escape closes, Fit /
100 %, Open original, Download, focus goes back to the image that opened it, and images added later are picked up by a MutationObserver."""

REPORT_CSS = """/* Lampway card reports: generated, local only */
:root { color-scheme: dark; --bg: #161922; --raised: #1E222D; --line: #2B303D; --text: #ECE8DF; --muted: #A9A69D; --accent: #EDB944; --go: #5BC48F; --stop: #F0766B; }
html[data-lw-theme="light"] [data-lw-report="document"], html[data-lw-theme="light"] body { --bg: #F7F3EA; --raised: #FFFFFF; --line: #DDD5C3; --text: #1B1B22; --muted: #5C5A55; }
body { margin: 0 auto; max-width: 1180px; padding: 24px; background: var(--bg); color: var(--text); font: 14px/1.5 system-ui, sans-serif; }
h1, h2, h3 { font-weight: 600; margin: 1.2em 0 .4em; } h1 { font-size: 24px; } .muted { color: var(--muted); }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 16px; }
.cell { background: var(--raised); border: 1px solid var(--line); border-radius: 8px; padding: 12px; }
.cell img, .cell video { width: 100%; border-radius: 5px; background: #0B0D12; cursor: zoom-in; }
.chosen { border-color: var(--go); } .rejected { opacity: .78; } .tag { font: 12px ui-monospace, monospace; color: var(--muted); }
.mark-chosen { color: var(--go); } .mark-rejected { color: var(--stop); } .base { border-color: var(--accent); }
details pre { white-space: pre-wrap; background: var(--bg); padding: 8px; border-radius: 5px; }
.scroll { overflow-x: auto; } table { border-collapse: collapse; } td, th { border-bottom: 1px solid var(--line); padding: 4px 10px; text-align: left; }
dialog.lw-box { max-width: 96vw; max-height: 96vh; padding: 0; background: #0B0D12; border: 1px solid var(--line); }
dialog.lw-box img { display: block; max-width: 92vw; max-height: 86vh; } dialog.lw-box.lw-full img { max-width: none; max-height: none; }
dialog.lw-box nav { display: flex; gap: 8px; padding: 8px; background: var(--raised); }
"""

REPORT_JS = """// Lampway card reports: the image lightbox (local only)
(function () {
  "use strict";
  const box = document.createElement("dialog");
  box.className = "lw-box";
  box.innerHTML = '<img alt=""><nav><button data-a="fit">Fit</button><button data-a="full">100 %</button>' +
                  '<a data-a="open" target="_blank" rel="noopener">Open original</a><a data-a="dl" download>Download</a><button data-a="close">Close</button></nav>';
  document.body.appendChild(box);
  const big = box.querySelector("img");
  let opener = null, index = -1;
  const images = () => Array.from(document.querySelectorAll("main img"));
  function show(i) {
    const list = images();
    if (!list.length) return;
    index = (i + list.length) % list.length;
    const src = list[index].getAttribute("src");
    big.src = src; big.alt = list[index].alt;
    box.querySelector('[data-a="open"]').href = src;
    box.querySelector('[data-a="dl"]').href = src;
  }
  function open(img) { opener = img; show(images().indexOf(img)); box.showModal(); }
  function close() { box.close(); }
  box.addEventListener("close", () => { if (opener) opener.focus(); });
  box.addEventListener("click", (e) => {
    const a = e.target.getAttribute && e.target.getAttribute("data-a");
    if (a === "fit") box.classList.remove("lw-full");
    if (a === "full") box.classList.add("lw-full");
    if (a === "close") close();
  });
  document.addEventListener("keydown", (e) => {
    if (!box.open) return;
    if (e.key === "ArrowLeft") show(index - 1);
    if (e.key === "ArrowRight") show(index + 1);
    if (e.key === "Escape") close();
  });
  function arm(img) {
    if (img.dataset.lwArmed) return;
    img.dataset.lwArmed = "1"; img.tabIndex = 0;
    img.addEventListener("click", () => open(img));
    img.addEventListener("keydown", (e) => { if (e.key === "Enter") open(img); });
  }
  images().forEach(arm);
  new MutationObserver(() => images().forEach(arm)).observe(document.body, { childList: true, subtree: true });
})();
"""
