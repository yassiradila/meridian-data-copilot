"""
Document Ingestion Script.
Extracts, chunks, and indexes all corporate manuals, technical specifications,
industrial footprint memos, and incident reports from data/pdf/ into ChromaDB.
"""

import os
import re
import hashlib
from pathlib import Path
from typing import List, Dict, Any
import numpy as np
import chromadb
from pypdf import PdfReader

BASE_DIR = Path(__file__).resolve().parent.parent
PDF_DIR = BASE_DIR / "data" / "pdf"
CHROMA_DIR = BASE_DIR / "data" / "chroma_db"

STOP_WORDS = {
    "le", "la", "les", "un", "une", "des", "du", "de", "d", "en", "dans", "et", "ou",
    "pour", "sur", "par", "avec", "ce", "cet", "cette", "ces", "qui", "que", "quoi",
    "the", "is", "for", "in", "and", "of", "to", "a", "an", "on", "at", "by", "with"
}


class SemanticFeatureEmbeddingFunction(chromadb.EmbeddingFunction):
    """
    Deterministic dense feature embedding function (384 dims) with subword, n-gram hashing,
    and bilingual French/English stop-word filtering for precise technical matching.
    """
    def __init__(self, dim=384):
        self.dim = dim

    def name(self) -> str:
        return "stellantis_semantic_hasher_384"

    def _embed_text(self, text: str) -> list[float]:
        vec = np.zeros(self.dim, dtype=np.float32)
        clean = re.sub(r"[#*_`\[\]()\-+:,.;/\\'\"]", " ", text.lower())
        tokens = [t.strip() for t in clean.split() if len(t.strip()) > 1 and t.strip() not in STOP_WORDS]
        
        for i, token in enumerate(tokens):
            weight = 1.0 + min(len(token) * 0.25, 3.0)
            h1 = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
            idx1 = h1 % self.dim
            sign1 = 1.0 if (h1 % 2 == 0) else -1.0
            vec[idx1] += sign1 * weight * 2.0
            
            if i > 0:
                bg = f"{tokens[i-1]}_{token}"
                h2 = int(hashlib.sha256(bg.encode("utf-8")).hexdigest(), 16)
                idx2 = h2 % self.dim
                sign2 = 1.0 if (h2 % 2 == 0) else -1.0
                vec[idx2] += sign2 * 3.5

            if i > 1:
                tg = f"{tokens[i-2]}_{tokens[i-1]}_{token}"
                h3 = int(hashlib.sha1(tg.encode("utf-8")).hexdigest(), 16)
                idx3 = h3 % self.dim
                sign3 = 1.0 if (h3 % 2 == 0) else -1.0
                vec[idx3] += sign3 * 4.0

        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        return vec.tolist()

    def __call__(self, input: list[str]) -> list[list[float]]:
        return [self._embed_text(t) for t in input]


def infer_stellantis_tags(text: str, filename: str) -> Dict[str, str]:
    """Infers vehicle models, assembly plants, brands, and document type from text and filename."""
    t_lower = text.lower()
    fn_lower = filename.lower()

    # Document Type
    if "incident" in fn_lower or "logistique" in fn_lower:
        doc_type = "incident_logistique"
    elif "empreinte" in fn_lower or "usine" in fn_lower:
        doc_type = "empreinte_industrielle"
    elif "catalogue" in fn_lower or "specification" in fn_lower:
        doc_type = "catalogue_specifications"
    elif "organisation" in fn_lower or "equipe" in fn_lower:
        doc_type = "organisation_equipes"
    else:
        doc_type = "corporate_doc"

    # Brand
    brands = []
    for b in ["Peugeot", "Citroën", "Fiat", "Jeep", "Alfa Romeo", "Opel"]:
        if b.lower() in t_lower:
            brands.append(b)
    brand_tag = brands[0] if len(brands) == 1 else ("MULTIPLE" if len(brands) > 1 else "GLOBAL")

    # Assembly Plants
    plants = []
    for p in ["Kénitra", "Kenitra", "Vigo", "Sochaux", "Trnava", "Madrid", "Tychy", "Bursa", "Melfi", "Pomigliano", "Saragosse", "Poissy"]:
        if p.lower() in t_lower:
            plants.append(p)
    plant_tag = "Kénitra" if "kénitra" in t_lower or "kenitra" in t_lower else (plants[0] if plants else "GLOBAL")

    # Models
    models = []
    for m in ["208", "2008", "3008", "C3", "C4", "Ami", "500", "Tipo", "Topolino", "Avenger", "Compass", "Tonale", "Corsa", "Mokka"]:
        if re.search(rf"\b{m}\b", text, re.IGNORECASE):
            models.append(m)
    model_tag = models[0] if len(models) == 1 else ("MULTIPLE" if len(models) > 1 else "NONE")

    month_tag = "Juin 2024" if ("juin 2024" in t_lower or "june 2024" in t_lower) else "ANNUAL"

    return {
        "doc_type": doc_type,
        "brand": brand_tag,
        "plant": plant_tag,
        "model": model_tag,
        "period": month_tag,
    }


