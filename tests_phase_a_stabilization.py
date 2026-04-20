import asyncio
import unittest
from types import SimpleNamespace

from executor import Executor, Strategy, Task, TaskType
from isaac_core import IsaacKernel, Intent, detect_intent
from low_complexity import (
    ClassificationResult,
    InteractionClass,
    classify_interaction_result,
    is_lightweight_local_class,
)


class TestCriticalBugs(unittest.TestCase):
    def setUp(self):
        self.kernel = object.__new__(IsaacKernel)

    def test_bug_1_greeting_stays_lightweight_local(self):
        result = classify_interaction_result("Hallo Isaac")
        self.assertEqual(result.interaction_class, InteractionClass.SOCIAL_GREETING)
        self.assertTrue(is_lightweight_local_class(result.interaction_class))

    def test_bug_2_status_query_maps_to_status_intent(self):
        intent = self.kernel._resolve_intent_from_classification(
            "status", Intent.CHAT, InteractionClass.STATUS_QUERY
        )
        self.assertEqual(intent, Intent.STATUS)

    def test_bug_3_tool_request_maps_to_search_intent(self):
        intent = self.kernel._resolve_intent_from_classification(
            "Suche: Wetter Berlin", Intent.SEARCH, InteractionClass.TOOL_REQUEST
        )
        self.assertEqual(intent, Intent.SEARCH)

    def test_bug_4_question_without_status_or_tool_stays_chat(self):
        intent = self.kernel._resolve_intent_from_classification(
            "Was ist 2+2?", Intent.CHAT, InteractionClass.NORMAL_CHAT
        )
        self.assertEqual(intent, Intent.CHAT)

    def test_bug_5_detected_search_is_ignored_without_tool_classification(self):
        intent = self.kernel._resolve_intent_from_classification(
            "Erkläre mir das Wetter als sprachliches Motiv in Literatur",
            Intent.SEARCH,
            InteractionClass.NORMAL_CHAT,
        )
        self.assertEqual(intent, Intent.CHAT)

    def test_bug_6_executor_uses_explicit_tool_policy_for_normal_chat(self):
        task = Task(
            id="t1",
            typ=TaskType.CHAT,
            prompt="Was ist 2+2?",
            beschreibung="chat",
            strategy=Strategy(allow_tools=True),
            interaction_class=InteractionClass.NORMAL_CHAT,
            classification=ClassificationResult(
                interaction_class=InteractionClass.NORMAL_CHAT,
                normalized_text="was ist 2 2",
                has_question=True,
                word_count=3,
            ),
        )
        executor = object.__new__(Executor)
        self.assertTrue(executor._should_try_tool(task, task.prompt, iteration=2))

    def test_bug_7_executor_respects_explicit_tool_disable_even_for_tool_request(self):
        task = Task(
            id="t2",
            typ=TaskType.CHAT,
            prompt="Suche: Wetter Berlin",
            beschreibung="chat",
            strategy=Strategy(allow_tools=False),
            interaction_class=InteractionClass.TOOL_REQUEST,
            classification=ClassificationResult(
                interaction_class=InteractionClass.TOOL_REQUEST,
                normalized_text="suche wetter berlin",
                has_question=False,
                word_count=3,
            ),
        )
        executor = object.__new__(Executor)
        self.assertFalse(executor._should_try_tool(task, task.prompt, iteration=0))

    def test_bug_8_kernel_uses_structured_retrieval_contract_without_legacy_build_context(self):
        class FakeRetrievalContext:
            def as_dict(self):
                return {
                    "active_directives": [{"text": "Antworten klar halten", "priority": 20}],
                    "relevant_facts": [{"key": "answer_style", "value": "nuechtern"}],
                    "semantic_context": "[semantik] routing context",
                    "conversation_history": [{"role": "steffen", "text": "Bitte stabil halten"}],
                    "relevant_task_results": [{"description": "alt", "result": "tools genutzt", "score": 3.0}],
                    "preferences_context": [{"source": "directive", "text": "Antworten klar halten", "priority": 20}],
                    "project_context": [{"role": "steffen", "text": "routing fokus"}],
                    "behavioral_risks": [{"description": "alt", "score": 3.0, "risks": ["tool_overreach_risk"]}],
                    "relevant_reflections": ["pattern"],
                    "open_questions": [],
                }

        class FakeMemory:
            def __init__(self):
                self.calls = []

            def build_retrieval_context(self, user_input, intent="", interaction_class="", n_history=6):
                self.calls.append((user_input, intent, interaction_class, n_history))
                return FakeRetrievalContext()

            def build_context(self, *args, **kwargs):
                raise AssertionError("legacy build_context should not be used")
            
            def format_retrieval_context(self, retrieval_ctx):
                return (
                    "[active_directives]\n  - prio=20: Antworten klar halten\n"
                    "[semantic_context]\n[semantik] routing context"
                )

            def add_conversation(self, *args, **kwargs):
                return None

            def save_task_result(self, *args, **kwargs):
                return None

        class FakeExecutor:
            def __init__(self):
                self.prompt = None

            def create_task(self, **kwargs):
                self.prompt = kwargs["prompt"]
                return SimpleNamespace(
                    typ=kwargs["typ"],
                    prompt=kwargs["prompt"],
                    antwort="ok",
                    fehler="",
                    score=SimpleNamespace(total=7.0),
                    provider_used="test-provider",
                    iteration=0,
                    id="task1",
                )

            async def submit_and_wait(self, task, timeout=180.0):
                return task

        kernel = object.__new__(IsaacKernel)
        kernel.memory = FakeMemory()
        kernel.executor = FakeExecutor()
        kernel.meaning = SimpleNamespace(record_impact=lambda *args, **kwargs: None)
        kernel.values = SimpleNamespace(update=lambda *args, **kwargs: None)
        kernel._build_system = lambda sudo_aktiv, emp, wissen_kontext="", strategy_note="": "system"
        kernel._provider_hint = lambda user_input: None
        classification = ClassificationResult(
            interaction_class=InteractionClass.NORMAL_CHAT,
            normalized_text="was ist 2 2",
            has_question=True,
            word_count=3,
        )

        result, score = asyncio.run(
            kernel._standard_task(
                user_input="Was ist 2+2?",
                intent=Intent.CHAT,
                sudo_aktiv=False,
                emp=SimpleNamespace(),
                wissen_kontext="",
                interaction_class=InteractionClass.NORMAL_CHAT,
                classification=classification,
            )
        )

        self.assertEqual(result, "ok")
        self.assertEqual(score, 7.0)
        self.assertEqual(kernel.memory.calls[0][0], "Was ist 2+2?")
        self.assertIn("[active_directives]", kernel.executor.prompt)
        self.assertIn("[semantic_context]", kernel.executor.prompt)
        self.assertNotIn("[Steffen-Direktiven]", kernel.executor.prompt)

    def test_bug_9_kernel_detects_natural_openrouter_browser_request(self):
        self.assertTrue(
            self.kernel._is_browser_request(
                "Isaac geh auf openrouter.com, öffne settings und generiere ein token"
            )
        )

    def test_bug_10_kernel_parses_structured_browser_flow(self):
        parsed = self.kernel._parse_browser_request(
            "browser: openrouter | https://openrouter.ai/settings/keys | click Settings; wait 1; extract #token -> token"
        )
        self.assertEqual(parsed["instance_id"], "openrouter")
        self.assertEqual(parsed["url"], "https://openrouter.ai/settings/keys")
        self.assertEqual(parsed["actions"][0]["action"], "click")
        self.assertEqual(parsed["actions"][1]["action"], "wait")
        self.assertEqual(parsed["actions"][2]["action"], "extract_text")


    def test_bug_11_process_short_circuits_greeting_without_runtime_dependencies(self):
        kernel = object.__new__(IsaacKernel)
        result = asyncio.run(kernel.process("Hallo Isaac"))
        self.assertEqual(result, "Hallo. Ich bin da.")

    def test_bug_12_process_short_circuits_ack_without_runtime_dependencies(self):
        kernel = object.__new__(IsaacKernel)
        result = asyncio.run(kernel.process("Danke"))
        self.assertEqual(result, "Gern. Ich bin da.")

    def test_bug_13_translate_keyword_without_prefix_stays_chat(self):
        intent = self.kernel._resolve_intent_from_classification(
            "Kannst du das bitte übersetzen?",
            detect_intent("Kannst du das bitte übersetzen?"),
            InteractionClass.NORMAL_CHAT,
        )
        self.assertEqual(intent, Intent.CHAT)

    def test_bug_14_explicit_translate_prefix_remains_command(self):
        intent = self.kernel._resolve_intent_from_classification(
            "Übersetze: Guten Morgen auf Englisch",
            detect_intent("Übersetze: Guten Morgen auf Englisch"),
            InteractionClass.NORMAL_CHAT,
        )
        self.assertEqual(intent, Intent.TRANSLATE)

    def test_bug_15_strategy_defaults_keep_chat_tooling_disabled(self):
        kernel = object.__new__(IsaacKernel)
        strategy = kernel._select_response_strategy(
            user_input="Was ist 2+2?",
            intent=Intent.CHAT,
            interaction_class=InteractionClass.NORMAL_CHAT,
            retrieval_ctx={},
        )
        self.assertFalse(strategy.allow_tools)
        self.assertTrue(strategy.allow_followup)


    def test_bug_16_translate_command_without_colon_is_preserved(self):
        detected = detect_intent("Übersetze bitte Hallo auf Englisch")
        self.assertEqual(detected, Intent.TRANSLATE)
        intent = self.kernel._resolve_intent_from_classification(
            "Übersetze bitte Hallo auf Englisch",
            detected,
            InteractionClass.NORMAL_CHAT,
        )
        self.assertEqual(intent, Intent.TRANSLATE)

    def test_bug_19_detect_intent_is_narrowed_to_explicit_command_patterns(self):
        detected = detect_intent("Kannst du den Satz bitte übersetzen?")
        self.assertEqual(detected, Intent.CHAT)

    def test_bug_20_status_classification_has_priority_over_regex_detection(self):
        intent = self.kernel._resolve_intent_from_classification(
            "status",
            detect_intent("status"),
            InteractionClass.STATUS_QUERY,
        )
        self.assertEqual(intent, Intent.STATUS)

    def test_bug_21_tool_classification_has_priority_for_search_routing(self):
        intent = self.kernel._resolve_intent_from_classification(
            "Suche: Wetter Berlin",
            detect_intent("Suche: Wetter Berlin"),
            InteractionClass.TOOL_REQUEST,
        )
        self.assertEqual(intent, Intent.SEARCH)


    def test_bug_22_status_classification_overrides_explicit_command_regex(self):
        intent = self.kernel._resolve_intent_from_classification(
            "übersetze hallo",
            Intent.TRANSLATE,
            InteractionClass.STATUS_QUERY,
        )
        self.assertEqual(intent, Intent.STATUS)

    def test_bug_17_executor_blocks_tool_for_status_class_even_if_tools_allowed(self):
        task = Task(
            id="t3",
            typ=TaskType.CHAT,
            prompt="status",
            beschreibung="chat",
            strategy=Strategy(allow_tools=True),
            interaction_class=InteractionClass.STATUS_QUERY,
        )
        executor = object.__new__(Executor)
        self.assertFalse(executor._should_try_tool(task, task.prompt, iteration=0))

    def test_bug_18_create_task_prefers_explicit_strategy_over_legacy_flags(self):
        executor = object.__new__(Executor)
        executor._tasks = {}
        executor.next_task_id = lambda: "t-fixed"
        strategy = Strategy(allow_tools=False, allow_followup=False, allow_provider_switch=False)
        task = executor.create_task(
            typ=TaskType.CHAT,
            prompt="Was ist 2+2?",
            strategy=strategy,
            allow_tools=True,
            allow_followup=True,
            allow_provider_switch=True,
        )
        self.assertFalse(task.allow_tools)
        self.assertFalse(task.allow_followup)
        self.assertFalse(task.allow_provider_switch)

if __name__ == '__main__':
    unittest.main()
