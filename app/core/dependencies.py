from fastapi import Depends, HTTPException, status

from app.core.auth import get_current_user


async def require_auth(user=Depends(get_current_user)):
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )
    return user
