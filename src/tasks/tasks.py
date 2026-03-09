from celery import shared_task
from sqlalchemy import delete, and_, or_
from datetime import datetime, timedelta
from src.database import async_session_maker
from src.links.models import Link
from src.config import CLEANUP_DAYS

# Удаляет истекшие ссылки
@shared_task
def delete_expired_links():
    import asyncio
    async def _delete():
        async with async_session_maker() as db:
            await db.execute(delete(Link).where(Link.expires_at < datetime.utcnow()))
            await db.commit()
    asyncio.run(_delete())


# удаляет ссылки, не использованные более CLEANUP_DAYS дней
@shared_task
def cleanup_unused_links():
    days = int(CLEANUP_DAYS)
    threshold = datetime.utcnow() - timedelta(days=days)
    import asyncio
    async def _cleanup():
        async with async_session_maker() as db:
            await db.execute(
                delete(Link).where(
                    or_(
                        Link.last_used < threshold,
                        and_(Link.last_used.is_(None), Link.created_at < threshold))))
            await db.commit()
    asyncio.run(_cleanup())