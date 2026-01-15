import math
from elasticsearch import Elasticsearch
from django.conf import settings
import google.generativeai as genai


es = Elasticsearch(settings.ELASTIC_URL)
INDEX = settings.ELASTIC_INDEX
EMBED_DIMS = 768  # text-embedding-004


def create_rag_index():
    """
    Creates (idempotently) an index for RAG with a vector field.
    """
    if es.indices.exists(index=INDEX):
        return

    body = {
        "settings": {
            "index": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
                "refresh_interval": "30s"
            }
        },
        "mappings": {
            "properties": {
                "content":   {"type": "text"},
                "source":    {"type": "keyword"},       # filename/url/etc.
                "chunk_id":  {"type": "integer"},
                "embedding": {
                    "type": "dense_vector",
                    "dims": EMBED_DIMS,
                    "index": True,
                    "similarity": "cosine"
                }
            }
        }
    }
    es.indices.create(index=INDEX, body=body)


genai.configure(api_key=settings.GOOGLE_AI_API_KEY)


def embed_text(text: str) -> list[float]:
    """
    Returns a 768-dim embedding using Gemini's text-embedding-004.
    """
    res = genai.embed_content(model="text-embedding-004", content=text)
    return res["embedding"]


def chunk_text(text: str, chunk_chars: int = 1400, overlap: int = 200):
    """
    Simple char-based splitter for demo. In prod, use a token-aware splitter.
    """
    text = text.strip()
    chunks = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + chunk_chars, n)
        chunks.append(text[start:end])
        start = end - overlap
        if start < 0:
            start = 0
    return chunks


def index_document(doc_id: str, content: str, source: str = "manual"):
    """
    Index a single (possibly long) document by chunking + embedding.
    doc_id is your logical id; each chunk becomes one ES doc with _id=f"{doc_id}-{i}".
    """
    chunks = chunk_text(content)
    for i, chunk in enumerate(chunks):
        vec = embed_text(chunk)
        es.index(
            index=INDEX,
            id=f"{doc_id}-{i}",
            document={
                "content": chunk,
                "source": source,
                "chunk_id": i,
                "embedding": vec
            }
        )
    # make searchable immediately
    es.indices.refresh(index=INDEX)


def index_many(docs: list[tuple[str, str, str]]):
    """
    Bulk helper: docs = [(doc_id, content, source), ...]
    """
    for (doc_id, content, source) in docs:
        index_document(doc_id, content, source)


def retrieve(query: str, top_k: int = 4) -> list[dict]:
    """
    Returns top_k hits: [{content, source, score, chunk_id}, ...]
    """
    qvec = embed_text(query)
    res = es.search(
        index=INDEX,
        knn={
            "field": "embedding",
            "query_vector": qvec,
            "k": top_k,
            "num_candidates": top_k * 3
        },
        _source=["content", "source", "chunk_id"]
    )
    hits = res["hits"]["hits"]
    return [
        {
            "content": h["_source"]["content"],
            "source":  h["_source"].get("source"),
            "chunk_id": h["_source"].get("chunk_id"),
            "score":   h["_score"],
        } for h in hits
    ]


def build_context(hits: list[dict]) -> str:
    """
    Formats retrieved chunks to feed the LLM.
    Keep it compact; more isn't always better.
    """
    blocks = []
    for i, h in enumerate(hits, 1):
        src = h.get("source") or "unknown"
        blk = f"[{i}] Source: {src} (chunk {h.get('chunk_id')})\n{h['content']}"
        blocks.append(blk)
    return "\n\n".join(blocks)
