# Запуск Digital HR на Render

Render запускает Docker-образы, а инфраструктуру из нескольких ресурсов описывает через Blueprint `render.yaml`. Команда `docker compose up` и файл `compose.yaml` на Render не выполняются. Для проекта подготовлены:

- [`render.yaml`](../render.yaml) — бесплатное временное демо: Free Web Service и Free PostgreSQL 17 со связью `DATABASE_URL`.
- [`render.paid.yaml`](../render.paid.yaml) — отдельный платный вариант с постоянным mock-диском.
- [`compose.render.yaml`](../compose.render.yaml) — локальная проверка бесплатного варианта: web с лимитом 512 MB, отдельный PostgreSQL и временные mock-файлы. Render этот файл не читает.

## Что будет создано

| Ресурс | Конфигурация | Назначение |
| --- | --- | --- |
| `digital-hr-web` | Docker, Free, 512 MB RAM, Oregon | Next.js, FastAPI, worker, HTTP mock 1С:ЗУП и Documentolog |
| `digital-hr-postgres` | PostgreSQL 17, Free, 1 GB, Oregon | Профили, заявки, история, аудит, документы, Academy и диалоги AI Jana |
| Mock-файлы | Временный `/var/data`, без persistent disk | Два mock SQLite-хранилища на срок жизни контейнера |

Стоимость compute/storage этой конфигурации — $0 в пределах бесплатных лимитов Render. Перед Deploy убедитесь, что оба тарифа обозначены Free, persistent disk отсутствует и платные дополнения отключены. Регион можно изменить до создания одновременно у Web Service и базы. В аккаунте разрешена только одна Free PostgreSQL; её срок — 30 дней. Сайт засыпает после 15 минут без входящих запросов, следующий запуск может занять около минуты или дольше из-за подготовки приложения. Нагрузочная ёмкость бесплатного стенда не заявляется.

Основные данные сохраняются в PostgreSQL до истечения срока базы, но локальные квитанции mock ЗУП и сессии mock Documentolog теряются при замене контейнера или его остановке Render. Старые подтверждённые заявки в PostgreSQL сохраняются; наличие их квитанции в сброшенном mock-сервисе не гарантируется. Для последовательного показа создания, согласования, подписи и отмены выполняйте сценарий в одной активной сессии сервера. Перед демонстрацией откройте сайт и проверьте `/api/health` и вход. Превышение лимитов трафика/сборок при добавленном способе оплаты может тарифицироваться отдельно — это не безлимитный тариф.

## Первый запуск

