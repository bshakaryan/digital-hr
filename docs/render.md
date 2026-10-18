# Запуск Digital HR на Render

Render запускает Docker-образы, а инфраструктуру из нескольких ресурсов описывает через Blueprint `render.yaml`. Команда `docker compose up` и файл `compose.yaml` на Render не выполняются. Для проекта подготовлены:

- [`render.yaml`](../render.yaml) — автоматически создаёт Docker Web Service, PostgreSQL 17, постоянный диск и связь `DATABASE_URL`.
- [`compose.render.yaml`](../compose.render.yaml) — локальная проверка того же Dockerfile с отдельным PostgreSQL; Render этот файл не читает.

## Что будет создано

| Ресурс | Конфигурация | Назначение |
| --- | --- | --- |
| `digital-hr-web` | Docker, `1c-2g`, Frankfurt | Next.js, FastAPI, worker, HTTP mock 1С:ЗУП и Documentolog |
| `digital-hr-postgres` | PostgreSQL 17, `0.1c-256mb`, диск 1 GB, Frankfurt | Профили, заявки, история, аудит, документы, Academy и диалоги AI Jana |
| Диск Web Service | `/var/data`, 1 GB | Только два mock SQLite-хранилища |

Это платная конфигурация. До нажатия Deploy Render показывает перечень ресурсов и стоимость; проверьте их в своём аккаунте. Web Service использует 2 GB RAM для нескольких процессов в одном контейнере; минимальный PostgreSQL выбран для демонстрации, нагрузочная ёмкость не подтверждена. Регион можно изменить до создания, одновременно в Web Service и базе. Диск привязан к одному экземпляру: горизонтальное масштабирование этой конфигурации не предусмотрено, при обновлениях возможен перерыв в доступности.

## Первый запуск

