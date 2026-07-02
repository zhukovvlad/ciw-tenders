# 2026-07-02 — Правка «уверенных» позиций на экране ревью

**Ветка:** `feat/editable-confident-rows`
**Спека:** [../superpowers/specs/2026-07-02-editable-confident-rows-design.md](../superpowers/specs/2026-07-02-editable-confident-rows-design.md)

## Что сделано

Frontend-only: снят особый случай «confident-строка нераскрываема» —
любая строка ревью раскрывается кликом (кандидаты + ручной поиск + «Оставить
без пары»). Для строк, у которых рекомендация AI-снимка не входит в
`candidates` (фонд-хиты), первой рисуется синтетическая карточка «текущая
рекомендация» — клик по ней откатывает правку через действие `confirm`
(бэкенд берёт нетронутый `matched_article_id`). Новый проп
`ReviewRow.onConfirmRecommendation`, прокинут из `ReviewScreen`
(`confirmArbiter` + `onReview "confirm"`).

Бэкенд-код не менялся. Инвариант, на котором держится откат («ревью пишет
только ось `review_status`/`final_*`, снимок `matched_*` иммутабелен»),
закреплён pinning-тестом `test_pick_and_reject_keep_ai_snapshot`; на фронте —
регрессионный тест карточки после override и pinning инвариантности
`progress()`.

## Сознательно вне объёма

Reject фонд-хита не гасит запись фонда — оператор будет отвергать тот же
матч в каждой новой смете. Заведено в
[TECH_DEBT](../TECH_DEBT.md#-золотой-фонд-reject-фонд-хита-не-гасит-запись-фонда).
