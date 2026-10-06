/* Page /salle : projection 2D (PCA) des embeddings en SVG pur, sans bibliothèque. */
(() => {
  "use strict";
  const { t, el, safeUrl, movementLabel, onLang } = window.Musee;
  const $ = (id) => document.getElementById(id);
  const NS = "http://www.w3.org/2000/svg";
  const W = 760, H = 520, PAD = 44;

  const model = { points: [], explained: [0, 0], movements: [], colors: {}, selected: null };

  function colorFor(index, total) {
    // Angle d'or : deux mouvements voisins dans la légende ont des teintes très différentes ;
    // luminosité alternée pour aider les cas proches. Fond sombre : tons clairs.
    const hue = Math.round(index * 137.508 + 20) % 360;
    const light = index % 2 ? 72 : 60;
    return `hsl(${hue} 68% ${light}%)`;
  }

  function svg(tag, attrs) {
    const n = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs || {})) n.setAttribute(k, v);
    return n;
  }

  const px = (x) => PAD + ((x + 1) / 2) * (W - 2 * PAD);
  const py = (y) => PAD + (1 - (y + 1) / 2) * (H - 2 * PAD);

  function drawMap() {
    const map = $("map");
    map.querySelectorAll(".dyn").forEach((n) => n.remove());
    const g = svg("g", { class: "dyn" });

    // repères
    g.append(svg("line", { x1: PAD, y1: py(0), x2: W - PAD, y2: py(0), class: "axis" }));
    g.append(svg("line", { x1: px(0), y1: PAD, x2: px(0), y2: H - PAD, class: "axis" }));
    const lbl = (x, y, text, anchor) => {
      const n = svg("text", { x, y, class: "axis-label", "text-anchor": anchor });
      n.textContent = text;
      return n;
    };
    g.append(lbl(W - PAD, H - 14, `PC1 · ${(model.explained[0] * 100).toFixed(0)} %`, "end"));
    g.append(lbl(PAD, 22, `PC2 · ${(model.explained[1] * 100).toFixed(0)} %`, "start"));

    model.points.forEach((p, i) => {
      const c = svg("circle", {
        cx: px(p.x).toFixed(1), cy: py(p.y).toFixed(1), r: 6.5, fill: model.colors[p.movement],
        class: "dot", tabindex: 0, role: "link",
        "aria-label": `${p.title}${p.artist ? ", " + p.artist : ""} — ${movementLabel(p.movement)}`,
        "data-movement": p.movement,
      });
      c.style.setProperty("--d", `${Math.min(i * 6, 900)}ms`);
      c.addEventListener("mouseenter", () => showTip(p, c));
      c.addEventListener("focus", () => showTip(p, c));
      c.addEventListener("mouseleave", hideTip);
      c.addEventListener("blur", hideTip);
      const open = () => { const u = safeUrl(p.source_url); if (u) window.open(u, "_blank", "noopener,noreferrer"); };
      c.addEventListener("click", open);
      c.addEventListener("keydown", (e) => { if (e.key === "Enter") open(); });
      g.append(c);
    });
    map.append(g);
    applySelection();
  }

  function showTip(p, node) {
    const tip = $("tip");
    const img = $("tip-img");
    const u = safeUrl(p.image_url);
    if (u) { img.src = u; img.referrerPolicy = "no-referrer"; } else img.removeAttribute("src");
    $("tip-title").textContent = p.title;
    $("tip-artist").textContent = [p.artist, p.year].filter(Boolean).join(" · ");
    $("tip-mov").textContent = movementLabel(p.movement);
    tip.hidden = false;
    const host = tip.parentElement.getBoundingClientRect();
    const r = node.getBoundingClientRect();
    let left = r.left - host.left + r.width + 10;
    if (left + tip.offsetWidth > host.width) left = r.left - host.left - tip.offsetWidth - 10;
    let top = r.top - host.top - 20;
    top = Math.max(4, Math.min(top, host.height - tip.offsetHeight - 4));
    tip.style.left = `${Math.max(4, left)}px`;
    tip.style.top = `${top}px`;
  }
  const hideTip = () => { $("tip").hidden = true; };

  function applySelection() {
    document.querySelectorAll("#map .dot").forEach((d) => {
      const off = model.selected && d.dataset.movement !== model.selected;
      d.classList.toggle("dim", Boolean(off));
    });
    document.querySelectorAll(".legend-item").forEach((b) => {
      b.setAttribute("aria-pressed", String(b.dataset.movement === model.selected));
    });
  }

  function drawLegend() {
    const list = $("legend");
    list.replaceChildren();
    model.movements.forEach((m) => {
      const count = model.points.filter((p) => p.movement === m).length;
      const dot = el("span", { class: "swatch" });
      dot.style.background = model.colors[m];
      const b = el("button", { class: "legend-item", attrs: { type: "button", "data-movement": m, "aria-pressed": "false" } },
        dot, el("span", { class: "legend-name", text: movementLabel(m) }), el("span", { class: "legend-n note", text: String(count) }));
      b.addEventListener("click", () => { model.selected = model.selected === m ? null : m; applySelection(); });
      list.append(el("li", null, b));
    });
  }

  function drawGroups() {
    const host = $("movement-groups");
    host.replaceChildren();
    model.movements.forEach((m) => {
      const works = model.points.filter((p) => p.movement === m);
      const dot = el("span", { class: "swatch" });
      dot.style.background = model.colors[m];
      const sum = el("summary", null, dot, el("span", { text: movementLabel(m) }),
        el("span", { class: "note legend-n", text: `${works.length} ${t("salle.works")}` }));
      const ul = el("ul", { class: "works" });
      works.forEach((p) => {
        const li = el("li");
        const href = safeUrl(p.source_url);
        const name = href ? el("a", { text: p.title, attrs: { href, target: "_blank", rel: "noopener noreferrer" } }) : el("span", { text: p.title });
        li.append(name, el("span", { class: "note", text: ` — ${[p.artist, p.year].filter(Boolean).join(", ")}` }));
        ul.append(li);
      });
      host.append(el("details", { class: "group" }, sum, ul));
    });
  }

  function drawMeta() {
    $("map-meta").textContent = t("salle.meta", {
      n: model.points.length,
      a: (model.explained[0] * 100).toFixed(0),
      b: (model.explained[1] * 100).toFixed(0),
    });
  }

  function renderAll() { drawMap(); drawLegend(); drawGroups(); drawMeta(); }

  $("legend-reset").addEventListener("click", () => { model.selected = null; applySelection(); });
  onLang(renderAll);

  (async () => {
    try {
      const res = await fetch("/api/corpus", { headers: { "X-Lang": window.Musee.state.lang } });
      const data = await res.json();
      model.points = data.points || [];
      model.explained = data.explained || [0, 0];
    } catch (_) { model.points = []; }

    if (!model.points.length) { $("salle-empty").hidden = false; return; }
    model.movements = [...new Set(model.points.map((p) => p.movement))].sort();
    model.movements.forEach((m, i) => (model.colors[m] = colorFor(i, model.movements.length)));
    $("salle-body").hidden = false;
    $("by-movement").hidden = false;
    renderAll();
  })();
})();
