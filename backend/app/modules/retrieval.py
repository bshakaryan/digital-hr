"""Small, deterministic multilingual retrieval over the authorized demo corpus."""
import math
import re
from collections import Counter


WORD = re.compile(r"[a-zа-яәіңғұқөүһ0-9]+", re.IGNORECASE)
STOP = {"как", "где", "что", "кто", "когда", "можно", "ли", "мне", "мой", "моего", "мою", "по", "на", "в", "и", "из", "для", "если", "нет", "о", "об", "делать", "the", "how", "is", "қа", "қалай", "мен", "менің"}
# Only terms present in the approved demo material are mapped. These are query aids,
# not claims about company policy or a general Kazakh translation model.
ALIASES = {
    "отдых": "отпуск", "итог": "результат", "обращени": "заявка",
    "демалыс": "отпуск", "өтініш": "заявка", "берем": "отправить",
    "оқу": "обучение", "оқуды": "обучение", "бітірем": "завершение",
    "аяқтай": "завершение", "курсын": "курс", "курсты": "курс",
    "профильд": "профиль", "мәлімет": "данные", "түзет": "исправить",
    "кадрлық": "кадровые", "деректер": "данные", "өзгерт": "исправить",
    "связат": "связ", "обратит": "обратиться", "помощ": "помощник",
    "подат": "подача", "подав": "подача",
}

# Query-only expansion: keep the original action as well as its close alternatives.
# The other query concepts must still be supported by the same source passage.
ACTION_EQUIVALENTS = frozenset({"оформ", "подач", "отпра"})


def terms(text: str) -> set[str]:
    result = set()
    for raw in WORD.findall(text.lower().replace("ё", "е")):
        if raw in STOP or len(raw) < 3:
            continue
        word = next((replacement for prefix, replacement in ALIASES.items() if raw.startswith(prefix)), raw)
        result.add(word[:5])
    return result


def concepts(question: str) -> tuple[frozenset[str], ...]:
    groups = {ACTION_EQUIVALENTS if term in {"оформ", "подач"} else frozenset({term})
              for term in terms(question)}
    return tuple(sorted(groups, key=lambda group: tuple(sorted(group))))


def supports(question: str, text: str) -> bool:
    groups = concepts(question)
    words = terms(text)
    return bool(groups) and all(group & words for group in groups)


def ranked(question: str, documents, min_score: float = 0.8) -> list[tuple[float, object]]:
    query = concepts(question)
    if not query or not documents:
        return []
    fields = [(terms(d.title), terms(d.section), terms(d.keywords), terms(d.content)) for d in documents]
    frequency = Counter(term for field in fields for term in set().union(*field))
    scored = []
    for document, (title, section, keywords, content) in zip(documents, fields):
        matched = [group for group in query if group & (title | section | keywords | content)]
        if len(matched) < max(1, (len(query) + 1) // 2):
            continue
        score = sum(max(math.log((len(documents) + 1) / (frequency[term] + 0.5)) *
                        max((3.0 if term in keywords else 0), (2.5 if term in title else 0),
                            (1.5 if term in section else 0), (1.0 if term in content else 0))
                        for term in group if term in title | section | keywords | content)
                    for group in matched)
        if score >= min_score:
            scored.append((len(matched), score, document))
    return [(score, document) for coverage, score, document in
            sorted(scored, key=lambda item: (-item[0], -item[1], item[2].id))]


def evidence(question: str, content: str) -> str:
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", content) if part.strip()]
    query = concepts(question)
    scored = sorted(enumerate(sentences), key=lambda pair: (-sum(bool(group & terms(pair[1])) for group in query), pair[0]))
    if scored and supports(question, scored[0][1]):
        return scored[0][1]
    chosen = sorted(scored[:2], key=lambda pair: pair[0])
    return " ".join(sentence for _, sentence in chosen)
