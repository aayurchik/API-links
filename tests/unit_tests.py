import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession 

from src.links.utils import generate_short_code
from src.links.schemas import LinkCreate, LinkUpdate, LinkExtend
from src.links.router import check_owner, get_link_or_404, update_stats_by_code
from src.links.cache import get_cached_url, set_cached_url, delete_cached_url
from src.auth.db import User
from src.links.models import Link

def test_short_code_always_string():
    assert isinstance(generate_short_code(), str)

def test_short_code_default_length():
    assert len(generate_short_code()) == 6

def test_short_code_accepts_custom_length():
    assert len(generate_short_code(10)) == 10

def test_short_code_contains_only_allowed_chars():
    import string
    allowed = set(string.ascii_letters + string.digits)
    code = generate_short_code()
    assert all(ch in allowed for ch in code)

def test_short_code_is_not_always_the_same():
    codes = {generate_short_code() for _ in range(10)}
    assert len(codes) > 1 

# Валидация схем
@pytest.mark.parametrize("input_data,should_pass", [
    ({"original_url": "https://example.com"}, True),
    ({"original_url": "ftp://example.com"}, False),  
    ({"original_url": "https://example.com", "custom_alias": "nice"}, True),
    ({"original_url": "https://example.com", "custom_alias": "no"}, False), 
    ({"original_url": "https://example.com", "custom_alias": "a"*21}, False),  
    ({"original_url": "https://example.com", "expires_at": "2025-12-31T23:59:59"}, True),
    ({"original_url": "https://example.com", "expires_at": "2025-13-01T00:00:00"}, False), 
    ({"original_url": "https://example.com", "project": "my_project"}, True),])
def test_link_create_schema(input_data, should_pass):
    if should_pass:
        obj = LinkCreate(**input_data)
        for key, value in input_data.items():
            if key == "original_url":
                assert str(obj.original_url) == value.rstrip('/') + '/'
            elif key == "expires_at":
                assert obj.expires_at == datetime.fromisoformat(value)
            else:
                assert getattr(obj, key) == value
    else:
        with pytest.raises(ValidationError):
            LinkCreate(**input_data)

# Обновление ссылки, валидность URL
def test_link_update_schema():
    obj = LinkUpdate(original_url="https://new.com")
    assert str(obj.original_url) == "https://new.com/"
    with pytest.raises(ValidationError):
        LinkUpdate(original_url="bad")

# проверка допустимых дней
@pytest.mark.parametrize("days,valid", [
    (1, True),
    (365, True),
    (0, False),
    (-1, False),
    (366, False),])
def test_link_extend_schema(days, valid):
    if valid:
        obj = LinkExtend(days=days)
        assert obj.days == days
    else:
        with pytest.raises(ValidationError):
            LinkExtend(days=days)

# Права владельца
def create_mock_user(user_id):
    user = MagicMock(spec=User)
    user.id = user_id
    return user

def create_mock_link(owner_id=None):
    link = MagicMock(spec=Link)
    link.user_id = owner_id
    return link

@pytest.mark.parametrize("link_owner, current_user, should_pass", [
    (1, 1, True),
    (1, 2, False),
    (None, 1, False),])
def test_check_owner_permissions(link_owner, current_user, should_pass):
    link = create_mock_link(link_owner)
    user = create_mock_user(current_user)
    if should_pass:
        check_owner(link, user)
    else:
        with pytest.raises(Exception) as exc:
            check_owner(link, user)
        assert exc.value.status_code == 403
        assert "Not enough permissions" in str(exc.value.detail)

# успешный поиск
@pytest.mark.asyncio
async def test_get_link_or_404_found():
    mock_link = Link(id=42, short_code="abc")
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_link
    mock_db = AsyncMock(spec=AsyncSession)
    mock_db.execute.return_value = mock_result
    result = await get_link_or_404(mock_db, "abc")
    assert result.id == 42

# ссылка не найдена
@pytest.mark.asyncio
async def test_get_link_or_404_not_found():
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db = AsyncMock(spec=AsyncSession)
    mock_db.execute.return_value = mock_result
    with pytest.raises(Exception) as exc:
        await get_link_or_404(mock_db, "abc")
    assert exc.value.status_code == 404

# преобразование naive expires_at в aware
@pytest.mark.asyncio
async def test_get_link_or_404_converts_naive():
    naive_date = datetime(2025, 1, 1, 12, 0)
    mock_link = Link(id=1, short_code="abc", expires_at=naive_date)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_link
    mock_db = AsyncMock(spec=AsyncSession)
    mock_db.execute.return_value = mock_result
    result = await get_link_or_404(mock_db, "abc")
    assert result.expires_at.tzinfo == timezone.utc

