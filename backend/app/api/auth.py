from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
import hmac
import os
from ..core.auth import configured, setup_admin, check_login, token_for, get_current_user
from ..core.config import COOKIE_SECURE, TOKEN_TTL_HOURS

router = APIRouter(prefix="/api/auth", tags=["authentication"])

class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=12, max_length=256)

class SetupCredentials(Credentials):
    setup_key: str = Field(min_length=16, max_length=256)

@router.get("/status")
def status():
    return {"configured": configured()}

@router.post("/setup")
def setup(body: SetupCredentials, response: Response):
    if configured():
        raise HTTPException(409, "Administrator is already configured")
    expected=os.getenv("SETUP_TOKEN", "")
    if not expected or not hmac.compare_digest(body.setup_key, expected):
        raise HTTPException(403, "Setup key is incorrect")
    setup_admin(body.username, body.password)
    response.set_cookie("arfeen_session", token_for(body.username), httponly=True, secure=COOKIE_SECURE, samesite="strict", max_age=TOKEN_TTL_HOURS * 3600, path="/")
    return {"username": body.username}

@router.post("/login")
def login(body: Credentials, response: Response):
    if not configured():
        raise HTTPException(428, "Complete administrator setup first")
    if not check_login(body.username, body.password):
        raise HTTPException(401, "Username or password is incorrect")
    response.set_cookie("arfeen_session", token_for(body.username), httponly=True, secure=COOKIE_SECURE, samesite="strict", max_age=TOKEN_TTL_HOURS * 3600, path="/")
    return {"username": body.username}

@router.post("/logout")
def logout(response: Response):
    response.delete_cookie("arfeen_session", path="/")
    return {"ok": True}

@router.get("/me")
def me(user: str = Depends(get_current_user)):
    return {"username": user}
