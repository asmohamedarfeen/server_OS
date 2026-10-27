import re

from fastapi import APIRouter, Depends, HTTPException

from ..core.auth import get_current_user
from ..services.github import (
    GitHubError,
    delete_github_token,
    github_token,
    list_branches,
    list_repositories,
    save_github_token,
    validate_github_token,
)

router = APIRouter(prefix="/api/github", tags=["github"], dependencies=[Depends(get_current_user)])


def _token_or_error() -> str:
    try:
        token = github_token()
    except GitHubError as exc:
        raise HTTPException(503, str(exc)) from exc
    if not token:
        raise HTTPException(409, "Connect a GitHub token in Settings before selecting a private repository.")
    return token


@router.get("/connection")
def connection_status():
    try:
        return {"connected": github_token() is not None}
    except GitHubError as exc:
        raise HTTPException(503, str(exc)) from exc


@router.put("/connection")
def connect(body: dict):
    token = body.get("token")
    if not isinstance(token, str) or not 20 <= len(token) <= 512 or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in token):
        raise HTTPException(400, "Enter a valid GitHub token")
    try:
        validate_github_token(token)
        save_github_token(token)
    except GitHubError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"connected": True}


@router.delete("/connection")
def disconnect():
    delete_github_token()
    return {"connected": False}


@router.get("/repositories")
def repositories():
    try:
        return list_repositories(_token_or_error())
    except GitHubError as exc:
        raise HTTPException(502, str(exc)) from exc


@router.get("/repositories/{owner}/{repo}/branches")
def branches(owner: str, repo: str):
    segment = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
    if not segment.fullmatch(owner) or not segment.fullmatch(repo):
        raise HTTPException(400, "Invalid GitHub owner or repository name.")
    try:
        return list_branches(_token_or_error(), owner, repo)
    except GitHubError as exc:
        raise HTTPException(502, str(exc)) from exc
