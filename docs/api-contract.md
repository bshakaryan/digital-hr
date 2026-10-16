# API Digital HR v0.1

Это целевой контракт первой реализации. Наличие маршрутов проверяется тестами и OpenAPI; статус реализации перечислен в verification.md. Префикс /api. JSON, даты YYYY-MM-DD, время UTC ISO 8601. Bearer JWT для всех маршрутов кроме login и health. Ошибки: {"detail": "сообщение"}; валидация FastAPI — detail массив.

## Вход и профиль

- POST /api/auth/login — {email, password} → {access_token, token_type:"bearer"}.
- GET /api/me → {id:number, email, full_name, role:"employee"|"manager"|"hr_admin", company, position, department, manager_id:number|null, manager_name:string|null, hire_date, leave_balance:number, data_source:"mock_zup"}. Имя руководителя является частью разрешённого собственного профиля; полный профиль руководителя сотруднику не раскрывается.
- GET /api/employees → массив тех же профилей: сотруднику только свой, руководителю свой и прямые подчинённые, HR все.
- GET /api/employees/{id} → профиль; недоступный id возвращает 404.

## Заявки

- GET /api/requests → массив доступных заявок, новые первыми.
- POST /api/requests — заголовок Idempotency-Key обязателен (8–128 символов); тело {start_date,end_date,comment:string}; результат 201.
- GET /api/requests/{id} → доступная заявка.
- PATCH /api/requests/{id}/status — {status:"approved"|"rejected",version:number,comment:string}; только руководитель прямого подчинённого либо HR, кроме автора заявки. Устаревшая version → 409. Решение окончательное в MVP.

Заявка: {id,employee_id,employee_name,type:"leave",start_date,end_date,comment,status:"submitted"|"approved"|"rejected",version:number,created_at,history:[{status,actor_name,comment,created_at}]}.

Повтор POST с тем же ключом и телом возвращает тот же id (201); другое тело — 409. Новая заявка не меняет кадровый остаток отпуска. Отправка в Documentolog в MVP отсутствует.

## Уведомления

- GET /api/notifications → [{id,kind,title,body,read:boolean,created_at}]; только свои.
- PATCH /api/notifications/{id}/read → тот же объект; повтор безопасен.

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

- GET /api/health → {status:"ok"}; проверяет БД.
- GET /api/audit → [{id,actor_id,action,entity_type,entity_id,created_at}]; только HR, последние 200 событий. Записываются входы, создание/решения заявок, назначение/увеличение прогресса/завершение курса и первое прочтение уведомления. Аудит не содержит паролей, JWT и текста вопросов.
- GET /docs, GET /openapi.json — автоматически формируются FastAPI.
