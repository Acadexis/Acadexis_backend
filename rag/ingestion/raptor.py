"""
Acadexis — RAPTOR Tree Builder (Sprint 2, Step 2.3)
====================================================
RAPTOR (Recursive Abstractive Processing for Tree-Organised Retrieval) builds
a multi-level summary hierarchy over existing leaf-level embeddings in Pinecone.

Why RAPTOR?
-----------
Standard RAG suffers from "needle in a haystack" problems for thematic queries.
Example: "Compare the main sorting algorithms covered in this course" requires
aggregating information from many scattered chunks — a single ANN search will
miss half of them.

RAPTOR solves this by building a BOTTOM-UP TREE:
  Level 0: Original chunks (leaf nodes) — ingested in Sprint 1
  Level 1: Cluster summaries (each summary covers ~5-15 related chunks)
  Level 2: Super-cluster summaries (each covers ~5-10 Level-1 summaries)
  Level 3: Course-level summary (optional; one node per course)

At query time (Sprint 2.1 retriever), we search ALL levels simultaneously.
Thematic queries naturally hit Level 2-3 nodes; factual queries hit Level 0.

Algorithm (for each level):
  1. Fetch all vectors at the current level from Pinecone
  2. Reduce dimensionality with UMAP (3072d → 10d)
  3. Fit a Gaussian Mixture Model to find the optimal number of clusters
  4. Assign each vector to its most-likely cluster (soft assignment)
  5. Concatenate the texts for each cluster
  6. Summarise each cluster using Gemini 1.5 Pro
  7. Embed the summary with Gemini (task_type=CLUSTERING)
  8. Upsert the summary vector into Pinecone with raptor_level=current+1

This is designed as a standalone CLI script, not a FastAPI endpoint, because:
  - It is a CPU+GPU-intensive batch job (not suitable for a web request).
  - It should run ONCE after initial bulk ingestion, then on demand.
  - In production, this would be triggered by a background worker (Celery/ARQ).

Usage:
  cd backend/
  python -m ingestion.raptor --course-id=csc501 --max-levels=2

Notes on UMAP parameters (documented in lesson.txt):
  - n_neighbors=15: controls local structure preservation.
    Too small → noisy clusters. Too large → loses local detail.
  - n_components=10: target dimensionality for GMM.
    GMM struggles above 20 dims (curse of dimensionality).
    10 is empirically optimal for academic text embeddings.
  - min_dist=0.1: prevents overlapping clusters in reduced space.
  - min_cluster_size=2: GMM minimum cluster size guard.

Notes on GMM (documented in lesson.txt):
  - We use Bayesian Information Criterion (BIC) to select the optimal number
    of Gaussian components (clusters). We test n=2 to n=min(50, N//2).
  - Soft assignment: each chunk belongs to its highest-probability cluster.
    This is more robust than K-means hard assignment for overlapping topics.
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

import numpy as np

# ---- Ensure backend/ is on sys.path when run as python -m ----------------
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# ---- These are lazy imports (inside functions) to keep startup fast --------
# They are large scientific packages (umap-learn, scikit-learn) that add
# ~2-3 seconds to startup time if imported at module level.

from rag.config import get_settings
from rag.ingestion.embedder import _get_gemini_client, get_pinecone_index

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RAPTOR_SUMMARY_TASK_TYPE = "CLUSTERING"   # Best task_type for summary embeddings
MAX_SUMMARY_INPUT_CHARS = 30_000          # Gemini 1.5 Pro has 1M token context
MIN_CLUSTER_SIZE = 2                      # Clusters with 1 doc get no summary
UMAP_N_COMPONENTS = 10                    # Reduced dimensionality for GMM clustering
UMAP_N_NEIGHBORS = 15                     # UMAP neighbourhood parameter
GMM_MAX_COMPONENTS = 50                   # Upper bound on cluster count search
PINECONE_FETCH_BATCH = 1000              # Max IDs per Pinecone fetch call
PINECONE_QUERY_TOP_K = 10_000            # Max results per Pinecone query call


# ---------------------------------------------------------------------------
# Step 1: Fetch all vectors at a given RAPTOR level from Pinecone
# ---------------------------------------------------------------------------

def _fetch_all_vectors_at_level(
    index,
    namespace: str,
    raptor_level: int,
) -> list[dict]:
    """
    Retrieve all vector IDs + metadata at a given RAPTOR level.

    Strategy:
      Pinecone serverless does not support native list-all-vectors.
      We use a "dummy query" with a zero vector to get the top_k IDs,
      then fetch metadata via index.fetch() in batches.

      NOTE: For production with millions of vectors, use Pinecone's
      list() method (available in some plans) or maintain an external
      ID registry in PostgreSQL (Sprint 3).

    Args:
        index:       A live Pinecone Index object.
        namespace:   Course namespace (= course_id from Sprint 1).
        raptor_level: 0 = leaf chunks, 1 = first-level summaries, etc.

    Returns:
        List of {"id": str, "text": str, "metadata": dict}
    """
    settings = get_settings()
    dimension = settings.pinecone_dimension

    logger.info(
        "Fetching all vectors at raptor_level=%d from namespace='%s'...",
        raptor_level,
        namespace,
    )

    # Use a zero-vector query with a metadata filter.
    # This is a common workaround when list() is unavailable.
    zero_vector = [0.0] * dimension
    response = index.query(
        vector=zero_vector,
        top_k=PINECONE_QUERY_TOP_K,
        namespace=namespace,
        filter={"raptor_level": {"$eq": raptor_level}},
        include_metadata=True,
        include_values=True,  # We need the raw vectors for UMAP
    )

    vectors = []
    for match in response.matches:
        meta = dict(match.metadata) if match.metadata else {}
        text = meta.pop("text", "")
        vectors.append(
            {
                "id": match.id,
                "text": text,
                "values": list(match.values),
                "metadata": meta,
            }
        )

    logger.info(
        "Fetched %d vectors at raptor_level=%d.", len(vectors), raptor_level
    )
    return vectors


# ---------------------------------------------------------------------------
# Step 2: UMAP Dimensionality Reduction
# ---------------------------------------------------------------------------

def _reduce_with_umap(
    embeddings: np.ndarray,
    n_components: int = UMAP_N_COMPONENTS,
    n_neighbors: int = UMAP_N_NEIGHBORS,
) -> np.ndarray:
    """
    Reduce high-dimensional embeddings to n_components dimensions using UMAP.

    Why UMAP over PCA?
      - UMAP preserves LOCAL structure better than PCA for semantic embeddings.
      - Academic topics form non-linear manifolds in embedding space.
      - UMAP's neighbourhood graph is better aligned with semantic clustering.

    Why NOT t-SNE?
      - t-SNE is non-deterministic (random seed aside) and slow on > 5K points.
      - t-SNE's output cannot be used to project NEW points (needed at query time).
      - UMAP supports `transform()` for out-of-sample projection.

    Args:
        embeddings:   Shape (N, D) where D = 3072 (Gemini dimension).
        n_components: Target dimensions for GMM (default 10).
        n_neighbors:  UMAP local neighbourhood size (default 15).

    Returns:
        Reduced embeddings of shape (N, n_components).
    """
    import umap  # Lazy import

    logger.info(
        "UMAP: reducing %d vectors from %d → %d dimensions...",
        embeddings.shape[0],
        embeddings.shape[1],
        n_components,
    )

    reducer = umap.UMAP(
        n_components=n_components,
        n_neighbors=n_neighbors,
        min_dist=0.1,       # Controls cluster compactness
        metric="cosine",    # Match Pinecone's cosine similarity metric
        random_state=42,    # Deterministic output for reproducibility
        low_memory=True,    # Reduces peak RAM for large corpora
    )

    reduced = reducer.fit_transform(embeddings)
    logger.info("UMAP complete. Output shape: %s.", reduced.shape)
    return reduced


# ---------------------------------------------------------------------------
# Step 3: Gaussian Mixture Model Clustering (BIC-optimal n_components)
# ---------------------------------------------------------------------------

def _cluster_with_gmm(
    reduced_embeddings: np.ndarray,
    max_components: int = GMM_MAX_COMPONENTS,
) -> np.ndarray:
    """
    Fit a Gaussian Mixture Model and return cluster assignments.

    We use BIC (Bayesian Information Criterion) to select the number of
    clusters automatically:
      - We fit GMMs for n_components = 2, 3, ..., min(max_components, N//2)
      - The model with the lowest BIC wins (best trade-off: fit vs. complexity)

    Why GMM over K-Means?
      - GMM produces SOFT assignments — each point belongs to a cluster
        with a probability, not a hard assignment.
      - Academic topics naturally overlap (e.g., "sorting" and "complexity").
        Soft assignment handles this better than K-Means.
      - We use the argmax (highest-probability cluster) for simplicity,
        but the probabilities could be used for weighted summarisation (Sprint 3).

    Args:
        reduced_embeddings: Shape (N, n_components) from UMAP.
        max_components:     Upper bound on search for optimal n_clusters.

    Returns:
        Array of shape (N,) with cluster assignments (0-indexed integers).
    """
    from sklearn.mixture import GaussianMixture  # Lazy import

    n_samples = reduced_embeddings.shape[0]
    if n_samples < 2:
        # Can't cluster fewer than 2 points
        return np.zeros(n_samples, dtype=int)

    max_k = min(max_components, n_samples // 2, n_samples - 1)
    if max_k < 2:
        return np.zeros(n_samples, dtype=int)

    logger.info(
        "GMM: searching for optimal n_clusters in range [2, %d]...", max_k
    )

    best_bic = float("inf")
    best_gmm = None
    best_k = 2

    for k in range(2, max_k + 1):
        try:
            gmm = GaussianMixture(
                n_components=k,
                covariance_type="full",
                random_state=42,
                max_iter=300,
                n_init=3,         # Multiple initialisations for stability
            )
            gmm.fit(reduced_embeddings)
            bic = gmm.bic(reduced_embeddings)

            if bic < best_bic:
                best_bic = bic
                best_gmm = gmm
                best_k = k
        except Exception as exc:
            logger.warning("GMM fit failed for k=%d: %s", k, exc)

    if best_gmm is None:
        logger.warning("All GMM fits failed; assigning all to cluster 0.")
        return np.zeros(n_samples, dtype=int)

    assignments = best_gmm.predict(reduced_embeddings)
    logger.info(
        "GMM: optimal k=%d (BIC=%.2f). Clusters: %s.",
        best_k,
        best_bic,
        dict(zip(*np.unique(assignments, return_counts=True))),
    )
    return assignments


# ---------------------------------------------------------------------------
# Step 4: Cluster Summarisation with Gemini 1.5 Pro
# ---------------------------------------------------------------------------

def _summarise_cluster(
    cluster_texts: list[str],
    course_id: str,
    level: int,
) -> str | None:
    """
    Summarise a cluster of text chunks using Gemini 1.5 Pro.

    Why Gemini 1.5 Pro (not Flash)?
      - RAPTOR summaries become the "authoritative" higher-level knowledge.
        They are retrieved and injected into the context window for thematic
        questions. Quality matters more than speed here.
      - Flash is used for real-time chat (Sprint 3 agent routing).
      - RAPTOR runs as a background batch job — latency is acceptable.

    Args:
        cluster_texts:  List of chunk texts to summarise.
        course_id:      Used for contextualising the summary prompt.
        level:          Current RAPTOR level (for informing the prompt).

    Returns:
        Summary string, or None if the API call fails.
    """
    from google import genai as _genai

    settings = get_settings()
    client = _get_gemini_client()

    # Concatenate texts with a separator — Gemini handles long contexts well
    combined_text = "\n\n---\n\n".join(cluster_texts)
    if len(combined_text) > MAX_SUMMARY_INPUT_CHARS:
        combined_text = combined_text[:MAX_SUMMARY_INPUT_CHARS]
        logger.debug("Cluster text truncated to %d chars.", MAX_SUMMARY_INPUT_CHARS)

    prompt = f"""You are a senior academic curriculum analyst for the Acadexis educational platform.

Below are {len(cluster_texts)} related text excerpts from course '{course_id}' (RAPTOR Level {level - 1} content).

Your task: Write a comprehensive, well-structured academic summary that captures ALL key concepts, 
definitions, algorithms, formulas, and relationships present in these excerpts.

Guidelines:
- Write 3-6 paragraphs covering the main themes.
- Preserve technical terminology, mathematical notation, and specific details.
- This summary will be used as a "retrieval node" to answer broad thematic questions.
- Do NOT add external knowledge — synthesise only what is provided.
- Write in clear academic English.

---EXCERPTS START---
{combined_text}
---EXCERPTS END---

COMPREHENSIVE ACADEMIC SUMMARY:"""

    try:
        response = client.models.generate_content(
            model=settings.gemini_pro_model,
            contents=prompt,
        )
        summary = response.text.strip()
        logger.debug(
            "Cluster summary generated: %d chars.", len(summary)
        )
        return summary
    except Exception as exc:
        logger.error("Gemini summarisation failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Step 5: Embed Summary and Upsert into Pinecone
# ---------------------------------------------------------------------------

def _embed_and_upsert_summary(
    index,
    summary_text: str,
    cluster_ids: list[str],
    namespace: str,
    raptor_level: int,
    cluster_idx: int,
) -> bool:
    """
    Embed a cluster summary and upsert it into Pinecone as a RAPTOR node.

    The summary's chunk_id format:
      "raptor::L{level}::C{cluster_idx}::{namespace}"
    This is distinct from leaf chunk IDs (which use filename::page::idx)
    so they can be easily identified and filtered.

    Args:
        index:         Live Pinecone Index.
        summary_text:  The cluster summary from Gemini.
        cluster_ids:   IDs of the source chunks that form this cluster.
        namespace:     Course namespace.
        raptor_level:  Level this summary node belongs to (1, 2, or 3).
        cluster_idx:   Index of this cluster within the current level.

    Returns:
        True if upsert succeeded.
    """
    settings = get_settings()
    client = _get_gemini_client()

    # Embed the summary with CLUSTERING task type
    # (different from both RETRIEVAL_DOCUMENT and RETRIEVAL_QUERY —
    # CLUSTERING is optimised for producing well-separated topic embeddings)
    try:
        response = client.models.embed_content(
            model=settings.gemini_embedding_model,
            contents=[summary_text],
            config={"task_type": RAPTOR_SUMMARY_TASK_TYPE,
                    "output_dimensionality": settings.gemini_embedding_dimension},
        )
        vector = response.embeddings[0].values
    except Exception as exc:
        logger.error(
            "Failed to embed summary for cluster %d at level %d: %s",
            cluster_idx,
            raptor_level,
            exc,
        )
        return False

    # Build a deterministic ID for this RAPTOR node
    node_id = f"raptor::L{raptor_level}::C{cluster_idx}::{namespace}"

    metadata = {
        "text": summary_text[:40_000],    # Pinecone 40KB metadata limit
        "raptor_level": raptor_level,
        "chunk_type": "raptor_summary",
        "course_id": namespace,
        "source_chunk_ids": ",".join(cluster_ids[:50]),  # Store up to 50 source IDs
        "cluster_size": len(cluster_ids),
        "filename": f"RAPTOR_L{raptor_level}_Cluster{cluster_idx}",
        "page_number": 0,                 # No page for synthetic summaries
        "is_ocr": False,
        "chunk_index": cluster_idx,
        "char_count": len(summary_text),
        "word_count": len(summary_text.split()),
        "excerpt": summary_text[:500],
    }

    try:
        index.upsert(
            vectors=[{"id": node_id, "values": vector, "metadata": metadata}],
            namespace=namespace,
        )
        logger.info(
            "Upserted RAPTOR node: %s (level=%d, cluster=%d, sources=%d)",
            node_id,
            raptor_level,
            cluster_idx,
            len(cluster_ids),
        )
        return True
    except Exception as exc:
        logger.error("Pinecone upsert for RAPTOR node %s failed: %s", node_id, exc)
        return False


# ---------------------------------------------------------------------------
# Main RAPTOR Loop — One Level of Tree Building
# ---------------------------------------------------------------------------

def build_raptor_level(
    course_id: str,
    source_level: int,
    target_level: int,
) -> dict:
    """
    Build one level of the RAPTOR tree.

    Fetches all vectors at source_level, clusters them, summarises each
    cluster, embeds the summaries, and upserts them at target_level.

    Args:
        course_id:    Pinecone namespace (= course_id from Sprint 1).
        source_level: Raptor level to read from (0 for leaf nodes).
        target_level: Raptor level to write summaries to (source_level + 1).

    Returns:
        Summary stats dict: {vectors_read, clusters_found, summaries_upserted}
    """
    index = get_pinecone_index()

    # --- Step 1: Fetch source vectors ----------------------------------------
    vectors = _fetch_all_vectors_at_level(index, course_id, source_level)

    if len(vectors) < MIN_CLUSTER_SIZE:
        logger.warning(
            "Only %d vectors at level %d — not enough to cluster. Skipping.",
            len(vectors),
            source_level,
        )
        return {"vectors_read": len(vectors), "clusters_found": 0, "summaries_upserted": 0}

    # --- Step 2: UMAP reduction -----------------------------------------------
    embeddings = np.array([v["values"] for v in vectors], dtype=np.float32)
    reduced = _reduce_with_umap(embeddings)

    # --- Step 3: GMM Clustering -----------------------------------------------
    assignments = _cluster_with_gmm(reduced)
    n_clusters = int(assignments.max()) + 1

    # --- Step 4 + 5: Summarise and upsert each cluster -----------------------
    upserted_count = 0

    for cluster_idx in range(n_clusters):
        member_indices = np.where(assignments == cluster_idx)[0]
        member_texts = [vectors[i]["text"] for i in member_indices]
        member_ids = [vectors[i]["id"] for i in member_indices]

        if len(member_texts) < MIN_CLUSTER_SIZE:
            logger.debug(
                "Cluster %d has only %d members — skipping.", cluster_idx, len(member_texts)
            )
            continue

        logger.info(
            "Processing cluster %d/%d (%d members) at level %d...",
            cluster_idx + 1,
            n_clusters,
            len(member_texts),
            source_level,
        )

        # Step 4: Summarise
        summary = _summarise_cluster(
            cluster_texts=member_texts,
            course_id=course_id,
            level=target_level,
        )

        if not summary:
            continue

        # Step 5: Embed + Upsert
        success = _embed_and_upsert_summary(
            index=index,
            summary_text=summary,
            cluster_ids=member_ids,
            namespace=course_id,
            raptor_level=target_level,
            cluster_idx=cluster_idx,
        )
        if success:
            upserted_count += 1

    stats = {
        "vectors_read": len(vectors),
        "clusters_found": n_clusters,
        "summaries_upserted": upserted_count,
    }
    logger.info("RAPTOR level %d → %d complete: %s", source_level, target_level, stats)
    return stats


# ---------------------------------------------------------------------------
# Full Multi-Level RAPTOR Builder
# ---------------------------------------------------------------------------

def build_raptor_tree(course_id: str, max_levels: int = 2) -> list[dict]:
    """
    Build the complete RAPTOR tree for a course, up to max_levels.

    Recommended max_levels:
      1 — Fast, modest improvement for factual and mid-range queries
      2 — Good balance for most academic courses (recommended)
      3 — Best for very large courses (100+ lecture PDFs); slower

    Args:
        course_id:  Pinecone namespace (= course_id from Sprint 1).
        max_levels: Number of RAPTOR levels to build above leaf nodes.

    Returns:
        List of per-level stats dicts.
    """
    all_stats = []

    for level in range(max_levels):
        source_level = level
        target_level = level + 1

        logger.info(
            "=== RAPTOR: Building level %d → %d for course='%s' ===",
            source_level,
            target_level,
            course_id,
        )

        stats = build_raptor_level(
            course_id=course_id,
            source_level=source_level,
            target_level=target_level,
        )
        all_stats.append({"from_level": source_level, "to_level": target_level, **stats})

        # Stop early if the previous level produced too few summaries to cluster further
        if stats["summaries_upserted"] < MIN_CLUSTER_SIZE:
            logger.info(
                "RAPTOR stopping early: only %d summaries at level %d "
                "(below MIN_CLUSTER_SIZE=%d).",
                stats["summaries_upserted"],
                target_level,
                MIN_CLUSTER_SIZE,
            )
            break

    return all_stats


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    parser = argparse.ArgumentParser(
        description="Build the RAPTOR knowledge tree for a course.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--course-id",
        required=True,
        help="Course namespace ID (e.g. csc501-dsa). Must have ingested content.",
    )
    parser.add_argument(
        "--max-levels",
        type=int,
        default=2,
        choices=[1, 2, 3],
        help="Number of RAPTOR levels to build above leaf nodes.",
    )
    args = parser.parse_args()

    logger.info("Starting RAPTOR tree build for course='%s'...", args.course_id)
    stats = build_raptor_tree(course_id=args.course_id, max_levels=args.max_levels)

    print("\n=== RAPTOR Build Complete ===")
    for level_stat in stats:
        print(
            f"  Level {level_stat['from_level']} → {level_stat['to_level']}: "
            f"{level_stat['vectors_read']} vectors → "
            f"{level_stat['clusters_found']} clusters → "
            f"{level_stat['summaries_upserted']} summaries upserted"
        )


if __name__ == "__main__":
    main()
