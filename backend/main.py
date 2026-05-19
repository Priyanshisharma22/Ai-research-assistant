from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import chat, upload
from routers.profile import router as profile_router
from routers.code import code_router
from routers.integrations import router as integrations_router  # NEW

app = FastAPI(title="AI Research Assistant API")

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
app.include_router(integrations_router, prefix="/api")  # NEW

@app.get("/")
def root():
    return {"status": "AI Research Assistant running"}