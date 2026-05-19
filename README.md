

# AI Research Assistant

This project is an AI-powered research assistant with a FastAPI backend and a Vite/React frontend. It supports document ingestion, RAG (Retrieval-Augmented Generation), and integration with Google Drive and Notion.

---

## Features
- **Backend (Python/FastAPI):**
   - REST API for chat, code, profile, upload, and integrations (Google Drive, Notion)
   - RAG pipeline with ChromaDB
   - Document ingestion and background processing
- **Frontend (React/TypeScript):**
   - Modern chat UI
   - Sidebar, persona switching, citations, and integration sync

---

## Getting Started

### Prerequisites
- Python 3.9+
- Node.js 18+
- (Recommended) Create a virtual environment for Python

### 1. Backend Setup

```bash
cd backend
python -m venv venv
venv\Scripts\activate  # On Windows
# or
source venv/bin/activate  # On Mac/Linux
pip install -r requirements.txt
```

#### Environment Variables
Copy `.env.example` to `.env` and fill in your API keys and credentials:
- OpenAI, Anthropic, Groq, Gemini, Mistral, HuggingFace tokens
- Google/Notion credentials for integrations

### 2. Run Backend Server

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at: [http://localhost:8000](http://localhost:8000)

### 3. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

The frontend will be available at: [http://localhost:5173](http://localhost:5173)

---

## API Endpoints

- `/api/chat` — Chat interface
- `/api/upload` — File uploads
- `/api/profile` — User profile
- `/api/code` — Code execution
- `/api/integrations` — Google Drive & Notion sync

---


## Project Structure

```
backend/
  main.py           # FastAPI entrypoint
  routers/          # API endpoints
  tools/            # Integration logic
  rag/              # RAG pipeline
  models/           # Pydantic schemas
  ...
frontend/
  src/              # React app source
  public/           # Static assets
  ...
```

---

## Troubleshooting
- If `uvicorn` is not found, run `pip install uvicorn` in your backend environment.
- Ensure all API keys are set in `.env`.
- For CORS issues, check the backend CORS middleware settings in `main.py`.

---


## License
MIT
