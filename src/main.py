from fastapi import FastAPI, Depends
from src.auth.users import auth_backend, current_active_user, fastapi_users
from src.auth.schemas import UserCreate, UserRead
from src.auth.db import User
from src.links.router import router as links_router
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
import asyncio
from src.tasks.cleanup_simple import delete_expired_links_simple
from src.core.redis import redis_client

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    async def periodic_cleanup():
        while True:
            await delete_expired_links_simple()
            await asyncio.sleep(3600) 

    task = asyncio.create_task(periodic_cleanup())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await redis_client.close()

app = FastAPI(title="ShortLink", lifespan=lifespan)

# роутеры аутентификации
app.include_router(
    fastapi_users.get_auth_router(auth_backend), prefix="/auth/jwt", tags=["auth"]
)
app.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    prefix="/auth",
    tags=["auth"],
)

# роутер ссылок
app.include_router(links_router)

@app.get("/")
async def root():
    return {"message": "Hello!"}

@app.get("/protected-route")
def protected_route(user: User = Depends(current_active_user)):
    return f"Hello, {user.email}"

@app.get("/unprotected-route")
def unprotected_route():
    return "Hello, anonym"
