# Standard library imports
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

# Third-party imports
from jinja2 import Template

# Project imports
from logger import configure_logging
from agents.shared_utils import LLMProvider

# Local imports
from .milvus_search import MilvusSearch
from .milvus_store import MilvusStore
from .prompts import (
    SMART_FIELD_PROMPT,
    KNOWLEDGE_TOPIC_PROMPT,
)
from .utils import SmartFieldExtraction, normalize_text

logger = configure_logging(__name__)


class LLMExtractor:
    """
    AI-based knowledge extraction using vector search.

    Handles extraction of document context, smart fields, and knowledge topics.
    """

    def __init__(self, db: Session, organization_schema: str):
        self.organization_schema = organization_schema

        # Initialize LLM
        self.llm_provider = LLMProvider(organization_schema, db)
        self.default_llm = self.llm_provider.get_llm()

        # Lazy-loaded Milvus clients (single instances — no per-collection config needed)
        self._milvus_store = None
        self._milvus_search = None

        logger.info(f"Initialized LLM extractor for organization: {organization_schema}")

    @property
    def milvus_store(self):
        """Lazy-loaded MilvusStore client."""
        if self._milvus_store is None:
            self._milvus_store = MilvusStore()
        return self._milvus_store

    @property
    def milvus_search(self):
        """Lazy-loaded MilvusSearch client."""
        if self._milvus_search is None:
            self._milvus_search = MilvusSearch()
        return self._milvus_search

    def extract_smart_field(
        self,
        collection_name: str,
        document_id: str,
        field_config: Dict[str, Any],
        embedding_model: str,
    ) -> Optional[Any]:
        """
        Extract a single smart field value for a document.

        Args:
            collection_name: Milvus collection name
            document_id: Document UUID to extract from
            field_config: Field configuration with name, description, type
            embedding_model: Dense embedding model name for vector search

        Returns:
            Optional[Any]: Extracted field value or None if failed
        """
        try:
            field_name = field_config.get("name", "unknown_field")
            field_description = field_config.get("description", "")
            field_keywords = field_config.get("keywords", [])
            field_type = field_config.get("data_type") or field_config.get(
                "type", "string"
            )

            logger.info(
                f"Extracting smart field '{field_name}' from document {document_id}"
            )

            # Get relevant chunks using vector search
            relevant_chunks = self.get_relevant_chunks(
                collection_name=collection_name,
                document_id=document_id,
                search_entity=field_config,
                embedding_model=embedding_model,
                limit=3,
            )

            if not relevant_chunks:
                logger.warning(
                    f"No relevant chunks found for field '{field_name}' in document {document_id}"
                )
                return None

            # Combine chunk content for AI processing
            content_parts = []
            for chunk in relevant_chunks:
                content_parts.append(chunk.get("content", "") + "\n\n---\n\n")

            combined_content = "".join(content_parts)

            # Create prompt for field extraction
            field_prompt = Template(SMART_FIELD_PROMPT).render(
                field_name=field_name,
                field_description=field_description,
                field_keywords=field_keywords,
                field_type=field_type,
                content=combined_content,
            )

            # Use LLM with structured output for JSON response
            structured_llm = self.default_llm.with_structured_output(
                SmartFieldExtraction
            )
            response = structured_llm.invoke(field_prompt)

            # Extract field value from structured response
            if response and response.field_value is not None:
                extracted_value = response.field_value

                # Normalize text and list fields for consistency
                if field_type in ["text", "list"] and (
                    isinstance(extracted_value, str)
                    or isinstance(extracted_value, list)
                ):
                    extracted_value = normalize_text(extracted_value)

                logger.info(
                    f"Successfully extracted field '{field_name}': {extracted_value}"
                )
                return extracted_value
            else:
                logger.info(
                    f"No value found for field '{field_name}' in document {document_id}"
                )
                return None

        except Exception as e:
            logger.error(
                f"Error extracting smart field '{field_name}' from document {document_id}: {e}"
            )
            return None

    def extract_knowledge_topic(
        self,
        collection_name: str,
        document_id: str,
        topic_config: Dict[str, Any],
        embedding_model: str,
    ) -> Optional[str]:
        """
        Extract a single knowledge topic from a document.

        Args:
            collection_name: Milvus collection name
            document_id: Document UUID to extract from
            topic_config: Topic configuration with name, keywords, description
            embedding_model: Dense embedding model name for vector search

        Returns:
            Optional[str]: Extracted knowledge content or None if failed
        """
        try:
            topic_name = topic_config.get("name", "unknown_topic")
            topic_description = topic_config.get("description", "")
            topic_keywords = topic_config.get("keywords", [])

            logger.info(
                f"Extracting knowledge topic '{topic_name}' from document {document_id}"
            )

            # Get relevant chunks using vector search (more chunks for topics)
            relevant_chunks = self.get_relevant_chunks(
                collection_name=collection_name,
                document_id=document_id,
                search_entity=topic_config,
                embedding_model=embedding_model,
                limit=5,
            )

            if not relevant_chunks:
                logger.warning(
                    f"No relevant chunks found for topic '{topic_name}' in document {document_id}"
                )
                return None

            # Combine chunk content for AI processing (use more chunks than fields)
            content_parts = []
            for chunk in relevant_chunks:
                content_parts.append(chunk.get("content", "") + "\n\n---\n\n")

            combined_content = "".join(content_parts)

            # Create prompt for knowledge topic extraction
            topic_prompt = Template(KNOWLEDGE_TOPIC_PROMPT).render(
                topic_name=topic_name,
                topic_description=topic_description,
                topic_keywords=topic_keywords,
                content=combined_content,
            )

            # Use LLM to extract knowledge content
            response = self.default_llm.invoke(topic_prompt)

            # Extract the actual response text
            if hasattr(response, "content"):
                extracted_knowledge = response.content.strip()
            else:
                extracted_knowledge = str(response).strip()

            # Handle null responses
            if (
                extracted_knowledge.lower() == "null"
                or extracted_knowledge.lower() == "none"
                or not extracted_knowledge
            ):
                logger.info(
                    f"No knowledge found for topic '{topic_name}' in document {document_id}"
                )
                return None

            logger.info(
                f"Successfully extracted knowledge topic '{topic_name}': {len(extracted_knowledge)} characters"
            )
            return extracted_knowledge

        except Exception as e:
            logger.error(
                f"Error extracting knowledge topic '{topic_name}' from document {document_id}: {e}"
            )
            return None

    def get_relevant_chunks(
        self,
        collection_name: str,
        document_id: str,
        search_entity: Dict[str, Any],
        embedding_model: str,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Get relevant document chunks using vector search.

        Args:
            collection_name: Milvus collection name
            document_id: Document UUID to filter by
            search_entity: Field or topic config with name, description, keywords
            embedding_model: Dense embedding model name for vector search
            limit: Maximum number of chunks to return

        Returns:
            List[Dict]: List of relevant chunks with metadata
        """
        try:
            # Create search query from entity information
            search_parts = []

            # Add name and alias
            name = search_entity.get("name", "")
            keywords = search_entity.get("keywords", [])
            keywords_str = ", ".join(keywords) if keywords else ""
            description = search_entity.get("description", "")

            # Add search query parts
            if name:
                search_parts.append(name)
            if keywords_str:
                search_parts.append(keywords_str)
            if description:
                search_parts.append(description)

            # Combine into search query
            search_query = " ".join(search_parts)
            if not search_query.strip():
                logger.warning(f"Empty search query for entity: {search_entity}")
                return []

            logger.debug(
                f"Searching for chunks with query: '{search_query}' in document {document_id}"
            )

            # Create document filter for hybrid search - only search document_chunk records
            document_filter = (
                f'document_id == "{document_id}" && record_type == "document_chunk"'
            )

            # First, get document_context record for this document
            relevant_chunks = []

            # Get document_context record using milvus_store.fetch_documents_with_filter
            context_records = self.milvus_store.fetch_documents_with_filter(
                collection_name=collection_name,
                file_uuid=document_id,
                record_type="document_context",
                result_limit=1,
            )

            # Add document_context as first item if found
            if context_records:
                context_record = context_records[0]
                context_data = {
                    "content": context_record.page_content,
                    "metadata": context_record.metadata,
                    "score": 1.0,  # Highest score for document context
                }
                relevant_chunks.append(context_data)
                logger.debug(f"Added document_context for document {document_id}")

            # Then perform hybrid search with document filter for chunks
            search_results = self.milvus_search.hybrid_search(
                collection_name=collection_name,
                queries=[search_query],
                dense_model=embedding_model,
                organization_schema=self.organization_schema,
                result_limit=limit,
                filter_expr=document_filter,
            )

            # Convert search results to expected format and append after document_context
            for result in search_results:
                if hasattr(result, "page_content") and hasattr(result, "metadata"):
                    chunk_data = {
                        "content": result.page_content,
                        "metadata": result.metadata,
                        "score": result.metadata.get("distance", 0.0),
                    }
                    relevant_chunks.append(chunk_data)

            logger.info(
                f"Found {len(relevant_chunks)} relevant chunks for entity '{search_entity.get('name', 'unknown')}' in document {document_id}"
            )
            return relevant_chunks

        except Exception as e:
            logger.error(
                f"Error getting relevant chunks for document {document_id}: {e}"
            )
            return []
