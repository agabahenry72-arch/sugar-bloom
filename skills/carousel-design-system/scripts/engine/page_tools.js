// Runs inside the rendered carousel page. Two jobs:
//   fit()      shrink copy inside [data-fit-box] containers until it fits
//   collect()  measure every [data-qa] element so qa.py can check the layout
window.__carousel = (() => {
  async function ready() {
    await document.fonts.ready;
    await Promise.all([...document.images].map((img) => (img.complete ? null : img.decode().catch(() => null))));
  }

  function overflows(box) {
    if (box.scrollHeight > box.clientHeight + 1 || box.scrollWidth > box.clientWidth + 1) return true;
    // Centred content can spill out on both sides, which scrollWidth doesn't report.
    const b = box.getBoundingClientRect();
    for (const el of box.querySelectorAll("[data-qa]")) {
      const r = el.getBoundingClientRect();
      if (r.left < b.left - 1 || r.right > b.right + 1 || r.top < b.top - 1 || r.bottom > b.bottom + 1) return true;
    }
    return false;
  }

  async function fit() {
    await ready();
    const results = [];
    for (const box of document.querySelectorAll("[data-fit-box]")) {
      const min = parseFloat(box.dataset.fitMin || "0.65");
      let scale = 1;
      box.style.setProperty("--fit", "1");
      while (overflows(box) && scale > min) {
        scale = Math.max(min, Math.round((scale - 0.02) * 1000) / 1000);
        box.style.setProperty("--fit", String(scale));
      }
      results.push({
        slide: Number(box.closest(".slide").dataset.slide),
        field: box.dataset.field || null,
        fit: scale,
        overflow: overflows(box),
        rect: relRect(box, box.getBoundingClientRect()),
      });
    }
    return results;
  }

  function relRect(el, r) {
    const s = el.closest(".slide").getBoundingClientRect();
    return { x: r.left - s.left, y: r.top - s.top, w: r.width, h: r.height };
  }

  function familyAvailable(family) {
    const ctx = document.createElement("canvas").getContext("2d");
    const sample = "mmmmmmmmmmlliWWQ@#0123456789";
    const quoted = '"' + family.replace(/"/g, '\\"') + '"';
    for (const base of ["monospace", "serif", "sans-serif"]) {
      ctx.font = `72px ${base}`;
      const without = ctx.measureText(sample).width;
      ctx.font = `72px ${quoted}, ${base}`;
      if (ctx.measureText(sample).width !== without) return true;
    }
    return false;
  }

  function lines(el) {
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    const range = document.createRange();
    const rows = [];
    let node;
    while ((node = walker.nextNode())) {
      const word = /\S+/g;
      let m;
      while ((m = word.exec(node.data))) {
        range.setStart(node, m.index);
        range.setEnd(node, m.index + m[0].length);
        const rects = range.getClientRects();
        if (!rects.length) continue;
        const top = rects[0].top;
        const last = rows[rows.length - 1];
        if (last && Math.abs(last.top - top) < rects[0].height * 0.5) last.words.push(m[0]);
        else rows.push({ top, words: [m[0]] });
      }
    }
    return rows.map((r) => r.words);
  }

  function describe(el, kind) {
    const cs = getComputedStyle(el);
    const entry = {
      kind,
      role: el.dataset.qaRole || null,
      field: el.dataset.field || null,
      rect: relRect(el, el.getBoundingClientRect()),
      rects: [...el.getClientRects()].map((r) => relRect(el, r)).filter((r) => r.w > 0 && r.h > 0),
      text: (el.innerText || "").trim().slice(0, 80),
    };
    if (kind === "text") {
      Object.assign(entry, {
        color: cs.color,
        fontSize: parseFloat(cs.fontSize),
        fontWeight: parseInt(cs.fontWeight, 10),
        fontStyle: cs.fontStyle,
        fontFamily: cs.fontFamily,
        overflowX: cs.display !== "inline" && el.scrollWidth > el.clientWidth + 1,
      });
    } else {
      Object.assign(entry, {
        loaded: el.complete && el.naturalWidth > 0,
        naturalWidth: el.naturalWidth,
        naturalHeight: el.naturalHeight,
        objectFit: cs.objectFit,
      });
    }
    return entry;
  }

  function collect(families) {
    const fonts = {};
    for (const family of families) fonts[family] = familyAvailable(family);
    const faceErrors = [];
    document.fonts.forEach((f) => {
      if (f.status === "error") faceErrors.push(f.family.replace(/"/g, ""));
    });

    const slides = [];
    for (const slide of document.querySelectorAll(".slide")) {
      const elements = [];
      for (const el of slide.querySelectorAll("[data-qa]")) {
        const kind = el.dataset.qa;
        const entry = describe(el, kind);
        if (kind === "text") {
          if (entry.role === "headline") entry.lines = lines(el);
          // Highlighted words get their own colour, so they need their own contrast check.
          entry.inline = [...el.querySelectorAll("strong, em, .hl")]
            .filter((c) => getComputedStyle(c).color !== entry.color)
            .map((c) => {
              const cs = getComputedStyle(c);
              return {
                color: cs.color,
                fontSize: parseFloat(cs.fontSize),
                fontWeight: parseInt(cs.fontWeight, 10),
                text: c.innerText.trim().slice(0, 40),
                rects: [...c.getClientRects()].map((r) => relRect(c, r)).filter((r) => r.w > 0 && r.h > 0),
              };
            });
        }
        elements.push(entry);
      }
      slides.push({ index: Number(slide.dataset.slide), elements });
    }
    return { fonts, faceErrors, slides };
  }

  function hideText(hidden) {
    let tag = document.getElementById("__qa_hide_text");
    if (hidden && !tag) {
      tag = document.createElement("style");
      tag.id = "__qa_hide_text";
      tag.textContent =
        '[data-qa="text"], [data-qa="text"] * { color: transparent !important; text-shadow: none !important;' +
        " -webkit-text-stroke: 0 !important; text-decoration-color: transparent !important; caret-color: transparent !important; }";
      document.head.appendChild(tag);
    } else if (!hidden && tag) {
      tag.remove();
    }
  }

  return { fit, collect, hideText };
})();
