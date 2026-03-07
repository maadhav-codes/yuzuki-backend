import os
import time
import logging
from typing import Dict, Any

import requests
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from database import get_db
from models import User

load_dotenv()


SUPABASE_URL = os.getenv("SUPABASE_URL")
if not SUPABASE_URL:
    raise ValueError("SUPABASE_URL not set")

JWKS_URL = os.getenv("SUPABASE_JWKS_URL")
if not JWKS_URL:
    raise ValueError("SUPABASE_JWKS_URL not set")


security = HTTPBearer()
logger = logging.getLogger(__name__)


JWKS_CACHE: Dict[str, Any] = {}

JWKS_LAST_FETCH: float = 0

CACHE_TTL: int = 3600


def get_jwt_token() -> Dict[str, Any]:

    global JWKS_CACHE, JWKS_LAST_FETCH

    current_time = time.time()

    if JWKS_CACHE and (current_time - JWKS_LAST_FETCH) < CACHE_TTL:
        return JWKS_CACHE

    try:
        response = requests.get(JWKS_URL, timeout=10)

        response.raise_for_status()

        keys = response.json().get("keys", [])

        JWKS_CACHE = {key["kid"]: key for key in keys}

        JWKS_LAST_FETCH = current_time
        return JWKS_CACHE
    except Exception:
        logger.exception("Failed to fetch Supabase JWKS")
        raise HTTPException(
            status_code=500, detail="Unable to validate authentication token"
        )


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    return get_user_from_token(credentials.credentials, db)


def get_user_from_token(token: str, db: Session) -> User:

    try:
        unverified_header = jwt.get_unverified_header(token)

        kid = unverified_header.get("kid")

        if not kid:
            raise HTTPException(
                status_code=401, detail="Invalid token header: missing kid"
            )

        jwks = get_jwt_token()

        signing_key = jwks.get(kid)

        if not signing_key:
            raise HTTPException(
                status_code=401, detail="Invalid token header: missing signing key"
            )

        issuer = f"{SUPABASE_URL}/auth/v1"

        token_alg = unverified_header.get("alg")
        key_alg = signing_key.get("alg")
        algorithm = key_alg or token_alg
        if not algorithm:
            raise HTTPException(
                status_code=401, detail="Invalid token header: missing alg"
            )

        payload = jwt.decode(
            token,
            signing_key,
            algorithms=[algorithm],
            audience="authenticated",
            issuer=issuer,
        )

        user_id: str = payload.get("sub")

        email: str | None = payload.get("email")

        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token payload")

        user = db.query(User).filter(User.supabase_uid == user_id).first()

        if not user:
            user = User(supabase_uid=user_id, email=email)
            db.add(user)
            db.commit()
            db.refresh(user)

        return user

    except HTTPException:
        raise

    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )

    except Exception:
        logger.exception("Unexpected error during authentication")
        raise HTTPException(status_code=500, detail="Internal authentication error")
