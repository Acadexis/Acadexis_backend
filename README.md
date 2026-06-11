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
*   **Vector Search & AI StudyLab (RAG):** Automated PDF processing (extracting pages, text chunking, generating OpenAI `text-embedding-3-small` vector embeddings), pgvector database storage, and GPT-4o-mini chat tutoring with precise source citations (specifying document name, page, and quoted snippet).
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
| **Database** | PostgreSQL + pgvector extension | 16+ |
| **Task Queue / Broker** | Celery + Redis | 5.3.x / 5.0.x |
| **Real-time / ASGI** | Django Channels + Daphne | 4.1.x / 4.1.x |
| **AI / LLM Integration** | OpenAI API SDK | 1.30.x |
| **PDF Extraction** | pdfplumber & pypdf | 0.11.x / 4.2.x |

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
│   ├── courses/              # Materials, Enrollments, Ratings & Vector chunks
│   ├── studylab/             # Study Sessions, Chat history & Citations
│   ├── analytics/            # Bookmarks & Struggle Heatmaps
│   ├── notifications/        # WebSockets consumers and push utilities
│   └── support/              # Contact forms, Bug reports, Admin requests
├── Docs/                     # Detailed guides and API specifications
├── Dockerfile                # Deployment container configuration
├── docker-compose.yml        # Multi-container local execution setup
├── Pipfile                   # Pipenv package dependencies
├── requirements.txt          # Standard requirements list
└── supervisord.conf          # Task monitor execution configuration
```

---

## ⚙️ Prerequisites & Setup

Ensure you have the following installed on your machine:
*   Python 3.12 or 3.14
*   PostgreSQL with the `pgvector` extension enabled
*   Redis server (listening on port `6379`)

### 1. Installation
Clone the repository and install the dependencies:

```bash
# Clone the project
git clone https://github.com/Acadexis/Acadexis_backend.git
cd Acadexis_backend

# Option A: Install dependencies via Pipenv (Recommended)
pipenv install

# Option B: Install dependencies via pip
python -m pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy the environment variables template and customize the values:

```bash
cp .env.example .env
```
Fill in the necessary credentials in `.env` (e.g. `DB_URL`, `REDIS_URL`, `OPENAI_API_KEY`, `RESEND_API_KEY`, and `GOOGLE_CLIENT_ID`).

### 3. Run Migrations & Seed Data
Initialize your database schema:

```bash
# Run Django database migrations
python manage.py migrate

# Enable pgvector if setting up PostgreSQL for the first time
python manage.py enable_pgvector

# Collect static assets
python manage.py collectstatic --noinput
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
