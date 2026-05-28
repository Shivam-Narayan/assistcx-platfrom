import os
import json
import tiktoken
import gc
import fitz
import warnings
import zipfile
import xml.etree.ElementTree as ET
from copy import deepcopy
from typing import Dict, Any, Optional, List, Callable, Tuple
from pathlib import Path
from logger import configure_logging
from dotenv import load_dotenv
from pydantic import BaseModel
from docling.document_converter import (
    ConversionResult,
    DocumentConverter,
    PdfFormatOption,
    WordFormatOption,
)
from docling.chunking import HybridChunker
from docling_core.transforms.chunker import DocChunk
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
    AcceleratorDevice,
    AcceleratorOptions,
    RapidOcrOptions,
    TableStructureOptions,
)
from docling_core.transforms.chunker.tokenizer.openai import OpenAITokenizer
from docling_core.transforms.chunker.hierarchical_chunker import (
    ChunkingDocSerializer,
    ChunkingSerializerProvider,
)
from docling_core.transforms.serializer.markdown import MarkdownTableSerializer
from docling.datamodel.base_models import InputFormat
from docling.backend.docling_parse_v2_backend import DoclingParseV2DocumentBackend
from docling.pipeline.simple_pipeline import SimplePipeline
from docling.datamodel.settings import settings
from docling_ocr_onnxtr import OnnxtrOcrOptions

load_dotenv()

logger = configure_logging(__name__)

# Set PyTorch environment variables for CPU-only operation
os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"
os.environ["PYTORCH_MPS_HIGH_WATERMARK_RATIO"] = "0.0"
# Disable pin_memory globally for DataLoaders
os.environ["DATALOADER_PIN_MEMORY"] = "false"
# Additional PyTorch warnings suppression
warnings.filterwarnings("ignore", message=".*pin_memory.*")
warnings.filterwarnings("ignore", message=".*no accelerator is found.*")

# Set OCR option to ONNXTR or RAPIDOCR
OCR_OPTION = "RAPIDOCR"  # Options: "ONNXTR", "RAPIDOCR"
CHUNK_OPTION = "DOCLING"  # Options: "DOCLING", "LANGCHAIN"


class NormalizedChunk(BaseModel):
    text: str
    meta: Dict[str, Any]


class MDTableSerializerProvider(ChunkingSerializerProvider):
    def get_serializer(self, doc):
        return ChunkingDocSerializer(
            doc=doc,
            table_serializer=MarkdownTableSerializer(),
        )


