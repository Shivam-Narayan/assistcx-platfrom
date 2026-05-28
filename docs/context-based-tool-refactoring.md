# Context-Based Tool Refactoring (v2)

## Problem Statement

Currently, 4 toolkits (extraction, classification, key_information, summarization) each implement 2-3 source-specific variants:

| Module | Class | Representative methods |
|--------|--------|-------------------------|
| `data_extractor.py` | `DataExtractor` | `extract_data_from_email()`, `extract_data_from_attachment()`, `extract_data_from_text()` |
| `content_classifier.py` | `ContentClassifier` | `classify_email_content()`, `classify_text_content()` |
| `key_information_extractor.py` | `KeyInformationExtractor` | `extract_email_key_information()`, `extract_text_key_information()` |
| `content_summarizer.py` | `ContentSummarizer` | `summarize_email_content()`, `summarize_text_content()` |

**Total: 10 tools** with ~70% duplicated code patterns.

---

## Proposed Solution (v2 - Write-Early + Hybrid)

### Key Insight
Instead of tools fetching data on-demand, **workers write context at each pipeline stage**. By the time agent tools run, data is already prepared.

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         WRITE-EARLY CONTEXT FLOW                            │
└─────────────────────────────────────────────────────────────────────────────┘

STAGE 1: Email Ingestion (backend_worker.py)
├─ Saves email to DB
├─ NEW: Writes /mnt/data-bucket/context/{email_uuid}/email.json
└─ Queues attachment processing OR dispatch

