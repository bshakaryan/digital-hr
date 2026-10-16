# JanaМен Digital HR

Адаптивный HR-прототип для второго кейса Jana Post × Terricon Valley. Next.js + FastAPI, SQLAlchemy и PostgreSQL; SQLite — для быстрого локального запуска и тестов.

Сценарий: вход → read-only профиль → заявка на отпуск → решение руководителя/HR → уведомление. Дополнительно: назначенный курс с тестом и помощник с источниками из демонстрационной базы.

## Запуск в Docker

Нужны Git и запущенный Docker с Compose v2. Python, Node.js и PostgreSQL на компьютере устанавливать не нужно.

```bash
git clone https://github.com/bshakaryan/digital-hr.git
cd digital-hr
./scripts/docker-up.sh
```

Скрипт создаёт `.env` с уникальными секретами через временный Python-контейнер, затем выполняет `docker compose up --build --detach --wait`. Существующий `.env` сохраняется. При ошибке сборки, миграции или healthcheck команда завершится с ошибкой. Для Windows запускайте скрипт в WSL2 либо подготовьте `.env` через `python scripts/setup_env.py` и выполните `docker compose up --build -d --wait`.

Откройте http://localhost:3000. Документация backend: http://localhost:8000/docs. Compose ждёт PostgreSQL, применяет миграции и заполняет демонстрационные данные, после чего запускает backend и frontend. Повторный запуск не сбрасывает существующие записи и пароли. Данные PostgreSQL сохраняются в именованном volume. Не используйте down -v, если хотите сохранить данные.

Если стандартные порты заняты:

```bash
WEB_PORT=3100 API_PORT=8100 ./scripts/docker-up.sh
```

В этом случае интерфейс доступен на http://localhost:3100, API — http://localhost:8100/docs. Чтобы сохранить выбор, добавьте `WEB_PORT=3100` и `API_PORT=8100` в `.env`. Браузер обращается к API через тот же origin интерфейса; адрес `backend` используется только внутри Docker. Порты опубликованы на loopback компьютера, PostgreSQL наружу не публикуется.

Управление из каталога проекта:

```bash
docker compose ps -a
docker compose logs -f backend frontend
docker compose down
```

`down` останавливает контейнеры, сохраняя базу; для следующего запуска используйте тот же скрипт. При смене каталога или Compose project name используется другой volume. Изменение `POSTGRES_PASSWORD` в `.env` не меняет пароль уже созданной базы; `DEMO_PASSWORD` также не меняет пароли существующих аккаунтов. Не подставляйте значения-заглушки из `.env.example` вместо генерации секретов.

## Учётные записи

Все имена, профили и кадровые данные вымышленные. Пароль для всех первоначально создаваемых аккаунтов — значение DEMO_PASSWORD из вашего локального .env. Пароль не зашит в исходники и не выводится в логи.

| Почта | Роль | Что можно проверить |
| --- | --- | --- |
| employee@example.com | Сотрудник | Свой профиль, заявки и курс |
| manager@example.com | Руководитель | Заявки сотрудника employee; запрет согласования собственной заявки |
| hr@example.com | HR | Все демо-заявки, решения, журнал через /api/audit |
| outsider@example.com | Сотрудник другого отдела | Изоляция от команды руководителя |

## Локальный запуск без Docker

Backend: Python 3.12+; frontend: Node.js 22+ и npm. Из корня проекта:

```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.lock
python3 scripts/setup_env.py
PYTHONPATH=backend .venv/bin/alembic -c backend/alembic.ini upgrade head
PYTHONPATH=backend .venv/bin/python -m app.seed
PYTHONPATH=backend .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Если .env уже создан, пропустите setup_env.py. В отдельном терминале:

```bash
cd frontend
npm ci
npm run dev
```

По умолчанию используется локальная SQLite jana.db. Для PostgreSQL задайте DATABASE_URL в окружении или .env и примените те же команды миграции/seed. Не переключайте URL, рассчитывая на автоматический перенос данных: миграции создают/обновляют схему в выбранной БД, перенос записей — отдельная операция.

## Проверки

Проверки полностью внутри Docker для уже запущенного стека:

```bash
docker compose exec -T backend python -m pytest -q
docker compose exec -T backend python - < scripts/compose_smoke.py
```

Первый набор проверяет регрессии на изолированных SQLite-базах. Второй проходит через Next.js `/api` proxy к FastAPI и PostgreSQL: вход четырёх ролей, права, создание/повтор/решение заявки, уведомления, курс, источники помощника. Затем сравнивает все прикладные таблицы до и после повторных миграции и seed. Он создаёт вымышленные заявки и завершает демо-курс; запускайте на демонстрационных данных без параллельных действий пользователей. Это функциональная проверка, не проверка конкурентных блокировок PostgreSQL. Тот же запуск и повторный подъём с сохранённым volume настроены в `.github/workflows/docker.yml`.

Проверки без Docker:

```bash
cd backend
../.venv/bin/python -m pytest -q
```

```bash
cd frontend
npm run typecheck
npm run build
```

Фактические результаты и ограничения: [docs/verification.md](docs/verification.md).

Браузерный сценарий для уже запущенной локальной платформы (использует DEMO_PASSWORD из .env и создаёт демонстрационную заявку):

```bash
npm install --prefix frontend --no-save --package-lock=false playwright
cd frontend
npx playwright install chromium
cd ..
node scripts/browser_smoke.mjs
```

Runner и снимки не входят в production-образ. Снимки сохраняются в игнорируемый frontend/.qa/browser-smoke. При установленном внешнем Playwright можно указать PLAYWRIGHT_PACKAGE вместо дополнительной установки. Тест рассчитан на исходные демо-имена и назначенный seed-курс.

## Границы первой версии

- Решения по заявке принимаются внутри прототипа. Упрощённый маршрут согласования — предположение MVP, не кадровая политика. Остаток отпуска не списывается и не рассчитывается.
- Данные 1С:ЗУП смоделированы seed-адаптером. Documentolog представлен интерфейсом будущей интеграции; документы наружу не отправляются.
- Помощник работает в mode=extractive_demo: извлекает подготовленный текст и возвращает источник либо отказ. Генеративный LLM, embeddings и pgvector пока не подключены. Для фактического AI-требования кейса следующий этап — оценённый RAG с разрешённым провайдером.
- Нет SSO, электронной подписи, полноценной LMS, внешних push/email, RU/KZ-переключателя и production-эксплуатации. Нет обещаний работы на реальном телефоне без отдельной проверки.
- JWT живёт 60 минут; frontend держит токен в памяти, перезагрузка требует нового входа. Для production нужны SSO/сессионная политика, ограничения частоты входа, TLS и операционные настройки.

[Архитектура](docs/architecture.md) · [Контракт API](docs/api-contract.md) · [Решения и открытые вопросы](docs/decisions.md) · [План и делегирование](docs/implementation-plan.md)
