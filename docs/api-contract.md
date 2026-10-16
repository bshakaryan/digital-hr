# API Digital HR v0.3

Наличие маршрутов проверяется тестами и OpenAPI; статус реализации перечислен в verification.md. Префикс /api. JSON, даты YYYY-MM-DD, время UTC ISO 8601. Bearer JWT для всех маршрутов кроме login, health и capability-маршрутов Documentolog ниже. Ошибки: {"detail": "сообщение"}; валидация FastAPI — detail массив.

## Вход и профиль

- POST /api/auth/login — {email, password} → {access_token, token_type:"bearer"}.
- GET /api/me → {id:number, email, full_name, role:"employee"|"manager"|"hr_admin", company, position, department, manager_id:number|null, manager_name:string|null, hire_date, leave_balance:number, data_source:"mock_zup"|"zup"}. `leave_balance` — текущий остаток из настроенного HTTP-источника 1С:ЗУП минус локальные списания, которые источник ещё не подтвердил по ключу команды. Исходные кадровые поля не перезаписываются. Недоступный источник → 503; несопоставленный профиль → 409. Имя руководителя является частью разрешённого собственного профиля; полный профиль руководителя сотруднику не раскрывается.
- GET /api/employees → массив тех же профилей: сотруднику только свой, руководителю свой и прямые подчинённые, HR все.
- GET /api/employees/{id} → профиль; недоступный id возвращает 404.

## Заявки

- GET /api/requests → массив доступных заявок, новые первыми.
- GET /api/requests/review-queue → только заявки, по которым текущий пользователь вправе принять решение, старые этапы первыми. Сотруднику — пустой массив; руководителю — `submitted` прямых подчинённых; HR — `manager_approved` и `cancellation_requested`, кроме собственных. `can_review` вычисляет сервер во всех ответах заявок.
- POST /api/requests/calculate — {start_date,end_date,comment?:string}; только для текущего пользователя. Возвращает {start_date,end_date,days_count,calendar_days,excluded_dates:string[],calendar_version,available_balance,balance_after,sufficient_balance,source:"mock_zup_http"|"zup_http"}. В mock-режиме действуют демонстрационные правила ниже; в real-режиме дни, исключения и версию календаря возвращает опубликованный сервис 1С. Недоступность источника → 503, неподдерживаемый период/неверный порядок/ноль списываемых дней → 422. Недостаточный остаток показывается `sufficient_balance=false`, отрицательный `balance_after` — прогноз нехватки. Расчёт ничего не резервирует и не создаёт заявку.

Пересечение с действующей локальной заявкой или зарегистрированным отпуском источника при расчёте → 409.
- POST /api/requests — заголовок Idempotency-Key обязателен (8–128 символов); тело {start_date,end_date,comment:string}; результат 201. Сервер заново запрашивает расчёт и сохраняет его снимок. Ненастроенный руководитель, недостаточный остаток или пересечение с submitted/manager_approved/approved своего сотрудника → 409 без создания. При недоступности источника → 503; клиентский days_count/employee_id не принимается.
- GET /api/requests/{id} → доступная заявка.
- PATCH /api/requests/{id}/status — {status:"approved"|"rejected",version:number,comment:string}. Для `submitted` решение принимает только непосредственный руководитель: `approved` переводит заявку в `manager_approved`, `rejected` завершает её. Для `manager_approved` решение принимает только HR: `approved` атомарно создаёт списание и outbox, `rejected` завершает заявку без списания. Перед списанием сервер повторно проверяет расчёт и доступный остаток под блокировкой сотрудника. Нехватка дней, новый календарь или пересечение с одобренным периодом → 409; источник недоступен → 503; заявка остаётся `manager_approved`. Исторические ожидающие заявки получают актуальный расчёт при финальном решении. Автор не может согласовывать свою заявку; неверный этап или устаревшая version → 409. После commit выполняется попытка доставки: её ошибка сохраняет решение HR и очередь, отражается `zup_sync_status="error"` в успешном ответе.
- POST /api/requests/{id}/sync — только HR, повторяет сохранённую команду. Возвращает заявку; доставка уже подтверждена → безопасный повтор, команда отсутствует → 409. Отказ/таймаут внешней системы сохраняется в очереди для повторной попытки. Worker повторяет автоматически с задержкой до 300 секунд.

