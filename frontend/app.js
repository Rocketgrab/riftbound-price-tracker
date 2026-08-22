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
  listingLang: "en",
  priceCharts: [],
  volumeChart: null,
  series: null,
  selectedDay: null,
  crossIndex: null,
};

function $(id) {
  return document.getElementById(id);
}

let mode = "live";
let snapshot = null;
let loadGen = 0;
let listingGen = 0;

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
  if (!res.ok) throw new Error(`Snapshot ${res.status}`);
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

document.querySelectorAll("#listingLangPills .pill").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("#listingLangPills .pill").forEach((b) => b.classList.remove("on"));
    btn.classList.add("on");
    state.listingLang = btn.dataset.lang;
    if (state.selectedDay) selectDay(state.selectedDay);
  });
});

$("msrpToggle").addEventListener("change", (e) => {
  state.showMsrp = e.target.checked;
  if (state.series) renderCharts(state.series);
});

$("collectBtn").addEventListener("click", async () => {
  const btn = $("collectBtn");
  btn.disabled = true;
  $("collectStatus").textContent = "Collecting… live marketplaces may time out or block.";
  try {
    const res = await fetch("/api/collect", { method: "POST" });
    if (res.status === 409) {
      $("collectStatus").textContent = "Collectors already running.";
      return;
    }
    const data = await res.json();
    const summary = (data.reports || [])
      .map((r) => `${r.marketplace}: ${r.status} (${r.kept})`)
      .join(" · ");
    $("collectStatus").textContent = summary || "Done";
    await load();
  } catch (err) {
    $("collectStatus").textContent = String(err);
  } finally {
    btn.disabled = false;
  }
});

