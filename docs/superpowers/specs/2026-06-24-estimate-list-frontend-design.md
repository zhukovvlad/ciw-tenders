# Дизайн: список разобранных смет на фронтенде

**Дата:** 2026-06-24
**Статус:** утверждён, готов к плану реализации

## Проблема

Бэкенд уже персистит разобранные сметы и отдаёт их через `GET /api/estimates`
(список, скоупится по пользователю — админ видит все), `GET /api/estimates/{id}`
(детали со строками) и `DELETE /api/estimates/{id}`. На фронте этого нет:

- в `lib/api/estimates.ts` нет функции списка (`listEstimates`) и удаления;
- `EstimateFlow` показывает ровно одну смету — ту, что регидратируется из
  `sessionStorage`. Доступа к ранее разобранным сметам у пользователя нет.

Цель: вывести список разобранных смет, дать открыть конкретную смету и удалить
ненужную.

## Решение (обзор)

Добавить функцию списка в API-слой и вывести список под зоной загрузки на
`StartScreen`. Клик по смете открывает её (поведение зависит от статуса), есть
удаление с подтверждением. Навигация остаётся на `useState` (роутер не вводим).

## Компоненты

### 1. API-слой — `frontend/src/lib/api/estimates.ts`

Добавить тип DTO, доменный тип элемента списка и две функции:

```ts
interface SummaryDto {
  id: number
  filename: string
  status: string
  nodes_count: number
  created_at: string // ISO
}

export interface EstimateListItem {
  id: number
  filename: string
  status: string
  nodesCount: number
  createdAt: string // ISO, форматируется в UI
}

export async function listEstimates(): Promise<EstimateListItem[]>
export async function deleteEstimate(id: number): Promise<void>
```

- `listEstimates` → `apiGet<SummaryDto[]>("/estimates")`, маппинг snake_case → camelCase.
- `deleteEstimate` → `apiSend("DELETE", "/estimates/${id}")` (204 No Content).
- `getEstimate` уже существует — переиспользуется при открытии.

### 2. Новый компонент — `frontend/src/components/estimate/EstimateList.tsx`

Самодостаточный компонент списка:

- Грузит данные сам (`useEffect` на маунт) через `listEstimates`.
- Состояния: loading (скелетон), error (сообщение + возможность повторить), empty
  («ещё нет разобранных смет»), список.
- Таблица на `ui/table`: колонки — имя файла, статус (бейдж), кол-во узлов, дата,
  действия. Дата форматируется из ISO в человекочитаемый вид.
- Удаление инкапсулировано: кнопка → `ui/alert-dialog` с подтверждением (паттерн
  как в `components/articles/WipeCatalog.tsx`) → `deleteEstimate` → рефетч списка.
- Props: `onOpen(id: number, status: string) => void`.

**Бейджи статусов** (через `ui/badge`):

| Статус бэка | Бейдж | Кликабельность строки |
|---|---|---|
| `ready` | «Готово» | да → review |
| `partial_error` | «Готово с ошибками» | да → review |
| `pending` | «В обработке» | да → processing (возобновить poll) |
| `running` | «В обработке» | да → processing (возобновить poll) |
| `blocked` | «Отклонено» | нет (только удаление) |

### 3. `StartScreen` + `EstimateFlow`

- `frontend/src/pages/estimate/StartScreen.tsx`: получает проп `onOpen` и рендерит
  `<EstimateList onOpen={onOpen} />` под дропзоной.
- `frontend/src/pages/estimate/EstimateFlow.tsx`: добавляет `handleOpen(id, status)`
  и прокидывает его в `StartScreen`:
  - `pending`/`running` → `setPhase("processing")` + `pollEstimate(id, ...)` (та же
    логика, что после загрузки) → по завершении `review`;
  - иначе → `getEstimate(id)` → `initReview(fileName, rows)` → `setPhase("review")`.
  - В обоих ветках выставляет `estimateIdRef.current = id` и `saveEstimateId(id)`,
    чтобы работали PATCH-ревью строк и экспорт.

При открытии сметы строки приходят с уже сохранёнными решениями (`final_*`); экран
проверки показывает их как есть, пользователь дорешает оставшиеся. Это ожидаемое
поведение.

## Поток данных

1. `StartScreen` маунтится → `EstimateList` зовёт `listEstimates()` → таблица.
2. Клик по строке → `onOpen(id, status)` → `EstimateFlow.handleOpen`.
3. `handleOpen` грузит детали (или возобновляет poll) → переводит фазу в
   `review`/`processing`, фиксирует `estimateIdRef`/`saveEstimateId`.
4. Удаление: внутри `EstimateList` → диалог → `deleteEstimate(id)` → рефетч.

## Обработка ошибок

- Сетевые ошибки `listEstimates`/`deleteEstimate` → `ApiError` из `client.ts`;
  в списке показываем сообщение об ошибке, на удалении — `toast.error`.
- `getEstimate` при открытии может вернуть 404 (смету удалили в другой вкладке) →
  `toast.error` и остаёмся на старте.

## Тесты (vitest + RTL)

- `frontend/src/lib/api/estimates.test.ts`: `listEstimates` (маппинг DTO, URL),
  `deleteEstimate` (метод DELETE, URL).
- `frontend/src/components/estimate/EstimateList.test.tsx`: рендер списка, бейджи
  по статусам, `blocked` некликабелен, клик зовёт `onOpen`, удаление через диалог
  зовёт DELETE и рефетчит, пустое состояние, состояние ошибки.

## Вне области (YAGNI)

- Роутер не вводим (навигация на `useState`).
- Экспорт прямо из строки списка — нет (экспорт внутри открытой сметы).
- Пагинация/поиск/сортировка по списку — нет.
- Поток смет на моках (`lib/mock/`) не трогаем.
