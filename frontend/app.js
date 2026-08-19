const LANGS = {
  en: { label: "English", color: "#6ea8fe" },
  ko: { label: "Korean", color: "#ff4b4b" },
  zh: { label: "Chinese", color: "#e0b84f" },
};

const MARKET_LABELS = {
  ebay: "eBay",
  ebay_au: "eBay Australia",
  ebay_us: "eBay United States",
  bunjang_kr: "Bunjang KR",
  bunjang_global: "Bunjang Global",
  karrot: "Karrot",
  xianyu: "Xianyu",
  taobao: "Taobao",
  dewu: "Dewu",
  zhuanzhuan: "Zhuanzhuan",
  jd: "JD.com",
  weidian: "Weidian",
};

const state = {
  sku: "signature",
  days: 14,
  marketplaces: "ALL",
  showMsrp: true,
  priceChart: null,
  volumeChart: null,
  series: null,
  selectedDay: null,
};

function $(id) {
  return document.getElementById(id);
}

let mode = "live";
let snapshot = null;

function isEbayFilter() {
  return state.marketplaces === "ebay";
}

function filterRows(rows) {
  if (!rows || state.marketplaces === "ALL") return rows || [];
  const wanted = new Set(
    isEbayFilter() ? ["ebay", "ebay_au", "ebay_us"] : state.marketplaces.split(",")
  );
  return rows.filter((row) => wanted.has(row.marketplace));
}

async function detectMode() {
  try {
    const res = await fetch("/api/health", { cache: "no-store" });
    if (res.ok) {
      mode = "live";
      return;
    }
  } catch {
    /* public static host */
  }
  mode = "static";
  const res = await fetch("data/snapshot.json", { cache: "no-store" });
  snapshot = await res.json();
  $("collectBtn").hidden = true;
  $("collectStatus").textContent = "Public site · collectors run every hour";
  if ($("runMeta") && snapshot.generated_at) {
    $("runMeta").textContent =
      "Data refreshes every hour. Last snapshot " + snapshot.generated_at.replace("T", " ").replace("Z", " UTC");
  }
}

document.querySelectorAll("#skuPills .pill").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("#skuPills .pill").forEach((b) => b.classList.remove("on"));
    btn.classList.add("on");
    state.sku = btn.dataset.sku;
    load();
  });
});

document.querySelectorAll("#rangePills .pill").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("#rangePills .pill").forEach((b) => b.classList.remove("on"));
    btn.classList.add("on");
    state.days = Number(btn.dataset.days);
    load();
  });
});

document.querySelectorAll("#marketPills .pill").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("#marketPills .pill").forEach((b) => b.classList.remove("on"));
    btn.classList.add("on");
    state.marketplaces = btn.dataset.mp;
    load();
  });
});

$("msrpToggle").addEventListener("change", (e) => {
  state.showMsrp = e.target.checked;
  if (state.series) renderCharts(state.series);
});

$("collectBtn").addEventListener("click", async () => {
  $("collectStatus").textContent = "Collecting… live marketplaces may time out or block.";
  try {
    const res = await fetch("/api/collect", { method: "POST" });
    const data = await res.json();
    const summary = (data.reports || [])
      .map((r) => `${r.marketplace}: ${r.status} (${r.kept})`)
      .join(" · ");
    $("collectStatus").textContent = summary || "Done";
    await load();
  } catch (err) {
    $("collectStatus").textContent = String(err);
  }
});

async function load() {
  try {
    let raw;
    if (mode === "static") {
      raw = snapshot?.series?.[state.sku]?.[String(state.days)]?.[state.marketplaces];
      if (!raw) throw new Error("No snapshot for this view yet.");
    } else {
      const params = new URLSearchParams({
        sku: state.sku,
        days: String(state.days),
        marketplaces: state.marketplaces,
      });
      const res = await fetch(`/api/series?${params}`);
      if (!res.ok) throw new Error(`Series ${res.status}`);
      raw = await res.json();
    }
    const data = trimEmptyDates(raw);
    state.series = data;
    renderStats(data);
    renderCharts(data);
    const last = [...data.dates].reverse().find((d, i) => {
      const idx = data.dates.length - 1 - i;
      return hasPoint(data, idx);
    });
    if (last) selectDay(last);
    await loadMarkets();
  } catch (err) {
    $("collectStatus").textContent = String(err);
    if (!state.series) throw err;
  }
}