1. Файлы из этой инструкции должны быть опубликованы в `main` репозитория `https://github.com/bshakaryan/digital-hr.git`. Render получает исходники из GitHub, локальные изменения он не видит. Команды публикации приведены ниже.
2. Откройте [Render Dashboard](https://dashboard.render.com/) → **New → Blueprint**.
3. Подключите репозиторий **bshakaryan/digital-hr**. Если его нет в списке, предоставьте GitHub-приложению Render доступ к нему.
4. Выберите ветку **main**, Blueprint Path **render.yaml**, задайте название Blueprint, например `digital-hr`.
5. Проверьте, что Render создаёт Web Service `digital-hr-web` и базу `digital-hr-postgres`, оба на тарифе **Free**, без диска и платных дополнений. Затем нажмите **Deploy Blueprint**.
6. Дождитесь статуса **Live** у Web Service. Его публичный HTTPS URL указан на странице сервиса; Render также предоставляет его приложению через `RENDER_EXTERNAL_URL`.
7. Откройте `digital-hr-web` → **Environment**, найдите `DEMO_PASSWORD` и раскройте значение. Пароль автоматически создаётся Render и используется для четырёх начальных демо-аккаунтов. `JWT_SECRET` тоже генерируется автоматически. `DATABASE_URL` связан с PostgreSQL через `fromDatabase`: вводить или копировать его вручную не требуется.
8. Откройте сайт и войдите как `hr@example.com`, `manager@example.com`, `employee@example.com` или `outsider@example.com` с этим паролем.

Можно перейти сразу к [созданию Blueprint из репозитория](https://render.com/deploy?repo=https://github.com/bshakaryan/digital-hr), когда `render.yaml` уже есть в GitHub. Перед запуском всё равно проверьте предлагаемые ресурсы.

При первом старте launcher проверяет настройки и права диска, поднимает mock-сервисы, выполняет `alembic upgrade head`, seed пустой базы, добавляет синтетический каталог Jana People, импортирует 11 исходных файлов и наполняет Academy существующими идемпотентными командами. Только после успешного завершения запускаются API, worker и интерфейс. Текущее демо подготавливается автоматически командой `app.provision_demo_workspace` после Academy; Айдана исключена из календаря, прежние активные периоды освобождаются только при первом запуске.

### Публикация подготовленных файлов в GitHub

Если изменения ещё находятся только локально, из корня репозитория на `main` проверьте и отправьте именно файлы этой задачи:

```sh
git status --short --branch
git add render.yaml render.paid.yaml compose.render.yaml .github/workflows/docker.yml \
  README.md docs/README.md docs/render.md docs/deployment.md \
  docs/decisions.md docs/implementation-plan.md docs/verification.md
git diff --cached --check
git diff --cached --stat
git commit -m "Configure free Render demo deployment"
git fetch origin
git diff --stat origin/main HEAD
git push origin main
```

Перед коммитом проверьте staged diff: в нём должны быть только ожидаемые изменения. Если Git отклонит push из-за новых удалённых коммитов, сначала объедините изменения с `origin/main`; не используйте force push. Эти команды не переносят `.env`, локальные базы или содержимое Docker volumes.

## Если Web Service уже существует

Для сохранения прежнего адреса сайта новый Web Service создавать не требуется:

1. Оставьте Web Service на тарифе **Free**.
2. Через **New → Postgres** создайте **Free** PostgreSQL 17 в том же регионе. Не выбирайте платные compute или дополнительные услуги.
3. После статуса **Available** возьмите **Internal Database URL** из раздела Connections. Во входящих IP-правилах PostgreSQL можно заблокировать внешний интернет; внутреннее подключение Web Service в том же регионе продолжит работать.
4. В Web Service → **Environment → Edit** замените только `DATABASE_URL` на этот полный адрес. Сохраните существующие `JWT_SECRET`, `DEMO_PASSWORD` и интеграционные секреты. Адрес `postgres` из локального Compose в Render не работает.
5. Выберите **Save, rebuild, and deploy**. Миграции и первоначальное наполнение выполняются автоматически; после **Live** проверьте `/api/health` и вход на прежнем URL.

Подключение к новой базе не переносит старые записи. Для текущего демо пользователь разрешил новую базу без переноса прежней облачной SQLite. Для другого заполненного сервиса такое согласие требуется отдельно: free-контейнер не даёт Shell и не сохраняет SQLite при перезапуске. Не обновляйте заполненный сервер в расчёте на автоматический перенос.

Чтобы управлять существующим сервисом через Blueprint, сначала используйте **Generate Blueprint** и согласуйте его имя, регион и переменные. Один ресурс не должен управляться несколькими Blueprint. Новый Blueprint с другим именем может создать другой сайт вместо изменения старого.

## Если нужно постоянное хранение mock-интеграций

Используйте `render.paid.yaml` только после подтверждения расходов. Он задаёт Web Service `1c-2g` (2 GB), PostgreSQL `0.1c-256mb` с 1 GB storage и mock-диск 1 GB в `/var/data`. По тарифам, проверенным 18 октября 2026, базовая стоимость — $25 + $6 + $0.30 + $0.25 = $31.55/мес без дополнительных объёмов трафика/сборок. Более дешёвые compute требуют отдельной проверки ресурсов приложения. Уплачивать или активировать этот вариант для временного Free-демо не нужно.

## Проверка после деплоя и обновления

- Откройте `https://АДРЕС-САЙТА/api/health`: ожидается `{"status":"ok"}`.
- Войдите сотрудником, откройте профиль, Academy и AI Jana. Под HR проверьте каталог и раздел интеграций. Healthcheck проверяет доступность HTTP, поэтому вход и функциональные действия проверяются отдельно.
- Автоматический деплой кода отключён (`autoDeployTrigger: "off"`). После публикации обновлений в `main` откройте Web Service → **Manual Deploy → Deploy latest commit**. Изменение `render.yaml` применяется через Blueprint → **Manual Sync** либо включённый Auto Sync Blueprint; это отдельная настройка от автодеплоя кода.
- Повторный старт применяет миграции и идемпотентное наполнение, сохраняя существующие записи и учебный прогресс. Смена `DEMO_PASSWORD` в Environment не меняет пароли уже созданных аккаунтов. Повторная синхронизация Blueprint не должна заменять существующие сгенерированные секреты.
- Основные данные живут в PostgreSQL. В Free-варианте mock-состояние в `/var/data` временное; только платный вариант подключает постоянный диск. Перед истечением 30 дней экспортируйте нужные основные данные либо перенесите их в другую базу. Автоматических резервных копий Free PostgreSQL нет. Git не переносит пользовательские данные.

При ошибке `DATABASE_URL must name a PostgreSQL database` откройте Environment: Blueprint должен ссылаться на `digital-hr-postgres`, а не на `sqlite:///...`. При недоступной базе убедитесь, что оба ресурса в одном регионе и база готова. Если старт завершился после миграций, посмотрите последнюю ошибку импорта или наполнения в **Logs**. Очищать build cache для исправления переменных среды не требуется.

LLM по умолчанию отключён; извлекающий AI Jana работает по загруженным материалам. Для внешней генерации настройте секреты по [ai-jana-llm.md](ai-jana-llm.md) в Environment Web Service. Корневой образ предназначен только для mock-интеграций.

## Локальная проверка через Compose

Нужен запущенный Docker с Compose v2. Если `.env` уже существует, сохраните его. Если отсутствует, создайте штатным генератором (из корня репозитория):

```sh
docker run --rm --user "$(id -u):$(id -g)" \
  --mount "type=bind,source=$(pwd),target=/workspace" --workdir /workspace \
  python:3.12-slim python scripts/setup_env.py
```

Затем выполните:

```sh
docker compose -f compose.render.yaml config --quiet
docker compose -f compose.render.yaml up --build -d --wait --wait-timeout 600
docker compose -f compose.render.yaml ps
curl --fail http://localhost:10000/api/health
```

Откройте `http://localhost:10000`, пароль возьмите из локального `.env`. При занятом порте используйте `RENDER_WEB_PORT=10100 docker compose -f compose.render.yaml up --build -d --wait --wait-timeout 600`.

```sh
docker compose -f compose.render.yaml logs -f web
docker compose -f compose.render.yaml down
```

Используется отдельный Compose project `digital-hr-render-local` с собственным PostgreSQL volume. Обычный локальный стек из `compose.yaml` продолжает работать отдельно. `down` сохраняет PostgreSQL, но удаляет временные mock-файлы вместе с web-контейнером; `down -v` дополнительно удаляет PostgreSQL этого стенда. Локальная проверка не подтверждает лимиты/сроки аккаунта Render, сеть провайдера или успешный удалённый деплой.

Основание: [бесплатные лимиты Render](https://render.com/docs/free), [Render Blueprints](https://render.com/docs/infrastructure-as-code), [поля Blueprint](https://render.com/docs/blueprint-spec), [Docker](https://render.com/docs/docker), [постоянные диски](https://render.com/docs/disks), [стоимость ресурсов](https://render.com/pricing).

Текущее демо (18 октября): после Academy launcher выполняет `app.provision_demo_workspace` до старта API/worker: 25 доступных дней каждому из 34 синтетических сотрудников после наполнения календаря без Айданы и помеченная учебная активность за 14 дней. Чекпоинты/allowance в PostgreSQL защищают новые ручные заявки от повторного сброса. При потере mock-файла восстанавливаются подтверждённые квитанции ЗУП; Documentolog остаётся временным. Подробности — docs/README.md.
