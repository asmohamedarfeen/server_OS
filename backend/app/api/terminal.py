import asyncio
import os
import pty
import select
import struct
import termios
import fcntl
import signal
from urllib.parse import urlsplit
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from ..core.auth import websocket_user

router = APIRouter(tags=["terminal"])

@router.websocket("/api/terminal")
async def terminal(websocket: WebSocket, container_id: str | None = None):
    origin=websocket.headers.get("origin","")
    host=websocket.headers.get("host","")
    if not origin or urlsplit(origin).hostname != urlsplit("//"+host).hostname:
        await websocket.close(code=1008,reason="Origin rejected"); return
    try: websocket_user(websocket)
    except ValueError:
        await websocket.close(code=1008,reason="Authentication required"); return
    await websocket.accept()
    if container_id:
        await container_terminal(websocket, container_id)
        return
    pid,fd=pty.fork()
    if pid==0:
        os.environ.update({"TERM":"xterm-256color","HOME":"/root","SHELL":"/bin/bash"})
        os.execl("/usr/sbin/chroot","chroot","/host","/bin/bash","-l")
    try:
        while True:
            try:
                message=await asyncio.wait_for(websocket.receive_text(),timeout=.025)
                if message.startswith("\u0000resize:"):
                    try:
                        rows,cols=map(int,message[8:].split(","))
                        fcntl.ioctl(fd,termios.TIOCSWINSZ,struct.pack("HHHH",rows,cols,0,0))
                        os.kill(pid,signal.SIGWINCH)
                    except Exception: pass
                else: os.write(fd,message.encode())
            except asyncio.TimeoutError: pass
            ready,_,_=select.select([fd],[],[],0)
            if ready:
                try:
                    output=os.read(fd,65536)
                    if output: await websocket.send_text(output.decode(errors="replace"))
                except OSError: break
            try:
                waited,status=os.waitpid(pid,os.WNOHANG)
                if waited: break
            except ChildProcessError: break
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        try: os.killpg(pid,signal.SIGHUP)
        except ProcessLookupError: pass
        try: os.kill(pid,signal.SIGTERM)
        except ProcessLookupError: pass
        try: os.close(fd)
        except OSError: pass

async def container_terminal(websocket: WebSocket, container_id: str):
    stream=None
    try:
        from ..services.docker_engine import client
        docker=client()
        container=docker.containers.get(container_id)
        if container.status != "running":
            await websocket.send_text("Container is not running. Start it before opening a shell.\r\n")
            await websocket.close(code=1008,reason="Container is stopped")
            return
        exec_id=docker.api.exec_create(container.id,cmd=["/bin/sh"],stdin=True,stdout=True,stderr=True,tty=True)
        stream=docker.api.exec_start(exec_id,socket=True,tty=True)
        raw=stream
        while hasattr(raw,"_sock") and raw._sock is not raw:
            raw=raw._sock
        raw.setblocking(False)
        await websocket.send_text(f"Connected to {container.name} · /bin/sh\r\n\r\n")
        while True:
            try:
                message=await asyncio.wait_for(websocket.receive_text(),timeout=.025)
                if message.startswith("\u0000resize:"):
                    try:
                        rows,cols=map(int,message[8:].split(","))
                        docker.api.exec_resize(exec_id,height=rows,width=cols)
                    except Exception: pass
                else: raw.sendall(message.encode())
            except asyncio.TimeoutError: pass
            ready,_,_=select.select([raw],[],[],0)
            if ready:
                try:
                    output=raw.recv(65536)
                    if not output: break
                    await websocket.send_text(output.decode(errors="replace"))
                except BlockingIOError: pass
    except (WebSocketDisconnect,RuntimeError):
        pass
    except Exception as exc:
        try: await websocket.send_text(f"\r\nUnable to open container shell: {exc}\r\n")
        except Exception: pass
    finally:
        try:
            if stream: stream.close()
        except Exception: pass
