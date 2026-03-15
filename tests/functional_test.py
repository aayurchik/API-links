# Функциональные тесты
# Тестирование API через TestClient FastAPI.
# Проверка всех CRUD-операций с короткими ссылками.
# Тестирование поведения при передаче невалидных данных.
# Проверка работы механизма перенаправления (GET /{short_code}).
# Подумайте о необходимости создания отдельной тестовой базы данных и её последующей очистке.

import pytest
import asyncio
from httpx import AsyncClient, ASGITransport
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text
from sqlalchemy.pool import NullPool
from src.main import app
from src.database import get_async_session, Base
from src.config import DB_USER, DB_PASS, DB_HOST, DB_PORT, DB_NAME

# тестовая бд
TEST_DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}_test"
engine = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)
TestingSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def override_get_async_session() -> AsyncSession:
    async with TestingSessionLocal() as session:
        yield session

app.dependency_overrides[get_async_session] = override_get_async_session

# fixtures were written with gpt
@pytest.fixture(scope="session", autouse=True)
async def setup_test_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest.fixture
async def db_session(setup_test_db):
    async with TestingSessionLocal() as session:
        yield session

# очистка таблиц после каждого теста
@pytest.fixture(autouse=True)
async def clean_db(db_session):
    yield
    await db_session.execute(text("TRUNCATE TABLE links RESTART IDENTITY CASCADE;"))
    await db_session.execute(text("TRUNCATE TABLE \"user\" RESTART IDENTITY CASCADE;"))
    await db_session.commit()

@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as ac:
        yield ac

@pytest.fixture
def user_data():
    return {"email": "user@test.com", "password": "secret"}

@pytest.fixture
async def registered_user(client, user_data):
    resp = await client.post("/auth/register", json=user_data)
    assert resp.status_code in (200, 201)
    return user_data

@pytest.fixture
async def auth_token(client, registered_user):
    resp = await client.post("/auth/jwt/login", data={
        "username": registered_user["email"],
        "password": registered_user["password"]})
    assert resp.status_code == 200
    return resp.json()["access_token"]

@pytest.fixture
def superuser_data():
    return {"email": "admin@test.com", "password": "adminpass"}

@pytest.fixture
async def registered_superuser(client, superuser_data, db_session):
    resp = await client.post("/auth/register", json=superuser_data)
    assert resp.status_code in (200, 201)
    await db_session.execute(
        text("UPDATE \"user\" SET is_superuser = TRUE WHERE email = :email"),
        {"email": superuser_data["email"]})
    await db_session.commit()
    return superuser_data

@pytest.fixture
async def superuser_token(client, registered_superuser):
    resp = await client.post("/auth/jwt/login", data={
        "username": registered_superuser["email"],
        "password": registered_superuser["password"]})
    assert resp.status_code == 200
    return resp.json()["access_token"]

# регистрация нового пользователя с валидными данными
@pytest.mark.asyncio
async def test_register_success(client):
    resp = await client.post("/auth/register", json={
        "email": "fresh@example.com",
        "password": "strong123"})
    assert resp.status_code == 201
    assert resp.json()["email"] == "fresh@example.com"

# регистрация с уже существующим email
@pytest.mark.asyncio
async def test_register_duplicate_email(client):
    await client.post("/auth/register", json={"email": "dup@test.com", "password": "pass"})
    resp = await client.post("/auth/register", json={"email": "dup@test.com", "password": "another"})
    assert resp.status_code == 400

# неверный формат email   
@pytest.mark.asyncio
async def test_register_invalid_email(client):
    resp = await client.post("/auth/register", json={"email": "not-an-email", "password": "pass"})
    assert resp.status_code == 422

# вход с правильными данными возвращает токен
@pytest.mark.asyncio
async def test_login_success(client, registered_user):
    resp = await client.post("/auth/jwt/login", data={
        "username": registered_user["email"],
        "password": registered_user["password"]})
    assert resp.status_code == 200
    assert "access_token" in resp.json()

# неверный пароль даёт 400  
@pytest.mark.asyncio
async def test_login_wrong_password(client, registered_user):
    resp = await client.post("/auth/jwt/login", data={
        "username": registered_user["email"],
        "password": "wrong"})
    assert resp.status_code in (400, 401)

# вход с несуществующим email 
@pytest.mark.asyncio
async def test_login_nonexistent(client):
    resp = await client.post("/auth/jwt/login", data={
        "username": "ghost@test.com",
        "password": "pass"})
    assert resp.status_code in (400, 401)

