import unittest

from isaac_core import IsaacKernel, Intent
from low_complexity import (
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

if __name__ == '__main__':
    unittest.main()
