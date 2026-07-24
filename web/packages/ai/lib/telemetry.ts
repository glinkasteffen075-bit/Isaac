/**
 * Default Sentry / Vercel AI SDK telemetry options.
 *
 * Pass `experimental_telemetry: aiTelemetry()` (or merge with overrides) on every
 * generateText / streamText / generateObject / ToolLoopAgent call so Sentry
 * vercelAIIntegration captures gen_ai spans with prompts and outputs.
 *
 * See: https://docs.sentry.io/platforms/javascript/guides/nextjs/configuration/integrations/vercelai/
 */

export type AiTelemetryOptions = {
  isEnabled?: boolean;
  recordInputs?: boolean;
  recordOutputs?: boolean;
  functionId?: string;
  metadata?: Record<string, string | number | boolean>;
};

/**
 * Build experimental_telemetry for Vercel AI SDK calls.
 * Prompts/outputs are recorded by default (owner-confirmed PII capture).
 */
export function aiTelemetry(
  functionId?: string,
  overrides: AiTelemetryOptions = {},
): AiTelemetryOptions {
  return {
    isEnabled: true,
    recordInputs: true,
    recordOutputs: true,
    ...(functionId ? { functionId } : {}),
    ...overrides,
  };
}
