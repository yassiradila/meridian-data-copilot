"""
Document Retrieval Layer (ChromaDB over PDF documents).
Performs vector similarity search over corporate manuals, specs, and incident reports
with Self-Querying metadata inference.
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional
import chromadb
from src.config import CHROMA_DIR


def _get_embedding_function():
    """Lazily imports the embedding function from scripts.ingest_docs with fallback."""
    try:
        from scripts.ingest_docs import SemanticFeatureEmbeddingFunction
        return SemanticFeatureEmbeddingFunction()
    except Exception:
        import importlib.util
        ingest_path = Path(__file__).resolve().parent.parent / "scripts" / "ingest_docs.py"
        if ingest_path.exists():
            spec = importlib.util.spec_from_file_location("ingest_docs", str(ingest_path))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod.SemanticFeatureEmbeddingFunction()
        raise


_chroma_client: Optional[chromadb.PersistentClient] = None
_chroma_collection = None


def get_chroma_collection():
    """Returns or initializes the singleton Chroma collection for Stellantis PDFs."""
    global _chroma_client, _chroma_collection
    if _chroma_collection is None:
        if not CHROMA_DIR.exists():
            raise FileNotFoundError(f"ChromaDB directory not found at {CHROMA_DIR}. Please run scripts/ingest_docs.py first.")
        
        _chroma_client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        ef = _get_embedding_function()
        _chroma_collection = _chroma_client.get_collection(
            name="stellantis_docs",
            embedding_function=ef
        )
    return _chroma_collection


def infer_metadata_filters(query: str, explicit_filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Translates natural language user prompts into precise ChromaDB metadata filters
    to eliminate retrieval noise.
    """
    filters = dict(explicit_filters or {})
    q_lower = query.lower()

    is_plant_or_org_query = bool(re.search(r"\b(usine|plant|factory|produces|fabrique|direction|director|organigramme|incident|logistique)\b", q_lower))
    if "brand" not in filters and not is_plant_or_org_query:
        brands_found = []
        for b in ["Peugeot", "Citroën", "Fiat", "Jeep", "Alfa Romeo", "Opel"]:
            if b.lower() in q_lower:
                brands_found.append(b)
        if len(brands_found) == 1:
            filters["brand"] = brands_found[0]

    if "plant" not in filters:
        if re.search(r"\b(kénitra|kenitra|afz)\b", q_lower):
            filters["plant"] = "Kénitra"
        elif re.search(r"\b(vigo|espagne)\b", q_lower):
            filters["plant"] = "Vigo"
        elif re.search(r"\b(sochaux|france)\b", q_lower):
            filters["plant"] = "Sochaux"
        elif re.search(r"\b(tychy|pologne)\b", q_lower):
            filters["plant"] = "Tychy"

    if "doc_type" not in filters:
        if re.search(r"\b(incident|retard|livraison|boulot|rupture|juin 2024|june 2024|strike|disruption|caused it|cause)\b", q_lower):
            filters["doc_type"] = "incident_logistique"
        elif re.search(r"\b(usine|factory|plant|produces|fabrique|capacit[eé]|capacite|capacity|effectif|salari[eé]s|workforce|industriel|empreinte)\b", q_lower):
            filters["doc_type"] = "empreinte_industrielle"
        elif re.search(r"\b(sp[eé]cification|spécification|catalogue|moteur|engine|puretech|bluehdi|autonomie|finition|prix|base price)\b", q_lower):
            filters["doc_type"] = "catalogue_specifications"
        elif re.search(r"\b(directeur|director|direction|general|organigramme|rh|hr|quipe|equipe|team|responsable|nom|who is|leadership|ceo)\b", q_lower):
            filters["doc_type"] = "organisation_equipes"

    return filters


def search_documents(
    query: str,
    filters: Optional[Dict[str, Any]] = None,
    n_results: int = 4
) -> List[Dict[str, Any]]:
    """Performs vector similarity search on ingested PDF documents with metadata filtering."""
    try:
        col = get_chroma_collection()
    except Exception as e:
        return [{
            "id": "error",
            "content": f"Vector Store Initialization Error: {str(e)}",
            "metadata": {},
            "source": "None"
        }]

    resolved_filters = infer_metadata_filters(query, filters)
    where_clause = None

    if resolved_filters:
        valid_filters = {k: v for k, v in resolved_filters.items() if v is not None and v != "" and v != "GLOBAL" and v != "NONE"}
        if len(valid_filters) == 1:
            where_clause = valid_filters
        elif len(valid_filters) > 1:
            where_clause = {"$and": [{k: v} for k, v in valid_filters.items()]}

    results = None
    if where_clause:
        try:
            results = col.query(
                query_texts=[query],
                n_results=min(n_results, 6),
                where=where_clause
            )
            if not results or not results.get("documents") or not results["documents"][0]:
                results = None
        except Exception:
            results = None

    # Fallback to unconstrained search if filtered search returned nothing
    if results is None:
        try:
            results = col.query(
                query_texts=[query],
                n_results=min(n_results, 6)
            )
        except Exception as retry_err:
            return [{
                "id": "error",
                "content": f"Retrieval Error: {str(retry_err)}",
                "metadata": {},
                "source": "None"
            }]

    output_chunks = []
    if results and "documents" in results and results["documents"]:
        docs = results["documents"][0]
        metas = results["metadatas"][0] if results.get("metadatas") else [{}] * len(docs)
        ids = results["ids"][0] if results.get("ids") else [""] * len(docs)
        distances = results["distances"][0] if results.get("distances") else [0.0] * len(docs)

        for i, text in enumerate(docs):
            meta = metas[i] if i < len(metas) else {}
            output_chunks.append({
                "id": ids[i] if i < len(ids) else f"chunk_{i}",
                "content": text,
                "metadata": meta,
                "source": meta.get("source", "Stellantis Document"),
                "section": meta.get("section", "General"),
                "page": meta.get("page", 1),
                "doc_type": meta.get("doc_type", "pdf"),
                "plant": meta.get("plant", "GLOBAL"),
                "distance": round(float(distances[i]), 4) if i < len(distances) else 0.0,
            })

    return output_chunks


def get_collection_stats() -> Dict[str, Any]:
    """Returns diagnostic statistics on the ChromaDB vector collection."""
    try:
        col = get_chroma_collection()
        count = col.count()
        data = col.get()
        sources = set()
        if data and "metadatas" in data and data["metadatas"]:
            for m in data["metadatas"]:
                if m and "source" in m:
                    sources.add(m["source"])
        return {
            "total_documents": count,
            "unique_sources": sorted(list(sources)),
        }
    except Exception as e:
        return {
            "total_documents": 0,
            "unique_sources": [],
            "error": str(e),
        }