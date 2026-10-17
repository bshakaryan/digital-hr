"""Small, deterministic multilingual retrieval over the authorized demo corpus."""
import math
import re
from collections import Counter


WORD = re.compile(r"[a-zа-яәіңғұқөүһ0-9]+", re.IGNORECASE)
STOP = {"как", "где", "что", "кто", "когда", "можно", "ли", "мне", "мой", "моего", "мою", "по", "на", "в", "и", "из", "для", "если", "нет", "о", "об", "как", "the", "how", "is", "қа", "қалай", "мен", "менің"}
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
}


def terms(text: str) -> set[str]:
    result = set()
    for raw in WORD.findall(text.lower().replace("ё", "е")):
        if raw in STOP or len(raw) < 3:
            continue
        word = next((replacement for prefix, replacement in ALIASES.items() if raw.startswith(prefix)), raw)
        result.add(word[:5])
    return result


def ranked(question: str, documents, min_score: float = 0.8) -> list[tuple[float, object]]:
    query = terms(question)
    if not query or not documents:
        return []
    fields = [(terms(d.title), terms(d.section), terms(d.keywords), terms(d.content)) for d in documents]
    frequency = Counter(term for field in fields for term in set().union(*field))
    scored = []
    for document, (title, section, keywords, content) in zip(documents, fields):
        score = sum(math.log((len(documents) + 1) / (frequency[term] + 0.5)) *
                    max((3.0 if term in keywords else 0), (2.5 if term in title else 0),
                        (1.5 if term in section else 0), (1.0 if term in content else 0))
                    for term in query if term in title | section | keywords | content)
        if score >= min_score:
            scored.append((score, document))
    return sorted(scored, key=lambda item: (-item[0], item[1].id))


def evidence(question: str, content: str) -> str:
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", content) if part.strip()]
    query = terms(question)
    scored = sorted(enumerate(sentences), key=lambda pair: (-len(query & terms(pair[1])), pair[0]))
    chosen = sorted(scored[:2], key=lambda pair: pair[0])
    return " ".join(sentence for _, sentence in chosen)
