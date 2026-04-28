import logging
import os
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from pymongo.errors import PyMongoError

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI") or os.getenv(
    "MONGODB_URL", "mongodb://localhost:27017"
)
DB_NAME = os.getenv("MONGODB_DB", "shared_text")
COLLECTION_NAME = os.getenv("MONGODB_COLLECTION", "text_board")
DOC_ID = "global-text"

logger = logging.getLogger("uvicorn.error")

app = FastAPI(title="Global Text Board")

cors_origins_env = os.getenv("CORS_ORIGINS", "*")
if cors_origins_env == "*":
    cors_origins = ["*"]
else:
    cors_origins = [
        origin.strip()
        for origin in cors_origins_env.split(",")
        if origin.strip()
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

client: Optional[AsyncIOMotorClient] = None
collection: Optional[AsyncIOMotorCollection] = None


class TextPayload(BaseModel):
    text: str = Field("", description="Global shared text")


def get_collection() -> AsyncIOMotorCollection:
    if collection is None:
        raise HTTPException(status_code=503, detail="Database not initialized")
    return collection


@app.on_event("startup")
async def startup() -> None:
    global client, collection
    try:
        client = AsyncIOMotorClient(MONGODB_URI)
        await client.admin.command("ping")
        collection = client[DB_NAME][COLLECTION_NAME]
        logger.info("MongoDB connected")
    except Exception as exc:
        collection = None
        logger.error("MongoDB connection failed: %s", exc)


@app.on_event("shutdown")
async def shutdown() -> None:
    if client is not None:
        client.close()


@app.get("/health")
async def health() -> dict:
    return {"status": "online"}


@app.get("/get-text")
async def get_text() -> dict:
    col = get_collection()
    try:
        doc = await col.find_one({"_id": DOC_ID})
    except PyMongoError as exc:
        raise HTTPException(status_code=500, detail="Database error") from exc

    if not doc:
        return {"text": ""}

    return {"text": doc.get("text", "")}


@app.post("/upload")
async def upload_text(payload: TextPayload) -> dict:
    col = get_collection()
    try:
        await col.update_one(
            {"_id": DOC_ID},
            {"$set": {"text": payload.text}},
            upsert=True,
        )
    except PyMongoError as exc:
        raise HTTPException(status_code=500, detail="Database error") from exc

    return {"text": payload.text}
