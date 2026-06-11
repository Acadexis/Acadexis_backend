# Acadexis AI Engineer Handover Guide 🎓🤖

Welcome to Acadexis! This document provides a comprehensive blueprint of the current AI-tutoring scaffolding (StudyLab, pgvector RAG, and background indexing) and outlines the steps necessary to replace the current naive stubs with a production-grade, state-of-the-art academic grounding engine.

---

## 🛠️ Current AI Architecture & Pipeline

The AI system is built with **PostgreSQL (pgvector) + OpenAI API (text-embedding-3-small & gpt-4o-mini) + Celery**. 

### 1. Document Indexing Flow (Celery background task)
*   **Trigger:** `POST /api/materials/` in `courses` app.
*   **Code Reference:** [courses/tasks.py](file:///c:/Users/Abiola%20John/Documents/OVERSIGHT/Acadexis_backend/apps/courses/tasks.py) (method `process_material`).
*   **Current Naive Implementation:**
    1. Opens PDF files using `pdfplumber` to extract text page-by-page.
    2. Runs a character-based chunking slider: `CHUNK_SIZE = 800` characters, `CHUNK_OVERLAP = 100` characters.
    3. Sends chunks in batches of 100 to OpenAI's `text-embedding-3-small` (1536 dimensions).
    4. Saves chunks into the database as `MaterialChunk` records with their vector representation.

### 2. Retrieval-Augmented Generation (RAG) Flow
*   **Trigger:** `POST /api/sessions/{session_id}/ask/` in `studylab` app.
*   **Code Reference:** [studylab/services.py](file:///c:/Users/Abiola%20John/Documents/OVERSIGHT/Acadexis_backend/apps/studylab/services.py) (method `answer_question`).
*   **Current RAG Implementation:**
    1. Embeds user query using `text-embedding-3-small`.
    2. Runs a similarity search using Cosine Distance (`CosineDistance`) to query the top $K=5$ closest chunks from the active course's materials.
    3. Builds a raw string context of these chunks formatted as:
       `[filename p. page_number]\nchunk_content`
    4. Submits the context and the question to `gpt-4o-mini` with a simple system prompt.
    5. Stores the answer in `ChatMessage` (role="assistant") and maps the 5 source chunks into the `MessageSource` table.

---

## 🚧 Current Limitations & Stubs (To Be Replaced)

The current "StudyLab" features naive stubs that need to be refactored for a production system:

### 1. Missing Chat History (No Conversational Memory)
*   **The Problem:** The `answer_question` RAG service only sends the *current* query and the retrieved context to the LLM. It does not load or pass previous session messages. Consequently, the AI cannot answer follow-up questions (e.g., "Can you explain the second bullet point in more detail?").
*   **Action Required:** Before querying pgvector or calling the LLM, retrieve the chat history for the session:
    ```python
    history = ChatMessage.objects.filter(session=session).order_by('created_at')
    ```
    Inject these previous messages in correct role format (`user` vs `assistant`) into the LLM payload, keeping a maximum window token count.

### 2. Naive Chunking Strategy
*   **The Problem:** The current chunking function slices strings purely by character offsets. This breaks sentences, truncates mathematical equations, and loses tabular layout semantics.
*   **Action Required:** Implement semantic chunking (e.g. splitting by sentence/paragraph boundaries, recursive headers, or layout-aware parsers). Consider integrating `LlamaParse` or `Unstructured` to handle complex PDF elements (tables, charts, graphs).

### 3. Missing Vector Indexing
*   **The Problem:** Currently, similarity searches are performing sequential scans because no index is defined on `MaterialChunk.embedding`. As materials scale, query performance will degrade.
*   **Action Required:** Create a Django migration that adds an HNSW (Hierarchical Navigable Small World) index:
    ```sql
    CREATE INDEX my_hnsw_idx ON courses_materialchunk USING hnsw (embedding vector_cosine_ops);
    ```

### 4. Primitive Topic Struggle Heatmap
*   **The Problem:** In `apps/analytics/tasks.py`, the `recompute_heatmap` task groups topics based on a naive check: extracting the first 3 words of student queries.
*   **Action Required:** Implement an LLM-based categorization function or cluster the embeddings of student questions to group student struggles into meaningful, actionable topic keys.

---

## 🎯 Production Engineering Tasks

### A. Backend Upgrades
1.  **Context Re-ranking:** Add a re-ranking step (e.g., Cohere Rerank or a local cross-encoder model) after retrieving the top 15-20 chunks from pgvector, filtering them down to the top 5 most relevant chunks to decrease LLM distraction.
2.  **Streaming Responses:** Transition from blocking request-responses to server-sent events (SSE) or WebSockets so that the user receives token streams in real-time.
3.  **Configurable Persona Prompts:** Move the `SYSTEM_PROMPT` out of hardcode into a database setting, allowing course instructors to customize their course AI tutor's persona (e.g., "Ask guiding Socratic questions instead of giving direct answers").

### B. Frontend Upgrades
1.  **Markdown & Code Rendering:** Integrate `react-markdown` and `prismjs` (or syntax-highlighter) to render structured outlines, tables, and code blocks cleanly in the chat interface.
2.  **LaTeX Math Equations:** Use `rehype-katex` or standard MathJax configurations to render LaTeX equations produced by the LLM (crucial for STEM courses).
3.  **Interactive Citations:** Wire the citations (`MessageSource` payloads) to the PDF viewer. Clicking on a source citation should automatically slide open the course document on the exact page referenced and highlight the matching snippet.

---

## 🔑 Key Configuration Variables

Ensure the following variables are configured in the `.env` dashboard:
*   `OPENAI_API_KEY`: Used to call `text-embedding-3-small` and `gpt-4o-mini`.
*   `REDIS_URL`: Runs the Celery background worker queue for processing PDF uploads.
