# Knowledge management and search

Knowledge are stored in Milvus collections containing dense and sparse vectors. When document is processed it gets embedded and stored in the collection. It contains three types of records: document_context, document_chunk, and document_knowledge. Standard document chunks are stored as document_chunk records. During document processing it goes through metadata and knowledge topic extraction as per the collection settings. There is always one recording per document containing combined metadata having record type document_context. Knowledge topics are stored as individual records with record type document_knowledge.

## Architecture

## Knowledge search types

- Document Focused Search -> document_focused_search
- Collection Wide Search -> collection_wide_search
- Document Metadata Search -> document_metadata_search
- Knowledge Topic Search -> knowledge_topic_search

### Document Focused Search (document_focused_search)

Two stage search where first stage is to find the relevant documents by searching through document_context type records and using LLM to filter the results to find the most relevant documents. After finding relevant documents, in second stage relevant chunks are found from the documents using hybrid search with document_id filter to get the chunks from relevant documents.

Best for: Questions about specific companies, entities, or topics requiring precise, detailed information.

### Document Metadata Search (document_metadata_search)

Search on document_context with metadata filters. This is useful when the search is about the document itself or its metadata rather than the content.

Best for: Finding documents by date, author, type, or other metadata fields, getting document summaries and overviews.

### Knowledge Topic Search (knowledge_topic_search)

Hybrid search on the collection with knowledge_topic filter. It is useful when the search can be narrowed down to a specific knowledge topic extracted during document processing.

Best for: Thematic research across multiple documents, when query aligns with available knowledge topics in the collection.

### Collection Wide Search (collection_wide_search)

Direct hybrid search on document_chunk type records in the collection. This is most broad search and mostly used as a fallback when other searches do not find relevant results.

Best for: Very broad or general questions, fallback when other search types return insufficient results.
