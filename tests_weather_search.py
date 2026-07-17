"""Weather web lookup: routing helpers + live-API integration shape."""
from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from search import (
    extract_weather_location,
    looks_like_weather_query,
    MultiSearch,
    SearchHit,
)


class TestWeatherSearchHelpers(unittest.TestCase):
    def test_looks_like_weather_positive(self):
        self.assertTrue(looks_like_weather_query("Wie wird das Wetter morgen?"))
        self.assertTrue(looks_like_weather_query("Suche: Wetter Berlin morgen"))
        self.assertTrue(looks_like_weather_query("Recherchiere Temperatur in Hamburg"))

    def test_looks_like_weather_explanatory_negative(self):
        self.assertFalse(
            looks_like_weather_query(
                "Erkläre mir das Wetter als sprachliches Motiv in Literatur"
            )
        )

    def test_extract_location(self):
        self.assertEqual(extract_weather_location("Suche: Wetter Berlin morgen"), "Berlin")
        self.assertEqual(extract_weather_location("Wetter in München heute"), "München")
        # default when no city
        self.assertEqual(extract_weather_location("Wie wird das Wetter morgen?"), "Berlin")

    def test_search_prefers_weather_api_hits(self):
        ms = MultiSearch()

        async def fake_weather(query: str):
            return (
                [
                    SearchHit(
                        titel="Open-Meteo Vorhersage: Berlin",
                        snippet="2026-07-18: Regen, 18–25°C",
                        url="https://api.open-meteo.com/example",
                        quelle="open-meteo",
                        score=10.0,
                    )
                ],
                "Wettervorhersage für Berlin, DE (Open-Meteo, live):\n2026-07-18: Regen, 18–25°C",
            )

        async def empty_engine(*_a, **_k):
            return []

        ms._weather_forecast = fake_weather
        ms._ddg = empty_engine
        ms._brave = empty_engine
        ms._searxng = empty_engine
        ms._wikipedia = empty_engine
        ms._reddit = empty_engine
        ms._arxiv = empty_engine
        ms.cache._c.clear()

        result = asyncio.run(
            ms.search("Wie wird das Wetter in Berlin morgen?", max_hits=5, load_fulltext=False)
        )
        self.assertIn("weather_api", result.quellen)
        self.assertTrue(result.abstract.startswith("Wettervorhersage"))
        self.assertGreaterEqual(result.hits[0].score, 10.0)
        self.assertEqual(result.hits[0].quelle, "open-meteo")

    def test_tool_request_weather_maps_to_search_intent(self):
        from low_complexity import classify_interaction_result, InteractionClass
        from isaac_core import IsaacKernel, Intent, detect_intent

        text = "Wie wird das Wetter morgen?"
        cls = classify_interaction_result(text)
        self.assertEqual(cls.interaction_class, InteractionClass.TOOL_REQUEST)
        # Kernel instance only needed for bound method; no full bootstrap
        kernel = object.__new__(IsaacKernel)
        intent = kernel._resolve_intent_from_classification(
            text, detect_intent(text), cls.interaction_class
        )
        self.assertEqual(intent, Intent.SEARCH)


if __name__ == "__main__":
    unittest.main()
