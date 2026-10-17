# Docker-комплект для сервера

## Один Docker Web Service и внешний PostgreSQL на Render

Корневой `Dockerfile` собирает Next.js, FastAPI, worker и два HTTP mock-сервиса в один web-контейнер. Основная БД всегда PostgreSQL, запущенный отдельно. Compose также использует PostgreSQL и отдельные сервисы. HTTP-маршруты `/api` и браузерная форма mock Documentolog проксируются через один внешний порт.

Для существующего Web Service в Render:

- Создайте или подключите Render Postgres в том же аккаунте и регионе. В Environment Web Service задайте `DATABASE_URL` из Internal Database URL. Поддерживаются `postgres://`, `postgresql://` и `postgresql+psycopg://`; launcher выбирает установленный psycopg 3, сохраняя адрес, пароль и параметры, включая `sslmode`.
- Runtime: Docker; Root Directory: пустое поле (корень Git-репозитория).
- Dockerfile Path: `./Dockerfile`; Docker Build Context: `.`; Docker Command: пустое поле, чтобы использовать `CMD` образа.
- Environment: задайте `JWT_SECRET` минимум 32 случайных символа и `DEMO_PASSWORD` минимум 12 символов. Дополнительные `ZUP_API_TOKEN` и `DOCUMENTOLOG_API_KEY` поддерживаются; иначе в этом демо применяется JWT-секрет. Значения не включаются в Git или образ.
- Health Check Path: `/api/health`. Next.js слушает `0.0.0.0:$PORT`; внутренние сервисы слушают только loopback. Render задаёт `PORT` и `RENDER_EXTERNAL_URL`; последний используется для ссылок на mock Documentolog.
- Для сохранения mock-данных подключите persistent disk с Mount Path `/var/data`. Здесь находятся только `zup.sqlite3` и `documentolog.sqlite3`. Основные данные backend хранятся в PostgreSQL. Без диска состояние mock-сервисов теряется при замене контейнера, поэтому полноценной сохранности демо нет.

`DATABASE_URL` обязателен. Удалите старое значение `sqlite:///...` и замените его URL PostgreSQL: без URL или с SQLite запуск завершится с диагностикой до создания mock-хранилищ. Локального fallback нет. Недоступный PostgreSQL останавливает запуск на миграциях. Launcher подготавливает каталоги и права только для двух mock-файлов и проверяет запись от UID приложения до запуска сервисов.

Если в предыдущем деплое основная БД уже была SQLite, сохраните её резервную копию. Смена URL не переносит записи: миграции обновляют схему выбранного PostgreSQL, а пустая база получает новый демо-seed. Перенос прежних заявок/истории/аудита и сверка с mock-хранилищами — отдельная явная операция. Старые SQLite-файлы не удаляются и не перезаписываются как новая основная база.

После настройки выполните Deploy latest commit. Корневой образ применяет миграции при каждом старте и создаёт демо-профили только в пустой базе. Миграция 0008 исправляет последовательности после явных seed ID, сохраняя строки и достигнутые значения ID. Перезапуск заполненной базы не восстанавливает специально удалённые начальные заявки. При завершении дочернего процесса launcher останавливает контейнер; SIGTERM останавливает все процессы.

Локальная проверка аналогичного запуска:

```sh
docker build -t digital-hr-web .
# .env.web содержит секреты и DATABASE_URL PostgreSQL, достижимого из контейнера.
docker run --rm --env-file .env.web -e PORT=10000 \
  -e RENDER_EXTERNAL_URL=http://localhost:10000 \
  -p 127.0.0.1:10000:10000 -v digital_hr_web_mock_data:/var/data digital-hr-web
```

Адрес `127.0.0.1` внутри контейнера относится к самому контейнеру. Для PostgreSQL на Docker Desktop используйте `host.docker.internal`, для базы в Docker-сети — её сетевое имя и ту же сеть (`--network`), для внешнего PostgreSQL — доступный hostname. Не передавайте URL mock-сервисов Compose (`backend`, `zup-mock`, `documentolog-mock`) в одиночный web-контейнер. Корневой образ предназначен для mock-демонстрации; для реальных интеграций используйте отдельные сервисы.

