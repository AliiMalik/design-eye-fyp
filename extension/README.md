# DesignEye for Chrome

Analyse **any live web page** the way DesignEye analyses a mockup. Click the
toolbar icon, the extension captures the page, and the same SalGAN model returns
a Clarity Score and a heatmap.

The web app only accepts files you export. This works on anything you can open —
a competitor's site, a staging build, a page you have not exported yet.

---

## Install it

**Chrome will not install this automatically, and no amount of code changes
that.** Side-loading was removed in 2014 and inline install in 2018: an
extension downloaded from a website cannot install itself, in developer mode or
otherwise. The Web Store is the only one-click route.

So the site does the next best thing. Sign in and open **Chrome Extension** in
the sidebar:

1. **Download** — one button, gives you `designeye-extension.zip`. Unzip it
   somewhere permanent; Chrome loads the folder from where it sits.
2. **`chrome://extensions`** — turn on **Developer mode**, top right.
3. **Load unpacked** — pick the unzipped folder.

Then return to the page and press **Check again**. It detects the extension and
offers **Connect my account**, which hands over the session you already have in
the browser — so there is no second sign-in, and captures cannot end up under a
different account from the one you are browsing the app with.

That handshake is possible because the extension lists the site under
`externally_connectable` and its id is pinned by the `key` field in
`manifest.json`. Only those origins can message it.

Rebuild the archive after changing anything in this folder:

```bash
python scripts/build_extension.py
```

`extension/test/zip.test.mjs` fails if you forget, so the download cannot go
stale silently.

## Use it

1. Open any website.
2. Click the DesignEye icon.
3. **Create an account** right here the first time — no need to visit the web app
   first — or sign in if you already have one.
4. **Whole page** captures everything by scrolling; untick it for just the
   visible part.
5. Read the score, or open the full analysis in the web app.

### Where captures go

Everything lands in **your own account**, and captures are grouped into a
project named after the site: capture `dribbble.com` three times and all three
sit in one "dribbble.com" project. The popup names the project after each run,
so you know where to find it.

The signed-in account is shown in the popup header. That matters because the
extension keeps its own session, separate from the web app's — if the two are
signed in as different people, opening "full analysis" lands on a page telling
you the analysis belongs to another account.

## What it does under the hood

`chrome.tabs.captureVisibleTab` only ever returns the visible viewport, so a
whole-page capture scrolls the page, takes one shot per screenful, and stitches
them into a single tall PNG with `OffscreenCanvas`. That image is uploaded to
`POST /upload` exactly like any other mockup and polled through `/status`.

Two details are load-bearing:

- **Captures happen in the service worker, not the popup.** The popup closes the
  moment focus moves, which on a multi-second capture is most of the time.
- **Chrome rate-limits `captureVisibleTab`.** Shots are spaced ~260ms apart; go
  faster and a long page fails part way down with
  `MAX_CAPTURE_VISIBLE_TAB_CALLS_PER_SECOND`.

A stitched full-page capture is exactly the tall image DesignEye is built for:
it is scored one screenful at a time rather than squashed
(`docs/DEVIATIONS.md` §19), and tall frames are split into near-square bands so
the model's square input is not wasted (§21).

## Permissions, and why each is needed

| Permission | Why |
|---|---|
| `activeTab` | Capture the page — only on the tab you are looking at, only when you click the icon |
| `scripting` | Read page height and scroll it during a whole-page capture |
| `storage` | Remember your sign-in and the server address |

There is no `<all_urls>` host permission and no content script: nothing runs on
any page until you click the icon.

## Publishing to the Chrome Web Store

Loading unpacked is fine for a demo. To send a plain install link instead:

1. Pay the one-time Chrome Web Store developer fee.
2. Zip `extension/` and upload it. **Keep the `key` field** so the id does not
   change and the API's CORS entry stays valid.
3. Set visibility to **Unlisted** — installable by link, not searchable.
4. Supply a privacy policy. This extension sends a screenshot of the page you
   explicitly capture to the DesignEye server you configured, and stores nothing
   else, which is what that policy needs to say.

Review typically takes a few days, and screenshot-capturing extensions are
looked at closely, so expect questions about `activeTab`.