# update_stats_by_code увеличивает счётчик и обновляет last_used
@pytest.mark.asyncio
async def test_update_stats_by_code_increments_clicks():
    mock_link = Link(id=7, short_code="test", clicks=5, last_used=None)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_link
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.execute.return_value = mock_result
    with patch('src.database.async_session_maker') as maker: 
        maker.return_value.__aenter__.return_value = mock_session
        await update_stats_by_code("test")
    assert mock_link.clicks == 6
    assert mock_link.last_used is not None
    mock_session.commit.assert_awaited_once()

# update_stats_by_code игнорирует отсутствующую ссылку
@pytest.mark.asyncio
async def test_update_stats_by_code_ignores_missing():
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.execute.return_value = mock_result
    with patch('src.database.async_session_maker') as maker: 
        maker.return_value.__aenter__.return_value = mock_session
        await update_stats_by_code("missing")
    mock_session.commit.assert_not_awaited()

# update_stats_by_code преобразует naive expires_at при обновлении
@pytest.mark.asyncio
async def test_update_stats_by_code_converts_expiry():
    naive_date = datetime(2025, 1, 1, 12, 0)
    mock_link = Link(id=7, short_code="test", clicks=5, last_used=None, expires_at=naive_date)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_link
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.execute.return_value = mock_result
    with patch('src.database.async_session_maker') as maker:
        maker.return_value.__aenter__.return_value = mock_session
        await update_stats_by_code("test")
    assert mock_link.expires_at.tzinfo == timezone.utc
    assert mock_link.clicks == 6
    mock_session.commit.assert_awaited_once()

# Кэширование
@pytest.mark.asyncio
async def test_cache_set_and_get():
    mock_redis = AsyncMock()
    mock_redis.get.return_value = '{"original_url": "https://ya.ru"}'
    with patch('src.links.cache.redis_client', mock_redis):
        await set_cached_url("key", "https://ya.ru")
        mock_redis.setex.assert_called_once()
        url = await get_cached_url("key")
        assert url == "https://ya.ru"

# get по отсутствующему ключу возвращает None
@pytest.mark.asyncio
async def test_cache_get_missing():
    mock_redis = AsyncMock()
    mock_redis.get.return_value = None
    with patch('src.links.cache.redis_client', mock_redis):
        url = await get_cached_url("unknown")
        assert url is None

# удаление ключа
@pytest.mark.asyncio
async def test_cache_delete():
    mock_redis = AsyncMock()
    mock_redis.get.return_value = '{"original_url": "https://ya.ru"}'
    with patch('src.links.cache.redis_client', mock_redis):
        url = await get_cached_url("key")
        assert url == "https://ya.ru"
        await delete_cached_url("key")
        mock_redis.delete.assert_called_once_with("link:key")
        mock_redis.get.return_value = None
        url = await get_cached_url("key")
        assert url is None

# обработка исключения в set_cached_url
@pytest.mark.asyncio
async def test_set_cached_url_exception():
    mock_redis = AsyncMock()
    mock_redis.setex.side_effect = Exception("Redis error")
    with patch('src.links.cache.redis_client', mock_redis):
        await set_cached_url("key", "https://example.com")
        mock_redis.setex.assert_called_once()

# обработка исключения в delete_cached_url
@pytest.mark.asyncio
async def test_delete_cached_url_exception():
    mock_redis = AsyncMock()
    mock_redis.delete.side_effect = Exception("Redis error")
    with patch('src.links.cache.redis_client', mock_redis):
        await delete_cached_url("key")
        mock_redis.delete.assert_called_once()

# обработка исключения в get_cached_url
@pytest.mark.asyncio
async def test_get_cached_url_exception():
    mock_redis = AsyncMock()
    mock_redis.get.side_effect = Exception("Redis error")
    with patch('src.links.cache.redis_client', mock_redis):
        result = await get_cached_url("key")
        assert result is None
        mock_redis.get.assert_called_once()

# исчерпание попыток генерации кода
@pytest.mark.asyncio
async def test_create_short_link_exhaust_attempts():
    from src.links.router import create_short_link
    from src.links.schemas import LinkCreate
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = True  
    mock_db.execute.return_value = mock_result
    mock_user = None
    link_data = LinkCreate(original_url="https://example.com")  
    with patch('src.links.utils.generate_short_code') as mock_gen:
        mock_gen.side_effect = ["a1", "a2", "a3", "a4", "a5", "a6", "a7", "a8", "a9", "a10"]
        with pytest.raises(Exception) as exc:
            await create_short_link(link_data, mock_db, mock_user)
        assert exc.value.status_code == 500
        assert "Could not generate unique short code" in str(exc.value.detail)

