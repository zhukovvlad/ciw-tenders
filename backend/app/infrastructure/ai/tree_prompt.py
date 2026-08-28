"""Промпт tree-движка и разбор ответа (спека 2026-08-27 §5.1). Единая семантика для провайдеров."""

from __future__ import annotations

import json
from collections.abc import Sequence

from app.domain.entities import CatalogArticle, FundPrecedent, SectionMatchRequest, TreeNode

SYSTEM_PROMPT = (
    "Ты — эксперт по строительным сметам. Тебе дают ИЕРАРХИЧЕСКИЙ справочник статей СМР "
    "(код и наименование, вложенность по коду) и ФРАГМЕНТ сметы — раздел с его подстроками, "
    "с отступами по вложенности. Задача: каждой строке-цели назначить код статьи справочника.\n"
    "Правила:\n"
    "1. Учитывай структуру: статья строки, как правило, лежит внутри статьи её родителя "
    "(или совпадает с ней), а соседние строки часто идут в том же порядке, что статьи "
    "справочника.\n"
    "2. Если строка — ТОЛЬКО организационный каркас (этап, очередь, корпус, секция, ЖК/БЦ, "
    "'1 Этап ЖК', '2 Этап БЦ' и т.п.) без обозначения работы — ответ \"org\". Если же строка "
    "называет вид работ или дисциплину, пусть даже с хвостом этапа "
    "('Механические системы 1 Этап ЖК', "
    "'Устройство кровли', заголовок раздела) — это НЕ org: дай ей статью-раздел справочника. "
    "Строки-корпуса ВНУТРИ работы ('Корпус № 1; 6' под 'Гидроизоляция плиты') — это разбивка "
    "работы: дай им статью родителя.\n"
    "2а. Строка 'Прочее' внутри раздела — это 'Прочее (...)' ЭТОГО раздела (код вида X.99), "
    "а не корневое.\n"
    "3. Если смета дробит работу мельче справочника — дай детям статью, которой соответствует "
    "ближайший подходящий предок (роллап).\n"
    "4. Если работа реальная, но статьи для неё в справочнике нет — \"none\". "
    "Не выбирай 'Прочее' лишь потому, что не уверен.\n"
    "5. Отвечай ТОЛЬКО по строкам с пометкой [цель] (их id перечислены в блоке ЦЕЛИ). "
    "Строки [контекст] и строки с [уже: код] — только опора: по ним не отвечать. "
    "Пометка [предположительно: код] — неподтверждённая догадка, опирайся на неё осторожно.\n"
    "6. Блок ПРЕЦЕДЕНТЫ (если есть) — как операторы решали такие же строки раньше; "
    "при совпадении контекста следуй им.\n"
    "7. Поле \"sure\": true — только если уверен без оговорок; иначе false и укажи в \"alt\" "
    "второй по вероятности код (или null).\n"
    "Ответ — СТРОГО JSON-массив объектов "
    "{\"i\": <номер строки>, \"code\": \"<код|org|none>\", \"sure\": true|false, "
    "\"alt\": \"<код>\"|null} "
    "для КАЖДОЙ строки [цель], без преамбулы и markdown."
)


def render_catalog(catalog: Sequence[CatalogArticle]) -> str:
    return "\n".join(f"{'  ' * a.code.count('.')}({a.code}) {a.name}" for a in catalog)


def render_precedents(precedents: Sequence[FundPrecedent]) -> str:
    if not precedents:
        return ""
    lines = [
        f"{p.name} | в разделе ({p.parent_article_code or '—'}) → "
        f"({p.article_code}) {p.article_name} — {p.votes} решений"
        for p in precedents
    ]
    return "ПРЕЦЕДЕНТЫ (решения операторов по таким же строкам):\n" + "\n".join(lines) + "\n\n"


def render_ancestors(ancestors: Sequence[tuple[TreeNode, tuple[str, bool] | None]]) -> str:
    if not ancestors:
        return ""
    lines = []
    for n, hint in ancestors:
        if hint is None:
            shown = "?"
        else:
            code, trusted = hint
            shown = code if trusted else f"{code} (предположительно)"
        lines.append(f"  {n.code} | {n.name} -> {shown}")
    return "КОНТЕКСТ (предки фрагмента и их статьи):\n" + "\n".join(lines) + "\n\n"


def render_fragment(req: SectionMatchRequest) -> str:
    base = req.nodes[0].depth
    lines = []
    for n in req.nodes:
        indent = "  " * (n.depth - base)
        if n.id in req.targets:
            lines.append(f"{indent}[цель] {n.id} | {n.code} | {n.name}")
            continue
        hint = req.hints.get(n.id)
        if hint is None:
            lines.append(f"{indent}[контекст] {n.id} | {n.code} | {n.name}")
        else:
            code, trusted = hint
            tag = f"[уже: {code}]" if trusted else f"[предположительно: {code}]"
            lines.append(f"{indent}{n.id} | {n.code} | {n.name}  {tag}")
    return "\n".join(lines)


def build_user_prompt(req: SectionMatchRequest, *, include_catalog: bool = True) -> str:
    catalog = f"СПРАВОЧНИК:\n{render_catalog(req.catalog)}\n\n" if include_catalog else ""
    targets = ", ".join(str(n.id) for n in req.nodes if n.id in req.targets)
    return (
        f"{catalog}{render_precedents(req.precedents)}{render_ancestors(req.ancestors)}"
        f"ФРАГМЕНТ СМЕТЫ (номер | код раздела | наименование):\n{render_fragment(req)}\n\n"
        f"ЦЕЛИ (ответить только по ним): {targets}"
    )


_DECODER = json.JSONDecoder()


def parse_verdicts(text: str) -> list[dict] | None:
    """Первый ДЕКОДИРУЕМЫЙ JSON-массив словарей в тексте.

    Не жадный срез: «[см. раздел 4]» пропускается.
    """
    pos = text.find("[")
    while pos != -1:
        try:
            data, _ = _DECODER.raw_decode(text, pos)
        except json.JSONDecodeError:
            pos = text.find("[", pos + 1)
            continue
        if isinstance(data, list) and all(isinstance(x, dict) for x in data):
            return data
        pos = text.find("[", pos + 1)
    return None
