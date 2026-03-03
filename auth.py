import os

from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from database import get_db
from models import User

# Load environment variables from .env file
load_dotenv()

JWT_SECRET = os.getenv("JWT_SECRET")

# Define the HTTPBearer security scheme for FastAPI
security = HTTPBearer()


# Function to get the current user based on the JWT token provided in the Authorization header
def get_current_user(
    # Extract the token from the Authorization header
    credentials: HTTPAuthorizationCredentials = Depends(security),
    # Get a database session
    db: Session = Depends(get_db),
):
    # Extract the token from the credentials
    token = credentials.credentials

    try:
        # Decode the JWT token using the secret and validate the audience
        payload = jwt.decode(
            token, JWT_SECRET, algorithms=["HS256"], audience="authenticated"
        )

        # The "sub" claim typically contains the user ID in JWT tokens
        user_id: str = payload.get("sub")

        # Extract the email from the token payload
        email: str = payload.get("email")

        # Raise an HTTP 401 error if the user ID is not found in the token payload
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token payload")

        # Check if the user exists in the database, if not create a new user
        user = db.query(User).filter(User.supabase_uid == user_id).first()

        # If the user does not exist in the database, create a new user with the extracted user ID and email
        if not user:
            # Create a new user with the extracted user ID and email
            user = User(supabase_uid=user_id, email=email)
            # Add the new user to the database session
            db.add(user)
            # Commit the transaction to save the new user in the database
            db.commit()
            # Refresh the user instance to get the updated data from the database
            db.refresh(user)

        return user

    # If there is an error decoding the JWT token, raise an HTTP 401 error indicating that the credentials could not be validated
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )
