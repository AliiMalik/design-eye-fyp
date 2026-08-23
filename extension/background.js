/**
 * Capture and upload. Lives in the service worker because chrome.tabs.captureVisibleTab
 * is not available to a content script, and because the popup closes the moment
 * focus moves — anything that must survive that has to run here.
 */

const DEFAULT_API = "http://localhost:8000/api/v1";

// captureVisibleTab is rate limited by Chrome. Full-page capture takes one shot
// per scroll position, so the gap below is the difference between a clean
// stitch and a MAX_CAPTURE_VISIBLE_TAB_CALLS_PER_SECOND failure part way down.
const CAPTURE_GAP_MS = 260;
const MAX_SLICES = 12;

async function getSettings() {
  const { apiBase, token } = await chrome.storage.local.get(["apiBase", "token"]);
  return { apiBase: apiBase || DEFAULT_API, token };
}

async function captureViewport(windowId) {
  return chrome.tabs.captureVisibleTab(windowId, { format: "png" });
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** Page geometry, read from the page itself. */
async function pageMetrics(tabId) {
  const [{ result }] = await chrome.scripting.executeScript({
    target: { tabId },
    func: () => ({
      full: Math.max(
        document.body.scrollHeight,
        document.documentElement.scrollHeight,
      ),
      view: window.innerHeight,
      width: window.innerWidth,
      dpr: window.devicePixelRatio || 1,
      startY: window.scrollY,
    }),
  });
  return result;
}

async function scrollTo(tabId, y) {
  await chrome.scripting.executeScript({
    target: { tabId },
    args: [y],
    func: (top) => window.scrollTo({ top, behavior: "instant" }),
  });
}

/**
 * Scroll the page, capture each screenful, and stitch them into one tall PNG.
 *
 * The result is deliberately the whole page rather than the fold: DesignEye
 * scores a long page one screenful at a time, so the extra height is analysed
 * properly rather than squashed.
 */
async function captureFullPage(tab) {
  const m = await pageMetrics(tab.id);
  const slices = Math.min(MAX_SLICES, Math.max(1, Math.ceil(m.full / m.view)));
  if (slices === 1) return { dataUrl: await captureViewport(tab.windowId), slices: 1 };

  const shots = [];
  for (let i = 0; i < slices; i += 1) {
    await scrollTo(tab.id, i * m.view);
    await sleep(CAPTURE_GAP_MS);
    shots.push(await captureViewport(tab.windowId));
  }
  await scrollTo(tab.id, m.startY);

  const bitmaps = await Promise.all(
    shots.map(async (d) => createImageBitmap(await (await fetch(d)).blob())),
  );
  const width = bitmaps[0].width;
  const sliceH = bitmaps[0].height;
  // The last screenful overlaps the one above it whenever the page does not
  // divide evenly, so it is drawn from its own bottom edge instead of stacked.
  const scale = sliceH / m.view;
  const totalH = Math.min(Math.round(m.full * scale), sliceH * slices);

  const canvas = new OffscreenCanvas(width, totalH);
  const ctx = canvas.getContext("2d");
  bitmaps.forEach((bmp, i) => {
    const y = i === slices - 1 ? totalH - sliceH : Math.round(i * m.view * scale);
    ctx.drawImage(bmp, 0, y);
  });

  const blob = await canvas.convertToBlob({ type: "image/png" });
  const dataUrl = await new Promise((resolve) => {
    const fr = new FileReader();
    fr.onloadend = () => resolve(fr.result);
    fr.readAsDataURL(blob);
  });
  return { dataUrl, slices };
}

async function apiFetch(path, options = {}) {
  const { apiBase, token } = await getSettings();
  const headers = { ...(options.headers || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${apiBase}${path}`, { ...options, headers });
  if (res.status === 401) throw new Error("SESSION_EXPIRED");
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch { /* keep the generic message */ }
    throw new Error(detail);
  }
  return res.json();
}

async function analyse({ fullPage }) {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab) throw new Error("No active tab.");
  if (/^(chrome|edge|about|chrome-extension):/i.test(tab.url || "")) {
    throw new Error("Chrome blocks capture on browser pages. Open a website first.");
  }

  const { dataUrl, slices } = fullPage
    ? await captureFullPage(tab)
    : { dataUrl: await captureViewport(tab.windowId), slices: 1 };

  const blob = await (await fetch(dataUrl)).blob();
  const form = new FormData();
  const name = (tab.title || "page").replace(/[^\w\- ]+/g, "").slice(0, 60) || "page";
  form.append("file", blob, `${name}.png`);

  const started = await apiFetch("/upload", { method: "POST", body: form });

  // Poll rather than hold the popup open: the popup may already be gone.
  for (let i = 0; i < 90; i += 1) {
    const status = await apiFetch(`/status/${started.task_id}`);
    if (status.status === "complete") {
      const result = await apiFetch(`/results/${started.asset_id}`);
      return { result, slices, title: tab.title, url: tab.url };
    }
    if (status.status === "failed") throw new Error(status.error || "Analysis failed.");
    await sleep(1000);
  }
  throw new Error("Analysis is taking longer than expected.");
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  const run = async () => {
    switch (msg.type) {
      case "ANALYSE":
        return { ok: true, data: await analyse({ fullPage: msg.fullPage }) };
      case "LOGIN": {
        const { apiBase } = await getSettings();
        const res = await fetch(`${apiBase}/auth/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email: msg.email, password: msg.password }),
        });
        if (!res.ok) throw new Error("Those details did not work.");
        const body = await res.json();
        await chrome.storage.local.set({ token: body.access_token, user: body.user });
        return { ok: true, data: body.user };
      }
      case "LOGOUT":
        await chrome.storage.local.remove(["token", "user"]);
        return { ok: true };
      default:
        throw new Error(`Unknown message: ${msg.type}`);
    }
  };

  run()
    .then(sendResponse)
    .catch((err) => sendResponse({ ok: false, error: err.message || String(err) }));
  return true; // keep the channel open for the async reply
});