Основание для настроек хостинга: [Render Postgres: подключение](https://render.com/docs/postgresql-creating-connecting), [Docker on Render](https://render.com/docs/docker), [Persistent Disks](https://render.com/docs/disks).

## Комплект для Docker Compose

Комплект содержит готовые образы backend, frontend и PostgreSQL, самостоятельный `compose.json`, `deploy.sh` и генератор секретов. Backend-образ также запускает миграции, worker и оба mock-сервиса. Сборка по умолчанию предназначена для Linux `amd64`; данные и секреты локального стенда в неё не входят.

## Сборка из Git

На машине сборки нужны Docker с Buildx, Compose и Python 3. Из корня репозитория:

```sh
./scripts/build-deploy.sh
# Для ARM-сервера:
PLATFORM=linux/arm64 ./scripts/build-deploy.sh
```

Результат — `dist/digital-hr-<revision>-<architecture>.tar.gz`. Каталог `dist/` игнорируется Git. `revision.txt` и OCI-метки образов содержат ревизию исходников. В комплект копируется только `.env.example` с заглушками; настоящий `.env` не копируется. Сборщик не перезапускает работающий локальный стенд.

## Запуск на сервере

Нужен Docker Engine с Compose v2, поддерживающим `up --wait`. Перенесите архив на сервер, затем:

```sh
tar -xzf digital-hr-<revision>-amd64.tar.gz
cd digital-hr-<revision>-amd64
./deploy.sh
docker compose -p digital-hr -f compose.json ps -a
```

`deploy.sh` загружает образы из `images.tar`, создаёт `.env` с уникальными секретами и правами `0600`, если его ещё нет, затем поднимает стек без сборки и скачивания образов. Для уже созданного `.env` значения сохраняются. Демо-пароль хранится в `DEMO_PASSWORD`. Стек по умолчанию использует mock 1С:ЗУП и mock Documentolog; миграция на новой базе создаёт демо-профили, курс и примеры заявок. Перенос существующей базы и остатка дней выполняется отдельно, volume в архив не включены.

Интерфейс слушает `127.0.0.1:3000`, API — `127.0.0.1:8001`, mock Documentolog — `127.0.0.1:8400`; PostgreSQL снаружи не публикуется. Для доступа с другого компьютера можно использовать SSH-туннель:

```sh
ssh -L 3000:127.0.0.1:3000 -L 8400:127.0.0.1:8400 user@server
```

После этого откройте `http://localhost:3000`. Для домена настройте HTTPS reverse proxy на `127.0.0.1:3000`. Браузерные запросы `/api` уже проксирует Next.js. При публикации mock Documentolog задайте его внешний URL в `DOCUMENTOLOG_BROWSER_URL` внутри `.env` и перезапустите `./deploy.sh`; для SSH-туннеля остаётся localhost. Порты меняются через `WEB_PORT`, `API_PORT` и `DOCUMENTOLOG_PORT` в `.env`.

## Обновление и сохранение данных

Для обновления распакуйте новый комплект, перенесите существующий серверный `.env` с сохранением прав `0600` и запустите `./deploy.sh`. Сохраняйте одинаковое имя проекта (`digital-hr`, либо явное `DEPLOY_PROJECT`): от него зависят имена трёх volume. Перед обновлением сохраните резервные копии PostgreSQL и двух mock-хранилищ. Не используйте `down -v` для остановки с сохранением данных. Повтор demo seed может восстановить отсутствующие начальные примеры; он не предназначен для сохранения специально очищенного набора данных.

```sh
docker compose -p digital-hr -f compose.json logs --tail=100 backend frontend migrate
docker compose -p digital-hr -f compose.json down
```

Этот комплект упаковывает текущий демонстрационный продукт. Настоящие интеграции, ЭЦП, SSO, домен и TLS на сервере требуют отдельной настройки. Фактические проверки сборки и запуска описаны в `docs/verification.md` репозитория.
