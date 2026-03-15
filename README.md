# API-links

Сервис для сокращения ссылок с аналитикой, кэшированием и фоновыми задачами.  

**Документация Swagger:** [https://api-links.onrender.com/docs](https://api-links.onrender.com/docs)  

Для деплоя используется отдельная ветка `new` , адаптированная под бесплатный тариф (без Celery).

---

## Аутентификация
Для запросов через curl требуется JWT-токен, полученный при логине. В Swagger авторизация выполняется через кнопку Authorize с вводом email и пароля.  

| Метод | URL | Описание | Доступ | Параметры / тело | Ответ |
|-------|-----|----------|--------|------------------|--------|
| POST | `/auth/register` | Регистрация | Все | `{"email": "user@example.com", "password": "secret123"}` | `{"id": "uuid", "email": "user@example.com", "is_active": true, "is_superuser": false, "is_verified": false}` |
| POST | `/auth/jwt/login` | Вход | Все | (form-data) `username=user@example.com&password=secret123` | `{"access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...", "token_type": "bearer"}` |

## Ссылки (обязательные функции)

| Метод | URL | Описание | Доступ | Параметры / тело | Ответ |
|-------|-----|----------|--------|------------------|--------|
| POST | `/links/shorten` | Создать короткую ссылку | Все | `{"original_url": "https://example.com", "custom_alias": "myalias", "expires_at": "2025-12-31T23:59:59"}` | `{"short_code": "myalias", "original_url": "https://example.com/", "created_at": "2026-03-09T12:00:00Z", "expires_at": "2025-12-31T23:59:59Z", "clicks": 0, "last_used": null}` |
| GET | `/links/{short_code}` | Редирект на оригинальный URL | Все | URL: `/links/myalias` | HTTP 302 → `https://example.com` |
| GET | `/links/{short_code}/stats` | Статистика по ссылке | Все | URL: `/links/myalias/stats` | `{"short_code": "myalias", "original_url": "https://example.com/", "created_at": "...", "expires_at": "...", "clicks": 1, "last_used": "..."}` |
| GET | `/links/search?original_url=...` | Поиск по оригинальному URL | Все | URL: `/links/search?original_url=example` | `[{"short_code": "myalias", "original_url": "https://example.com/", ...}]` |
| DELETE | `/links/{short_code}` | Удалить ссылку | Только владелец | URL: `/links/myalias` (нет тела) | `204 No Content` |
| PUT | `/links/{short_code}` | Обновить оригинальный URL | Только владелец | `{"original_url": "https://google.com"}` | `{"short_code": "myalias", "original_url": "https://google.com/", "created_at": "...", "expires_at": "...", "clicks": 1, "last_used": "..."}` |

## Дополнительные функции

| Метод | URL | Описание | Доступ | Параметры / тело | Ответ |
|-------|-----|----------|--------|------------------|--------|
| GET | `/links/expired` | Список истекших ссылок | Все | URL: `/links/expired` | `[{"short_code": "expired1", "original_url": "...", "expires_at": "2020-01-01T00:00:00Z", ...}]` |
| DELETE | `/links/cleanup?days=30` | Удалить неиспользуемые ссылки | Суперпользователь | URL: `/links/cleanup?days=0` | `204 No Content` |
| GET | `/links/project/{project_name}` | Фильтрация по проекту | Все | URL: `/links/project/work` | `[{"short_code": "work1", "project": "work", ...}]` |
| GET | `/links/popular?limit=5` | Топ популярных ссылок | Все | URL: `/links/popular?limit=3` | `[{"short_code": "pop1", "clicks": 10}, {"short_code": "pop2", "clicks": 5}]` |
| PATCH | `/links/{short_code}/extend` | Продлить срок действия ссылки | Только владелец | `{"days": 10}` | `{"short_code": "myalias", "expires_at": "2026-01-10T23:59:59Z", ...}` |

## Примеры запросов (curl)


### Регистрация
    ```bash
    curl -X POST "https://api-links.onrender.com/auth/register" \
      -H "Content-Type: application/json" \
      -d '{"email": "user@example.com", "password": "secret123"}'

### Login
    ```bash
    curl -X POST "https://api-links.onrender.com/auth/jwt/login" \
      -H "Content-Type: application/x-www-form-urlencoded" \
      -d "username=user@example.com&password=secret123"

### Создание короткой ссылки (с токеном)
    ```bash
    curl -X POST "https://api-links.onrender.com/links/shorten" \
      -H "Authorization: Bearer <ваш_токен>" \
      -H "Content-Type: application/json" \
      -d '{"original_url": "https://example.com", "custom_alias": "myalias", "expires_at": "2025-12-31T23:59:59"}'

### Редирект
    ```bash
     curl -v "https://api-links.onrender.com/links/myalias"

### Статистика
    ```bash
    curl "https://api-links.onrender.com/links/myalias/stats"
    
### Поиск
    ```bash
    curl "https://api-links.onrender.com/links/search?original_url=example"

### Удаление ссылки (с токеном)
    ```bash
     curl -X DELETE "https://api-links.onrender.com/links/myalias" \
      -H "Authorization: Bearer <ваш_токен>" 
### Обновление ссылки (с токеном)
    ```bash
    curl -X PUT "https://api-links.onrender.com/links/myalias" \
      -H "Authorization: Bearer <ваш_токен>" \
      -H "Content-Type: application/json" \
      -d '{"original_url": "https://google.com"}'

### Популярные ссылки
    ```bash
    curl "https://api-links.onrender.com/links/popular?limit=3"
    
### Продление срока (с токеном)
    ```bash
    curl -X PATCH "https://api-links.onrender.com/links/myalias/extend" \
      -H "Authorization: Bearer <ваш_токен>" \
      -H "Content-Type: application/json" \
      -d '{"days": 10}'

## Запуск локально (Docker Compose)  
(Для локальной разработки используется ветка main с Celery)  

1. Клонируйте репозиторий и перейдите в папку:  
   ```bash
   git clone https://github.com/aayurchik/API-links.git
   cd API-links

2. Создайте файл .env на основе примера. Отредактируйте при необходимости (секретный ключ, параметры БД).
    
    ```bash
    cp .env.example .env
    
3. Пример содержимого файла .env:  
    ```ini
    DB_USER=postgres  
    DB_PASS=password  
    DB_NAME=shortlink  
    DB_HOST=localhost 
    DB_PORT=5432  
    REDIS_HOST=localhost  
    REDIS_PORT=6379  
    SECRET_KEY=your-secret-key-here  
    CLEANUP_DAYS=30  

4. Запустите контейнеры:

    ```bash
    docker-compose up -d

5. Примените миграции:

    ```bash
    docker-compose exec app alembic upgrade head

* Сервис доступен по адресу: http://localhost:8000  
* Документация Swagger: http://localhost:8000/docs  

## База данных  

### Таблица `user` (fastapi-users)  

| Поле | Тип | Модификаторы |
|------|-----|--------------|
| `id` | UUID | PRIMARY KEY |
| `email` | VARCHAR | UNIQUE NOT NULL |
| `hashed_password` | VARCHAR | NOT NULL |
| `is_active` | BOOLEAN | DEFAULT TRUE |
| `is_superuser` | BOOLEAN | DEFAULT FALSE |
| `is_verified` | BOOLEAN | DEFAULT FALSE |

### Таблица `links`  

| Поле | Тип | Модификаторы |
|------|-----|--------------|
| `id` | SERIAL | PRIMARY KEY |
| `short_code` | VARCHAR | UNIQUE NOT NULL |
| `original_url` | VARCHAR | NOT NULL |
| `custom_alias` | VARCHAR | UNIQUE |
| `created_at` | TIMESTAMPTZ | DEFAULT NOW() |
| `expires_at` | TIMESTAMPTZ |  |
| `clicks` | INTEGER | DEFAULT 0 |
| `last_used` | TIMESTAMPTZ |  |
| `user_id` | UUID | REFERENCES `user`(`id`) ON DELETE SET NULL |
| `project` | VARCHAR |  |
