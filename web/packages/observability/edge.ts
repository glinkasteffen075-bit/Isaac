/*
 * This file configures the initialization of Sentry for edge runtime.
 * The config you add here will be used whenever a page or API route is loaded in an edge runtime.
 * https://docs.sentry.io/platforms/javascript/guides/nextjs/
 */

// biome-ignore lint/performance/noNamespaceImport: Sentry SDK convention
import * as Sentry from "@sentry/nextjs";
import { keys } from "./keys";

const isProd = process.env.NODE_ENV === "production";
const tracesSampleRate = Number.parseFloat(
  process.env.SENTRY_TRACES_SAMPLE_RATE ?? (isProd ? "0.1" : "1"),
);

export const initializeSentry = (): ReturnType<typeof Sentry.init> =>
  Sentry.init({
    dsn: keys().NEXT_PUBLIC_SENTRY_DSN,

    // Enable logging
    enableLogs: true,

    tracesSampleRate: Number.isFinite(tracesSampleRate) ? tracesSampleRate : isProd ? 0.1 : 1,

    // Stream gen_ai spans as standalone items (required for Conversations / large prompts)
    streamGenAiSpans: true,

    // Capture prompts/outputs for AI agent monitoring (PII — owner-confirmed)
    sendDefaultPii: true,

    environment:
      process.env.SENTRY_ENVIRONMENT ||
      process.env.VERCEL_ENV ||
      process.env.NODE_ENV ||
      "development",

    // Setting this option to true will print useful information to the console while you're setting up Sentry.
    debug: false,

    // Edge: vercelAIIntegration is NOT auto-enabled — register explicitly
    integrations: [
      // Send console.log, console.error, and console.warn calls as logs to Sentry
      Sentry.consoleLoggingIntegration({ levels: ["log", "error", "warn"] }),
      Sentry.vercelAIIntegration(),
    ],
  });