function hasPoint(data, idx) {
  return ["en", "ko", "zh"].some(
    (lang) =>
      data.languages[lang].median[idx] != null ||
      (data.languages[lang].volume[idx] || 0) > 0 ||
      (data.languages[lang].sold_volume?.[idx] || 0) > 0
  );
}

function trimEmptyDates(data) {
  let start = 0;
  while (start < data.dates.length && !hasPoint(data, start)) start += 1;
  let end = data.dates.length - 1;
  while (end > start && !hasPoint(data, end)) end -= 1;
  const cut = (arr) => arr.slice(start, end + 1);
  const languages = {};
  for (const lang of ["en", "ko", "zh"]) {
    languages[lang] = {
      median: cut(data.languages[lang].median),
      high: cut(data.languages[lang].high),
      low: cut(data.languages[lang].low),
      volume: cut(data.languages[lang].volume),
      sold_volume: cut(data.languages[lang].sold_volume || []),
    };
  }
  return { ...data, dates: cut(data.dates), languages };
}

function shortDate(iso) {
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const [, month, day] = iso.split("-");
  return `${Number(day)} ${months[Number(month) - 1]}`;
}

function renderStats(data) {
  $("statCards").innerHTML = ["en", "ko", "zh"]
    .map((lang) => {
      const cheap = data.cheapest?.[lang];
      const price = cheap?.price_aud ?? findLast(data.languages[lang].median);
      const msrp = data.msrp?.[lang] || data.msrp_usd?.[lang];
      const msrpAud = msrp?.aud;
      const delta = price && msrpAud ? (((price - msrpAud) / msrpAud) * 100).toFixed(1) : "—";
      const native = msrp
        ? `${msrp.native.toLocaleString()} ${msrp.currency}`
        : "";
      const where = cheap
        ? `${MARKET_LABELS[cheap.marketplace] || cheap.marketplace} · ${Number(cheap.price_native).toLocaleString()} ${cheap.currency}`
        : "No kept ask yet";
      return `<article class="card">
        <div class="lang" style="color:${LANGS[lang].color}">${LANGS[lang].label} edition</div>
        <div class="price">${fmtAud(price)}</div>
        <div class="vs">Cheapest ${escapeHtml(where)}</div>
        <div class="vs">vs MSRP ${native} (${delta}% in AUD)</div>
      </article>`;
    })
    .join("");
}

function findLast(arr) {
  for (let i = arr.length - 1; i >= 0; i -= 1) {
    if (arr[i] != null) return arr[i];
  }
  return null;
}

function priceBounds(data) {
  const vals = [];
  const candles = buildCandles(data);
  for (const series of candles) {
    for (const c of series) {
      if (!c) continue;
      vals.push(c.h, c.l, c.o, c.c);
    }
  }
  for (const lang of ["en", "ko", "zh"]) {
    if (state.showMsrp && data.msrp?.[lang]?.aud) vals.push(data.msrp[lang].aud);
    else if (state.showMsrp && data.msrp_usd?.[lang]?.aud) vals.push(data.msrp_usd[lang].aud);
  }
  if (!vals.length) return { min: 0, max: 100 };
  const lo = Math.min(...vals);
  const hi = Math.max(...vals);
  const pad = Math.max((hi - lo) * 0.12, 40);
  return { min: Math.max(0, Math.floor(lo - pad)), max: Math.ceil(hi + pad) };
}

function axisStyle() {
  return {
    ticks: { color: "#9a9386", font: { family: "IBM Plex Sans", size: 12 } },
    grid: { color: "#2a2e38" },
  };
}

function onChartClick(data) {
  return (_evt, _elts, chart) => {
    const hit = chart.getElementsAtEventForMode(_evt, "index", { intersect: false }, true)[0];
    const index = hit ? hit.index : chart.tooltip?.dataPoints?.[0]?.dataIndex;
    if (index != null) selectDay(data.dates[index]);
  };
}

