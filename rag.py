"""
rag.py
------
RAG module: chunk Java files, embed, store in Chroma, retrieve context.
"""

import os
import re
import hashlib
from pathlib import Path

import chromadb
from openai import OpenAI

_openai_client = None
_chroma_client = None

CHUNK_SIZE = 60
CHUNK_OVERLAP = 10
EMBED_MODEL = os.getenv("EMBED_MODEL", "text-embedding-3-small")
CHROMA_PATH = os.getenv("CHROMA_PATH", ".chroma_db")
COLLECTION_NAME = "changelens_repo"
TOP_K = 5


def _get_openai():
    global _openai_client
    if _openai_client is None:
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL")
        if base_url:
            _openai_client = OpenAI(api_key=api_key, base_url=base_url)
        else:
            _openai_client = OpenAI(api_key=api_key)
    return _openai_client


def _get_chroma(persist_dir=CHROMA_PATH):
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(path=persist_dir)
    return _chroma_client


def chunk_java_files(repo_path: str) -> list:
    chunks = []
    repo = Path(repo_path)
    for java_file in repo.rglob("*.java"):
        try:
            lines = java_file.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            continue
        rel_path = str(java_file.relative_to(repo))
        step = CHUNK_SIZE - CHUNK_OVERLAP
        for i in range(0, max(1, len(lines)), step):
            chunk_lines = lines[i: i + CHUNK_SIZE]
            text = "\n".join(chunk_lines)
            if not text.strip():
                continue
            chunk_id = hashlib.md5(f"{rel_path}:{i}:{text[:50]}".encode()).hexdigest()
            chunks.append({"id": chunk_id, "text": text, "file": rel_path, "start_line": i + 1})
    return chunks


def index_repo(repo_path: str, persist_dir: str = CHROMA_PATH, force: bool = False) -> int:
    db = _get_chroma(persist_dir)
    collection = db.get_or_create_collection(COLLECTION_NAME)
    if not force and collection.count() > 0:
        return collection.count()

    chunks = chunk_java_files(repo_path)
    if not chunks:
        return 0

    client = _get_openai()
    BATCH = 100
    for start in range(0, len(chunks), BATCH):
        batch = chunks[start: start + BATCH]
        texts = [c["text"] for c in batch]
        resp = client.embeddings.create(model=EMBED_MODEL, input=texts)
        vectors = [e.embedding for e in resp.data]
        collection.upsert(
            ids=[c["id"] for c in batch],
            embeddings=vectors,
            documents=[c["text"] for c in batch],
            metadatas=[{"file": c["file"], "start_line": c["start_line"]} for c in batch],
        )
    return len(chunks)


def retrieve_context(query: str, persist_dir: str = CHROMA_PATH, top_k: int = TOP_K) -> list:
    db = _get_chroma(persist_dir)
    try:
        collection = db.get_collection(COLLECTION_NAME)
    except Exception:
        return []

    client = _get_openai()
    resp = client.embeddings.create(model=EMBED_MODEL, input=[query])
    q_vec = resp.data[0].embedding
    n = min(top_k, collection.count())
    if n == 0:
        return []
    results = collection.query(
        query_embeddings=[q_vec], n_results=n,
        include=["documents", "metadatas", "distances"],
    )
    out = []
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    dists = results.get("distances", [[]])[0]
    for doc, meta, dist in zip(docs, metas, dists):
        out.append({"text": doc, "file": meta.get("file", ""),
                    "start_line": meta.get("start_line", 0), "distance": round(dist, 4)})
    return out


def build_rag_context(diff_text: str, changed_files: list, persist_dir: str = CHROMA_PATH) -> str:
    query = _build_query(diff_text, changed_files)
    chunks = retrieve_context(query, persist_dir=persist_dir)
    if not chunks:
        return ""
    parts = ["### Related code context (retrieved via RAG):"]
    for c in chunks:
        parts.append(f"\n--- {c['file']} (line {c['start_line']}) ---")
        parts.append(c["text"])
    return "\n".join(parts)


def _build_query(diff_text, changed_files):
    names = set()
    for f in changed_files:
        stem = Path(f).stem
        if stem:
            names.add(stem)
    method_re = re.compile(r"[+-]\s+(?:public|private|protected)\s+\S+\s+(\w+)\s*\(")
    for m in method_re.finditer(diff_text):
        names.add(m.group(1))
    if names:
        return "Spring Boot: " + ", ".join(sorted(names))
    return "Spring Boot changed code"