Заявка: {id,employee_id,employee_name,type:"leave",start_date,end_date,days_count:number,excluded_dates:string[],calendar_version:string,zup_sync_status:"not_required"|"pending"|"synced"|"error"|"legacy",zup_reference:string|null,comment,status:"submitted"|"manager_approved"|"approved"|"rejected",version:number,created_at,history:[{status,actor_name,comment,created_at}]}.

`legacy` означает историческое одобрение без новой команды доставки. Такой статус не выдаётся за успешную передачу. Статусы бизнес-согласования и доставки независимы.

Дополнительные поля v0.3: `calendar_days` — длина периода включительно; `days_count` — дни к списанию; `can_review:boolean`; `cancellation_allowed:boolean`, `cancellation_block_reason:string|null`; `cancellation_sync_status:null|pending|synced|error`, `cancellation_reference:string|null`. Расширенные `status` заявки и истории: также `withdrawn|cancellation_requested|cancelled`. У `approved` после `cancellation_requested` смысл «HR отклонил отмену, отпуск сохранён».

### Отзыв, замена дат и отмена (демонстрационный процесс)

Все команды ниже, кроме расчёта и повтора передачи, требуют `Idempotency-Key` (8–128 символов). Ключ уникален в рамках автора команды. Повтор той же команды возвращает тот же объект/ID с его текущим состоянием; другое тело, операция или исходная заявка с тем же ключом → 409. Изменение выполняется с `version`, устаревшая версия → 409. История, аудит, уведомления и ключ команды записываются атомарно. Собственные действия не предоставляют права согласования.

- POST /api/requests/{id}/withdraw — `{version,comment}` с непустой причиной. Только автор, только `submitted|manager_approved` → `withdrawn`; остаток не меняется. Уведомляются автор, руководитель и (если этап HR уже начался) HR. Период освобождается.
- POST /api/requests/{id}/replacement-calculation — `{start_date,end_date,comment?}`, только автор ожидающей заявки. Расчёт как `/calculate`, но собственная заменяемая заявка исключена из локальной проверки пересечения; записей не создаёт.
- POST /api/requests/{id}/replace — `{start_date,end_date,comment,version}`; только автор ожидающей заявки. Результат 201 — новая заявка `submitted`; исходная атомарно становится `withdrawn`, прежние даты и история сохраняются. Оба человеческих этапа проходятся заново. Ошибка расчёта не отзывает исходную заявку.
- POST /api/requests/{id}/cancel — `{version,comment}` с непустой причиной; только автор `approved` → `cancellation_requested`. Поддерживается полная отмена до начала отпуска, только mock ЗУП, при наличии исходной команды передачи и отсутствии любого сохранённого Documentolog-документа. Иначе 409. Списанные дни остаются учтёнными; период продолжает блокировать пересечения.
- POST /api/requests/{id}/cancellation-decision — `{status:"approved"|"rejected",version,comment}`; только HR, кроме автора, комментарий обязателен. `rejected` возвращает `approved` без изменения учёта; `approved` переводит в `cancelled` и атомарно сохраняет неизменяемую команду возврата в `leave_cancellations`. После commit выполняется доставка. Ошибка источника не отменяет решение HR, `cancellation_sync_status="error"` и автоматический повтор сохраняются. Дни доступны только после отражения возврата источником.
- POST /api/requests/{id}/cancellation-sync — только HR; безопасный повтор сохранённой команды возврата. Команды нет → 409. Worker обрабатывает возвраты с задержкой до 300 секунд; первоначальная регистрация завершается перед отменой, если её квитанция потерялась. Постоянные ключи обеих команд исключают повторное списание/возврат.

Отозванные и отменённые заявки не блокируют локальную проверку пересечения. Пока источник не подтвердил отмену, он ещё может блокировать период и не возвращает дни. Новый период одобренного отпуска оформляется новой заявкой после отмены. Исторические одобрения, частичная отмена, начавшийся отпуск, аннулирование Documentolog и реальная отмена ЗУП требуют отдельного контракта/процесса; Q01–Q07 не считаются закрытыми.

