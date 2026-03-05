import os
import time
from typing import Dict, Any

import requests
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from database import get_db
from models import User

# Load environment variables from .env file
load_dotenv()

# Ensure that the necessary environment variables are set
SUPABASE_URL = os.getenv("SUPABASE_URL")
if not SUPABASE_URL:
    raise ValueError("SUPABASE_URL not set")

JWKS_URL = os.getenv("SUPABASE_JWKS_URL")
if not JWKS_URL:
    raise ValueError("SUPABASE_JWKS_URL not set")


# Define the HTTPBearer security scheme for FastAPI
security = HTTPBearer()

# Cache for JWKS keys, mapping 'kid' to the key data
JWKS_CACHE: Dict[str, Any] = {}
# Timestamp of the last JWKS fetch, used to determine when to refresh the cache
JWKS_LAST_FETCH: float = 0
# Time-to-live for the JWKS cache in seconds (1 hour)
CACHE_TTL: int = 3600


# Function to fetch the JWKS keys from the Supabase endpoint, with caching to reduce unnecessary network calls
def get_jwt_token() -> Dict[str, Any]:
    # Use global variables to access and update the JWKS cache and last fetch time
    global JWKS_CACHE, JWKS_LAST_FETCH
    # Get the current time in seconds since the epoch
    current_time = time.time()

    # Return the cached JWKS keys if they are still valid based on the TTL
    if JWKS_CACHE and (current_time - JWKS_LAST_FETCH) < CACHE_TTL:
        return JWKS_CACHE

    try:
        # Fetch the JWKS keys from the specified URL
        response = requests.get(JWKS_URL, timeout=10)
        # Check if the request was successful, raise an error if not
        response.raise_for_status()
        # Extract the 'keys' from the JSON response, defaulting to an empty list if not present
        keys = response.json().get("keys", [])

        # Create a dictionary mapping 'kid' to the key data for easy lookup
        JWKS_CACHE = {key["kid"]: key for key in keys}
        # Update the last fetch time to the current time
        JWKS_LAST_FETCH = current_time
        return JWKS_CACHE
    except Exception as ex:
        raise HTTPException(
            status_code=500, detail=f"Could not fetch JWT token: {str(ex)}"
        )


# Function to get the current user based on the JWT token provided in the Authorization header
def get_current_user(
    # Extract the token from the Authorization header
    credentials: HTTPAuthorizationCredentials = Depends(security),
    # Get a database session
    db: Session = Depends(get_db),
):
    # Extract the token from the credentials
    token = credentials.credentials

    # Attempt to decode the JWT token and retrieve the user information
    try:
        # Get the 'kid' from the unverified header to identify which key to use for verification
        unverified_header = jwt.get_unverified_header(token)
        # Extract the 'kid' from the unverified header
        kid = unverified_header.get("kid")

        # Raise an HTTP 401 error if the 'kid' is missing from the token header
        if not kid:
            raise HTTPException(
                status_code=401, detail="Invalid token header: missing kid"
            )

        # Retrieve the JWKS keys, using the caching mechanism to avoid unnecessary network calls
        jwks = get_jwt_token()
        # Retrieve the signing key from the JWKS cache using the 'kid' from the token header
        signing_key = jwks.get(kid)

        # If the signing key is not found in the cache, raise an HTTP 401 error indicating that the signing key is missing
        if not signing_key:
            raise HTTPException(
                status_code=401, detail="Invalid token header: missing signing key"
            )

        # Construct the expected issuer URL based on the Supabase URL
        issuer = f"{SUPABASE_URL}/auth/v1"

        # Use the algorithm published by Supabase's JWK when present (e.g., ES256).
        token_alg = unverified_header.get("alg")
        key_alg = signing_key.get("alg")
        algorithm = key_alg or token_alg
        if not algorithm:
            raise HTTPException(
                status_code=401, detail="Invalid token header: missing alg"
            )

        # Decode the JWT token using the signing key, specifying the expected algorithm, audience, and issuer for validation
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=[algorithm],
            audience="authenticated",
            issuer=issuer,
        )

        # The 'sub' claim in the JWT payload typically contains the user ID, which is used to identify the user in the database
        user_id: str = payload.get("sub")
        # The 'email' claim may also be present in the JWT payload, providing the user's email address if available
        email: str | None = payload.get("email")

        # Raise an HTTP 401 error if the 'sub' claim is missing from the token payload, indicating that the token is invalid
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token payload")

        # Check if a user with the given Supabase UID already exists in the database, and if not, create a new user record with the provided email and commit it to the database
        user = db.query(User).filter(User.supabase_uid == user_id).first()

        # If the user does not exist in the database, create a new user record with the Supabase UID and email, add it to the session, commit the transaction, and refresh the user instance to get the updated data from the database
        if not user:
            user = User(supabase_uid=user_id, email=email)
            db.add(user)
            db.commit()
            db.refresh(user)

        return user

    # Re-raise intentionally raised HTTP errors (e.g., invalid token header) unchanged.
    except HTTPException:
        raise

    # Catch any JWT-related errors that occur during token decoding and raise an HTTP 401 error with a message indicating that the credentials could not be validated, including the specific error message for debugging purposes
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate credentials: {str(e)}",
        )

    # Catch any other exceptions that may occur during the authentication process and raise an HTTP 500 error with a message indicating that there was an internal authentication error, including the specific error message for debugging purposes
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Internal authentication error: {str(e)}"
        )