1. Файлы из этой инструкции должны быть опубликованы в `main` репозитория `https://github.com/bshakaryan/digital-hr.git`. Render получает исходники из GitHub, локальные изменения он не видит. Команды публикации приведены ниже.
2. Откройте [Render Dashboard](https://dashboard.render.com/) → **New → Blueprint**.
3. Подключите репозиторий **bshakaryan/digital-hr**. Если его нет в списке, предоставьте GitHub-приложению Render доступ к нему.
4. Выберите ветку **main**, Blueprint Path **render.yaml**, задайте название Blueprint, например `digital-hr`.
5. Проверьте, что Render создаёт Web Service `digital-hr-web`, базу `digital-hr-postgres` и диск `/var/data`. Проверьте стоимость, затем нажмите **Deploy Blueprint**.
6. Дождитесь статуса **Live** у Web Service. Его публичный HTTPS URL указан на странице сервиса; Render также предоставляет его приложению через `RENDER_EXTERNAL_URL`.
7. Откройте `digital-hr-web` → **Environment**, найдите `DEMO_PASSWORD` и раскройте значение. Пароль автоматически создаётся Render и используется для четырёх начальных демо-аккаунтов. `JWT_SECRET` тоже генерируется автоматически. `DATABASE_URL` связан с PostgreSQL через `fromDatabase`: вводить или копировать его вручную не требуется.
8. Откройте сайт и войдите как `hr@example.com`, `manager@example.com`, `employee@example.com` или `outsider@example.com` с этим паролем.

Можно перейти сразу к [созданию Blueprint из репозитория](https://render.com/deploy?repo=https://github.com/bshakaryan/digital-hr), когда `render.yaml` уже есть в GitHub. Перед запуском всё равно проверьте предлагаемые ресурсы.

При первом старте launcher проверяет настройки и права диска, поднимает mock-сервисы, выполняет `alembic upgrade head`, seed пустой базы, добавляет синтетический каталог Jana People, импортирует 11 исходных файлов и наполняет Academy существующими идемпотентными командами. Только после успешного завершения запускаются API, worker и интерфейс. Большой демонстрационный набор отпусков `app.provision_jana_people_leave` автоматически не запускается.

### Публикация подготовленных файлов в GitHub

Если изменения ещё находятся только локально, из корня репозитория на `main` проверьте и отправьте именно файлы этой задачи:

```sh
git status --short --branch
git add render.yaml compose.render.yaml .github/workflows/docker.yml \
  README.md docs/README.md docs/render.md docs/deployment.md \
  docs/decisions.md docs/implementation-plan.md docs/verification.md
git diff --cached --check
git diff --cached --stat
git commit -m "Add Render Blueprint deployment"
git fetch origin
git diff --stat origin/main HEAD
git push origin main
```

Перед коммитом проверьте staged diff: в нём должны быть только ожидаемые изменения. Если Git отклонит push из-за новых удалённых коммитов, сначала объедините изменения с `origin/main`; не используйте force push. Эти команды не переносят `.env`, локальные базы или содержимое Docker volumes.

## Если Web Service уже существует

Для простого отдельного запуска используйте новый Blueprint и проверьте в предпросмотре, что создаются новые ресурсы. Старый сервис и его данные оставьте до проверки нового сайта. Новый стек получает собственную базу; записи прежнего сервиса и локального Compose туда не переносятся. При совпадении имён ориентируйтесь на фактические имена и URL в Render, а не на предполагаемый адрес сайта.

Если нужно сохранить именно существующий сервис, его URL и данные, сначала выделите этот сервис в Dashboard → **Generate Blueprint** и согласуйте с `render.yaml` его имя, регион, тариф, существующий диск и подключение к базе. Не подключайте заполненный сервис к новой пустой базе в расчёте на автоматический перенос. Один ресурс должен управляться только одним Blueprint. Существующие дополнительные переменные Render может сохранить: проверьте старые `ZUP_BASE_URL`, `DOCUMENTOLOG_*` и `DATABASE_URL`, чтобы не использовать адреса локального Compose. Резервные копии основной базы и mock-хранилищ должны соответствовать одному состоянию.

## Проверка после деплоя и обновления

- Откройте `https://АДРЕС-САЙТА/api/health`: ожидается `{"status":"ok"}`.
- Войдите сотрудником, откройте профиль, Academy и AI Jana. Под HR проверьте каталог и раздел интеграций. Healthcheck проверяет доступность HTTP, поэтому вход и функциональные действия проверяются отдельно.
- Автоматический деплой кода отключён (`autoDeployTrigger: "off"`). После публикации обновлений в `main` откройте Web Service → **Manual Deploy → Deploy latest commit**. Изменение `render.yaml` применяется через Blueprint → **Manual Sync** либо включённый Auto Sync Blueprint; это отдельная настройка от автодеплоя кода.
- Повторный старт применяет миграции и идемпотентное наполнение, сохраняя существующие записи и учебный прогресс. Смена `DEMO_PASSWORD` в Environment не меняет пароли уже созданных аккаунтов. Повторная синхронизация Blueprint не должна заменять существующие сгенерированные секреты.
- Основные данные живут в PostgreSQL, mock-состояние — на диске `/var/data`. Перед заменой базы, диска или переносом сервиса сделайте резервные копии обоих хранилищ. Git не переносит пользовательские данные. Прежняя основная SQLite-база требует отдельного переноса.

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

Используется отдельный Compose project `digital-hr-render-local` и его volumes. Обычный локальный стек из `compose.yaml` продолжает работать отдельно. `down` сохраняет данные; `down -v` удаляет базу и mock-хранилища этого стенда. Локальная проверка не подтверждает доступ к вашему аккаунту Render, выделение ресурсов или успешный удалённый деплой.

Основание: [Render Blueprints](https://render.com/docs/infrastructure-as-code), [поля Blueprint](https://render.com/docs/blueprint-spec), [Docker](https://render.com/docs/docker), [постоянные диски](https://render.com/docs/disks).
