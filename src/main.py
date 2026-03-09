from fastapi import FastAPI, Depends
from src.auth.users import auth_backend, current_active_user, fastapi_users
from src.auth.schemas import UserCreate, UserRead
from src.auth.db import User
from src.links.router import router as links_router

app = FastAPI(title="ShortLink")

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