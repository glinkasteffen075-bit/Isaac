import { createOpenAI } from "@ai-sdk/openai";
import { keys } from "../keys";

const openai = createOpenAI({
  apiKey: keys().OPENAI_API_KEY,
  compatibility: "strict",
});

export const models = {
  chat: openai("gpt-4o-mini"),
  embeddings: openai("text-embedding-3-small"),
};

/**
 * Sentry AI monitoring: pass experimental_telemetry on every AI SDK call, e.g.
 *
 *   import { generateText, models, aiTelemetry } from "@repo/ai";
 *   await generateText({
 *     model: models.chat,
 *     prompt: "Hello",
 *     experimental_telemetry: aiTelemetry("chat"),
 *   });
 */
export { aiTelemetry } from "./telemetry";
