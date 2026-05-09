# Demo Recorder

Drives the Kubeastra chat UI through 7 scenarios with realistic typing and
records a video of the entire run — ready to embed in the project README
or post on YouTube/Loom.

## What you get

A `.webm` video (~30–60s, ~5–15 MB) showing:

1. **What's broken?** — `what's broken in the demo namespace?`
2. **Drill down** — `why is payment-service crashing?`
3. **Visual graph** — `show me the resource graph for demo namespace`
4. **Workload investigation** — `investigate deployment: payment-service in demo namespace`
5. **Namespace health** — `analyze the health of the demo namespace`
6. **Runbook generation** — `generate a runbook for ImagePullBackOff`
7. **Resource list** — `show me everything in the demo namespace`

Each prompt is typed character-by-character (35ms per char), gets ~12–16s
of dwell time so the AI response is fully visible, then auto-advances.

## Prerequisites

- Node.js 20+ and npm
- Docker + kind + kubectl (for `make demo`)
- An LLM configured in `ui/backend/.env` (Gemini key or `LLM_PROVIDER=ollama`)
- `ffmpeg` (only needed if you want mp4 instead of webm)

## One-shot — run everything end-to-end

From the repo root:

```bash
./scripts/demo-recorder/run-demo.sh
```

This orchestrates:

1. `make demo` (kind cluster + broken workloads + web UI)
2. waits for backend health (`/api/health` 200)
3. waits for the frontend to respond on :3300
4. installs Playwright + Chromium (one-time, ~150 MB)
5. runs the walkthrough — Chromium opens **headed** so you can watch / record

The video lands at `scripts/demo-recorder/output/<id>.webm`.

## Manual mode — UI already running

If you've already got `make demo` up and the UI on localhost:3300:

```bash
cd scripts/demo-recorder
npm install                          # one-time
npx playwright install chromium      # one-time
node walkthrough.mjs
```

## Convert to mp4 (for GitHub README embedding)

GitHub's README accepts uploaded mp4/webm via drag-and-drop into an issue,
but mp4 is more universally supported:

```bash
cd scripts/demo-recorder/output
ffmpeg -i *.webm -c:v libx264 -crf 23 -movflags +faststart demo.mp4
```

Result: a ~5–10 MB mp4 you can drag into a GitHub issue, copy the
generated CDN URL, and paste into `README.md`.

## Tuning

Edit the top of [`walkthrough.mjs`](walkthrough.mjs):

| Variable | Default | Effect |
|---|---|---|
| `SCENARIOS` | 7 prompts | Add/remove/reorder demo beats |
| `TYPING_DELAY_MS` | 35 | Per-character typing speed (lower = faster) |
| `PAUSE_BETWEEN_PROMPTS_MS` | 2500 | Gap between prompts |
| `VIEWPORT` | 1440×900 | Recording resolution |
| `BASE_URL` env | http://localhost:3300 | Override via `KUBEASTRA_URL` |

## Troubleshooting

**Browser opens but nothing types** — the chat input selector
(`textarea` or `[contenteditable="true"]`) didn't match. Inspect your UI's
chat input element and adjust the locator in `typeAndSend()`.

**Responses cut off in the recording** — increase `waitMs` for that
scenario. Ollama is noticeably slower than Gemini; if you're using
Ollama, double the `waitMs` values.

**"Playwright failed to install Chromium"** — corporate proxy or
firewall. Set `HTTPS_PROXY` then re-run `npx playwright install chromium`.

**Video file is empty / 0 bytes** — Playwright flushes video on
`context.close()`. If the script crashed before that, the file is
incomplete. Re-run; the new video replaces the old.