`calendar_version="legacy-deducted"` сохраняет число ранее списанных дней по прежнему правилу. Для него `excluded_dates=[]`; современный календарь не переопределяет исторический расчёт.

Повтор POST /api/requests с тем же ключом и телом возвращает тот же id (201); другое тело — 409. Создание и промежуточное согласование не резервируют остаток; поэтому конкурирующая ожидающая заявка может получить 409 при финальном решении HR. Повтор финального решения не создаёт второе списание. Документ в Documentolog создаётся отдельной явной командой HR после одобрения.

## Documentolog

- GET /api/requests/{id}/documentolog — доступ по видимости заявки; `{status,mode,external_id?,view_url?,file_sha256?,last_error?,expires_at?}`. Режим `disabled|mock|real`; статус `not_created|prepared|creating|signing|completed_reported|completed|declined|needs_review`. `completed` — завершённая **имитация** в mock; `completed_reported` — непроверенное сообщение реального сервиса, не подтверждённая ЭЦП.
- POST /api/requests/{id}/documentolog — только HR, только approved, собственная заявка HR → 403; тело `{recipient?:string}`. Mock использует demo-email, real требует ИИН из 12 цифр. Сохраняет DOCX, SHA-256 и команду, затем однократно создаёт сессию. Возвращает статус и `session_url:string|null`. Повтор возвращает прежнюю команду, другой получатель → 409. При таймауте статус `needs_review`, повторной отправки нет; падение после начала оставляет `creating`, требуется сверка. Режим старой команды не меняется автоматически. Одно заявление на заявку.
- GET /api/requests/{id}/documentolog/session — только HR; `{url,mode}`, ссылка сессии инициатора. Нет подтверждённой сессии → 409; срок истёк → 404. Не содержит сервисного API-ключа.
- GET /api/documentolog/files/{token} — без JWT, отдельный случайный capability-токен; сохранённый DOCX, `no-store`, срок 30 дней. Неизвестный/просроченный токен → 404.
- POST /api/documentolog/webhook/{token} — без JWT, другой случайный capability-токен; `{event,doc_id,document?:URL,...}`. Принимает `document_sent|signer_signed|signer_declined|document_completed`. Подпись участника не завершает документ. Другой doc_id → 409, неизвестное событие → 422. Повтор не создаёт второй эффект; завершённый статус не ухудшается запоздавшими событиями. Разрешённая ссылка — только origin Documentolog. В real-режиме событие завершения требует проверки HR. Не меняет решение, остаток и передачу в ЗУП.
- GET /api/integrations/documentolog — только HR; `{mode,connected,provider,counts,real_connection_verified:false}`. В mock `connected` проверяется через HTTP `/health`. Для real конфигурация не выдаётся за проверенное соединение: без документированного read-only probe не выполняет создающий запрос.

В аудите: `documentolog.prepared`, `creation_started`, `session_created`, `needs_review`, изменения статусов. Capability URL, API-ключи, содержимое документа и получатель не попадают в аудит. Подробности и ограничения: [documentolog-integration.md](documentolog-integration.md).

## Уведомления

- GET /api/notifications → [{id,kind,title,body,read:boolean,created_at,entity_type:"request"|"course"|"employee"|null,entity_id:number|null,actor_id:number|null,actor_name:string|null}]; только свои, кроме убранных пользователем (`cleared_at IS NULL`). Новые события содержат ссылку на объект и автора; исторические уведомления сохраняются, неизвестные связи остаются null. Переход к объекту повторно проверяет серверные права. Клиент обновляет уведомления и заявки каждые 30 секунд при видимой странице и при возврате фокуса. Раздел открывает непрочитанные; после прочтения событие остаётся только во вкладке «Прочитанные». Блок «На связи» главной показывает только непрочитанные.
- PATCH /api/notifications/{id}/read → тот же объект; повтор безопасен.
- PATCH /api/notifications/read-all → `{updated:number}`; отмечает только собственные непрочитанные, аудит на каждое первое прочтение. Повтор возвращает updated=0 без новых событий.
- PATCH /api/notifications/clear-read → `{updated:number}`; убирает только собственные прочитанные из обеих вкладок и последующих ответов списка, атомарно записывая `cleared_at` и аудит `notification.cleared` для каждого события. Непрочитанные и чужие уведомления не меняются. Повтор возвращает updated=0 без второго эффекта. Это постоянная очистка списка, а не удаление записей: содержимое события, история заявки и аудит сохраняются. Автоматический срок физического хранения не установлен (Q07). Отложенный повтор `/read` не восстанавливает убранное событие.

