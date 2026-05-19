from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import os

# Set cache dir BEFORE importing chromadb
os.environ["CHROMA_CACHE_DIR"] = os.getenv("CHROMA_CACHE_DIR", "/var/data/chroma")

from routers import chat, upload
from routers.profile import router as profile_router
from routers.code import code_router
from routers.integrations import router as integrations_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Pre-warm ChromaDB so model downloads at startup, not on first upload
    print("🔄 Pre-warming ChromaDB...")
    try:
        import chromadb
        client = chromadb.Client()
        client.get_or_create_collection("warmup")
        print("✅ ChromaDB ready")
    except Exception as e:
        print(f"⚠️ ChromaDB warmup failed: {e}")
    yield  # App runs here
    print("🛑 Shutting down...")


app = FastAPI(title="AI Research Assistant API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router, prefix="/api")
app.include_router(upload.router, prefix="/api")
app.include_router(profile_router)
app.include_router(code_router, prefix="/api")
app.include_router(integrations_router, prefix="/api")


@app.get("/")
def root():
    return {"status": "AI Research Assistant running"}