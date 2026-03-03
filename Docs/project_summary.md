# Acadexis: Personalized Learning Platform with Lecturer-Curated LLM

> **Tagline:** Grounded Intelligence. Guided Learning.

## 📌 Project Overview
**Acadexis** is a scalable SaaS educational platform designed to bridge the gap between static course materials and active student engagement. Unlike generalized AI tools, Acadexis utilizes **Retrieval-Augmented Generation (RAG)** to provide students with a 24/7 interactive tutor strictly grounded in their lecturer’s specific notes, slides, and textbooks.

By anchoring AI responses to verified academic sources, Acadexis eliminates "hallucinations" and ensures that students receive guidance aligned with their specific university curriculum.

---

## 🎯 The Problem & Solution

### The Problem
* **Generalized AI:** Standard LLMs often provide information that contradicts specific course syllabi or includes "hallucinated" facts.
* **The "Black Box" of Learning:** Lecturers often don't know which topics students are struggling with until the mid-term or final exams.
* **Lack of Scalability:** In large university classes, one-on-one tutoring is physically and financially impossible.

### The Solution (Acadexis)
* **Curated Knowledge:** Lecturers upload their own materials to create a "closed-loop" AI brain.
* **Source Transparency:** Every AI response includes a citation/link to the exact page of the lecture note used.
* **The Struggle Heatmap:** Real-time analytics provide lecturers with data on common student queries and quiz failure points.

---

## 🛠️ Technical Ecosystem

### Core Tech Stack
* **Frontend:** Next.js (App Router), Tailwind CSS v4, Framer Motion (for fluid UI/UX).
* **Backend:** Django REST Framework (DRF), PostgreSQL (Primary DB), JWT Auth.
* **AI Architecture:** Python-based RAG pipeline (LangChain/LlamaIndex), Vector Database (Pinecone/ChromaDB), LLM (Gemini 1.5 Pro / GPT-4o).
* **DevOps:** GitHub Actions (CI/CD), Postman (API Testing), Vercel/Render (Deployment).

### System Architecture
1. **The Ingestion Layer:** PDF/PPTX parsing and vector embedding.
2. **The Retrieval Layer:** Semantic search to find relevant "chunks" of lecture notes.
3. **The Augmentation Layer:** Feeding the "found" notes into the LLM as a "Grounding Truth."
4. **The Analytics Layer:** Aggregating student quiz data into actionable insights for the lecturer.

---

## 👥 User Roles & Workflows

### 1. The Lecturer (The Curator)
* **Goal:** Create a high-fidelity digital tutor.
* **Key Features:** Knowledge Hub (File Upload), Sandbox Testing, Analytics Dashboard (Struggle Heatmap).

### 2. The Student (The Learner)
* **Goal:** Get instant, accurate help 24/7.
* **Key Features:** AI Chat Interface, Integrated PDF Viewer (Citations), Auto-generated Knowledge Check Quizzes.

### 3. The Super Admin (The Manager)
* **Goal:** Manage the university-wide SaaS instance.
* **Key Features:** University Onboarding, User Management, AI Token/Cost Monitoring.

---

## 📅 Project Timeline (4-Month Sprint)
* **Month 1:** Discovery, UI/UX Design (Figma), and Backend Foundation (Auth/Profile).
* **Month 2:** AI RAG Pipeline Development & File Ingestion Logic.
* **Month 3:** Feature Integration (Chat UI, Quiz Engine, Analytics Visualization).
* **Month 4:** Testing, Polishing, Documentation (Thesis), and Final Defense.

---

## 💡 The "Impact Trifecta" Focus
Acadexis is built to scale within the **EdTech**, **FinTech** (Education Financing), and **HealthTech** (Medical Education) domains, ensuring that high-stakes learning is supported by high-accuracy AI.

---
*Created by the Acadexis Project Team (2026)*