function prevMedian(row, idx) {
  for (let i = idx - 1; i >= 0; i -= 1) {
    if (row.median[i] != null) return row.median[i];
  }
  return row.median[idx];
}

function buildCandles(data) {
  return ["en", "ko", "zh"].map((lang) => {
    const row = data.languages[lang];
    return data.dates.map((_, i) => {
      const close = row.median[i];
      const open = prevMedian(row, i);
      if (close == null && row.high[i] == null && row.low[i] == null) return null;
      const c = close ?? open;
      const o = open ?? c;
      if (o == null || c == null) return null;
      const high = row.high[i] != null ? row.high[i] : Math.max(o, c);
      const low = row.low[i] != null ? row.low[i] : Math.min(o, c);
      return {
        o,
        c,
        h: Math.max(high, o, c),
        l: Math.min(low, o, c),
        up: c >= o,
      };
    });
  });
}

const editionCandles = {
  id: "editionCandles",
  afterDatasetsDraw(chart) {
    const series = chart.options.plugins.editionCandles?.candles;
    if (!series) return;
    const xScale = chart.scales.x;
    const yScale = chart.scales.y;
    const { ctx } = chart;
    const langs = ["en", "ko", "zh"];
    const slot = Math.abs(xScale.getPixelForValue(1) - xScale.getPixelForValue(0)) || 48;
    const groupW = Math.min(72, slot * 0.78);
    const step = groupW / langs.length;
    const bodyW = Math.max(7, step * 0.62);

    ctx.save();
    series.forEach((candles, li) => {
      const color = LANGS[langs[li]].color;
      candles.forEach((candle, i) => {
        if (!candle) return;
        const cx = xScale.getPixelForValue(i) + (li - 1) * step;
        const yH = yScale.getPixelForValue(candle.h);
        const yL = yScale.getPixelForValue(candle.l);
        const yO = yScale.getPixelForValue(candle.o);
        const yC = yScale.getPixelForValue(candle.c);
        const top = Math.min(yO, yC);
        const bot = Math.max(yO, yC);

        ctx.strokeStyle = color;
        ctx.lineWidth = 1.6;
        ctx.beginPath();
        ctx.moveTo(cx, yH);
        ctx.lineTo(cx, yL);
        ctx.stroke();

        ctx.beginPath();
        ctx.rect(cx - bodyW / 2, top, bodyW, Math.max(2, bot - top));
        ctx.fillStyle = candle.up ? color : "#0c0d10";
        ctx.fill();
        ctx.stroke();
      });
    });
    ctx.restore();
  },
};

