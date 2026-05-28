from typing import Any, Dict, List
from sqlalchemy.orm import Session
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.documents import Document
from pydantic import BaseModel, Field

from logger import configure_logging
from agents.shared_utils import LLMProvider

logger = configure_logging(__name__)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class ChunkSection(BaseModel):
    chunk_id: int = Field(description="The chunk_id from the input")
    section_title: str = Field(
        description="Concise title covering all topics in the chunk, under 15 words"
    )
    section_description: str = Field(
        description="Brief summary of all key points in the chunk, under 50 words"
    )


class SectionBatch(BaseModel):
    sections: List[ChunkSection] = Field(
        description="One entry per input chunk, same order as input"
    )


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

SECTION_SYSTEM_PROMPT = """\
You are a document structure analyst. Generate a section title and description for each chunk.

Rules:
1. Every chunk gets exactly ONE section_title and ONE section_description.
2. The title should capture ALL topics in the chunk, even if it spans multiple subjects.
3. The description should summarize every key point — don't omit transitional content.
4. Use consistent titles for consecutive chunks on the same topic.
5. Titles under 15 words. Descriptions under 50 words."""


# ---------------------------------------------------------------------------
# SectionGenerator
# ---------------------------------------------------------------------------


class SectionGenerator:
    """
    Generates section titles and descriptions for document chunks using an LLM.

    Processes chunks in configurable batches and returns structured section data
    that can be merged back with the original chunk text and metadata.
    """

    def __init__(
        self,
        db: Session,
        organization_schema: str,
        batch_size: int = 100,
    ):
        self.batch_size = batch_size
        self.llm_provider = LLMProvider(organization_schema, db)
        self.default_llm = self.llm_provider.get_llm()

    def generate_sections(
        self,
        chunks: List[Document],
        source_file: str,
    ) -> List[Dict[str, Any]]:
        """
        Generate section titles and descriptions for all chunks.

        Args:
            chunks: LangChain Document objects from Milvus (document_chunk records).
            source_file: Original filename, used for prompt context.

        Returns:
            List of dicts with chunk_id, text, section_title, section_description, metadata.
        """
        # Build numbered chunk inputs
        chunk_inputs = [
            {"chunk_id": i, "text": doc.page_content, "metadata": doc.metadata}
            for i, doc in enumerate(chunks)
        ]

        # Process in batches
        all_sections: List[ChunkSection] = []
        total_batches = (len(chunk_inputs) - 1) // self.batch_size + 1

        for i in range(0, len(chunk_inputs), self.batch_size):
            batch = chunk_inputs[i : i + self.batch_size]
            batch_num = i // self.batch_size + 1
            logger.info(
                f"Processing section batch {batch_num}/{total_batches} "
                f"({len(batch)} chunks)"
            )
            batch_sections = self._process_batch(batch, source_file)
            all_sections.extend(batch_sections)

        # Merge sections back with original chunk data
        section_map = {s.chunk_id: s for s in all_sections}
        output = []
        for chunk_input in chunk_inputs:
            cid = chunk_input["chunk_id"]
            sec = section_map.get(cid)
            output.append(
                {
                    "chunk_id": cid,
                    "text": chunk_input["text"],
                    "section_title": sec.section_title if sec else "Untitled",
                    "section_description": sec.section_description if sec else "",
                    "metadata": chunk_input["metadata"],
                }
            )

        return output

    def _process_batch(
        self,
        batch: List[Dict[str, Any]],
        source_file: str,
    ) -> List[ChunkSection]:
        """Process a single batch of chunks through the LLM."""
        try:
            messages = self._build_messages(batch, source_file)
            structured_llm = self.default_llm.with_structured_output(SectionBatch)
            result: SectionBatch = structured_llm.invoke(messages)

            # Validate count
            if len(result.sections) != len(batch):
                logger.warning(
                    f"Section count mismatch: expected {len(batch)}, "
                    f"got {len(result.sections)}"
                )
                # Pad with placeholders if fewer than expected
                while len(result.sections) < len(batch):
                    missing_id = batch[len(result.sections)]["chunk_id"]
                    result.sections.append(
                        ChunkSection(
                            chunk_id=missing_id,
                            section_title="Untitled",
                            section_description="",
                        )
                    )

            return result.sections

        except Exception as e:
            logger.error(f"Error processing section batch: {e}")
            # Return placeholders for entire batch
            return [
                ChunkSection(
                    chunk_id=c["chunk_id"],
                    section_title="Untitled",
                    section_description="",
                )
                for c in batch
            ]

    def _build_messages(
        self,
        batch: List[Dict[str, Any]],
        source_file: str,
    ) -> list:
        """Build the LLM message list for a batch of chunks."""
        chunks_text = "\n\n".join(
            f"--- Chunk {c['chunk_id']} ---\n{c['text'].strip()}" for c in batch
        )
        return [
            SystemMessage(content=SECTION_SYSTEM_PROMPT),
            HumanMessage(
                content=f'{len(batch)} sequential chunks from "{source_file}":\n\n{chunks_text}'
            ),
        ]
