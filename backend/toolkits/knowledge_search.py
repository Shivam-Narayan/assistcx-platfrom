# Custom libraries
from logger import configure_logging
from knowledge.milvus_search import MilvusSearch
from knowledge.utils import get_embedding_model_for_collection

# Default libraries
from typing import Dict, Optional
import asyncio
import json

# Installed libraries
from dotenv import load_dotenv


load_dotenv()

logger = configure_logging(__name__)


class KnowledgeSearch:
    """
    Handles knowledge collection searches using Milvus.
    """

    def __init__(self, organization_schema: str):
        """
        Initializes KnowledgeSearch with organization schema.

        Args:
            organization_schema (str): Schema identifier for the organization
        """
        self.organization_schema = organization_schema

    def search_knowledge_collections(
        self,
        tool_runtime: Dict,
        collection: str,
        query: str,
        result_count: Optional[int] = 5,
    ) -> str:
        """
        Performs hybrid search on knowledge collections by leveraging the optimized MilvusSearch.

        Args:
            tool_runtime (Dict): Tool runtime context containing organization_schema, plan, etc
            collection (str): Name of the collection to search
            query (str): Search query text
            result_count (Optional[int]): Number of results to return

        Returns:
            str: JSON string of list of documents with text and metadata
        """
        task_id = tool_runtime.get("task_id", "unknown")

        try:
            if not collection or not collection.strip():
                return json.dumps(
                    {"error": "collection is required."},
                    ensure_ascii=False,
                )

            if not query or not query.strip():
                return json.dumps(
                    {"error": "query is required."},
                    ensure_ascii=False,
                )

            logger.info(
                f"[task_id={task_id}] knowledge_search_started: "
                f"tool=search_knowledge_collections, collection={collection}, query={query}, result_count={result_count}"
            )

            # Get the embedding model for this collection
            embedding_model = get_embedding_model_for_collection(
                self.organization_schema, collection
            )
            logger.info(
                f"Using embedding model {embedding_model} for collection {collection}"
            )

            # Perform knowledge search
            milvus_search = MilvusSearch()
            documents = asyncio.run(
                milvus_search.knowledge_search(
                    collection_name=collection,
                    queries=query,
                    dense_model=embedding_model,
                    organization_schema=self.organization_schema,
                    result_limit=result_count,
                )
            )

            # Convert to the expected output format
            results = [
                {
                    "document_id": doc.metadata.get("file_uuid"),
                    "page_content": doc.page_content,
                    "metadata": doc.metadata,
                    "distance": doc.metadata.get("distance"),
                }
                for doc in documents
            ]

            logger.info(
                f"[task_id={task_id}] knowledge_search_completed: "
                f"tool=search_knowledge_collections, status=SUCCESS, records_found={len(results)}"
            )

            result = json.dumps(results, ensure_ascii=False)
            return result

        except Exception as e:
            logger.error(
                f"[task_id={task_id}] knowledge_search_completed: "
                f"tool=search_knowledge_collections, status=FAILED, error={str(e)}"
            )
            return json.dumps(
                {"error": f"Error in search_knowledge_collections: {str(e)}"},
                ensure_ascii=False,
            )


# Example usage
if __name__ == "__main__":
    tool_runtime = {
        "organization_schema": "public",
    }

    # Initialize the KnowledgeSearch
    organization_schema = tool_runtime.get("organization_schema", "public")
    knowledge_search = KnowledgeSearch(organization_schema)

    # Test 1: Search Knowledge Collections
    print("\n --- Testing search_knowledge_collections ---")
    results = knowledge_search.search_knowledge_collections(
        collection_name="folder_name_testing_o1js",
        query="meeting notes",
    )
    print(results)