STAGE 2B: Attachment Parsing (attachment_worker.py)
├─ Parses attachment content + OCR
├─ NEW: Writes /mnt/data-bucket/context/{email_uuid}/attachments/{attachment_uuid}.json
├─ NEW: Writes /mnt/data-bucket/context/{email_uuid}/attachments/{attachment_uuid}/images/*.jpg
└─ Queues dispatch

STAGE 4: Task Execution (agent_worker.py)
├─ Agent tools run
├─ get_context() → READS pre-written context (no DB queries!)
└─ extract_data() / classify_content() etc. use the context
```

### Benefits Over v1
1. **Zero DB queries in tools** - context already on disk
2. **Faster tool execution** - just file reads
3. **Vision images pre-converted** - no PDF→image conversion during tool execution
4. **Reusable across multiple actions** - same context for extract, classify, summarize
5. **Debug-friendly** - context files are human-readable JSON

---

## Storage Structure

```
/mnt/data-bucket/
  context/
    {email_uuid}/
      email.json                              # Written in Stage 1
      attachments/
        {attachment_uuid}.json                # Written in Stage 2B
        {attachment_uuid}/
          images/                             # Written in Stage 2B (if PDF/image)
            page_001.jpg
            page_002.jpg

    text/                                     # For raw text (no email_uuid)
      {generated_uuid}.json                   # Written on-demand by get_context()
```

---

## Context JSON Schemas

### email.json (written by backend_worker)
```json
{
  "email_uuid": "uuid",
  "message_id": "outlook-message-id",
  "conversation_id": "thread-id",
  "sender_email": "sender@example.com",
  "mailbox_email": "inbox@company.com",
  "mailbox_folder": "Inbox",
  "subject": "Email Subject",
  "body": "Email body content...",
  "received_at": "ISO datetime",
  "created_at": "ISO datetime",
  "web_link": "outlook web url",
  "has_attachments": true,
  "attachment_ids": ["uuid1", "uuid2"]
}
```

### {attachment_uuid}.json (written by attachment_worker)
```json
{
  "attachment_uuid": "uuid",
  "email_uuid": "parent-email-uuid",
  "file_name": "document.pdf",
  "file_type": "pdf",
  "size": 102400,
  "remote_url": "s3://bucket/path/document.pdf",
  "content": ["Extracted text content..."],
  "vision_data": {
    "enabled": true,
    "image_count": 5,
    "image_folder": "attachments/{attachment_uuid}/images/"
  }
}
```

---

## Implementation Plan

### Phase 1: Modify Workers to Write Context

#### 1.1 backend_worker.py - After saving email
```python
# After outlook.parse_and_save_email()
from toolkits.context_utils import write_email_context
write_email_context(saved_message, organization_schema)
```

#### 1.2 attachment_worker.py - After parsing attachment
```python
# After service.parse_attachment()
from toolkits.context_utils import write_attachment_context
write_attachment_context(
    attachment_data=service_result,
    email_uuid=email_uuid,
    organization_schema=organization_schema,
    include_vision_images=polling_config.get("vision_data_extraction", False)
)
```

#### 1.3 New File: `backend/toolkits/context_utils.py`
```python
CONTEXT_BASE_PATH = "/mnt/data-bucket/context"

def write_email_context(email_data, organization_schema: str) -> str:
    """Write email context JSON. Returns context path."""

def write_attachment_context(attachment_data, email_uuid, organization_schema, include_vision_images=False) -> str:
    """Write attachment context JSON + vision images. Returns context path."""

def read_context(email_uuid: str, attachment_uuid: str = None) -> dict:
    """Read context from pre-written files."""

def write_text_context(raw_text: str, metadata: dict = None) -> str:
    """Write text context (for non-email sources). Returns context path."""
```

### Phase 2: Hybrid get_context Tool

#### 2.1 New File: `backend/toolkits/context_tools.py`
```python
def get_context(
    tool_runtime: dict,
    source_type: str = "auto",      # "auto", "email", "attachment", "text"
    email_id: str = None,           # Optional - defaults to tool_runtime["email_uuid"]
    attachment_id: str = None,      # Optional
    raw_text: str = None,           # Required only for source_type="text"
    **kwargs
) -> str:
    """
    Hybrid context retrieval:
    - For email/attachment: READ pre-written context (fast path)
    - For text: WRITE context on-demand (fallback path)

    Returns: JSON with context data
    """
```

**Auto-detection logic:**
```python
if source_type == "auto":
    if raw_text:
        source_type = "text"
    elif attachment_id:
        source_type = "attachment"
    else:
        source_type = "email"
```

### Phase 3: Unified Action Tools

| Module | New function (planned) |
|--------|-------------------------|
| `data_extractor.py` | `extract_data(tool_runtime, data_template, context=None)` |
| `content_classifier.py` | `classify_content(tool_runtime, class_group, context=None)` |
| `key_information_extractor.py` | `extract_key_information(tool_runtime, data_template, context=None)` |
| `content_summarizer.py` | `summarize_content(tool_runtime, context=None)` |

**context parameter:**
- If provided: Use the passed context dict
- If None: Auto-load from `tool_runtime["email_uuid"]`

### Phase 4: Remove Legacy Functions

Delete old source-specific functions from all toolkit files.

---

## Files to Create/Modify

| File | Action |
|------|--------|
| `backend/toolkits/context_utils.py` | **CREATE** - write/read context helpers |
| `backend/toolkits/context_tools.py` | **CREATE** - get_context tool |
| `backend/workers/backend_worker.py` | **MODIFY** - call write_email_context() |
| `backend/workers/attachment_worker.py` | **MODIFY** - call write_attachment_context() |
| `backend/toolkits/data_extractor.py` | **MODIFY** - add extract_data(), keep existing extract_data_from_* |
| `backend/toolkits/content_classifier.py` | **MODIFY** - add classify_content(), keep existing methods |
| `backend/toolkits/key_information_extractor.py` | **MODIFY** - add extract_key_information(), keep existing methods |
| `backend/toolkits/content_summarizer.py` | **MODIFY** - add summarize_content(), keep existing methods |
| `backend/toolkits/` (package) | **Note** — no `__init__.py` / `tool_function_map`; tools are loaded by module path from `configs/agent_tools_data.py` via `ToolsFactory` |

---

## Optimizations in v2

| Aspect | v1 (Original) | v2 (Write-Early) |
|--------|---------------|------------------|
| DB queries in tools | 2-3 per tool call | 0 (pre-written) |
| Vision image conversion | During tool execution | Pre-converted in Stage 2B |
| Context reuse | Possible with context_path | Automatic (same folder) |
| Tool complexity | Medium (fetch + process) | Low (just process) |
| Worker complexity | Low | Medium (extra writes) |
| Debug visibility | DB only | JSON files on disk |

---

## Edge Cases

### 1. Email without attachments
- `email.json` exists
- `attachments/` folder empty or missing
- Tools handle gracefully

### 2. Raw text input (no email)
- No pre-written context
- `get_context()` writes to `context/text/{uuid}.json`
- Works same as before

### 3. Context file missing (worker failed)
- Tools fall back to DB query
- Log warning for debugging
- Graceful degradation

### 4. Multiple agents on same email
- All read same context files
- No race conditions (read-only after write)

---

## Usage Examples

### Agent Workflow (Typical)
```python
# Context already written by workers - just use it!
result = extract_data(tool_runtime, "invoice")
classification = classify_content(tool_runtime, "document_types")
summary = summarize_content(tool_runtime)
```

### Explicit Context (Advanced)
```python
# Get context explicitly if needed
context = get_context(tool_runtime, attachment_id="specific-uuid")

# Pass to multiple tools
result = extract_data(tool_runtime, "invoice", context=context)
classification = classify_content(tool_runtime, "document_types", context=context)
```

### Raw Text (No Email)
```python
# Text source - get_context writes on-demand
context = get_context(tool_runtime, source_type="text", raw_text="Some text to process...")
result = extract_data(tool_runtime, "invoice", context=context)
```

---

## Verification Plan

1. **Worker Integration Tests**
   - Verify email.json written after email save
   - Verify attachment.json + images written after parse
   - Check file permissions and paths

2. **Tool Tests**
   - Verify tools read from context files (no DB queries)
   - Verify fallback to DB if context missing
   - Compare output with legacy functions

3. **End-to-End Test**
   - Process email through full pipeline
   - Verify context files at each stage
   - Run extraction/classification/summarization
   - Compare results with legacy approach

---

## Migration Checklist

### Phase 1: Context Infrastructure
- [ ] Create `context_utils.py` with write/read functions
- [ ] Create `context_tools.py` with get_context()
- [ ] Add context writing to `backend_worker.py`
- [ ] Add context writing to `attachment_worker.py`
- [ ] Test context file creation

### Phase 2: Unified Tools
- [ ] Add `extract_data()` to `data_extractor.py` (`DataExtractor`)
- [ ] Add `classify_content()` to `content_classifier.py` (`ContentClassifier`)
- [ ] Add `extract_key_information()` to `key_information_extractor.py` (`KeyInformationExtractor`)
- [ ] Add `summarize_content()` to `content_summarizer.py` (`ContentSummarizer`)
- [ ] Test new tools with pre-written context

### Phase 3: Cleanup
- [ ] Remove or fold any remaining per-source duplicates inside the class modules above
- [ ] Keep agent definitions in `configs/agent_tools_data.py` aligned with handler `module` / `class` / `method`
- [ ] Run full regression tests

---

## Future Considerations

1. **Context TTL/Cleanup**
   - Add cleanup job for old context folders
   - Based on email age or storage quota

2. **Context Versioning**
   - Add version field to context JSON
   - Handle schema migrations

3. **Additional Sources**
   - Web browser results → `context/crawl/{url_hash}/`
   - API responses → `context/api/{request_hash}/`
   - Same pattern, just different writers
