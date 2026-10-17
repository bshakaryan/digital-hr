# Передача проекта: три параллельных агента

Снимок до настройки агентов: 18 октября 2026, около 01:55 Asia/Qyzylorda. При составлении документа ветки, worktree, код приложения и данные БД не менялись. Источники: текущий Git, исходники, `docs/api-contract.md`, `docs/decisions.md`, `compose.yaml` и проверки ниже. **Фактический дедлайн подачи: воскресенье 18 октября 2026, 16:00 по времени Казахстана. Новую функциональность прекращаем к 08:00.**

## 1. Состояние Git

| Проверка | Факт |
| --- | --- |
| Корень рабочего дерева | `C:/Users/Dilnaz/digital-hr` |
| Ветка | `main`, отслеживает `origin/main` |
| HEAD | `f098b86d3c9be717952091c9765dde6a4efa43a4` |
| Сравнение с локальной ссылкой `origin/main` | `0` позади / `0` впереди; актуальность сервера GitHub отдельно не запрашивалась |
| Отслеживаемые изменения и неотслеживаемые файлы **до создания этого документа** | Нет: `git status --porcelain=v1 -uall` пуст |
| Worktree **до создания этого документа** | Только основное дерево `C:/Users/Dilnaz/digital-hr`, ветка `main` |
| После первого создания документа, до санкционированной настройки | Единственный неотслеживаемый файл: `docs/PROJECT_HANDOFF.md`; затем его нужно отдельно закоммитить до создания worktree |

Локальные `.env`, `frontend/node_modules` и `frontend/.next` существуют, но игнорируются Git; их содержимое здесь не раскрывается. Worktree не копируют эти файлы. Данные PostgreSQL и mock-сервисов находятся в Docker volumes, облачный одно-контейнерный вариант использует отдельное SQLite-хранилище (`docs/deployment.md`). Ни Git, ни новый worktree не переносят пользовательские курсы, документы или прогресс между базами. Риск потери данных связан прежде всего с `docker compose down -v`, удалением volume, подменой URL БД, `git clean`, принудительным сбросом и force push. Эти действия запрещены в параллельной работе.

Инструкция о родительском репозитории и `Jana-hack/` в переданном AGENTS.md противоречит проверенному `git worktree list`: фактический корень этого Git-репозитория — `digital-hr`. Для команд ниже используется **проверенный** корень; перед началом работы интегратор повторно проверяет `git rev-parse --show-toplevel`.

## 2. Архитектура и контракты

| Область | Фактические файлы и роль |
| --- | --- |
| Вход и клиентский каркас | `frontend/app/page.tsx` вызывает `frontend/components/use-session.ts` и `frontend/components/workspace.tsx`; последний содержит навигацию, общие ресурсы и маршрутизацию разделов. |
| AI Jana | `frontend/components/assistant.tsx` — общий чат; `frontend/components/course-assistant.tsx` — чат внутри курса. `backend/app/modules/assistant.py` применяет права к источникам, `backend/app/modules/retrieval.py` ищет фрагменты. `backend/app/modules/knowledge_files.py` и `knowledge_ingestion.py` отвечают за файлы, метаданные и загрузку. |
| Jana Academy | `frontend/components/academy-dashboard.tsx` собирает карточки, фильтры, награды, HR-конструктор и аналитику; `academy.tsx` — чтение материала и тест; `course-admin.tsx` и `knowledge-admin.tsx` — HR-интерфейсы. Серверный маршрут и правила находятся в `backend/app/modules/academy.py`. |
| HR Learning Analytics | `frontend/components/learning-analytics.tsx` — обзор и учебный профиль; `backend/app/modules/academy_analytics.py` — вычисления по назначениям и аудиту. Маршруты и RBAC находятся в общем `backend/app/modules/academy.py`. |
| Общие контракты и модель | `frontend/lib/api.ts` — клиент и TypeScript-типы; `frontend/lib/academy-labels.ts` — подписи, используемые Academy и аналитикой; `backend/app/schemas.py` и `backend/app/models.py` — API и ORM. `backend/migrations/versions/` заканчивается миграцией `0011_academy_analytics.py`. |
| Общий дизайн и запуск | `frontend/app/globals.css`, `frontend/app/brand.css`, `frontend/components/ui.tsx`, `frontend/components/use-resource.ts`; `frontend/next.config.ts`, `compose.yaml`, корневой `Dockerfile`, `scripts/start-web.py`. Backend собирается через `backend/Dockerfile`, FastAPI включает роутеры в `backend/app/main.py`. |

