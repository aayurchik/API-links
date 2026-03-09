from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, delete, and_
from datetime import datetime, timedelta, timezone

from src.database import get_async_session
from src.links.models import Link
from src.links.schemas import LinkCreate, LinkOut, LinkUpdate, LinkStats, LinkExtend
from src.links.utils import generate_short_code
from src.links.cache import get_cached_url, set_cached_url, delete_cached_url
from src.auth.users import current_active_user, current_user_optional, current_superuser
from src.auth.db import User
from fastapi.responses import RedirectResponse

router = APIRouter(
    prefix="/links", 
    tags=["links"])

# Вспомогательная функция для поиска ссылки по коду (используется в нескольких эндпоинтах)
# Возвращает ссылку по short_code или custom_alias, иначе 404
async def get_link_or_404(db: AsyncSession, code: str) -> Link:
    result = await db.execute(
        select(Link).where(or_(Link.short_code == code, Link.custom_alias == code)))
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    # Приведение expires_at к aware (UTC), если оно naive
    if link.expires_at is not None and link.expires_at.tzinfo is None:
        link.expires_at = link.expires_at.replace(tzinfo=timezone.utc)
    return link

# Проверка прав владельца (для удаления и обновления)
def check_owner(link: Link, user: User):
    if link.user_id is None or link.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")

# для фонового обновления статистики
async def update_stats_by_code(short_code: str):
    from src.database import async_session_maker
    from sqlalchemy import select, or_
    from src.links.models import Link
    async with async_session_maker() as db:
        result = await db.execute(
            select(Link).where(or_(Link.short_code == short_code, Link.custom_alias == short_code)))
        link = result.scalar_one_or_none()
        if link:
            if link.expires_at is not None and link.expires_at.tzinfo is None:
                link.expires_at = link.expires_at.replace(tzinfo=timezone.utc)
            link.clicks += 1
            link.last_used = datetime.now(timezone.utc)
            await db.commit()

# Обязательные функции

# Создание короткой ссылки (п.1), с поддержкой кастомного alias (п.3) и expires_at (п.5)
@router.post("/shorten", response_model=LinkOut)
async def create_short_link(
    link_data: LinkCreate,
    db: AsyncSession = Depends(get_async_session),
    current_user: User | None = Depends(current_user_optional)):
    # Если указан custom_alias, проверяем уникальность
    if link_data.custom_alias:
        existing = await db.execute(
            select(Link).where(Link.custom_alias == link_data.custom_alias))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Custom alias already in use")
        short_code = link_data.custom_alias
    else:
        # Генерируем уникальный код
        for _ in range(10):
            short_code = generate_short_code()
            existing = await db.execute(
                select(Link).where(Link.short_code == short_code))
            if not existing.scalar_one_or_none():
                break
        else:
            raise HTTPException(status_code=500, detail="Could not generate unique short code")

    new_link = Link(
        short_code=short_code,
        original_url=str(link_data.original_url),
        custom_alias=link_data.custom_alias,
        expires_at=link_data.expires_at,
        project=link_data.project,
        user_id=current_user.id if current_user else None)
    db.add(new_link)
    await db.commit()
    await db.refresh(new_link)
    return new_link

# Поиск ссылок по оригинальному URL (п.4)
@router.get("/search", response_model=list[LinkOut])
async def search_links(
    original_url: str,
    db: AsyncSession = Depends(get_async_session)):
    result = await db.execute(
        select(Link).where(Link.original_url.contains(original_url)))
    return result.scalars().all()


# Отображение истории истекших ссылок с информацией о них
@router.get("/expired", response_model=list[LinkOut])
async def get_expired_links(
    db: AsyncSession = Depends(get_async_session)):
    result = await db.execute(
        select(Link).where(Link.expires_at < datetime.now(timezone.utc)))
    return result.scalars().all()


# топ популярных ссылок
@router.get("/popular", response_model=list[LinkOut])
async def get_popular_links(
    limit: int = 5,
    db: AsyncSession = Depends(get_async_session)):
    result = await db.execute(
        select(Link).order_by(Link.clicks.desc()).limit(limit))
    return result.scalars().all()


# Удаление неиспользуемых ссылок
@router.delete("/cleanup", status_code=204)
async def cleanup_unused_links(
    days: int = 30,
    db: AsyncSession = Depends(get_async_session),
    _: User = Depends(current_superuser)):
    threshold = datetime.now(timezone.utc) - timedelta(days=days)
    await db.execute(
        delete(Link).where(
            or_(
                Link.last_used < threshold,
                and_(Link.last_used.is_(None), Link.created_at < threshold))))
    await db.commit()
    return None


# Группировка ссылок по проектам
@router.get("/project/{project_name}", response_model=list[LinkOut])
async def get_links_by_project(project_name: str, db: AsyncSession = Depends(get_async_session)):
    result = await db.execute(select(Link).where(Link.project == project_name))
    return result.scalars().all()


# Получение статистики по ссылке (п.2)
@router.get("/{short_code}/stats", response_model=LinkStats)
async def get_link_stats(
    short_code: str,
    db: AsyncSession = Depends(get_async_session)):
    link = await get_link_or_404(db, short_code)
    return link


# Продлевает срок жизни ссылки на указанное количество дней
@router.patch("/{short_code}/extend", response_model=LinkOut)
async def extend_link_expiry(
    short_code: str,
    extend_data: LinkExtend,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_active_user)):
    link = await get_link_or_404(db, short_code)
    check_owner(link, current_user)
    if link.expires_at is None:
        raise HTTPException(status_code=400, detail="Link has no expiration date")
    link.expires_at += timedelta(days=extend_data.days)
    await db.commit()
    await db.refresh(link)
    await delete_cached_url(short_code)
    return link

# Редирект по короткой ссылке (п.1)
@router.get("/{short_code}", status_code=302)
async def redirect_to_original(
    short_code: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_session)):
    cached_url = await get_cached_url(short_code)
    if cached_url:
        background_tasks.add_task(update_stats_by_code, short_code)
        return RedirectResponse(url=cached_url, status_code=302)
    link = await get_link_or_404(db, short_code)
    # Проверка срока действия (п.5)
    if link.expires_at and link.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Link has expired")
    # Обновляем статистику (п.2)
    link.clicks += 1
    link.last_used = datetime.now(timezone.utc)
    await db.commit()
    await set_cached_url(short_code, link.original_url)
    # Возвращаем редирект (HTTP 302)
    return RedirectResponse(url=link.original_url, status_code=302)


# Удаление ссылки (п.1) только для авторизованного владельца
@router.delete("/{short_code}", status_code=204)
async def delete_link(
    short_code: str,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_active_user)):
    link = await get_link_or_404(db, short_code)
    check_owner(link, current_user)
    await db.delete(link)
    await db.commit()
    await delete_cached_url(short_code)
    return None

# Обновление оригинального URL (п.1) только для владельца
@router.put("/{short_code}", response_model=LinkOut)
async def update_link(
    short_code: str,
    link_update: LinkUpdate,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_active_user)):
    link = await get_link_or_404(db, short_code)
    check_owner(link, current_user)
    link.original_url = str(link_update.original_url)
    await db.commit()
    await db.refresh(link)
    await delete_cached_url(short_code)
    return link