# анонимный пользователь может создать ссылку
@pytest.mark.asyncio
async def test_create_link_anonymous(client):
    resp = await client.post("/links/shorten", json={"original_url": "https://example.com"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["short_code"]) == 6
    assert data["original_url"] == "https://example.com/"

# авторизованный пользователь создаёт ссылку с кастомным алиасом  
@pytest.mark.asyncio
async def test_create_link_with_alias(client, auth_token):
    resp = await client.post("/links/shorten",
                       json={"original_url": "https://custom.com", "custom_alias": "myalias"},
                       headers={"Authorization": f"Bearer {auth_token}"})
    assert resp.status_code == 200
    assert resp.json()["short_code"] == "myalias"

# попытка создать ссылку с уже занятым алиасом вызывает 400
@pytest.mark.asyncio
async def test_create_link_duplicate_alias(client, auth_token):
    await client.post("/links/shorten",
                json={"original_url": "https://first.com", "custom_alias": "taken"},
                headers={"Authorization": f"Bearer {auth_token}"})
    resp = await client.post("/links/shorten",
                       json={"original_url": "https://second.com", "custom_alias": "taken"},
                       headers={"Authorization": f"Bearer {auth_token}"})
    assert resp.status_code == 400
    assert "already in use" in resp.text

# ссылка может быть создана с указанием проекта
@pytest.mark.asyncio
async def test_create_link_with_project(client, auth_token):
    create_resp = await client.post("/links/shorten",
                       json={"original_url": "https://project.com", "project": "work"},
                       headers={"Authorization": f"Bearer {auth_token}"})
    assert create_resp.status_code == 200
    project_resp = await client.get("/links/project/work")
    assert project_resp.status_code == 200
    data = project_resp.json()
    assert len(data) == 1
    assert data[0]["original_url"] == "https://project.com/"

# ссылка может быть создана с датой истечения
@pytest.mark.asyncio
async def test_create_link_with_expiry(client, auth_token):
    future = (datetime.now(timezone.utc) + timedelta(days=10)).isoformat()
    resp = await client.post("/links/shorten",
                       json={"original_url": "https://temp.com", "expires_at": future},
                       headers={"Authorization": f"Bearer {auth_token}"})
    assert resp.status_code == 200
    resp_date = datetime.fromisoformat(resp.json()["expires_at"].replace('Z', '+00:00'))
    expected_date = datetime.fromisoformat(future)
    assert resp_date == expected_date

# невалидный URL 
@pytest.mark.asyncio
async def test_create_link_invalid_url(client):
    resp = await client.post("/links/shorten", json={"original_url": "not-a-url"})
    assert resp.status_code == 422

# переход по короткой ссылке должен редиректить на оригинальный URL
@pytest.mark.asyncio
async def test_redirect(client):
    create = await client.post("/links/shorten",
                         json={"original_url": "https://redirect.com", "custom_alias": "redir"})
    assert create.status_code == 200
    short_code = create.json()["short_code"]
    resp = await client.get(f"/links/{short_code}", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "https://redirect.com/"

# статистика должна отображать количество кликов и дату последнего использования
@pytest.mark.asyncio
async def test_stats(client):
    create = await client.post("/links/shorten",
                         json={"original_url": "https://stats.com", "custom_alias": "stat"})
    assert create.status_code == 200
    short_code = create.json()["short_code"]
    await client.get(f"/links/{short_code}") 
    resp = await client.get(f"/links/{short_code}/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["short_code"] == "stat"
    assert data["clicks"] >= 1
    assert data["last_used"] is not None

# поиск по оригинальному URL возвращает ссылки, содержащие подстроку
@pytest.mark.asyncio
async def test_search(client):
    await client.post("/links/shorten", json={"original_url": "https://hello.world"})
    await client.post("/links/shorten", json={"original_url": "https://world.hello"})
    await client.post("/links/shorten", json={"original_url": "https://hello.com"})
    resp = await client.get("/links/search", params={"original_url": "hello"})
    assert len(resp.json()) == 3
    resp = await client.get("/links/search", params={"original_url": "world"})
    assert len(resp.json()) == 2
    resp = await client.get("/links/search", params={"original_url": "none"})
    assert resp.json() == []

# владелец может удалить свою ссылку 
@pytest.mark.asyncio
async def test_delete_own_link(client, auth_token):
    create = await client.post("/links/shorten", json={"original_url": "https://todelete.com", "custom_alias": "testdel"},
                         headers={"Authorization": f"Bearer {auth_token}"})
    assert create.status_code == 200
    short_code = create.json()["short_code"]
    del_resp = await client.delete(f"/links/{short_code}", headers={"Authorization": f"Bearer {auth_token}"})
    assert del_resp.status_code == 204
    get_resp = await client.get(f"/links/{short_code}/stats")
    assert get_resp.status_code == 404

# пользователь не может удалить чужую ссылку
@pytest.mark.asyncio
async def test_delete_others_link(client, auth_token):
    create = await client.post("/links/shorten", json={"original_url": "https://user1.com", "custom_alias": "user1"},
                         headers={"Authorization": f"Bearer {auth_token}"})
    assert create.status_code == 200
    short_code = create.json()["short_code"]
    user2_data = {"email": "user2@test.com", "password": "pass"}
    reg2 = await client.post("/auth/register", json=user2_data)
    assert reg2.status_code in (200, 201)
    login2 = await client.post("/auth/jwt/login", data={
        "username": user2_data["email"],
        "password": user2_data["password"]})
    assert login2.status_code == 200, f"Login failed: {login2.status_code} - {login2.text}"
    token2 = login2.json()["access_token"]
    del_resp = await client.delete(f"/links/{short_code}", headers={"Authorization": f"Bearer {token2}"})
    assert del_resp.status_code == 403

# владелец может обновить оригинальный URL своей ссылки
@pytest.mark.asyncio
async def test_update_own_link(client, auth_token):
    create = await client.post("/links/shorten", json={"original_url": "https://old.com", "custom_alias": "testupd"}, 
                         headers={"Authorization": f"Bearer {auth_token}"})
    assert create.status_code == 200
    short_code = create.json()["short_code"]
    update = await client.put(f"/links/{short_code}", json={"original_url": "https://new.com"},
                        headers={"Authorization": f"Bearer {auth_token}"})
    assert update.status_code == 200
    assert update.json()["original_url"] == "https://new.com/"

# пользователь не может обновить чужую ссылку 
@pytest.mark.asyncio
async def test_update_others_link(client, auth_token):
    create = await client.post("/links/shorten", json={"original_url": "https://user1.com", "custom_alias": "user1"},
                         headers={"Authorization": f"Bearer {auth_token}"})
    assert create.status_code == 200
    short_code = create.json()["short_code"]
    user2_data = {"email": "user2@test.com", "password": "pass"}
    reg2 = await client.post("/auth/register", json=user2_data)
    assert reg2.status_code in (200, 201)
    # Явно формируем данные для логина
    login2 = await client.post("/auth/jwt/login", data={
        "username": user2_data["email"],
        "password": user2_data["password"]})
    assert login2.status_code == 200, f"Login failed: {login2.status_code} - {login2.text}"
    token2 = login2.json()["access_token"]
    update = await client.put(f"/links/{short_code}", json={"original_url": "https://hacked.com"},
                        headers={"Authorization": f"Bearer {token2}"})
    assert update.status_code == 403

# удаление несуществующей 
@pytest.mark.asyncio
async def test_delete_nonexistent(client, auth_token):
    resp = await client.delete("/links/nonexistent", headers={"Authorization": f"Bearer {auth_token}"})
    assert resp.status_code == 404

# обновление несуществующей ссылки 
@pytest.mark.asyncio
async def test_update_nonexistent(client, auth_token):
    resp = await client.put("/links/nonexistent", json={"original_url": "https://new.com"}, headers={"Authorization": f"Bearer {auth_token}"})
    assert resp.status_code == 404

# список истекших ссылок содержит только те, у которых expires_at в прошлом
@pytest.mark.asyncio
async def test_expired_links(client, auth_token):
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    await client.post("/links/shorten",
                json={"original_url": "https://past.com", "custom_alias": "pastlink", "expires_at": past},
                headers={"Authorization": f"Bearer {auth_token}"})
    await client.post("/links/shorten",
                json={"original_url": "https://future.com", "custom_alias": "futurelink", "expires_at": future},
                headers={"Authorization": f"Bearer {auth_token}"})
    resp = await client.get("/links/expired")
    data = resp.json()
    codes = [item["short_code"] for item in data]
    assert "pastlink" in codes
    assert "futurelink" not in codes

# при попытке перейти по истекшей ссылке должна возвращаться ошибка 410
@pytest.mark.asyncio
async def test_redirect_expired_link(client, auth_token):
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    create = await client.post("/links/shorten",
                               json={"original_url": "https://expired.com",
                                     "custom_alias": "expired410",
                                     "expires_at": past},
                               headers={"Authorization": f"Bearer {auth_token}"})
    assert create.status_code == 200
    short_code = create.json()["short_code"]
    resp = await client.get(f"/links/{short_code}", follow_redirects=False)
    assert resp.status_code == 410


# фильтрация по проекту возвращает только ссылки с указанным проектом
@pytest.mark.asyncio
async def test_project_filter(client, auth_token):
    await client.post("/links/shorten",
                json={"original_url": "https://work1.com", "project": "work"},
                headers={"Authorization": f"Bearer {auth_token}"})
    await client.post("/links/shorten",
                json={"original_url": "https://work2.com", "project": "work"},
                headers={"Authorization": f"Bearer {auth_token}"})
    await client.post("/links/shorten",
                json={"original_url": "https://play.com", "project": "play"},
                headers={"Authorization": f"Bearer {auth_token}"})
    resp = await client.get("/links/project/work")
    assert len(resp.json()) == 2
    resp = await client.get("/links/project/play")
    assert len(resp.json()) == 1
    resp = await client.get("/links/project/void")
    assert resp.json() == []

# продление срока действия ссылки должно увеличить expires_at
@pytest.mark.asyncio
async def test_extend_link(client, auth_token):
    future = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    create = await client.post("/links/shorten",
                         json={"original_url": "https://extend.com", "custom_alias": "extendme", "expires_at": future},
                         headers={"Authorization": f"Bearer {auth_token}"})
    assert create.status_code == 200
    old = create.json()["expires_at"]
    resp = await client.patch("/links/extendme/extend", json={"days": 10},
                        headers={"Authorization": f"Bearer {auth_token}"})
    assert resp.status_code == 200
    new = resp.json()["expires_at"]
    assert new != old

# попытка продлить ссылку без expires_at
@pytest.mark.asyncio
async def test_extend_link_no_expiry(client, auth_token):
    create = await client.post("/links/shorten",
                         json={"original_url": "https://noexpire.com", "custom_alias": "noexp"},
                         headers={"Authorization": f"Bearer {auth_token}"})
    assert create.status_code == 200
    short_code = create.json()["short_code"]
    resp = await client.patch(f"/links/{short_code}/extend", json={"days": 5},
                        headers={"Authorization": f"Bearer {auth_token}"})
    assert resp.status_code == 400

# очистка неиспользуемых ссылок доступна только суперпользователю
@pytest.mark.asyncio
async def test_cleanup_superuser(client, auth_token, superuser_token):
    await client.post("/links/shorten",
                json={"original_url": "https://unused.com", "custom_alias": "unused"},
                headers={"Authorization": f"Bearer {auth_token}"})
    resp = await client.delete("/links/cleanup", params={"days": 0}, headers={"Authorization": f"Bearer {auth_token}"})
    assert resp.status_code == 403
    resp = await client.delete("/links/cleanup", params={"days": 0}, headers={"Authorization": f"Bearer {superuser_token}"})
    assert resp.status_code == 204
    get_resp = await client.get("/links/unused/stats")
    assert get_resp.status_code == 404

@pytest.mark.asyncio
async def test_cleanup_negative_days(client, superuser_token):
    resp = await client.delete("/links/cleanup", params={"days": -5},
                         headers={"Authorization": f"Bearer {superuser_token}"})
    assert resp.status_code in (204, 422)

# анонимные запросы на изменение возвращают 401
@pytest.mark.asyncio
async def test_anonymous_modification_forbidden(client):
    create = await client.post("/links/shorten", json={"original_url": "https://anon.com"})
    assert create.status_code == 200
    short_code = create.json()["short_code"]
    del_resp = await client.delete(f"/links/{short_code}")
    assert del_resp.status_code == 401
    put_resp = await client.put(f"/links/{short_code}", json={"original_url": "https://new.com"})
    assert put_resp.status_code == 401
    patch_resp = await client.patch(f"/links/{short_code}/extend", json={"days": 5})
    assert patch_resp.status_code == 401

# защищённый маршрут доступен авторизованному пользователю
@pytest.mark.asyncio
async def test_protected_route(client, auth_token):
    resp = await client.get("/protected-route", headers={"Authorization": f"Bearer {auth_token}"})
    assert resp.status_code == 200
    assert resp.json() == "Hello, user@test.com" 

# незащищённый маршрут доступен всем
@pytest.mark.asyncio
async def test_unprotected_route(client):
    resp = await client.get("/unprotected-route")
    assert resp.status_code == 200
    assert resp.json() == "Hello, anonym"

# после обновления ссылки кэш должен инвалидироваться
@pytest.mark.asyncio
async def test_cache_invalidation_on_update(client, auth_token):
    create = await client.post("/links/shorten", json={"original_url": "https://old.com", "custom_alias": "cachetest"},
                               headers={"Authorization": f"Bearer {auth_token}"})
    assert create.status_code == 200
    short_code = create.json()["short_code"]
    await client.get(f"/links/{short_code}", follow_redirects=False)
    update = await client.put(f"/links/{short_code}", json={"original_url": "https://new.com"},
                              headers={"Authorization": f"Bearer {auth_token}"})
    assert update.status_code == 200
    resp = await client.get(f"/links/{short_code}", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "https://new.com/"