Подтверждённый контракт (`docs/api-contract.md`): `POST /api/assistant/query` возвращает извлекающий ответ с источниками или отказ; `POST /api/courses/{id}/ask` ограничен материалами назначенного курса. HR создаёт черновик через `POST /api/courses`, добавляет тест и материал, публикует и назначает; сотрудник видит назначенное через `GET /api/courses`, каталог — через `/api/courses/discover`, сохраняет прогресс и сдаёт тест. `GET /api/courses/rewards` вычисляет XP/уровень/значки из завершённых назначений. `GET /api/courses/analytics` доступен HR; `/analytics/employees` и `/{employee_id}` разрешают руководителю только прямых подчинённых. Клиентские кнопки не являются проверкой прав: её выполняет сервер. Текущий помощник — `extractive_demo`, без генеративного LLM; синтетические документы не являются официальной политикой Jana Post.

## 3. Владение файлами

**Правило allowlist:** агент может менять только перечисленные для него файлы. Остальные файлы доступны для чтения, но не для записи. Предложенные новые CSS Modules ниже **пока не существуют**; их можно создать после одобрения. Каждый агент работает в своей ветке/worktree и передаёт интегратору коммит и краткий отчёт о проверках. Никаких прямых push в `main`.

| Агент | Задача | Существующие файлы, разрешённые к изменению | Разрешённый новый файл | Не изменять |
| --- | --- | --- | --- | --- |
| A | Приветствие AI Jana, контекстные действия, UX чата | `frontend/components/assistant.tsx`, `frontend/components/course-assistant.tsx` | `frontend/components/assistant-ux.module.css` | `workspace.tsx`, общий API/стили, backend retrieval/RBAC; изменения пропсов в общем каркасе передать интегратору |
| B | UX Academy, показ существующих XP/значков и каталога | `frontend/components/academy.tsx`, `frontend/components/academy-dashboard.tsx`, `frontend/components/course-admin.tsx`, `frontend/components/knowledge-admin.tsx` | `frontend/components/academy-ux.module.css` | `course-assistant.tsx` (владелец A), `learning-analytics.tsx` (владелец C), серверное начисление XP и общий API |
| C | HR Learning Analytics и профили обучения | `frontend/components/learning-analytics.tsx`, `backend/app/modules/academy_analytics.py`, `backend/tests/test_academy_analytics.py` | `frontend/components/learning-analytics-ux.module.css` | `academy-dashboard.tsx` (владелец B), `backend/app/modules/academy.py` (общие маршруты/RBAC), схемы и модели; новый маршрут запрашивать у интегратора |

**Только Integration Lead:** `frontend/components/workspace.tsx`, `frontend/lib/api.ts`, `frontend/lib/academy-labels.ts`, `frontend/app/globals.css`, `frontend/app/brand.css`, `frontend/components/ui.tsx`, `frontend/components/use-resource.ts`, `frontend/components/use-session.ts`, `frontend/app/page.tsx`, `frontend/app/layout.tsx`; `backend/app/main.py`, `backend/app/models.py`, `backend/app/schemas.py`, `backend/app/modules/academy.py`, `backend/app/modules/assistant.py`, `backend/app/modules/retrieval.py`, `backend/app/modules/knowledge_files.py`, `backend/app/modules/knowledge_ingestion.py`, `backend/app/security.py`, `backend/app/seed.py`, `backend/app/provision_academy_demo.py`, все `backend/migrations/versions/*`; `compose.yaml`, Dockerfiles, `scripts/*`, `docs/api-contract.md`, `docs/verification.md`, `docs/PROJECT_HANDOFF.md`, lockfiles и зависимости. Исходные `knowledge_base_docs/*` и рабочие данные не менять никому. Любую потребность выйти за allowlist агент описывает предложением интегратору, а не правит общий файл.

## 4. Безопасность параллельной разработки