function renderCharts(data) {
  const labels = data.dates.map(shortDate);
  const bounds = priceBounds(data);
  const candles = buildCandles(data);
  const priceSets = [];
  const volumeSets = [];

  ["en", "ko", "zh"].forEach((lang, li) => {
    volumeSets.push({
      type: "bar",
      label: `${LANGS[lang].label} listings`,
      data: data.languages[lang].volume,
      backgroundColor: hex(LANGS[lang].color, 0.82),
      borderColor: LANGS[lang].color,
      borderWidth: 1,
      borderRadius: 4,
      borderSkipped: false,
    });
    volumeSets.push({
      type: "bar",
      label: `${LANGS[lang].label} sales`,
      data: data.languages[lang].sold_volume || [],
      backgroundColor: hex(LANGS[lang].color, 0.28),
      borderColor: LANGS[lang].color,
      borderWidth: 1.5,
      borderRadius: 4,
      borderSkipped: false,
    });
    priceSets.push({
      type: "line",
      label: LANGS[lang].label,
      data: candles[li].map((c) => (c ? c.c : null)),
      borderColor: LANGS[lang].color,
      backgroundColor: LANGS[lang].color,
      showLine: false,
      borderWidth: 2,
      pointRadius: 0,
      pointHoverRadius: 0,
      spanGaps: true,
    });
    if (state.showMsrp && data.msrp?.[lang]?.aud) {
      priceSets.push({
        type: "line",
        label: `${LANGS[lang].label} MSRP`,
        data: data.dates.map(() => data.msrp[lang].aud),
        borderColor: hex(LANGS[lang].color, 0.55),
        borderDash: [6, 5],
        pointRadius: 0,
        borderWidth: 1.5,
      });
    }
  });

  if (state.priceChart) state.priceChart.destroy();
  if (state.volumeChart) state.volumeChart.destroy();

  state.priceChart = new Chart($("priceChart"), {
    data: { labels, datasets: priceSets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: {
          labels: {
            color: "#ece7dc",
            boxWidth: 14,
            padding: 16,
            filter: (item) => !String(item.text || "").includes("MSRP"),
          },
        },
        tooltip: {
          filter: (item) => !String(item.dataset.label || "").includes("MSRP"),
          callbacks: {
            title: (items) => data.dates[items[0]?.dataIndex] || "",
            label(item) {
              const lang = ["en", "ko", "zh"].find((key) => LANGS[key].label === item.dataset.label);
              if (!lang) return "";
              const li = ["en", "ko", "zh"].indexOf(lang);
              const candle = candles[li][item.dataIndex];
              if (!candle) return `${item.dataset.label}: —`;
              const dir = candle.up ? "up" : "down";
              return `${item.dataset.label} ${dir}  O ${fmt(candle.o)}  H ${fmt(candle.h)}  L ${fmt(candle.l)}  C ${fmt(candle.c)}`;
            },
          },
        },
        editionCandles: { candles },
      },
      scales: {
        x: { ...axisStyle(), offset: true },
        y: {
          ...axisStyle(),
          min: bounds.min,
          max: bounds.max,
          title: { display: true, text: "AUD", color: "#9a9386" },
          ticks: { ...axisStyle().ticks, callback: (v) => "A$" + v },
        },
      },
      onClick: onChartClick(data),
    },
    plugins: [editionCandles],
  });

  const volMax = Math.max(
    4,
    ...["en", "ko", "zh"].flatMap((lang) => [
      ...(data.languages[lang].volume || []),
      ...(data.languages[lang].sold_volume || []),
    ])
  );

  state.volumeChart = new Chart($("volumeChart"), {
    type: "bar",
    data: { labels, datasets: volumeSets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { labels: { color: "#ece7dc", boxWidth: 14, padding: 16 } },
        tooltip: {
          filter: (item) => Number(item.raw) > 0,
          callbacks: {
            title: (items) => data.dates[items[0]?.dataIndex] || "",
            label(item) {
              const kind = String(item.dataset.label || "").toLowerCase().includes("sales")
                ? "sale"
                : "listing";
              return `${item.dataset.label}: ${item.raw} ${kind}${item.raw === 1 ? "" : "s"}`;
            },
          },
        },
      },
      datasets: {
        bar: { categoryPercentage: 0.72, barPercentage: 0.88 },
      },
      scales: {
        x: { stacked: false, offset: true, ...axisStyle() },
        y: {
          stacked: false,
          beginAtZero: true,
          max: volMax + 1,
          ticks: { ...axisStyle().ticks, stepSize: 1 },
          grid: { color: "#2a2e38" },
          title: { display: true, text: "Listings / sales", color: "#9a9386" },
        },
      },
      onClick: onChartClick(data),
    },
    plugins: [volumeValueLabels],
  });
}

const volumeValueLabels = {
  id: "volumeValueLabels",
  afterDatasetsDraw(chart) {
    const { ctx } = chart;
    ctx.save();
    ctx.font = "600 11px IBM Plex Mono, monospace";
    ctx.textAlign = "center";
    ctx.textBaseline = "bottom";
    chart.data.datasets.forEach((dataset, i) => {
      const meta = chart.getDatasetMeta(i);
      meta.data.forEach((bar, idx) => {
        const value = dataset.data[idx];
        if (!value) return;
        ctx.fillStyle = "#ece7dc";
        ctx.fillText(String(value), bar.x, bar.y - 4);
      });
    });
    ctx.restore();
  },
};