# возврат отсортированных ссылки
@pytest.mark.asyncio
async def test_get_popular_links():
    from src.links.router import get_popular_links
    mock_db = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [
        Link(id=1, short_code="pop1", clicks=5),
        Link(id=2, short_code="pop2", clicks=3)]
    mock_db.execute.return_value = mock_result
    result = await get_popular_links(limit=2, db=mock_db)
    assert len(result) == 2
    assert result[0].short_code == "pop1"
    mock_db.execute.assert_called_once()

# получение статистики
@pytest.mark.asyncio
async def test_get_link_stats():
    from src.links.router import get_link_stats
    mock_db = AsyncMock()
    with patch('src.links.router.get_link_or_404', new_callable=AsyncMock) as mock_get:
        mock_link = Link(id=1, short_code="abc")
        mock_get.return_value = mock_link
        result = await get_link_stats("abc", db=mock_db)
        assert result == mock_link
        mock_get.assert_awaited_once_with(mock_db, "abc")

# очистка неиспользуемых ссылок
@pytest.mark.asyncio
async def test_cleanup_unused_links():
    from src.links.router import cleanup_unused_links
    mock_db = AsyncMock(spec=AsyncSession)
    mock_db.execute.return_value = None
    mock_db.commit.return_value = None
    mock_user = MagicMock()  
    result = await cleanup_unused_links(days=10, db=mock_db, _=mock_user)
    assert result is None
    mock_db.execute.assert_awaited_once()
    mock_db.commit.assert_awaited_once()

# успешное удаление
@pytest.mark.asyncio
async def test_delete_link_success():
    from src.links.router import delete_link
    mock_db = AsyncMock()
    mock_user = MagicMock(spec=User)
    mock_user.id = 1
    mock_link = Link(id=1, user_id=1)
    with patch('src.links.router.get_link_or_404', new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_link
        with patch('src.links.router.check_owner') as mock_check:
            with patch('src.links.router.delete_cached_url', new_callable=AsyncMock) as mock_del:
                result = await delete_link("abc", mock_db, mock_user)
                assert result is None
                mock_get.assert_awaited_once_with(mock_db, "abc")
                mock_check.assert_called_once_with(mock_link, mock_user)
                mock_db.delete.assert_awaited_once_with(mock_link)
                mock_db.commit.assert_awaited_once()
                mock_del.assert_awaited_once_with("abc")

# успешное обновление
@pytest.mark.asyncio
async def test_update_link_success():
    from src.links.router import update_link
    from src.links.schemas import LinkUpdate
    mock_db = AsyncMock()
    mock_user = MagicMock(spec=User)
    mock_user.id = 1
    mock_link = Link(id=1, user_id=1, original_url="https://old.com")
    with patch('src.links.router.get_link_or_404', new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_link
        with patch('src.links.router.check_owner') as mock_check:
            with patch('src.links.router.delete_cached_url', new_callable=AsyncMock) as mock_del:
                link_update = LinkUpdate(original_url="https://new.com")
                result = await update_link("abc", link_update, mock_db, mock_user)
                assert result == mock_link
                assert mock_link.original_url == "https://new.com/"
                mock_get.assert_awaited_once_with(mock_db, "abc")
                mock_check.assert_called_once_with(mock_link, mock_user)
                mock_db.commit.assert_awaited_once()
                mock_db.refresh.assert_awaited_once_with(mock_link)
                mock_del.assert_awaited_once_with("abc")

# фильтрация по проекту
@pytest.mark.asyncio
async def test_get_links_by_project():
    from src.links.router import get_links_by_project
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [Link(id=1, project="work")]
    mock_db.execute.return_value = mock_result
    result = await get_links_by_project("work", mock_db)
    assert len(result) == 1
    assert result[0].project == "work"
    mock_db.execute.assert_awaited_once()

# продление срока действия
@pytest.mark.asyncio
async def test_extend_link_expiry_with_mocks():
    from src.links.router import extend_link_expiry
    from src.links.schemas import LinkExtend
    mock_db = AsyncMock()
    mock_user = MagicMock(spec=User)
    mock_user.id = 1
    aware_date = datetime.now(timezone.utc)
    mock_link = Link(id=1, user_id=1, expires_at=aware_date)
    with patch('src.links.router.get_link_or_404', new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_link
        with patch('src.links.router.check_owner') as mock_check:
            with patch('src.links.router.delete_cached_url', new_callable=AsyncMock) as mock_del:
                extend_data = LinkExtend(days=5)
                result = await extend_link_expiry("abc", extend_data, mock_db, mock_user)
                assert result == mock_link
                assert mock_link.expires_at == aware_date + timedelta(days=5)
                mock_get.assert_awaited_once_with(mock_db, "abc")
                mock_check.assert_called_once_with(mock_link, mock_user)
                mock_db.commit.assert_awaited_once()
                mock_db.refresh.assert_awaited_once_with(mock_link)
                mock_del.assert_awaited_once_with("abc")