async function load() {
  const gen = ++loadGen;
  try {
    let raw;
    if (mode === "static") {
      const snapRes = await fetch("data/snapshot.json", { cache: "no-store" });
      if (!snapRes.ok) throw new Error(`Snapshot ${snapRes.status}`);
      snapshot = await snapRes.json();
      raw = snapshot?.series?.[state.sku]?.[String(state.days)]?.[state.marketplaces];
      if (!raw) throw new Error("No snapshot for this view yet.");
      if ($("runMeta") && snapshot.generated_at) {
        $("runMeta").textContent =
          "Data refreshes every hour. Last snapshot " + snapshot.generated_at.replace("T", " ").replace("Z", " UTC");
      }
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
    if (gen !== loadGen) return;
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
    if (gen !== loadGen) return;
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

function soldHeadlineKey(lang) {
  return `riftboundSoldHeadline:${state.sku}:${lang}`;
}

function rememberSold(lang, sold) {
  try {
    if (sold && sold.price_aud != null) {
      localStorage.setItem(soldHeadlineKey(lang), JSON.stringify(sold));
    }
  } catch {
    /* ignore private-mode storage */
  }
}

function lastPrintedSold(lang) {
  try {
    const raw = localStorage.getItem(soldHeadlineKey(lang));
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed?.price_aud != null ? { ...parsed, carried: true } : null;
  } catch {
    return null;
  }
}

function renderStats(data) {
  $("statCards").innerHTML = ["en", "ko", "zh"]
    .map((lang) => {
      let sold = data.sold_24h?.[lang];
      if (!sold) sold = lastPrintedSold(lang);
      else if (sold.kind !== "ask" && sold.source !== "seed") rememberSold(lang, sold);
      const price = sold?.price_aud ?? null;
      const msrp = data.msrp?.[lang] || data.msrp_usd?.[lang];
      const msrpAud = msrp?.aud;
      const delta = price && msrpAud ? (((price - msrpAud) / msrpAud) * 100).toFixed(1) : null;
      const native = msrp
        ? `${msrp.native.toLocaleString()} ${msrp.currency}`
        : "";
      const count = sold?.sample_count || 0;
      const sales = count === 1 ? "1 sale" : `${count} sales`;
      const listings = count === 1 ? "1 listing" : `${count} listings`;
      let where = "No sales recorded yet";
      if (sold?.kind === "ask") {
        where = `Median ask · ${sold.as_of || "today"} · ${listings}`;
      } else if (sold?.carried) {
        where = `Last printed median · ${sales}`;
      } else if (sold && !sold.stale && sold.window_hours === 24) {
        where = `Median sold · last 24h · ${sales}`;
      } else if (sold?.as_of) {
        where = `Last sold median · ${sold.as_of} · ${sales}`;
      } else if (sold) {
        where = `Last sold median · ${sales}`;
      }
      const vs = native
        ? (delta == null ? `vs MSRP ${native}` : `vs MSRP ${native} (${delta}% in AUD)`)
        : "";
      return `<article class="card">
        <div class="lang" style="color:${LANGS[lang].color}">${LANGS[lang].label} edition</div>
        <div class="price">${fmtAud(price)}</div>
        <div class="vs">${escapeHtml(where)}</div>
        <div class="vs">${vs}</div>
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

function priceBoundsFor(data, lang) {
  const vals = [];
  const li = ["en", "ko", "zh"].indexOf(lang);
  for (const c of buildCandles(data)[li] || []) {
    if (!c) continue;
    vals.push(c.h, c.l, c.o, c.c);
  }
  if (state.showMsrp && data.msrp?.[lang]?.aud) vals.push(data.msrp[lang].aud);
  else if (state.showMsrp && data.msrp_usd?.[lang]?.aud) vals.push(data.msrp_usd[lang].aud);
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

function xAxis(data) {
  const dense = (data?.dates || []).length > 21;
  return {
    ...axisStyle(),
    offset: true,
    ticks: {
      ...axisStyle().ticks,
      autoSkip: dense,
      maxRotation: dense ? 45 : 0,
      minRotation: 0,
    },
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
    let last = null;
    return data.dates.map((_, i) => {
      const close = row.median[i];
      const open = prevMedian(row, i);
      let candle = null;
      if (close == null && row.high[i] == null && row.low[i] == null) {
        if (last) {
          candle = { o: last.c, c: last.c, h: last.c, l: last.c, up: true };
        }
      } else {
        const c = close ?? open ?? last?.c;
        const o = open ?? c;
        if (o != null && c != null) {
          const high = row.high[i] != null ? row.high[i] : Math.max(o, c);
          const low = row.low[i] != null ? row.low[i] : Math.min(o, c);
          candle = {
            o,
            c,
            h: Math.max(high, o, c),
            l: Math.min(low, o, c),
            up: c >= o,
          };
        }
      }
      if (candle) last = candle;
      return candle;
    });
  });
}

const editionCandles = {
  id: "editionCandles",
  afterDatasetsDraw(chart) {
    const series = chart.options.plugins.editionCandles?.candles;
    const langs = chart.options.plugins.editionCandles?.langs || ["en", "ko", "zh"];
    if (!series) return;
    const xScale = chart.scales.x;
    const yScale = chart.scales.y;
    const { ctx } = chart;
    const slot = Math.abs(xScale.getPixelForValue(1) - xScale.getPixelForValue(0)) || 48;
    const n = Math.max(series.length, 1);
    const groupW = Math.min(72, slot * 0.78);
    const step = n > 1 ? groupW / n : 0;
    const bodyW = n > 1 ? Math.max(7, step * 0.62) : Math.max(12, Math.min(36, slot * 0.42));

    ctx.save();
    series.forEach((candles, li) => {
      const color = LANGS[langs[li]].color;
      candles.forEach((candle, i) => {
        if (!candle) return;
        const cx = xScale.getPixelForValue(i) + (n > 1 ? (li - (n - 1) / 2) * step : 0);
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

const OHLC_IDS = { en: "ohlcEn", ko: "ohlcKo", zh: "ohlcZh" };

function indexFromEvent(chart, event) {
  const xScale = chart.scales.x;
  if (!xScale || event.x == null) return null;
  const value = xScale.getValueForPixel(event.x);
  if (value == null || Number.isNaN(Number(value))) return null;
  const max = (chart.data.labels || []).length - 1;
  if (max < 0) return null;
  return Math.max(0, Math.min(max, Math.round(value)));
}

function writeOhlc(lang, index, data, candle) {
  const el = $(OHLC_IDS[lang]);
  if (!el) return;
  const date = data.dates[index];
  if (!date) {
    el.textContent = "";
    return;
  }
  if (!candle) {
    el.textContent = `${shortDate(date)}  —`;
    return;
  }
  el.textContent = `${shortDate(date)}  O ${fmt(candle.o)}  H ${fmt(candle.h)}  L ${fmt(candle.l)}  C ${fmt(candle.c)}`;
}

function applyCrosshair(index, sourceChart, y) {
  state.crossIndex = index;
  const data = state.series;
  const candles = data ? buildCandles(data) : null;
  const charts = [...(state.priceCharts || []), state.volumeChart].filter(Boolean);
  charts.forEach((chart) => {
    chart.$crossIndex = index;
    chart.$crossY = chart === sourceChart ? y : null;
    if (chart !== sourceChart) chart.draw();
  });
  if (data && candles && index != null) {
    ["en", "ko", "zh"].forEach((lang, li) => writeOhlc(lang, index, data, candles[li][index]));
  }
}

const chartCrosshair = {
  id: "chartCrosshair",
  afterEvent(chart, args) {
    const event = args.event;
    if (!event) return;
    if (event.type === "mouseout") return;
    if (!["mousemove", "click", "touchstart", "touchmove"].includes(event.type)) return;
    if (event.x == null) return;
    const area = chart.chartArea;
    if (event.x < area.left || event.x > area.right) return;
    const index = indexFromEvent(chart, event);
    if (index == null) return;
    const y = event.y >= area.top && event.y <= area.bottom ? event.y : null;
    applyCrosshair(index, chart, y);
    if ((event.type === "click" || event.type === "touchstart") && state.series?.dates?.[index]) {
      selectDay(state.series.dates[index]);
    }
    args.changed = true;
  },
  afterDatasetsDraw(chart) {
    const index = chart.$crossIndex;
    if (index == null) return;
    const xScale = chart.scales.x;
    const area = chart.chartArea;
    const x = xScale.getPixelForValue(index);
    const { ctx } = chart;
    ctx.save();
    ctx.strokeStyle = "rgba(236, 231, 220, 0.38)";
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 3]);
    ctx.beginPath();
    ctx.moveTo(x, area.top);
    ctx.lineTo(x, area.bottom);
    ctx.stroke();
    if (chart.$crossY != null) {
      ctx.beginPath();
      ctx.moveTo(area.left, chart.$crossY);
      ctx.lineTo(area.right, chart.$crossY);
      ctx.stroke();
    }
    ctx.restore();
  },
};

function renderCharts(data) {
  if (typeof Chart === "undefined" || window.__chartLoadError) {
    $("collectStatus").textContent = "Chart library failed to load.";
    return;
  }
  const labels = data.dates.map(shortDate);
  const candles = buildCandles(data);
  const volumeSets = [];
  const canvasIds = { en: "priceChartEn", ko: "priceChartKo", zh: "priceChartZh" };

  ["en", "ko", "zh"].forEach((lang) => {
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
  });

  (state.priceCharts || []).forEach((chart) => chart.destroy());
  if (state.volumeChart) state.volumeChart.destroy();

  state.priceCharts = ["en", "ko", "zh"].map((lang, li) => {
    const bounds = priceBoundsFor(data, lang);
    const datasets = [
      {
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
      },
    ];
    if (state.showMsrp && data.msrp?.[lang]?.aud) {
      datasets.push({
        type: "line",
        label: `${LANGS[lang].label} MSRP`,
        data: data.dates.map(() => data.msrp[lang].aud),
        borderColor: hex(LANGS[lang].color, 0.55),
        borderDash: [6, 5],
        pointRadius: 0,
        borderWidth: 1.5,
      });
    }
    return new Chart($(canvasIds[lang]), {
      data: { labels, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        events: ["mousemove", "mouseout", "click", "touchstart", "touchmove", "touchend"],
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: { enabled: false },
          editionCandles: { candles: [candles[li]], langs: [lang] },
        },
        scales: {
          x: xAxis(data),
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
      plugins: [editionCandles, chartCrosshair],
    });
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
      events: ["mousemove", "mouseout", "click", "touchstart", "touchmove", "touchend"],
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { labels: { color: "#ece7dc", boxWidth: 14, padding: 16 } },
        tooltip: { enabled: false },
      },
      datasets: {
        bar: { categoryPercentage: 0.72, barPercentage: 0.88 },
      },
      scales: {
        x: { stacked: false, ...xAxis(data) },
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
    plugins: [volumeValueLabels, chartCrosshair],
  });

  const startIndex =
    state.selectedDay && data.dates.includes(state.selectedDay)
      ? data.dates.indexOf(state.selectedDay)
      : data.dates.length - 1;
  if (startIndex >= 0) applyCrosshair(startIndex, null, null);
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
  const gen = ++listingGen;
  state.selectedDay = day;
  $("selectedDay").textContent = day;
  const lang = state.listingLang;
  let rows;
  if (mode === "static") {
    const packed = snapshot?.listings?.[state.sku]?.[day];
    if (Array.isArray(packed)) {
      rows = filterRows(packed).filter((row) => (row.language || "") === lang);
    } else {
      rows = filterRows(packed?.[lang] || []);
    }
  } else {
    const params = new URLSearchParams({
      day,
      sku: state.sku,
      language: lang,
      marketplaces: state.marketplaces,
      limit: "100",
    });
    const res = await fetch(`/api/listings?${params}`);
    if (!res.ok) {
      if (gen !== listingGen) return;
      $("listingBody").innerHTML = `<tr><td colspan="5" class="muted">Could not load listings (${res.status}).</td></tr>`;
      return;
    }
    rows = await res.json();
  }
  if (gen !== listingGen) return;
  if (!Array.isArray(rows)) rows = [];
  rows = [...rows].sort(
    (a, b) => (a.price_aud ?? a.price_usd ?? 0) - (b.price_aud ?? b.price_usd ?? 0)
  );
  const body = $("listingBody");
  const label = LANGS[lang]?.label || lang.toUpperCase();
  if (!rows.length) {
    body.innerHTML = `<tr><td colspan="5" class="muted">No kept ${escapeHtml(label)} listings for this date.</td></tr>`;
    return;
  }
  body.innerHTML = rows
    .map((row) => {
      const title = row.source === "seed"
        ? `${escapeHtml(row.title)} <span class="muted">(seed)</span>`
        : `<a href="${safeUrl(row.url)}" target="_blank" rel="noreferrer">${escapeHtml(row.title)}</a>`;
      return `<tr>
        <td>${escapeHtml(row.marketplace)}</td>
        <td>${title}</td>
        <td>${Number(row.price_native).toLocaleString()} ${escapeHtml(row.currency)}</td>
        <td>${fmtAud(row.price_aud ?? row.price_usd)}</td>
        <td>${escapeHtml(row.listing_type)}</td>
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

function safeUrl(value) {
  try {
    const parsed = new URL(String(value), window.location.href);
    if (parsed.protocol === "http:" || parsed.protocol === "https:") return parsed.href;
  } catch {
    /* ignore */
  }
  return "#";
}

detectMode()
  .then(() => load())
  .catch((err) => {
    $("collectStatus").textContent = String(err);
  });

setInterval(() => {
  load().catch(() => {});
}, 60 * 60 * 1000);