Главные точки конфликта: `academy-dashboard.tsx` встраивает компонент C и `CourseReader` B; `academy.tsx` встраивает `course-assistant.tsx` A; `workspace.tsx` монтирует Academy и AI Jana; `frontend/lib/api.ts` и глобальные CSS используются всеми тремя. У C серверные расчёты находятся отдельно, но HTTP-маршруты, RBAC и схемы — в общих файлах. Изменения интерфейса пропсов, TypeScript-типов и общего оформления интегрирует только Lead. Уже существует миграция `0011`; два агента, создающие `0012`, дадут две головы Alembic. **Новых миграций, таблиц, статусов и API-контрактов в этих трёх задачах не планировать.** При реальной необходимости — остановить параллельное внедрение этой части и передать её Lead.

**Worktree: условно безопасны.** Они разделят файлы и рабочие ветки, но сохранят общую базу Git-объектов и доступ к Docker daemon. Каждый агент должен использовать уникальную ветку и каталог; нельзя переключать одну ветку в двух деревьях, запускать общий Compose/seed/миграции, использовать рабочие `.env` и URL БД или чистить чужое дерево. Worktree сами по себе не изолируют PostgreSQL и порты. Интегратор один владеет `main` и единственным финальным push, так как push запускает деплой.

Команды санкционированной настройки в Windows Git Bash. Они сохраняют локальный baseline; пушить его до финальной интеграции нельзя:

```bash
cd /c/Users/Dilnaz/digital-hr
git rev-parse --show-toplevel
git status --porcelain=v1 -uall      # ожидать только ?? docs/PROJECT_HANDOFF.md; при других изменениях остановиться
git add -- docs/PROJECT_HANDOFF.md
git diff --cached --name-only        # должен быть только docs/PROJECT_HANDOFF.md
git commit -m "Document parallel agent handoff"
BASE=$(git rev-parse HEAD)
TAG=handoff-baseline-2026-10-18
git show-ref --verify --quiet "refs/tags/$TAG" && { echo "Tag already exists; stop"; exit 1; }
git tag -a "$TAG" -m "Baseline for three parallel Codex worktrees"
git worktree add -b codex/ai-jana ../digital-hr-agent-a "$BASE"
git worktree add -b codex/academy ../digital-hr-agent-b "$BASE"
git worktree add -b codex/learning-analytics ../digital-hr-agent-c "$BASE"
git worktree list
```

Агенты получают точный allowlist из раздела 3 и путь к этому документу в основном дереве. Новые worktree не получают игнорируемый `.env` и не должны подключаться к рабочей базе. Если хотя бы одна команда создания worktree завершилась ошибкой, прекратить настройку и разобрать её; не удалять каталоги автоматически.

**Вердикт: GO только для трёх узких, независимых веток с указанным владением и одним интегратором. NO-GO для свободных правок общего каркаса/контрактов, одновременных миграций, общего Docker Compose и прямых push агентов.** При потере времени на разрешение общих конфликтов остановить новую функциональность по сроку из раздела 6.

## 5. Исходные проверки

| Проверка 18 октября 2026 | Фактический результат | Ограничение |
| --- | --- | --- |
| `git status --porcelain=v1 -uall`, `git worktree list --porcelain` | Чистое основное дерево, других worktree нет **до создания этого файла** | При санкционированной настройке handoff отдельно коммитится перед созданием worktree |
| `docker compose run --rm --no-deps -e POSTGRES_TEST=0 backend pytest -q` | **168 passed, 5 skipped**, 1 предупреждение Starlette/httpx; 172.24 с | Тестовая фикстура ставит временный SQLite URL; PostgreSQL-конкуренция и рабочая БД не проверялись |
| `docker compose build backend frontend` | Обе сборки завершились; использован Docker cache | Эта проверка сама по себе не доказывает свежую компиляцию frontend |
| `docker compose build --no-cache frontend` | Новая production-сборка Next.js 16.4.2 успешна; TypeScript завершился успешно | Браузерное поведение не проверяется сборкой |
| `docker compose ps` | Backend, frontend, PostgreSQL, ZUP mock, Documentolog mock — healthy; worker — Up без healthcheck | Контейнеры были запущены около 7 часов; не перезапускались в рамках задания |
| `GET http://127.0.0.1:8100/api/health`, `GET http://127.0.0.1:3100/` | Оба HTTP 200 | `docker inspect` показал, что запущенные backend/frontend используют **другие image ID**, чем только что собранные образы; health относится к прежним контейнерам, а не к HEAD |

