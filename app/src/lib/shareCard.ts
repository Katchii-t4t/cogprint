/**
 * Share-card rendering for the cognitive fingerprint — the growth engine.
 *
 * Composes a 1080×1350 portrait PNG (dark base, radial glow, the user's
 * generative fingerprint, and a small wordmark) entirely client-side, then
 * offers it via the Web Share API with a plain download as the fallback.
 * No backend involvement, no cost, no new dependencies.
 */

import { fingerprintSvgMarkup } from "./fingerprint";

export interface ShareCardOpts {
  seed: number;
  sessions: number;
  vigor?: number[];
  confidence: string;
}

const W = 1080;
const H = 1350;

export async function renderShareCard(opts: ShareCardOpts): Promise<Blob> {
  const canvas = document.createElement("canvas");
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("canvas 2d context unavailable");

  // Dark base + soft radial cyan glow behind the print (matches the app).
  ctx.fillStyle = "#070b12";
  ctx.fillRect(0, 0, W, H);
  const glow = ctx.createRadialGradient(W / 2, H * 0.47, 0, W / 2, H * 0.47, W * 0.72);
  glow.addColorStop(0, "rgba(34,211,238,0.10)");
  glow.addColorStop(1, "rgba(34,211,238,0)");
  ctx.fillStyle = glow;
  ctx.fillRect(0, 0, W, H);

  // Header
  ctx.textAlign = "center";
  ctx.fillStyle = "#e6f0f7";
  ctx.font = "600 58px system-ui, sans-serif";
  ctx.fillText("My Cognitive Fingerprint", W / 2, 150);
  ctx.fillStyle = "#8fa3b8";
  ctx.font = "400 34px system-ui, sans-serif";
  const conf = opts.confidence.charAt(0).toUpperCase() + opts.confidence.slice(1);
  ctx.fillText(
    `${opts.sessions} session${opts.sessions !== 1 ? "s" : ""} · ${conf} confidence`,
    W / 2,
    212
  );

  // The fingerprint itself: rasterize the same generative SVG the app shows.
  const svg = fingerprintSvgMarkup(opts.seed, opts.sessions, opts.vigor ?? []);
  const url = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg);
  const img = new Image();
  await new Promise<void>((resolve, reject) => {
    img.onload = () => resolve();
    img.onerror = () => reject(new Error("failed to rasterize fingerprint SVG"));
    img.src = url;
  });
  const size = 840;
  ctx.drawImage(img, (W - size) / 2, 265, size, size);

  // Footer wordmark
  ctx.fillStyle = "#22d3ee";
  ctx.font = "700 44px system-ui, sans-serif";
  ctx.fillText("C O G P R I N T", W / 2, H - 150);
  ctx.fillStyle = "#64748b";
  ctx.font = "400 28px system-ui, sans-serif";
  ctx.fillText("The study companion that learns how you learn.", W / 2, H - 96);

  return await new Promise<Blob>((resolve, reject) =>
    canvas.toBlob(
      (b) => (b ? resolve(b) : reject(new Error("canvas.toBlob returned null"))),
      "image/png"
    )
  );
}

export type ShareOutcome = "shared" | "downloaded" | "cancelled";

/** Native share where supported; silent PNG download everywhere else. */
export async function shareFingerprint(
  blob: Blob,
  filename = "cogprint-fingerprint.png"
): Promise<ShareOutcome> {
  const file = new File([blob], filename, { type: "image/png" });

  if (navigator.canShare && navigator.canShare({ files: [file] })) {
    try {
      await navigator.share({
        files: [file],
        title: "My Cognitive Fingerprint",
        text: "My brain, as drawn by CogPrint — it learns how you learn.",
      });
      return "shared";
    } catch (e) {
      // User dismissed the share sheet — that's a choice, not an error.
      if ((e as Error).name === "AbortError") return "cancelled";
      // Anything else: fall through to download.
    }
  }

  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objectUrl;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(objectUrl);
  return "downloaded";
}