function hex(color, alpha) {
  const n = color.replace("#", "");
  const r = parseInt(n.slice(0, 2), 16);
  const g = parseInt(n.slice(2, 4), 16);
  const b = parseInt(n.slice(4, 6), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}

function fmt(n) {
  return fmtAud(n);
}

function fmtAud(n) {
  return n == null || Number.isNaN(Number(n)) ? "—" : "A$" + Number(n).toFixed(0);
}

function offerUrl(url, fallback) {
  if (!url || url.includes("example.local")) return fallback;
  return url;
}

async function loadMarkets() {
  let data;
  if (mode === "static") {
    data = snapshot?.markets?.[state.sku] || { markets: [] };
  } else {
    const res = await fetch(`/api/markets?sku=${encodeURIComponent(state.sku)}`);
    data = await res.json();
  }
  const note = $("marketNote");
  const next = data.next_run ? ` Next collect ${data.next_run}.` : "";
  note.textContent =
    (mode === "static"
      ? "Search links plus the cheapest kept ask in AUD. This public snapshot refreshes every hour."
      : "Search links plus the cheapest kept ask in AUD. Collectors and this list refresh every hour while the server is running.") +
    next;
  const withAsk = (data.markets || []).filter((market) => market.cheapest);
  $("marketCards").innerHTML = withAsk
    .map((market) => {
      const cheap = market.cheapest;
      const href = offerUrl(cheap.url, market.search_url);
      return `<article class="card market-card">
        <h3>${escapeHtml(market.label)}</h3>
        <div class="links">
          <a href="${market.search_url}" target="_blank" rel="noreferrer">Open marketplace</a>
          <a href="${href}" target="_blank" rel="noreferrer">Cheapest offer</a>
        </div>
        <div class="cheap">${fmtAud(cheap.price_aud)}</div>
        <div class="native">${Number(cheap.price_native).toLocaleString()} ${cheap.currency} · ${escapeHtml(cheap.title)}</div>
      </article>`;
    })
    .join("") || `<p class="muted">No kept asks yet. Use Marketplace searches below.</p>`;
  renderSearchLinks(data.searches);
}

async function selectDay(day) {
  state.selectedDay = day;
  $("selectedDay").textContent = day;
  let rows;
  if (mode === "static") {
    rows = filterRows(snapshot?.listings?.[state.sku]?.[day] || []);
  } else {
    const params = new URLSearchParams({
      day,
      sku: state.sku,
      marketplaces: state.marketplaces,
    });
    const res = await fetch(`/api/listings?${params}`);
    rows = await res.json();
  }
  const body = $("listingBody");
  if (!rows.length) {
    body.innerHTML = `<tr><td colspan="6" class="muted">No kept listings for this date.</td></tr>`;
    return;
  }
  body.innerHTML = rows
    .map((row) => {
      const langClass = `lang-${row.language}`;
      const title = row.source === "seed"
        ? `${row.title} <span class="muted">(seed)</span>`
        : `<a href="${row.url}" target="_blank" rel="noreferrer">${escapeHtml(row.title)}</a>`;
      return `<tr>
        <td class="${langClass}">${(row.language || "").toUpperCase()}</td>
        <td>${row.marketplace}</td>
        <td>${title}</td>
        <td>${Number(row.price_native).toLocaleString()} ${row.currency}</td>
        <td>${fmtAud(row.price_aud ?? row.price_usd)}</td>
        <td>${row.listing_type}</td>
      </tr>`;
    })
    .join("");
}

function renderSearchLinks(sites) {
  const root = $("searchLinks");
  if (!root) return;
  if (!sites || !sites.length) {
    root.innerHTML = `<p class="muted">No search links yet.</p>`;
    return;
  }
  root.innerHTML = sites
    .map((site) => {
      const chips = (site.queries || [])
        .map((query) => {
          const label = query.site ? `${query.term} · ${query.site}` : query.term;
          return `<a class="search-chip" href="${query.url}" target="_blank" rel="noreferrer">${escapeHtml(label)}</a>`;
        })
        .join("");
      return `<article class="card search-card">
        <h3>${escapeHtml(site.label)}</h3>
        <div class="search-chips">${chips}</div>
      </article>`;
    })
    .join("");
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[ch]);
}

detectMode()
  .then(() => load())
  .catch((err) => {
    $("collectStatus").textContent = String(err);
  });

setInterval(() => {
  load().catch(() => {});
}, 60 * 60 * 1000);
