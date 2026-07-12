# Acadexis Backend 🎓🤖
### Institutional AI Knowledge Grounding SaaS

[![Python Version](https://img.shields.io/badge/python-3.12%20%7C%203.14-blue.svg)](https://www.python.org/)
[![Django Version](https://img.shields.io/badge/django-6.0-green.svg)](https://www.djangoproject.com/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/docker-enabled-blue.svg)](#docker-deployment)

Acadexis is an **Institutional AI Knowledge Grounding SaaS** designed to bridge the gap between academic course content and AI-powered learning. Built on a robust Django backend, it utilizes vector search, real-time WebSockets, background tasks, and custom analytics to provide students with contextual RAG (Retrieval-Augmented Generation) tutoring while providing lecturers with learning insight heatmaps.

---

## 🚀 Key Features

*   **Custom Authentication & Single Sign-On (SSO):** Custom user model using Email as primary identifier, supporting roles (Student, Lecturer, Admin), secure JWT Token rotation (`SimpleJWT`), and Google OAuth2 academic domain validation.
*   **Agentic AI StudyLab (RAG):** Multi-agent LangGraph orchestration pipeline with 5 core agent nodes: `RetrieverAgent`, `ProfilerAgent`, `WikiLoader`, `PedagogicalAgent` (Socratic tutor), and `VerifierAgent` (hallucination checker). Powered by Gemini 1.5 Pro/Flash and namespaced Pinecone vector store search (with Cohere reranking).
*   **Query Security & PII Masking:** Microsoft Presidio + custom regex patterns (for matriculation numbers, academic emails) for PII masking. 3-layer guardrail scan (sandwich defense, regex pattern detection, and Gemini Flash classifier).
*   **Multimodal Ingestion Pipeline:** Automated PDF processing via PyMuPDF parsing, LangChain text splitters, Gemini Embedding 2, and Pinecone upsert. Supports multimodal image extraction, syllabus wiki compilation, and Gemini context caching.
*   **RAGAS Evaluation & Logger:** Asynchronous background RAGAS scoring (context precision, recall, faithfulness, answer relevancy) using Gemini Flash as the LLM judge. Logs interactions to a local SQLite database.
*   **Institutional Hierarchy:** Hierarchical data architecture linking Universities to Faculties, Departments, Profiles, and Courses.
*   **Learning Heatmap & Analytics:** Aggregation of search keywords, struggle tracking by course topic, and question counts to map student difficulties.
*   **Real-time Notifications:** Real-time push system using Django Channels (WebSockets) powered by a Redis channel layer.
*   **Robust File Handling:** Local media storage in development with direct S3 bucket integration (`django-storages`) for production environments.

---

## 🛠️ Technology Stack

| Component | Technology | Version |
| :--- | :--- | :--- |
| **Backend Framework** | Django | 6.0.x |
| **API Framework** | Django REST Framework | 3.16.x |
| **Database** | PostgreSQL + pgvector (fallback) & aiosqlite (RAG logs) | 16+ / 0.22.x |
| **Task Queue / Broker** | Celery + Redis | 5.3.x / 5.0.x |
| **Real-time / ASGI** | Django Channels + Daphne | 4.1.x / 4.1.x |
| **Agentic AI Orchestrator**| LangGraph & LangChain | 0.2.x / 0.2.x |
| **AI / LLM / Vector Store**| Gemini SDK (Google GenAI) & Pinecone & Cohere | 1.55.x / 9.1.x / 7.0.x |
| **PDF / Image Parser** | PyMuPDF (fitz) | 1.28.x |
| **PII Masking & NLP** | Presidio (Microsoft) & spaCy (en_core_web_sm) | 2.2.x / 3.8.x |

---

## 📁 Directory Structure

```text
Acadexis_backend/
├── Acadexis_backend/         # Core configuration
│   ├── settings/             # Environment-specific settings (base, dev, prod)
│   ├── asgi.py               # Channels routing
│   ├── celery.py             # Celery app instantiation
│   └── urls.py               # Root API endpoints routing
├── apps/                     # Application components
│   ├── accounts/             # Authentication, Roles, Profile & SSO
│   ├── institutions/         # Universities, Faculties, and Departments
│   ├── courses/              # Materials, Enrollments, Ratings & fallback chunks
│   ├── studylab/             # Study Sessions, Chat history & Citations
│   ├── analytics/            # Bookmarks & Struggle Heatmaps
│   ├── notifications/        # WebSockets consumers and push utilities
│   └── support/              # Contact forms, Bug reports, Admin requests
├── rag/                      # Agentic RAG AI & Security subsystem
│   ├── agents/               # LangGraph StateGraph & 5 Agent Nodes
│   ├── ingestion/            # Parsers, Chunkers, Embedder, Cache manager
│   ├── security/             # PII masking & 3-layer guardrail system
│   ├── evaluation/           # RAGAS Triad scoring & Local SQLite Logging
│   ├── schemas/              # Pydantic internal state schemas
│   ├── config.py             # Django settings → RAG config bridge
│   └── startup.py            # SQLite log DB and Pinecone index bootstrapper
├── Docs/                     # Detailed guides and API specifications
├── Dockerfile                # Deployment container configuration
├── docker-compose.yml        # Multi-container local execution setup
├── requirements.txt          # Package dependencies (including AI stack)
└── supervisord.conf          # Task monitor execution configuration
```

---

## ⚙️ Prerequisites & Setup

Ensure you have the following installed on your machine:
*   Python 3.12+ (tested on Python 3.12.3)
*   Redis server (listening on port `6379`, required for Django Channels)
*   Pinecone Vector Database account
*   Google Gemini API Key (Google AI Studio)

### 1. Installation
Clone the repository, create a virtual environment, and install package dependencies:

```bash
# Clone the project
git clone https://github.com/Acadexis/Acadexis_backend.git
cd Acadexis_backend

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies (includes Django, Celery, and RAG AI stack)
pip install -r requirements.txt

# Download spaCy model for PII masking NER
python -m spacy download en_core_web_sm
```

### 2. Configure Environment Variables
Copy the environment variables template and customize the values:

```bash
cp .env.example .env
```
Fill in the necessary credentials in `.env`. Ensure the RAG specific environment variables are set:
*   `GOOGLE_API_KEY`: Google Gemini API Key
*   `PINECONE_API_KEY`: Pinecone API Key
*   `PINECONE_INDEX_NAME`: Name of your Pinecone index
*   `PINECONE_CLOUD`/`PINECONE_REGION`: e.g. `aws` / `us-east-1`
*   `COHERE_API_KEY`: (Optional) For retrieval reranking

### 3. Run Migrations & Setup
Initialize the database schemas and bootstrapping:

```bash
# Run Django database migrations
python manage.py migrate

# Collect static assets
python manage.py collectstatic --noinput

# Verify system & RAG pipeline startup
python manage.py check
```

---

## 💻 Running the Services

To run the full asynchronous ecosystem, you need to start the web app, WebSocket layer, and background task worker:

```bash
# Start Django Development Server (WSGI)
python manage.py runserver

# Start ASGI server directly (for WebSocket testing)
daphne Acadexis_backend.asgi:application

# Start Celery worker in another terminal
celery -A Acadexis_backend worker -l info
```

### 🐳 Docker Deployment
Alternatively, you can run all components (Postgres, Redis, Celery, Daphne) using Docker Compose:

```bash
docker-compose up --build
```

---

## 🧪 Testing

To execute the unit tests suite (covers API views, custom JWT token claims, email backends, RAG search integrations, and task behavior):

```bash
python manage.py test
```

---

## 📄 API Documentation

Acadexis features automated OpenAPI v3 schema generation. With the server running, you can access:
*   **Swagger UI:** `http://localhost:8000/api/schema/swagger-ui/`
*   **Redoc:** `http://localhost:8000/api/schema/redoc/`
*   **Raw OpenAPI JSON:** `http://localhost:8000/api/schema/`
