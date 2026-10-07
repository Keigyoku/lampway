"""The shared stylesheet and lightbox every card page links (``cards/_shared/report.css``, ``report.js`` and the lockup): the brand's faces inlined, no CDN, nothing fetched from the network.
The lightbox is written for Lampway (not a copy): every image opens full size in a ``<dialog>``, ArrowLeft / ArrowRight step through the page's images, Escape closes, Fit /
100 %, Open original, Download, focus goes back to the image that opened it, and images added later are picked up by a MutationObserver."""

from .. import brand_page as _BP

# The card's own layout on the brand's tokens (lampway_server/brand_page.py): Night by default, Paper under the light theme the
# content server marks on a document (data-lw-theme="light"); Fraunces for the headings, IBM Plex Sans for the text.
_CARD_CSS = """/* Lampway card reports: generated, local only */
:root { color-scheme: dark; }
html[data-lw-theme="light"] { color-scheme: light; }
body { margin: 0 auto; max-width: 1180px; padding: 24px; background: var(--lw-surface); color: var(--lw-text);
  font: 14px/1.55 'IBM Plex Sans', system-ui, sans-serif; -webkit-font-smoothing: antialiased; }
img.mark { display: block; height: 30px; margin: 4px 0 18px; }
h1, h2, h3 { font-family: 'Fraunces', Georgia, serif; font-weight: 400; color: var(--lw-text_hi); margin: 1.2em 0 .4em; }
h1 { font-size: 30px; margin-top: 0; } .muted { color: var(--lw-muted); }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 16px; }
.cell { background: var(--lw-raised); border: 1px solid var(--lw-line); border-radius: 10px; padding: 12px; }
.cell img, .cell video { width: 100%; border-radius: 6px; background: var(--lw-viewport_lo); cursor: zoom-in; }
.chosen { border-color: var(--lw-go); } .rejected { opacity: .78; } .tag { font: 12px ui-monospace, monospace; color: var(--lw-muted); }
.mark-chosen { color: var(--lw-go); } .mark-rejected { color: var(--lw-stop); } .base { border-color: var(--lw-accent); }
a { color: var(--lw-accent_text); }
details pre { white-space: pre-wrap; background: var(--lw-well); padding: 8px; border-radius: 6px; }
.scroll { overflow-x: auto; } table { border-collapse: collapse; } td, th { border-bottom: 1px solid var(--lw-line); padding: 4px 10px; text-align: left; }
dialog.lw-box { max-width: 96vw; max-height: 96vh; padding: 0; background: var(--lw-viewport_lo); border: 1px solid var(--lw-line); }
dialog.lw-box img { display: block; max-width: 92vw; max-height: 86vh; } dialog.lw-box.lw-full img { max-width: none; max-height: none; }
dialog.lw-box nav { display: flex; gap: 8px; padding: 8px; background: var(--lw-raised); }
"""
REPORT_CSS = _BP.faces_css() + _BP.tokens_css('html[data-lw-theme="light"]') + _CARD_CSS
LOCKUP_SVG = _BP.mark_svg()

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