## Academy

- GET /api/courses → назначенные текущему пользователю курсы.
- GET /api/courses/{id} → назначенный курс.
- POST /api/courses/{id}/progress — {progress:integer 0..100}; увеличивает прогресс, не отмечает завершение без теста.
- POST /api/courses/{id}/complete — {answer_index:integer}; неверный ответ → 422. При успехе progress=100, completed=true. Повтор не создаёт второе уведомление.

Курс: {id,title,description,content:string,duration_minutes,progress,completed,question,options:string[]}.

## Помощник

- POST /api/assistant/query — {question:string 3..1000} → {answer,sources:[{document_id,title,section,content}],escalate_to_hr:boolean,mode:"extractive_demo"}.
- GET /api/knowledge/{id} → {document_id,title,section,content}; доступ только по области документа. Никаких персональных данных и инструментов записи у помощника нет.

Демо-база описывает прототип, а не кадровые правила компании. Неизвестный вопрос → отказ и sources=[]. Источник открывается в UI по document_id. Внешний LLM не вызывается.

## Служебное

- GET /api/integrations/zup — только HR; проверяет HTTP-соединение и возвращает {connected:true,mode:"mock_http"|"real_http",contract:"jana-zup-v1",auth_type:"bearer"|"basic",tls_verified:boolean,mapped_employees,pending,error,synced}. Если источник не ответил → 503. URL, имя пользователя и секреты не раскрываются. Контракт и подключение настоящей 1С — [zup-integration.md](zup-integration.md).

- GET /api/health → {status:"ok"}; проверяет БД.
- GET /api/audit → [{id,actor_id,action,entity_type,entity_id,created_at}]; только HR, последние 200 событий. Записываются входы, создание/решения заявок, `leave.deducted`, подтверждение `zup.leave_registered`, назначение/увеличение прогресса/завершение курса и первое прочтение уведомления. Неудачные попытки доставки и их число сохранены в outbox. Аудит не содержит паролей, JWT и текста вопросов.
- GET /docs, GET /openapi.json — автоматически формируются FastAPI.

### Расширение служебных ответов v0.3

`GET /api/integrations/zup` дополнительно возвращает `cancellations:{pending,error,synced}` — число команд возврата. Панели связи вынесены в отдельный HR-раздел «Интеграции и очереди».

`GET /api/audit` возвращает последние 200 событий с дополнительными полями `actor_name,action_label,employee_id,employee_name`. Добавлены события отзыва/замены/запроса и решения отмены, `zup.leave_cancelled`; исходный аудит и история не удаляются.

- GET /api/audit/page → `{items:AuditEvent[],total,page,page_size}`; `page>=1`, `page_size=1..100`, по умолчанию 25. Только HR. Фильтры всех audit-маршрутов: `employee_id` (сотрудник заявки/целевой профиль, иначе автор события), `actor_id`, точный `action`, `start_date`, `end_date` (обе даты включительно, UTC). Неверный порядок дат → 422.
- GET /api/audit/export → CSV с теми же фильтрами, ФИО и названиями событий, UTF-8 BOM, no-store. Только HR. Более 10 000 событий → 422 с просьбой сузить период. Текст, начинающийся с формулы таблицы, экранируется.

Календарь и каталог используют существующие read-only `/requests` и `/employees` с серверной областью видимости. Поиск/фильтры каталога, представление структуры и пересечения командных отпусков вычисляются на клиенте; отсутствие сотрудника в доступной структуре не раскрывает закрытый профиль. Дополнительных кадровых полей или правил автоматического отказа не добавлено.
