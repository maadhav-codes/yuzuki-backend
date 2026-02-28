from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Database URL for SQLite, using a file named test.db in the current directory
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"

# Create a SQLAlchemy engine to connect to the SQLite database, with the option to allow multiple threads
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

# Create a session factory that will be used to create database sessions
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create a base class for our SQLAlchemy models
Base = declarative_base()


# Define a SQLAlchemy model for the messages table
class Message(Base):
    # Table name in the database
    __tablename__ = "messages"

    # Unique identifier for each message, set as primary key and indexed for faster queries
    id = Column(Integer, primary_key=True, index=True)

    # Column to store the content of the message
    content = Column(String)


# Create the messages table in the database if it doesn't already exist
Base.metadata.create_all(bind=engine)


# Define a Pydantic model for the message creation request
class MessageCreate(BaseModel):
    content: str


# Create a FastAPI instance to define the API endpoints
app = FastAPI()


# Endpoint to check if the backend is running
@app.get("/")
def read_root():
    return {"message": "Backend is running"}


# Endpoint to receive a message and store it in the database
@app.post("/message/")
def create_message(message: MessageCreate):
    # Create a new database session
    with SessionLocal() as db:
        # Create a new Message instance with the content from the request
        db_message = Message(content=message.content)

        # Add the new message to the database session
        db.add(db_message)

        # Commit the transaction to save the message to the database
        db.commit()

        # Refresh the instance to get the generated ID after commit
        db.refresh(db_message)

        # Return the received message content and the generated ID as a response
        return {"received": message.content, "id": db_message.id}
