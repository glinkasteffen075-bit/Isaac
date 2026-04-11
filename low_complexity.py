import re
from dataclasses import dataclass


class InteractionClass:
    SOCIAL_GREETING = "SOCIAL_GREETING"
    SOCIAL_ACKNOWLEDGMENT = "SOCIAL_ACKNOWLEDGMENT"
    SHORT_CLARIFICATION = "SHORT_CLARIFICATION"
    STATUS_QUERY = "STATUS_QUERY"
    TOOL_REQUEST = "TOOL_REQUEST"
    AMBIGUOUS_SHORT = "AMBIGUOUS_SHORT"
    NORMAL_CHAT = "NORMAL_CHAT"


@dataclass(frozen=True)
class ClassificationResult:
    interaction_class: str
    normalized_text: str
    has_question: bool
    word_count: int

    def as_dict(self) -> dict[str, object]:
        return {
            "interaction_class": self.interaction_class,
            "normalized_text": self.normalized_text,
            "has_question": self.has_question,
            "word_count": self.word_count,
        }


_GREETING_MARKERS = {
    "hallo", "hi", "hey", "servus", "moin", "guten morgen", "guten tag", "guten abend"
}
_ACK_MARKERS = {
    "danke", "dankeschön", "danke schön", "thx", "thanks", "ok danke", "okidoki danke"
}
_CLARIFY_MARKERS = {
    "ist nur eine begrüßung", "war nur ein test", "nur kurz hallo", "ich wollte nur testen ob du antwortest"
}
_STATUS_MARKERS = {"status", "info", "hilfe"}
_TOOL_PREFIXES = ("suche:", "suche ", "search:", "search ", "recherchiere:", "recherchiere ", "finde:")
_TOOL_MARKERS = ("internet", "web", "browser", "wetter", "github", "api", "tool", "mcp", "suche", "search")
_ACTION_SHORT_MARKERS = ("mach", "weiter", "fortsetzen", "hilfe", "erklär", "erklär", "wer", "was", "wie", "warum")


def normalize_low_complexity(text: str) -> str:
    t = (text or "").strip().lower()
    t = re.sub(r"[^\wäöüß\s]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def classify_interaction(text: str) -> str:
    return classify_interaction_result(text).interaction_class


def classify_interaction_result(text: str) -> ClassificationResult:
    normalized = normalize_low_complexity(text)
    if not normalized:
        return ClassificationResult(
            interaction_class=InteractionClass.AMBIGUOUS_SHORT,
            normalized_text=normalized,
            has_question="?" in (text or ""),
            word_count=0,
        )

    tokens = normalized.split()
    normalized_wo_name = " ".join(t for t in tokens if t != "isaac").strip()
    if normalized_wo_name:
        normalized = normalized_wo_name
        tokens = normalized.split()
    word_count = len(tokens)
    has_question = "?" in (text or "")

    if normalized in _STATUS_MARKERS:
        return ClassificationResult(
            interaction_class=InteractionClass.STATUS_QUERY,
            normalized_text=normalized,
            has_question=has_question,
            word_count=word_count,
        )

    if normalized.startswith(_TOOL_PREFIXES):
        return ClassificationResult(
            interaction_class=InteractionClass.TOOL_REQUEST,
            normalized_text=normalized,
            has_question=has_question,
            word_count=word_count,
        )
    if any(marker in normalized for marker in _TOOL_MARKERS) and word_count >= 2:
        if ":" in (text or "") or word_count >= 3:
            return ClassificationResult(
                interaction_class=InteractionClass.TOOL_REQUEST,
                normalized_text=normalized,
                has_question=has_question,
                word_count=word_count,
            )

    if normalized in _CLARIFY_MARKERS or (
        word_count <= 6 and
        any(x in normalized for x in ("nur", "test", "begrüßung", "begruessung"))
    ):
        return ClassificationResult(
            interaction_class=InteractionClass.SHORT_CLARIFICATION,
            normalized_text=normalized,
            has_question=has_question,
            word_count=word_count,
        )

    if normalized in _ACK_MARKERS:
        return ClassificationResult(
            interaction_class=InteractionClass.SOCIAL_ACKNOWLEDGMENT,
            normalized_text=normalized,
            has_question=has_question,
            word_count=word_count,
        )

    if normalized in _GREETING_MARKERS:
        return ClassificationResult(
            interaction_class=InteractionClass.SOCIAL_GREETING,
            normalized_text=normalized,
            has_question=has_question,
            word_count=word_count,
        )
    if word_count <= 3 and any(g in normalized for g in ("hallo", "hi", "hey", "moin")):
        return ClassificationResult(
            interaction_class=InteractionClass.SOCIAL_GREETING,
            normalized_text=normalized,
            has_question=has_question,
            word_count=word_count,
        )

    if word_count <= 2 and not has_question and not any(m in normalized for m in _ACTION_SHORT_MARKERS):
        return ClassificationResult(
            interaction_class=InteractionClass.AMBIGUOUS_SHORT,
            normalized_text=normalized,
            has_question=has_question,
            word_count=word_count,
        )

    return ClassificationResult(
        interaction_class=InteractionClass.NORMAL_CHAT,
        normalized_text=normalized,
        has_question=has_question,
        word_count=word_count,
    )


def is_lightweight_local_class(interaction_class: str) -> bool:
    return interaction_class in {
        InteractionClass.SOCIAL_GREETING,
        InteractionClass.SOCIAL_ACKNOWLEDGMENT,
        InteractionClass.SHORT_CLARIFICATION,
    }


def is_low_complexity_local_input(text: str) -> bool:
    return is_lightweight_local_class(classify_interaction(text))


def local_class_response(interaction_class: str, text: str = "") -> str:
    if interaction_class == InteractionClass.SOCIAL_GREETING:
        normalized = normalize_low_complexity(text)
        if "guten morgen" in normalized:
            return "Guten Morgen. Ich bin da."
        return "Hallo. Ich bin da."
    if interaction_class == InteractionClass.SOCIAL_ACKNOWLEDGMENT:
        return "Gern. Ich bin da."
    if interaction_class == InteractionClass.SHORT_CLARIFICATION:
        return "Alles gut. Verstanden."
    if interaction_class == InteractionClass.AMBIGUOUS_SHORT:
        return "Ich bin da."
    return "Ich bin da."


def local_fast_response(text: str) -> str:
    return local_class_response(classify_interaction(text), text)
