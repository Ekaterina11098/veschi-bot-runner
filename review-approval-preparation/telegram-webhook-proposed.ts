import { routeReviewApproval } from "../_shared/review_callback_route.mjs";
// Telegram sends commands here; long WB/MoySklad checks run in GitHub Actions.
// Requires TELEGRAM_WEBHOOK_SECRET and TELEGRAM_ALLOWED_CHAT_ID in Edge Function secrets.
const PROJECT_URL = Deno.env.get("SUPABASE_URL") ?? "";
const SECRET_KEYS = Deno.env.get("SUPABASE_SECRET_KEYS");
let SERVICE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
if (SECRET_KEYS) {
  try {
    SERVICE_KEY = JSON.parse(SECRET_KEYS).default ?? SERVICE_KEY;
  } catch {
    // The legacy service role key remains available on older projects.
  }
}
const WEBHOOK_SECRET = Deno.env.get("TELEGRAM_WEBHOOK_SECRET") ?? "";
const ALLOWED_CHAT = Deno.env.get("TELEGRAM_ALLOWED_CHAT_ID") ?? "";
const DISPATCH_TOKEN = Deno.env.get("GITHUB_WORKFLOW_DISPATCH_TOKEN") ?? "";
const VERSION = "2026-09-29-r38";
const WORKFLOW_URL = "https://api.github.com/repos/Ekaterina11098/VESCHI_AI/actions/workflows/telegram-commands.yml/dispatches";

function reply(chatId: number, text: string): Response {
  return Response.json({ method: "sendMessage", chat_id: chatId, text });
}

Deno.serve(async (request: Request): Promise<Response> => {
  if (request.method !== "POST") return new Response("Method not allowed", { status: 405 });
  if (!WEBHOOK_SECRET || !ALLOWED_CHAT || !PROJECT_URL || !SERVICE_KEY) {
    console.error("Telegram webhook missing configuration:", [
      !WEBHOOK_SECRET && "TELEGRAM_WEBHOOK_SECRET",
      !ALLOWED_CHAT && "TELEGRAM_ALLOWED_CHAT_ID",
      !PROJECT_URL && "SUPABASE_URL",
      !SERVICE_KEY && "SUPABASE_SECRET_KEYS",
    ].filter(Boolean).join(", "));
    return new Response("Webhook configuration incomplete", { status: 503 });
  }
  if (request.headers.get("X-Telegram-Bot-Api-Secret-Token") !== WEBHOOK_SECRET) {
    console.warn("Telegram webhook rejected request: secret mismatch");
    return new Response("Unauthorized", { status: 401 });
  }
  let update: Record<string, unknown>;
  try {
    update = await request.json();
  } catch {
    return new Response("Invalid JSON", { status: 400 });
  }
  const reviewResponse = await routeReviewApproval(request, update, {
    enabled: Deno.env.get("REVIEW_APPROVAL_ENABLED") === "true",
    mode: "github-encrypted",
    webhookSecret: WEBHOOK_SECRET,
    receiverURL: "https://api.github.com/repos/Ekaterina11098/veschi-bot-runner/actions/workflows/review-approval-process.yml/dispatches",
    ingressKey: Deno.env.get("REVIEW_APPROVAL_INGRESS_KEY") ?? "",
    dispatchToken: Deno.env.get("REVIEW_APPROVAL_DISPATCH_TOKEN") ?? "",
    ownerId: Deno.env.get("REVIEW_APPROVAL_OWNER_ID") ?? "",
    chatId: ALLOWED_CHAT,
    botId: Deno.env.get("REVIEW_APPROVAL_BOT_ID") ?? "",
  });
  if (reviewResponse) return reviewResponse;
  const message = update?.message as { chat?: { id?: number }; text?: string } | undefined;
  const chatId = message?.chat?.id;
  const raw = message?.text?.trim().toLocaleLowerCase("ru") ?? "";
  const command = raw.split("@", 1)[0];
  if (typeof chatId !== "number" || !Number.isSafeInteger(chatId)) {
    return new Response("OK");
  }
  if (String(chatId) !== ALLOWED_CHAT) {
    console.warn("Telegram webhook ignored update: chat ID differs from allowed chat");
    if (command === "/version" || command === "/chatid") {
      return reply(chatId, `Chat ID этого диалога: ${chatId}. Укажите это число в TELEGRAM_ALLOWED_CHAT_ID в Supabase и GitHub.`);
    }
    return new Response("OK"); // Ignore every other chat, without exposing seller data.
  }
  if (command === "/chatid") return reply(chatId, `Chat ID этого диалога: ${chatId}`);
  if (command === "/version") return reply(chatId, `VESCHI AI ${VERSION}`);
  if (command === "/start") {
    return reply(chatId, "Отправьте: остатки, новинки, аудит, инвентаризация или отзывы. Команды принимаются без Streamlit.");
  }
  const kinds: Record<string, string> = {
    "остатки": "остатки", "/остатки": "остатки",
    "новинки": "новинки", "/новинки": "новинки",
    "аудит": "аудит", "/аудит": "аудит",
    "инвентаризация": "инвентаризация", "/инвентаризация": "инвентаризация", "/inventory": "инвентаризация",
    "отзывы": "отзывы", "/отзывы": "отзывы",
  };
  const kind = kinds[command];
  if (!kind) return reply(chatId, "Неизвестная команда. Доступны: остатки, новинки, аудит, инвентаризация, отзывы.");
  const updateId = update.update_id;
  if (typeof updateId !== "number" || !Number.isSafeInteger(updateId)) {
    return new Response("Invalid update", { status: 400 });
  }
  const res = await fetch(`${PROJECT_URL}/rest/v1/telegram_jobs?on_conflict=update_id`, {
    method: "POST",
    headers: {
      apikey: SERVICE_KEY,
      "Content-Type": "application/json",
      Prefer: "resolution=ignore-duplicates,return=representation",
    },
    body: JSON.stringify({ update_id: updateId, chat_id: chatId, kind }),
  });
  if (!res.ok) {
    // Telegram retries non-2xx webhooks. update_id is unique, so retries don't duplicate jobs.
    return new Response("Queue unavailable", { status: 503 });
  }
  const inserted = await res.json();
  if (!Array.isArray(inserted) || inserted.length === 0) {
    return new Response("OK"); // Telegram retried this same update; it is already queued.
  }
  if (DISPATCH_TOKEN) {
    try {
      const launch = await fetch(WORKFLOW_URL, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${DISPATCH_TOKEN}`,
          Accept: "application/vnd.github+json",
          "X-GitHub-Api-Version": "2022-11-28",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ ref: "main" }),
        signal: AbortSignal.timeout(8000),
      });
      if (launch.ok) {
        return reply(chatId, `Принято: ${kind}. Запустила проверку, пришлю результат.`);
      }
      console.error("GitHub Actions dispatch failed:", launch.status);
    } catch (error) {
      console.error("GitHub Actions dispatch unavailable:", String(error));
    }
  } else {
    console.warn("GITHUB_WORKFLOW_DISPATCH_TOKEN is missing; waiting for scheduled worker");
  }
  return reply(chatId, `Принято: ${kind}. Команда в очереди, результат придёт после автоматического запуска.`);
});