Браузерный сценарий, PostgreSQL-интеграционные тесты, реальный облачный деплой и данные аналитики в этом задании не проверялись. Запуск `scripts/browser_smoke.mjs` или полного Academy-сценария может записать заявки/прогресс в рабочую БД, поэтому он намеренно не выполнялся. Исторические результаты в `docs/verification.md` относятся к указанным там ревизиям и не подменяют финальную интеграционную проверку.

**Критичный путь демо:** вход HR → существующий файл базы знаний → создать черновик курса → прикрепить материал → задать тест → опубликовать → назначить сотруднику → сотрудник открывает материал и задаёт вопрос AI Jana по курсу с цитатой → отмечает прогресс и правильно сдаёт тест → 100 XP ровно один раз → HR видит назначение, завершение и профиль сотрудника. Должны сохраниться серверные права, повторная отправка без второго эффекта, изоляция курса и персональных данных. Параллельные UI-работы не должны ломать также базовый маршрут заявки на отпуск с человеческим решением, уведомлением, историей и аудитом.

## 6. План интеграции и отката

1. Lead сохраняет за собой `main`, проверяет allowlist каждого агента командой `git diff --name-only main...codex/ai-jana` (и аналогично для B/C), а также `git diff --check`. Агент передаёт один или несколько локальных коммитов, не пушит `main` и не редактирует общие файлы.
2. Локальный порядок: **A → B → C**. После A проверить frontend production build и `backend/tests/test_academy_assistant.py`; после B — frontend build и `backend/tests/test_academy_management.py`; после C — frontend build и `backend/tests/test_academy_analytics.py`. Backend-тесты выполнять на временной SQLite, PostgreSQL — только в явно изолированной тестовой схеме после отдельной подготовки. Если агент изменил только UI, серверные тесты остаются регрессией контракта.
3. После всех объединений: полный backend pytest, свежая frontend сборка/TypeScript, `git diff --check`, затем браузерный сценарий **на отдельном тестовом стенде**; проверить A/B/C и критичный путь, отрицательные права, повторное завершение без второго XP. Не запускать мутационные browser scripts на сохранённой демо-БД. Затем проверить Docker Compose и облачный одно-контейнерный запуск на тестовых данных; реальный деплой оценивать отдельно после единственного push.
4. До push сверить удалённую `main`, просмотреть суммарный diff и убедиться, что нет секретов, БД, кэшей и чужих изменений. При новой удалённой ревизии остановиться и интегрировать её до push. Не использовать force push.

Команды **для будущей локальной интеграции** (Git Bash, после коммитов агентов; не выполнялись сейчас):

```bash
cd /c/Users/Dilnaz/digital-hr
git status --short                    # после baseline-коммита ожидать пусто; остальные изменения сначала разобрать
git diff --name-only main...codex/ai-jana
git merge --no-ff --no-edit codex/ai-jana
# выполнить проверки этапа A; при ошибке остановиться
git diff --name-only main...codex/academy
git merge --no-ff --no-edit codex/academy
# выполнить проверки этапа B; при ошибке остановиться
git diff --name-only main...codex/learning-analytics
git merge --no-ff --no-edit codex/learning-analytics
# выполнить проверки этапа C и полный регрессионный набор
git fetch origin main
git rev-list --left-right --count origin/main...HEAD   # слева должно быть 0; иначе остановиться
git diff --check origin/main..HEAD
git status --short
# handoff уже входит в baseline-коммит; после итоговой проверки Lead делает один push
git push origin main
```

При конфликте ещё не завершённого слияния: `git merge --abort`; проверить `git status` и вернуться к конфликту без удаления файлов. Если уже создан ошибочный последний merge-коммит, сохранить его SHA командой `BAD_MERGE=$(git rev-parse HEAD)`, затем выполнить `git revert -m 1 --no-edit "$BAD_MERGE"` и снова прогнать проверки. После автоматического деплоя отправлять только проверенный revert-коммит, без `reset --hard` и force push. Откат кода не откатывает миграции/данные: поэтому новые миграции здесь запрещены. Снимок/резервная копия рабочей БД перед любым будущим развёртыванием — задача Lead, не агентов.

**Последний безопасный срок для новых функций: воскресенье 18 октября, 08:00 по времени Казахстана** (за 8 часов до подачи в 16:00). После 08:00 — только интеграция, регрессионные проверки, презентация, запись демо и отправка работы. Если к этому времени хотя бы один агент не готов или основной сценарий красный, исключить незавершённую ветку из интеграции.
