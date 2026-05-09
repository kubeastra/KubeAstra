// Kubeastra demo walkthrough — drives the chat UI through 7 scenarios.
//
// Records a video of the entire run to scripts/demo-recorder/output/.
//
// Usage:
//   cd scripts/demo-recorder
//   npm install            # one-time, installs playwright
//   npx playwright install chromium   # one-time, installs the browser binary
//   node walkthrough.mjs
//
// Pre-requisites (handled by run-demo.sh if you use it):
//   - kind cluster + broken workloads up   (`make demo` from repo root)
//   - backend running on http://localhost:8800
//   - frontend running on http://localhost:3300

import { chromium } from "playwright";
import { mkdirSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const OUTPUT_DIR = resolve(__dirname, "output");
mkdirSync(OUTPUT_DIR, { recursive: true });

// ── Scenarios — pick prompts that route to different tools so the video
//    showcases breadth, not just one feature.
const SCENARIOS = [
  {
    title: "1. What's broken?",
    prompt: "what's broken in the demo namespace?",
    waitMs: 12000,
  },
  {
    title: "2. Drill down on the failing pod",
    prompt: "why is payment-service crashing?",
    waitMs: 14000,
  },
  {
    title: "3. Visual resource graph",
    prompt: "show me the resource graph for demo namespace",
    waitMs: 10000,
  },
  {
    title: "4. Deployment-level investigation",
    prompt: "investigate deployment: payment-service in demo namespace",
    waitMs: 14000,
  },
  {
    title: "5. Holistic namespace health",
    prompt: "analyze the health of the demo namespace",
    waitMs: 16000,
  },
  {
    title: "6. AI-generated runbook",
    prompt: "generate a runbook for ImagePullBackOff",
    waitMs: 14000,
  },
  {
    title: "7. Resource list",
    prompt: "show me everything in the demo namespace",
    waitMs: 10000,
  },
];

// ── Tunables you might want to tweak ──────────────────────────────────────
const BASE_URL = process.env.KUBEASTRA_URL || "http://localhost:3300";
const TYPING_DELAY_MS = 35; // per character — realistic typing speed
const PAUSE_BETWEEN_PROMPTS_MS = 2500; // breathing room between scenarios
const VIEWPORT = { width: 1440, height: 900 };

async function typeAndSend(page, text) {
  // The chat input is an <input> (not textarea) inside IntentBar with a
  // distinctive placeholder. Match on a stable substring of the placeholder.
  const input = page
    .locator('input[placeholder*="Ask"], input[placeholder*="cluster"]')
    .first();
  await input.waitFor({ state: "visible", timeout: 10000 });
  await input.click();
  await input.fill(""); // clear any leftover
  await page.keyboard.type(text, { delay: TYPING_DELAY_MS });
  await page.waitForTimeout(400);
  await page.keyboard.press("Enter");
}

async function run() {
  console.log("Launching Chromium…");
  const browser = await chromium.launch({
    headless: false, // headed so you (and the recorder) can see it work
    slowMo: 0,
  });

  const context = await browser.newContext({
    viewport: VIEWPORT,
    recordVideo: {
      dir: OUTPUT_DIR,
      size: VIEWPORT,
    },
  });

  const page = await context.newPage();
  // Land directly on /chat — / redirects to /chat anyway, but this is faster
  // and avoids any redirect race with the input mounting.
  const target = BASE_URL.replace(/\/$/, "") + "/chat";
  console.log(`Opening ${target}…`);
  await page.goto(target, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(2500); // let the chat UI settle

  for (const [i, sc] of SCENARIOS.entries()) {
    console.log(`\n[${i + 1}/${SCENARIOS.length}] ${sc.title}`);
    console.log(`  > ${sc.prompt}`);

    await typeAndSend(page, sc.prompt);
    await page.waitForTimeout(sc.waitMs);
    await page.waitForTimeout(PAUSE_BETWEEN_PROMPTS_MS);
  }

  console.log("\nFinal pause for the video tail…");
  await page.waitForTimeout(3000);

  await context.close(); // flushes the video
  await browser.close();

  console.log(`\nDone. Video saved under: ${OUTPUT_DIR}`);
  console.log("Look for the .webm file — convert to mp4 with:");
  console.log(`  ffmpeg -i ${OUTPUT_DIR}/<video>.webm -c:v libx264 -crf 23 demo.mp4`);
}

run().catch((err) => {
  console.error("Walkthrough failed:", err);
  process.exit(1);
});
