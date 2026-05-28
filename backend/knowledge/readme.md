# Knowledge Module

Document processing, vector storage, hybrid search, and AI knowledge extraction.

## Module Structure

```
knowledge/
  indexer.py             # Document indexing orchestrator (parse, embed, index)
  document_parser.py     # Document parsing & chunking (Docling + OCR)
  extractor.py           # AI extraction orchestrator (smart fields + knowledge topics)
  llm_extractor.py       # LLM-based field/topic extraction from chunks
  milvus_store.py        # Vector store: collection management, insert, delete, update
  milvus_search.py       # Hybrid search: dense + BM25, multiple search strategies
  milvus_base.py         # Shared base: Milvus client, embedder access, LRU loader
  model_provider.py      # Embedding model cache (SentenceTransformer + OpenAI)
  prompts.py             # LLM prompt templates
  utils.py               # Shared utilities and Pydantic models
```

## Pipeline Overview

Two Celery tasks run sequentially on the `knowledge_queue`:

```
  index_document (priority=9)              extract_knowledge (priority=0)
  ─────────────────────────────           ─────────────────────────────
  Download → Parse → Embed → Index   →   Smart Fields → Knowledge Topics
  (DocumentIndexer)                       (KnowledgeExtractor)
```

---

## Task 1: Document Indexing (`index_document`)

**Entry:** `DocumentIndexer.process_document()` in `indexer.py`

```
1. Validate & Download
   File downloaded from S3/SharePoint to temp directory

2. Parse & Chunk                                          Status: PARSING
   DocumentParser (Docling) → semantic chunks (~400 words each)
   Supports: PDF (with OCR), DOCX, PPTX, MD

3. Document Context (LLM)
   First 5-10 chunks → LLM → structured context:
   { title, overview, type, keywords, entities, filename }
   Saved to DB as doc_* prefixed metadata

4. Embed & Index                                          Status: INDEXING
   For each chunk, enhanced text = chunk + document context
   ┌─────────────────────┐  ┌──────────────────────────┐
   │ Dense Embedding      │  │ BM25 Sparse Embedding    │
   │ Model: configurable  │  │ Milvus built-in function │
   │ (local or OpenAI)    │  │ Auto-generated on insert │
   │ Input: enhanced text │  │ Input: search_content    │
   └─────────────────────┘  └──────────────────────────┘

5. Store in Milvus
   Insert document_context record (1 per document)
   Insert document_chunk records (N per document)

6. Trigger AI extraction if enabled                       Status: SUCCESSFUL
```

## Task 2: AI Knowledge Extraction (`extract_knowledge`)

**Entry:** `KnowledgeExtractor.process_extraction()` in `extractor.py`

Triggered after document indexing, or when new smart fields/topics are added to a collection.

```
1. Smart Fields (sequential extract, batch index)         Status: EXTRACTING
   For each field config:
     - Search relevant chunks via hybrid search
     - LLM extracts field value (structured output)
   Then: single batch update of document_context record
   Then: update DB metadata for all fields

2. Knowledge Topics (parallel extract, individual index)
   For each topic config (up to 10 concurrent):
     - Search relevant chunks via hybrid search
     - LLM extracts topic knowledge (free text)
     - Index as document_knowledge record              Status: SUCCESSFUL
```

---

## Milvus Collection Schema

```
Field            Type                  Purpose
─────            ────                  ───────
id               VARCHAR (PK)          Unique record ID (UUID)
record_type      VARCHAR (indexed)     "document_context" | "document_chunk" | "document_knowledge"
document_id      VARCHAR (indexed)     File UUID (groups all records for one document)
content          VARCHAR               Original text (for display in search results)
search_content   VARCHAR               Enhanced text (chunk + context) — feeds BM25 function
metadata         JSON                  Chunk metadata + document context fields
dense_vector     FLOAT_VECTOR          Semantic embeddings (configurable model/dimensions)
sparse_vector    SPARSE_FLOAT_VECTOR   BM25 sparse vectors (auto-generated from search_content)
timestamp        INT64                 Creation timestamp
```

**Indexes:** dense_vector (IVF_FLAT, IP), sparse_vector (BM25), record_type (INVERTED), document_id (INVERTED)

## Hybrid Search

**Entry:** `MilvusSearch` in `milvus_search.py`

Combines dense (semantic) + BM25 (keyword) search with weighted ranking.

**Search strategies** (via `knowledge_search()`):
- **document_focused** (default) — Two-stage: discover relevant documents, then search their chunks
- **collection_wide** — Direct chunk search across entire collection
- **document_metadata** — Search document_context records only
- **knowledge_topic** — Search document_knowledge records filtered by topic

## Embedding Models

Configured per collection (immutable after creation). Defined in `configs/embedding_models.py`.

| Model | Provider | Dimensions |
|-------|----------|------------|
| Alibaba-NLP/gte-multilingual-base | local | 768 |
| openai/text-embedding-3-small | OpenAI API | 1024 |
| openai/text-embedding-3-large | OpenAI API | 1536 |
