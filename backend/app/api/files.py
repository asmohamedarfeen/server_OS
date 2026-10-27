from pathlib import Path
import shutil
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel, Field
from ..core.auth import get_current_user
from ..core.config import STORAGE_DIR

router = APIRouter(prefix="/api/files", tags=["storage"], dependencies=[Depends(get_current_user)])

def resolve(path: str):
    target = (STORAGE_DIR / path.lstrip("/")).resolve()
    if target != STORAGE_DIR.resolve() and STORAGE_DIR.resolve() not in target.parents:
        raise HTTPException(400, "Path is outside the managed storage area")
    return target

@router.get("")
def list_files(path: str = ""):
    target = resolve(path)
    if not target.exists():
        raise HTTPException(404, "Folder not found")
    if not target.is_dir():
        raise HTTPException(400, "Path is not a folder")
    return [{"name": p.name, "path": str(p.relative_to(STORAGE_DIR)), "directory": p.is_dir(), "size": p.stat().st_size if p.is_file() else None, "modified": p.stat().st_mtime} for p in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))]

class FolderBody(BaseModel):
    path: str = Field(min_length=1, max_length=500)

class RenameBody(BaseModel):
    path: str = Field(min_length=1, max_length=500)
    name: str = Field(min_length=1, max_length=255)

@router.post("/folders")
def create_folder(body: FolderBody):
    target = resolve(body.path)
    target.mkdir(parents=True, exist_ok=False)
    return {"ok": True}

@router.post("/upload")
async def upload(path: str = "", file: UploadFile = File(...)):
    parent = resolve(path)
    parent.mkdir(parents=True, exist_ok=True)
    name = Path(file.filename or "upload.bin").name
    target = resolve(str(Path(path) / name))
    size = 0
    with target.open("wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk: break
            size += len(chunk)
            if size > 200 * 1024 * 1024:
                target.unlink(missing_ok=True)
                raise HTTPException(413, "File uploads are limited to 200 MB")
            out.write(chunk)
    return {"name": name, "size": target.stat().st_size}

@router.get("/download")
def download(path: str):
    from fastapi.responses import FileResponse
    target = resolve(path)
    if not target.is_file():
        raise HTTPException(404, "File not found")
    return FileResponse(target, filename=target.name)

@router.delete("")
def delete_file(path: str):
    target = resolve(path)
    if target == STORAGE_DIR.resolve():
        raise HTTPException(400, "The storage root cannot be deleted")
    if not target.exists():
        raise HTTPException(404, "Path not found")
    shutil.rmtree(target) if target.is_dir() else target.unlink()
    return {"ok": True}

@router.post("/rename")
def rename_file(body: RenameBody):
    if body.name in {".", ".."} or "/" in body.name or "\\" in body.name:
        raise HTTPException(400, "Choose a name without path separators")
    target = resolve(body.path)
    if not target.exists(): raise HTTPException(404, "Path not found")
    replacement = resolve(str(Path(body.path).parent / body.name))
    if replacement.exists(): raise HTTPException(409, "An item with that name already exists")
    target.rename(replacement)
    return {"ok": True, "name": replacement.name}
