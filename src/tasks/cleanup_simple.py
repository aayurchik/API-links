from datetime import datetime
from src.database import async_session_maker
from src.links.models import Link
from sqlalchemy import delete

async def delete_expired_links_simple():
    async with async_session_maker() as db:
        await db.execute(delete(Link).where(Link.expires_at < datetime.utcnow()))
        await db.commit()
