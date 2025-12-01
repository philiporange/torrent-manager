import asyncio
import os
from fastapi import APIRouter, Depends, HTTPException, status, WebSocket
from fastapi.responses import FileResponse
from torrent_manager.auth import UserManager, SessionManager
from torrent_manager.models import User
from torrent_manager.config import Config
from ..schemas import CreateUserRequest, UpdateUserRequest
from ..dependencies import get_current_admin
from ..constants import SESSION_COOKIE_NAME

router = APIRouter(tags=["admin"])
config = Config()

@router.get("/admin/users")
async def list_users(admin: User = Depends(get_current_admin)):
    """List all users (Admin only)."""
    users = UserManager.list_users()
    return [
        {
            "id": u.id,
            "username": u.username,
            "is_admin": u.is_admin,
            "created_at": u.timestamp.isoformat()
        }
        for u in users
    ]


@router.post("/admin/users")
async def create_user_admin(
    request: CreateUserRequest,
    admin: User = Depends(get_current_admin)
):
    """Create a new user (Admin only)."""
    try:
        user = UserManager.create_user(
            username=request.username,
            password=request.password,
            is_admin=request.is_admin
        )
        return {"message": "User created", "user_id": user.id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/admin/users/{user_id}")
async def update_user_admin(
    user_id: str,
    request: UpdateUserRequest,
    admin: User = Depends(get_current_admin)
):
    """Update a user (Admin only)."""
    user = UserManager.update_user(
        user_id=user_id,
        password=request.password,
        is_admin=request.is_admin
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "User updated"}


@router.delete("/admin/users/{user_id}")
async def delete_user_admin(
    user_id: str,
    admin: User = Depends(get_current_admin)
):
    """Delete a user (Admin only)."""
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    
    success = UserManager.delete_user(user_id)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "User deleted"}


@router.websocket("/admin/logs/ws")
async def websocket_logs(websocket: WebSocket):
    """WebSocket endpoint to stream logs."""
    # We can't use standard dependency injection easily here for auth, so we'll check the cookie manually
    # or require a token. For simplicity in this context, we'll verify the session cookie.
    
    # Verify Auth
    session_id = websocket.cookies.get(SESSION_COOKIE_NAME)
    is_admin = False
    if session_id:
        session = SessionManager.validate_session(session_id)
        if session:
            user = UserManager.get_user_by_id(session.user_id)
            if user and user.is_admin:
                is_admin = True
    
    if not is_admin:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    
    log_path = config.LOG_PATH
    if not os.path.exists(log_path):
        await websocket.send_text("Log file not found.")
        await websocket.close()
        return

    try:
        with open(log_path, "r") as f:
            # Send last 20 lines first
            lines = f.readlines()[-20:]
            for line in lines:
                await websocket.send_text(line.strip())
            
            # Tail the file
            f.seek(0, os.SEEK_END)
            while True:
                line = f.readline()
                if line:
                    await websocket.send_text(line.strip())
                else:
                    await asyncio.sleep(0.5)
    except Exception as e:
        await websocket.send_text(f"Error reading log: {e}")
        await websocket.close()


@router.get("/admin/console")
async def admin_page(user: User = Depends(get_current_admin)):
    """Serve the admin console page."""
    return FileResponse("torrent_manager/static/admin.html", media_type="text/html")