def parse_pdf_document(file_path: Path) -> List[Dict[str, Any]]:
    """Parses a binary PDF file using pypdf, extracting text page-by-page and section-by-section."""
    filename = file_path.name
    reader = PdfReader(str(file_path))
    enriched_chunks = []

    for page_idx, page in enumerate(reader.pages):
        page_text = page.extract_text() or ""
        if not page_text.strip():
            continue

        sections = re.split(r"\n(?=[0-9]+\.\s+[A-Z])", page_text)
        for s_idx, sec in enumerate(sections):
            clean_sec = re.sub(r"(\w+)-\n(\w+)", r"\1\2", sec.strip())
            clean_sec = re.sub(r"(?<!\n)\n(?!\n)", " ", clean_sec)
            clean_sec = re.sub(r"[ \t]+", " ", clean_sec).strip()
            if len(clean_sec) < 30:
                continue

            lines = clean_sec.splitlines()
            sec_title = lines[0][:80].strip() if lines else f"Page {page_idx+1} Section {s_idx+1}"
            tags = infer_stellantis_tags(clean_sec, filename)

            chunk_id = f"{file_path.stem}_p{page_idx+1}_s{s_idx}"
            meta = {
                "source": filename,
                "section": sec_title,
                "page": page_idx + 1,
                "doc_type": tags["doc_type"],
                "brand": tags["brand"],
                "plant": tags["plant"],
                "model": tags["model"],
                "period": tags["period"],
                "format": "pdf",
            }

            enriched_chunks.append({
                "id": chunk_id,
                "text": clean_sec,
                "metadata": meta
            })

    return enriched_chunks


def ingest_all_pdfs(pdf_dir: Path = PDF_DIR, chroma_dir: Path = CHROMA_DIR) -> int:
    """Ingests all PDF files from data/pdf into the ChromaDB vector collection."""
    print(f"[RAG] Ingesting PDF documents from: {pdf_dir}")
    print(f"[RAG] Storing ChromaDB in: {chroma_dir}")

    if not pdf_dir.exists():
        raise FileNotFoundError(f"PDF directory not found at: {pdf_dir}")

    os.makedirs(chroma_dir, exist_ok=True)
    client = chromadb.PersistentClient(path=str(chroma_dir))
    ef = SemanticFeatureEmbeddingFunction()

    try:
        client.delete_collection("stellantis_docs")
    except Exception:
        pass

    collection = client.create_collection(
        name="stellantis_docs",
        embedding_function=ef,
        metadata={"description": "Stellantis Maroc Corporate Manuals, Specs, and Incident Reports (PDF)"}
    )

    pdf_files = list(pdf_dir.glob("*.pdf"))
    if not pdf_files:
        print("[RAG] Warning: No PDF files found in data/pdf/")
        return 0

    total_chunks = 0
    for pdf_file in pdf_files:
        chunks = parse_pdf_document(pdf_file)
        if not chunks:
            continue

        ids = [c["id"] for c in chunks]
        docs = [c["text"] for c in chunks]
        metas = [c["metadata"] for c in chunks]

        collection.add(
            ids=ids,
            documents=docs,
            metadatas=metas
        )
        total_chunks += len(chunks)
        print(f"  -> Ingested '{pdf_file.name}': {len(chunks)} chunks")

    print(f"[RAG] Document ingestion complete! Total indexed PDF chunks: {total_chunks}")
    return total_chunks


if __name__ == "__main__":
    ingest_all_pdfs()