class DocumentParser:
    """
    A class focused on parsing document files (PDF, Markdown, DOCX, PPTX) by extracting content,
    and chunking text for knowledge processing.

    Attributes:
        file_path (str): Path to the document file to process.
        supported_extensions (list): List of allowed file extensions.
        docling_converter (DocumentConverter): Docling converter for parsing documents.
        docling_chunker (HybridChunker): Docling chunker for splitting text.
        max_chunk_tokens (int): Maximum tokens per chunk.
        max_chunk_size (int): Maximum words per chunk.
    """

    def __init__(
        self,
        use_ocr: bool = True,
        full_page_ocr: bool = False,
        detect_tables: bool = True,
        max_chunk_tokens: int = 768,
        max_chunk_size: int = 400,
    ):
        self.supported_extensions = [".docx", ".md", ".pdf", ".pptx"]
        self.use_ocr = use_ocr
        self.detect_tables = detect_tables
        self.max_chunk_tokens = max_chunk_tokens
        self.max_chunk_size = max_chunk_size
        self.full_page_ocr = full_page_ocr
        self.docling_chunker = None

    def _initialize_docling_converter(self) -> DocumentConverter:
        """
        Create DocumentConverter with current OCR options at runtime.
        This allows dynamic OCR configuration based on document analysis.
        """
        # Setup OCR options
        # ocr_options = EasyOcrOptions(force_full_page_ocr=self.full_page_ocr)
        # ocr_options = TesseractCliOcrOptions(force_full_page_ocr=self.full_page_ocr)

        if OCR_OPTION == "ONNXTR":
            logger.info("Using ONNXTR OCR backend for document parsing")

            # OCR configuration using ONNXTR backend (no model download needed)
            ocr_options = OnnxtrOcrOptions(
                det_arch="db_mobilenet_v3_large",  # detection model
                reco_arch="crnn_mobilenet_v3_large",  # recognition model
                auto_correct_orientation=False,
                force_full_page_ocr=self.full_page_ocr,
            )

            # CPU accelerator configuration
            accelerator_options = AcceleratorOptions(
                num_threads=4,
                device=AcceleratorDevice.CPU,
            )

            # PDF pipeline configuration
            pdf_pipeline_options = PdfPipelineOptions(
                accelerator_options=accelerator_options,
                do_ocr=self.use_ocr,
                do_table_structure=self.detect_tables,
                table_structure_options=TableStructureOptions(do_cell_matching=True),
                ocr_options=ocr_options,
                allow_external_plugins=True,  # Required for external OCR plugins like onnxtr
            )
        else:
            logger.info("Using RapidOCR backend for document parsing")

            ocr_options = RapidOcrOptions(
                force_full_page_ocr=self.full_page_ocr,
            )

            # PDF pipeline configuration
            pdf_pipeline_options = PdfPipelineOptions(
                do_ocr=self.use_ocr,
                do_table_structure=self.detect_tables,
                table_structure_options=TableStructureOptions(do_cell_matching=True),
                ocr_options=ocr_options,
            )

        # DocumentConverter with both PDF + DOCX pipelines
        return DocumentConverter(
            allowed_formats=[
                InputFormat.DOCX,
                InputFormat.MD,
                InputFormat.PDF,
                InputFormat.PPTX,
            ],
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_options=pdf_pipeline_options,
                    backend=DoclingParseV2DocumentBackend,
                ),
                InputFormat.DOCX: WordFormatOption(pipeline_cls=SimplePipeline),
            },
        )

    def _detect_scanned_pdf(self, file_path: str) -> bool:
        """
        Detect scanned pages in PDF by analyzing all pages.
        Returns True if any scanned content is detected, False otherwise.
        """
        try:
            doc = fitz.open(file_path)
            total_pages = len(doc)
            logger.info(f"Total {total_pages} pages in file {file_path}")

            # Configuration
            image_coverage_threshold = 0.5  # Lowered slightly
            text_length_threshold = 50  # Increased
            min_text_quality_ratio = 0.7  # New: ratio of alphanumeric chars

            for page_num in range(total_pages):
                page = doc[page_num]

                # Get text analysis
                text = page.get_text("text").strip()
                has_meaningful_text = len(text) > text_length_threshold

                # Check text quality (reduce false positives from OCR artifacts)
                if text:
                    alphanumeric_chars = sum(c.isalnum() for c in text)
                    text_quality = alphanumeric_chars / len(text) if text else 0
                    has_quality_text = text_quality > min_text_quality_ratio
                else:
                    has_quality_text = False

                has_fonts = bool(page.get_fonts())

                # Calculate image coverage with better validation
                page_area = page.rect.width * page.rect.height
                if page_area == 0:
                    continue

                total_image_area = 0
                for img in page.get_images(full=True):
                    try:
                        rects = page.get_image_rects(img[0])
                        if rects:
                            for rect in rects:
                                if rect.width > 0 and rect.height > 0:
                                    total_image_area += rect.width * rect.height
                    except Exception:
                        continue

                image_coverage = total_image_area / page_area

                # Enhanced classification
                likely_scanned = image_coverage > image_coverage_threshold and (
                    not has_meaningful_text or not has_quality_text or not has_fonts
                )

                if likely_scanned:
                    logger.info(
                        f"Detected scanned content on page {page_num + 1}/{total_pages} "
                        f"(img_coverage: {image_coverage:.2f}, text_len: {len(text)}, "
                        f"has_fonts: {has_fonts}) - enabling full page OCR"
                    )
                    doc.close()
                    return True

            doc.close()
            logger.info(f"No scanned pages detected in {total_pages} pages")
            return False

        except Exception as e:
            logger.warning(f"Error detecting scanned pages: {e}")
            return False

    def _create_docling_chunker(self):
        """Create docling chunker with tiktoken tokenizer when needed."""
        if self.docling_chunker is not None:
            return self.docling_chunker

        try:
            # Create lightweight tiktoken tokenizer
            logger.info("Creating tiktoken tokenizer with gpt-4o encoding")

            tokenizer = OpenAITokenizer(
                tokenizer=tiktoken.encoding_for_model("gpt-4o"),
                max_tokens=self.max_chunk_tokens,
            )

            # Create docling chunker with the tokenizer
            self.docling_chunker = HybridChunker(
                tokenizer=tokenizer,
                serializer_provider=MDTableSerializerProvider(),
                merge_peers=True,
            )

            logger.info("Docling chunker created successfully")
            return self.docling_chunker

        except Exception as e:
            logger.error(f"Failed to create docling chunker: {e}")
            raise

    def _word_count(self, text: str) -> int:
        """Return the number of words in the provided text."""
        return len(text.split())

    def _get_docx_page_count(self, file_path: str) -> Optional[int]:
        """
        Extract page count from DOCX metadata (docProps/app.xml).

        DOCX files don't contain page information internally; pagination happens
        dynamically during rendering. However, Word/LibreOffice saves the page count
        from the last save operation in the document's metadata.

        Args:
            file_path (str): Path to the DOCX file

        Returns:
            Optional[int]: Page count if found in metadata, None otherwise
        """
        try:
            with zipfile.ZipFile(file_path, "r") as docx_zip:
                # Read the app.xml file which contains document properties
                app_xml = docx_zip.read("docProps/app.xml")
                root = ET.fromstring(app_xml)

                # Find the Pages element (search by tag suffix to handle namespaces)
                for elem in root.iter():
                    if elem.tag.endswith("Pages"):
                        return int(elem.text) if elem.text else None
            return None
        except Exception as e:
            logger.warning(f"Could not extract page count from DOCX metadata: {e}")
            return None

    def normalize_chunks(
        self,
        chunks: List[DocChunk],
        file_metadata: Dict[str, Any],
        chunker: HybridChunker,
    ) -> List[NormalizedChunk]:
        """
        Take a list of DocChunk (with .text and .meta) plus file-level metadata,
        and produce a list of NormalizedChunk(text, meta) where meta is a single
        flattened dict containing both file- and chunk-level info.

        meta keys include (but aren't limited to):
        - any keys in file_metadata
        - source_file, mime_type, source_uri
        - headings, captions

        Args:
            chunks:         List of DocChunk objects
            file_metadata:  Dict of metadata common to the whole file
            chunker:        HybridChunker instance for contextualization
        Returns:
            List[NormalizedChunk] with .text and flattened .meta
        """
        processed: List[NormalizedChunk] = []

        for chunk in chunks:
            # 1) build the contextualized text
            full_text = chunker.contextualize(chunk=chunk).strip()

            raw_meta = chunk.meta
            origin = raw_meta.origin

            # 2) start with a copy of your file‐level metadata
            normalized_meta: Dict[str, Any] = dict(file_metadata)

            # 3) merge in the chunk‐specific fields (these win on conflict)
            normalized_meta.update(
                {
                    "source_file": origin.filename,
                    "mime_type": origin.mimetype,
                    "source_uri": origin.uri,
                    "headings": raw_meta.headings or [],
                }
            )

            # 4) emit the normalized chunk
            processed.append(NormalizedChunk(text=full_text, meta=normalized_meta))

        return processed

    def merge_small_chunks(
        self,
        chunks: List[Any],
        max_size: int = 400,  # Number of words per chunk
        size_fn: Optional[Callable[[str], int]] = None,
        chunk_delimiter: str = "\n\n",
    ) -> List[Any]:
        """
        Merge adjacent DocChunk-like objects so no returned chunk exceeds max_size,
        as measured by size_fn(contextualized_text).

        If anything goes wrong (e.g. a type error), logs a warning and returns the
        original `chunks` list unmodified.

        Args:
            chunks:            list of objects with .text and .meta
            max_size:          maximum allowed size per merged chunk
            size_fn:           function(text)->int to measure "size"
                                (defaults to simple word count)
            chunk_delimiter:   string to join merged pieces
        Returns:
            A new list of the same chunk type, each ≤ max_size, or the original
            list if merging fails.
        """
        try:
            if not chunks:
                return []

            measure = size_fn or self._word_count
            # ensure max_size is an int (guards against env-var strings)
            max_size = int(self.max_chunk_size or max_size)

            chunk_cls = type(chunks[0])
            merged_chunks: List[Any] = []
            buffer_text = ""
            buffer_size = 0
            buffer_meta = None

            def flush_buffer():
                nonlocal buffer_text, buffer_size, buffer_meta
                if buffer_text:
                    merged_chunks.append(chunk_cls(text=buffer_text, meta=buffer_meta))
                    buffer_text = ""
                    buffer_size = 0
                    buffer_meta = None

            for chunk in chunks:
                full_text = chunk.text or ""
                if not full_text:
                    continue

                part_size = measure(full_text)

                # if this single piece is already too big:
                if part_size > max_size:
                    flush_buffer()
                    merged_chunks.append(
                        chunk_cls(text=full_text, meta=deepcopy(chunk.meta))
                    )
                    continue

                # if buffer empty, start a new buffer
                if buffer_size == 0:
                    buffer_text = full_text
                    buffer_size = part_size
                    buffer_meta = deepcopy(chunk.meta)
                    continue

                # if it fits, merge it in
                if buffer_size + part_size <= max_size:
                    buffer_text += chunk_delimiter + full_text
                    buffer_size += part_size
                    # Merge headings (de-duplicated, order-preserved)
                    try:
                        combined = buffer_meta.get("headings", []) + chunk.meta.get(
                            "headings", []
                        )
                        buffer_meta["headings"] = list(dict.fromkeys(combined))
                    except Exception:
                        pass
                else:
                    # flush and start fresh
                    flush_buffer()
                    buffer_text = full_text
                    buffer_size = part_size
                    buffer_meta = deepcopy(chunk.meta)

            # final flush
            flush_buffer()
            return merged_chunks

        except Exception as e:
            logger.warning(
                f"merge_small_chunks failed ({e!r}), returning original chunks",
                exc_info=True,
            )
            return chunks

    def parse_document(
        self, file_path: str, file_metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Main function to parse a document file and create chunks.

        Args:
            file_path (str): Path to the file to process.
            file_metadata (Dict[str, Any]): Metadata for the file.
        Returns:
            Dict[str, Any]: Result containing:
                - file_path: Original file path
                - parsed_text: Full text of document
                - doc_chunks: List of document chunks
                - metadata: List of chunk metadata
                - chunk_count: Number of chunks
                - conversion_time: Time taken for document conversion (in seconds)
                - error: Error message (if any)
        """
        try:
            file_metadata = file_metadata or {}
            logger.info(f"Parsing document: {file_path}")
            # Validate file type
            file_extension = Path(file_path).suffix.lower()
            if file_extension not in self.supported_extensions:
                logger.warning(f"Unsupported file type: {file_extension}")
                return {
                    "file_path": file_path,
                    "error": f"Unsupported file type: {file_extension}",
                }

            # For PDFs, detect scanned pages and update OCR settings
            if file_extension == ".pdf":
                self.full_page_ocr = self._detect_scanned_pdf(file_path)

            # Enable docling time tracking
            settings.debug.profile_pipeline_timings = True

            # Extract document
            docling_converter = self._initialize_docling_converter()
            result: ConversionResult = docling_converter.convert(source=file_path)
            doc = result.document

            # Export markdown
            markdown_result = doc.export_to_markdown()

            # Page count
            if hasattr(doc, "pages") and doc.pages:
                page_count = len(doc.pages)
            elif file_extension == ".docx":
                # For DOCX, extract page count from metadata
                # Note: DOCX files don't contain page info internally, but Word saves
                # the page count from the last save operation in the metadata
                page_count = self._get_docx_page_count(file_path)
            elif file_extension in [".pptx"]:
                # For presentations, count slides
                page_count = len(getattr(doc, "slides", [])) or 1
            else:
                # Default fallback
                page_count = None

            # Word count
            word_count = self._word_count(markdown_result)

            # Get conversion time
            conversion_time = 0
            if hasattr(result, "timings") and "pipeline_total" in result.timings:
                conversion_time = sum(result.timings["pipeline_total"].times)
                logger.info(f"Time taken to parse document: {conversion_time:.2f}s")

            if not doc:
                return {}

            # Create chunks
            logger.info(f"Chunking parsed data: {file_path}")

            if CHUNK_OPTION == "LANGCHAIN":
                # LangChain chunking from in-memory markdown
                processed_chunks = self.langchain_chunk(
                    markdown_text=markdown_result,
                    file_metadata=file_metadata,
                    merge=True,
                )
            else:
                # Docling chunking (default)
                docling_chunker = self._create_docling_chunker()
                chunks = list(docling_chunker.chunk(dl_doc=doc))

                # Normalize chunks
                normalized_chunks = self.normalize_chunks(
                    chunks, file_metadata, docling_chunker
                )
                logger.info(f"Total chunks before merging: {len(normalized_chunks)}")

                # Merge small chunks
                processed_chunks = self.merge_small_chunks(normalized_chunks)

            logger.info(f"Total chunks after merging: {len(processed_chunks)}")

            # Create metadata
            metadata_list = [chunk.meta for chunk in processed_chunks]

            # Simple cleanup
            del result, doc

            # Force garbage collection
            gc.collect()

            return {
                "file_path": file_path,
                "parsed_text": markdown_result,
                "doc_chunks": processed_chunks,
                "metadata_list": metadata_list,
                "chunk_count": len(processed_chunks),
                "page_count": page_count,
                "word_count": word_count,
                "parse_time": conversion_time,
            }

        except Exception as e:
            logger.error(f"Error parsing document {file_path}: {e}")
            # Clean up on error
            gc.collect()
            return {"file_path": file_path, "error": f"Processing failed: {e}"}

    def parse(
        self, file_path: str, output_dir: str = "./data/output"
    ) -> Tuple[Optional[Any], Dict[str, Any]]:
        """
        Parse a document and export it to Markdown.

        Args:
            file_path (str): Path to the document file.
            output_dir (str): Directory to save the markdown output.

        Returns:
            Tuple of (docling document object, stats dict).
            Stats dict contains: file_path, md_output_path, page_count,
            word_count, parse_time, text_length, or error.
        """
        try:
            logger.info(f"Parsing document: {file_path}")
            file_extension = Path(file_path).suffix.lower()
            if file_extension not in self.supported_extensions:
                return None, {"error": f"Unsupported file type: {file_extension}"}

            # For PDFs, detect scanned pages and update OCR settings
            if file_extension == ".pdf":
                self.full_page_ocr = self._detect_scanned_pdf(file_path)

            # Enable docling time tracking
            settings.debug.profile_pipeline_timings = True

            # Extract document
            docling_converter = self._initialize_docling_converter()
            result: ConversionResult = docling_converter.convert(source=file_path)
            doc = result.document
            markdown_result = doc.export_to_markdown()

            # Page count
            if hasattr(doc, "pages") and doc.pages:
                page_count = len(doc.pages)
            elif file_extension == ".docx":
                page_count = self._get_docx_page_count(file_path)
            elif file_extension in [".pptx"]:
                page_count = len(getattr(doc, "slides", [])) or 1
            else:
                page_count = None

            word_count = self._word_count(markdown_result)

            # Get conversion time
            conversion_time = 0
            if hasattr(result, "timings") and "pipeline_total" in result.timings:
                conversion_time = sum(result.timings["pipeline_total"].times)

            # Save markdown output
            os.makedirs(output_dir, exist_ok=True)
            base_name = Path(file_path).stem
            md_output_path = Path(output_dir) / f"{base_name}.md"
            with open(md_output_path, "w", encoding="utf-8") as md_file:
                md_file.write(markdown_result)

            logger.info(f"Successfully saved parsed text to: {md_output_path}")

            stats = {
                "file_path": file_path,
                "md_output_path": str(md_output_path),
                "page_count": page_count,
                "word_count": word_count,
                "parse_time": conversion_time,
                "text_length": len(markdown_result),
            }
            return doc, stats

        except Exception as e:
            logger.error(f"Error parsing document {file_path}: {e}")
            return None, {"error": str(e)}

    def langchain_chunk(
        self,
        markdown_text: str,
        file_metadata: Optional[Dict[str, Any]] = None,
        merge: bool = True,
    ) -> List[NormalizedChunk]:
        """
        Chunk markdown text semantically using LangChain splitters.

        Uses MarkdownHeaderTextSplitter for header-aware splitting, then
        RecursiveCharacterTextSplitter for size-constrained chunks.

        Args:
            markdown_text (str): Markdown text to chunk.
            file_metadata (Optional[Dict]): File-level metadata to include in each chunk.
            merge (bool): Whether to merge small adjacent chunks.

        Returns:
            List[NormalizedChunk] for indexer consumption.
        """
        from langchain_text_splitters import (
            MarkdownHeaderTextSplitter,
            RecursiveCharacterTextSplitter,
        )

        logger.info(f"Starting LangChain chunking (merge={merge})")

        # Split by markdown headers first
        headers_to_split_on = [
            ("#", "Header 1"),
            ("##", "Header 2"),
            ("###", "Header 3"),
        ]
        markdown_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=headers_to_split_on,
            strip_headers=False,
        )
        md_header_splits = markdown_splitter.split_text(markdown_text)

        # Then split by character size
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=2000,
            chunk_overlap=200,
        )
        final_splits = text_splitter.split_documents(md_header_splits)

        # Build chunk list
        langchain_chunks = []
        for doc_chunk in final_splits:
            metadata = dict(file_metadata) if file_metadata else {}
            # Convert header metadata to headings list
            headings = []
            for key in ["Header 1", "Header 2", "Header 3"]:
                if key in doc_chunk.metadata:
                    headings.append(doc_chunk.metadata[key])
            metadata["headings"] = headings
            langchain_chunks.append(
                NormalizedChunk(text=doc_chunk.page_content.strip(), meta=metadata)
            )

        # Optionally merge small chunks
        if merge:
            langchain_chunks = self.merge_small_chunks(langchain_chunks)

        logger.info(f"LangChain chunking produced {len(langchain_chunks)} chunks")
        return langchain_chunks


# Simplified test code for document_parser.py
if __name__ == "__main__":
    import os
    from pathlib import Path

    # Configure test file path
    file_path = Path("./data/10k-apple-2024.pdf")
    # file_path = Path("./data/Menasha_2023-2028.pdf")
    output_dir = Path("./data/output")
    os.makedirs(output_dir, exist_ok=True)

    print(f"Testing document parsing on: {file_path.name}")

    # Initialize and test
    document_parser = DocumentParser()
    results = document_parser.parse_document(str(file_path.absolute()))

    # Report results
    if "error" in results:
        print(f"ERROR: {results['error']}")
    else:
        print("\nSUCCESS!")
        print(f"Parse time: {results.get('parse_time', 0):.2f}s")
        print(f"Chunk count: {results.get('chunk_count', 0)}")
        print(f"Text length: {len(results.get('parsed_text', ''))}")

        # Save parsed text as markdown file
        base_name = file_path.stem
        md_output_path = output_dir / f"{base_name}.md"
        with open(md_output_path, "w", encoding="utf-8") as md_file:
            md_file.write(results.get("parsed_text", ""))
        print(f"Saved parsed text to: {md_output_path}")

        # Save chunks with headers to text file
        chunks_output_path = output_dir / f"{base_name}-chunks.txt"
        with open(chunks_output_path, "w", encoding="utf-8") as chunks_file:
            chunks = results.get("doc_chunks", [])
            total_chunks = len(chunks)
            for i, chunk in enumerate(chunks, 1):
                chunks_file.write(f"===== chunk {i} of {total_chunks} =====\n")
                chunks_file.write(chunk.text.strip())
                chunks_file.write("\n\n")
        print(f"Saved {total_chunks} chunks to: {chunks_output_path}")
