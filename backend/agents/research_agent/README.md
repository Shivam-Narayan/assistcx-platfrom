# Research Agent Architecture & Process Flow

## Overview

The Research Agent is an intelligent query processing system built on LangGraph that conducts comprehensive research to answer user questions. It combines internal knowledge base searches with external web searches, synthesizes information from multiple sources, and generates well-cited answers.

### Key Features

-**Intelligent Query Triage**: Classifies queries and routes them appropriately

-**Multi-Source Research**: Searches both internal knowledge collections and external web sources

-**Knowledge Synthesis**: Combines information from multiple sources with proper citations

-**Streaming Support**: Real-time updates during research execution

-**State Persistence**: Maintains conversation state using PostgreSQL checkpointer

-**Token Tracking**: Comprehensive token usage and credit calculation

---

## Architecture

### High-Level Architecture

```

┌─────────────────┐

│  API Routes     │  (research_query_routes.py)

│  (FastAPI)      │

└────────┬────────┘

         │

         ▼

┌─────────────────┐

│  Service Layer  │  (service.py)

│  ResearchQuery  │  - Request handling

│  Service        │  - Context preparation

└────────┬────────┘  - State management

         │

         ▼

┌─────────────────┐

│  Graph Layer    │  (graph.py)

│  ResearchAgent  │  - Graph orchestration

│  Graph          │  - State routing

└────────┬────────┘

         │

         ▼

┌─────────────────────────────────────┐

│         Node Execution              │

│  ┌──────────┐  ┌──────────┐         │

│  │  Triage  │→ │  Agent   │         │

│  └──────────┘  └────┬─────┘         │

│                     │               │

│              ┌──────▼──────┐        │

│              │    Tool     │        │

│              │  Execution  │        │

│              └──────┬──────┘        │

│                     │               │

│              ┌──────▼──────┐        │

│              │   Answer    │        │

│              └─────────────┘        │

└─────────────────────────────────────┘

```

### Component Structure

```

research_agent/

├── service.py          # Service layer - API interface

├── graph.py            # Graph definition and orchestration

├── schemas.py          # Pydantic models and state definitions

├── utils.py            # Utility functions (formatting, synthesis, etc.)

├── prompts.py          # LLM prompts for all nodes

├── config.py           # Configuration constants

├── nodes/              # Graph node implementations

│   ├── triage.py      # Query classification node

│   ├── agent.py       # Agent reasoning node

│   ├── tool.py        # Tool execution node

│   └── answer.py      # Final answer generation node

└── tools/              # Research tools

    ├── registry.py    # Tool registration

    ├── knowledge_search.py  # Internal knowledge search tools

    ├── web_search.py   # External web search tool

    └── complete_research.py # Research completion tool

```

---

## Process Flow

### Complete Execution Flow

```

1. USER QUERY

   │

   ▼

2. SERVICE LAYER (service.py)

   ├── Validate/Create chat thread

   ├── Fetch knowledge collections

   ├── Load previous messages

   ├── Prepare execution context

   └── Initialize graph with checkpointer

   │

   ▼

3. GRAPH ENTRY: TRIAGE NODE

   ├── Classify query type:

   │   ├── direct_response → END (immediate answer)

   │   ├── needs_clarification → END (ask for clarification)

   │   ├── harmful_query → END (reject query)

   │   └── requires_research → Continue to Agent

   └── Generate thread title

   │

   ▼

4. AGENT NODE (if requires_research)

   ├── Analyze query and available knowledge

   ├── Decide on action:

   │   ├── Call search tool (knowledge/web)

   │   ├── Call confirm_research_complete

   │   └── Continue reasoning (loop back)

   └── Track tool call count

   │

   ▼

5. TOOL NODE (if tool called)

   ├── Execute selected tool:

   │   ├── Knowledge Search Tools:

   │   │   ├── document_focused_search

   │   │   ├── document_metadata_search

   │   │   ├── knowledge_topic_search

   │   │   └── collection_wide_search

   │   ├── external_web_search

   │   └── confirm_research_complete

   ├── Synthesize knowledge from results

   ├── Deduplicate sources

   └── Update state with new knowledge

   │

   ▼

6. ROUTING DECISION

   ├── If research_complete → Answer Node

   ├── If tool calls remaining → Agent Node (loop)

   └── If max tool calls reached → Answer Node

   │

   ▼

7. ANSWER NODE

   ├── Synthesize all accumulated knowledge

   ├── Generate comprehensive answer with citations

   ├── Create suggested follow-up queries

   └── Stream answer tokens (if enabled)

   │

   ▼

8. SERVICE LAYER (response handling)

   ├── Save assistant message

   ├── Calculate token usage & credits

   ├── Update chat thread title

   └── Return final response

```

### State Flow Diagram

```

ResearchState

├── messages: [HumanMessage, AIMessage, ToolMessage, ...]

│   └── Conversation history with tool calls

│

├── original_query: "User's question"

│

├── query_type: "requires_research" | "direct_response" | ...

│

├── relevant_sources: [SourceDocument, ...]

│   └── Deduplicated sources used in research

│

├── research_knowledge: [ResearchKnowledge, ...]

│   ├── selected_sources: [source_ids]

│   └── synthesized_knowledge: "Knowledge with [uuid] citations"

│

├── tool_call_count: 0

│   └── Tracks number of tool invocations

│

├── research_complete: false

│   └── Flag to route to answer node

│

├── final_answer: null

│   └── Generated answer (for all query types)

│

├── suggested_queries: []

│   └── Follow-up question suggestions

│

└── token_usage: [{node, tool_call, tokens, ...}, ...]

    └── Accumulated token consumption records

```

---

## Key Components

### 1. Service Layer (`service.py`)

**Purpose**: Main entry point for API requests, handles context preparation and state management.

**Key Methods**:

-`execute_query_direct()`: Non-streaming query execution

-`execute_query_stream()`: Streaming query execution with real-time updates

-`observe_query_execution()`: Read-only state observation for ongoing queries

-`_prepare_execution_context()`: Consolidates thread validation, collection fetching, message retrieval

**Responsibilities**:

- Chat thread management (create/validate)
- Knowledge collection fetching
- Message history retrieval
- Token usage tracking and credit calculation
- Response serialization

### 2. Graph Layer (`graph.py`)

**Purpose**: Defines the LangGraph state machine and routing logic.

**Key Components**:

-`ResearchAgentGraph`: Main graph class

-`triage_router()`: Routes after triage (agent or end)

-`node_router()`: Routes from agent (tool, answer, or loop)

-`tool_router()`: Routes after tool execution (agent or answer)

**Graph Structure**:

```

Entry: triage

  ├─→ [triage_router] → agent (if requires_research)

  │                     └─→ END (if direct_response/needs_clarification/harmful)

  │

  └─→ agent

        ├─→ [node_router] → tool (if tool_calls exist)

        │                  → answer (if research_complete)

        │                  → agent (if no tool_calls, loop back)

        │

        └─→ tool

              ├─→ [tool_router] → agent (continue research)

              │                  → answer (if research_complete)

              │

              └─→ answer → END

```

### 3. State Schema (`schemas.py`)

**ResearchState**: Core state object that flows through the graph.

**Key Fields**:

-`messages`: Conversation history (annotated with `add_messages` for automatic merging)

-`relevant_sources`: Deduplicated sources actually used

-`research_knowledge`: Synthesized knowledge with citations

-`tool_call_count`: Prevents infinite loops

-`research_complete`: Control flag for routing

-`token_usage`: Accumulated token records (annotated with `add`)

**SourceDocument**: Represents a source (document chunk or web page)

-`id`: UUID for citation references

-`content`: Text content

-`source_type`: "doc_chunk" or "web_page"

-`metadata`: Additional context (title, URL, relevance_score, etc.)

**ResearchKnowledge**: Synthesized knowledge from a search

-`selected_sources`: Source IDs actually cited

-`synthesized_knowledge`: Knowledge text with inline [uuid] citations

### 4. Nodes

#### Triage Node (`nodes/triage.py`)

**Purpose**: First node that classifies queries and performs safety screening.

**Process**:

1. Receives user query and context
2. Uses fast LLM to classify query:

-`direct_response`: Simple queries (greetings, basic facts)

-`needs_clarification`: Ambiguous queries

-`harmful_query`: Safety violations

-`requires_research`: Complex queries needing research

3. Generates thread title
4. For non-research queries, sets `final_answer` and routes to END
5. For research queries, routes to agent node

**Output**: Updates `query_type`, `title`, and optionally `final_answer`

#### Agent Node (`nodes/agent.py`)

**Purpose**: Core reasoning node that decides which tools to call.

**Process**:

1. Receives current state with accumulated knowledge
2. Uses primary LLM with tool bindings
3. LLM analyzes query and decides:

- Call a search tool (if knowledge insufficient)
- Call `confirm_research_complete` (if knowledge sufficient)
- Continue reasoning (if no tool call, adds reminder)

4. Tracks tool call count
5. Enforces max tool call limit (default: 4)

**Output**: Adds AIMessage with tool_calls (or reasoning message)

#### Tool Node (`nodes/tool.py`)

**Purpose**: Executes tools called by the agent.

**Process**:

1. Extracts tool call from last message
2. Looks up tool by name
3. Injects ResearchState into tool arguments (for InjectedState support)
4. Executes tool with token tracking
5. Wraps result in ToolMessage
6. If `confirm_research_complete`, sets `research_complete = True`
7. Returns Command with state updates

**Output**: ToolMessage with results, updates to `relevant_sources`, `research_knowledge`, `token_usage`

#### Answer Node (`nodes/answer.py`)

**Purpose**: Generates final comprehensive answer from accumulated research.

**Process**:

1. Checks if research knowledge exists (fallback if none)
2. Converts UUID citations to numeric citations [1], [2] for LLM
3. Formats all research knowledge with search context
4. Uses primary LLM to generate answer with:

- Comprehensive markdown-formatted answer
- Inline citations [1], [2], [3]
- Suggested follow-up queries

5. Streams answer tokens progressively (if enabled)
6. Converts numeric citations back to UUIDs for storage

**Output**: Updates `final_answer` and `suggested_queries`

### 5. Tools

#### Knowledge Search Tools (`tools/knowledge_search.py`)

Four specialized tools for searching internal knowledge collections:

1.**document_focused_search**: Two-stage search (find documents → extract content)

- Best for: Specific subjects, entities, detailed facts
- Uses: `DOCUMENT_FOCUSED_SEARCH_TOP_K = 50`

2.**document_metadata_search**: Filter documents by metadata properties

- Best for: Document properties, metadata filtering
- Uses: `DOCUMENT_METADATA_SEARCH_TOP_K = 20`
- Supports: Metadata filter expressions (e.g., `metadata["year"] == 2024`)

3.**knowledge_topic_search**: Search by predefined knowledge topics

- Best for: Thematic research, topic-based queries
- Uses: `KNOWLEDGE_TOPIC_SEARCH_TOP_K = 30`

4.**collection_wide_search**: Broad search across all content

- Best for: General queries, fallback option
- Uses: `COLLECTION_WIDE_SEARCH_TOP_K = 100`

**Common Process**:

1. Validate collection_index exists
2. Execute Milvus search with queries
3. Convert results to SourceDocument objects
4. Deduplicate against existing sources
5. Synthesize knowledge using LLM
6. Filter to LLM-selected sources
7. Return Command with updates

#### Web Search Tool (`tools/web_search.py`)

**external_web_search**: Searches external web sources using Exa API.

**Process**:

1. Performs concurrent Exa searches for all queries
2. Converts results to SourceDocument objects
3. Deduplicates by URL
4. Synthesizes knowledge (with previous knowledge context)
5. Returns Command with updates

**Use Cases**:

- Recent news and current events
- Public information not in knowledge base
- Industry trends and market data

#### Complete Research Tool (`tools/complete_research.py`)

**confirm_research_complete**: Signals that research is sufficient.

**Process**:

1. Agent calls this when knowledge is sufficient
2. Sets `research_complete = True` in state
3. Routes to answer node
4. Returns confirmation message

### 6. Utilities (`utils.py`)

**Key Functions**:

-**Knowledge Synthesis**:

-`synthesize_knowledge()`: Uses LLM to synthesize sources into knowledge with citations

- Handles both web and document sources
- Converts numeric citations to UUIDs for storage

-**Source Formatting**:

-`format_knowledge_sources()`: Formats document sources for LLM prompts

-`format_web_sources()`: Formats web sources for LLM prompts

-`format_knowledge_collections()`: Formats collection metadata for prompts

-**Citation Management**:

-`sources_to_citations()`: Converts [uuid] → [1], [2] for display

-`citations_to_sources()`: Converts [1], [2] → [uuid] for storage

-`selected_sources_to_uuids()`: Converts numeric indices to UUIDs

-**Content Cleaning**:

-`clean_web_content()`: Removes navigation, ads, excessive formatting

-`clean_doc_chunk()`: Basic cleanup for document chunks

-**Deduplication**:

-`deduplicate_sources()`: Removes duplicate sources by URL (web) or ID (documents)

-**Message Creation**:

-`create_research_input_message()`: Formats initial query with context for agent

### 7. Prompts (`prompts.py`)

**TRIAGE_PROMPT**: Query classification and safety screening

- Classifies into 4 categories
- Generates responses for non-research queries
- Creates thread titles

**AGENT_SYSTEM_PROMPT**: Agent reasoning instructions

- Tool selection guidelines
- Search strategy recommendations
- Knowledge evaluation criteria
- Metadata filter syntax

**KNOWLEDGE_SYNTHESIS_PROMPT**: Knowledge synthesis from sources

- Comprehensive extraction guidelines
- Citation format requirements
- Conflict handling instructions

**ANSWER_GENERATION_PROMPT**: Final answer generation

- Answer formatting guidelines (markdown, sections, tables)
- Citation requirements
- Completeness standards

**RESEARCH_INPUT_PROMPT**: Initial query formatting

- Includes knowledge collections, previous messages, user context

---

## State Management

### State Persistence

The graph uses **PostgreSQL checkpointer** for state persistence:

- State is saved after each node execution
- Enables query observation and resumption
- Thread ID format: `thread-{chat_id}-{microsecond_timestamp}`

### State Updates

State updates use LangGraph's reducer pattern:

-`messages`: Annotated with `add_messages` - automatically merges new messages

-`research_knowledge`: Annotated with `add` - appends new knowledge items

-`token_usage`: Annotated with `add` - accumulates token records

- Other fields: Direct replacement

### Citation System

**Internal Representation**: Uses UUIDs for stable references

- Sources stored with UUID IDs
- Knowledge synthesized with [uuid] citations
- Prevents citation breakage when source order changes

**Display Representation**: Uses numeric indices for readability

- Converted to [1], [2], [3] for LLM prompts and final answers
- Conversion happens at answer generation time

---

## Configuration

### Key Constants (`config.py`)

```python

MAX_ITERATIONS = 25# Graph recursion limit

MAX_TOOL_CALLS = 4# Max tool calls before forcing completion


# Search Top-K Values

DOCUMENT_FOCUSED_SEARCH_TOP_K = 50

DOCUMENT_METADATA_SEARCH_TOP_K = 20

KNOWLEDGE_TOPIC_SEARCH_TOP_K = 30

COLLECTION_WIDE_SEARCH_TOP_K = 100

WEB_SEARCH_RESULT_COUNT = 4


# LLM Configuration

PRIMARY_LLM_KEY = "openai/gpt-4o"

FAST_LLM_KEY = "openai/gpt-4o-mini"

```

### Environment Variables

-`EXA_API_KEY`: Required for web search functionality

---

## API Usage

### Streaming Query Execution

```python

# From routes/research_query_routes.py

POST /research/stream


Request:

{

"query": "User question",

"chat_id": "optional-uuid",

"collections": [{"id": "collection-uuid"}],

"user_context": {},

"web_search_enabled": true

}


Response: Server-Sent Events (SSE)

- type: "state" - State updates

- type: "answer" - Answer token chunks

- type: "event" - Custom events

- type: "final_state" - Final response with answer

```

### Direct Query Execution

```python

# From service.py

result = await service.execute_query_direct(

    query="User question",

    user_id="user-uuid",

    chat_id="optional-chat-uuid",

    collections=[{"id": "collection-uuid"}],

    web_search_enabled=True,

    timeout=120

)


# Returns:

{

"answer": "Final answer",

"suggested_queries": ["follow-up 1", "follow-up 2"],

"token_usage": {...},

"credits_used": 2,

"execution_time": 15.3

}

```

### Observing Query Execution

```python

# Read-only state observation

asyncfor state in service.observe_query_execution(

    thread_id="thread-uuid",

    poll_interval=1.0# Poll every second

):

    print(state)  # ResearchState dict

```

---

## Token Usage & Credits

### Token Tracking

Token usage is tracked at multiple levels:

1.**Node-level**: Each LLM call in nodes (triage, agent, answer)

2.**Tool-level**: LLM calls within tools (synthesis, analysis)

3.**Accumulation**: All records stored in `state.token_usage`

### Credit Calculation

Credits are calculated based on token consumption:

- Rule: 0-10,000 tokens = 1 credit, 10,001-20,000 = 2 credits, etc.
- Aggregated by `tool_call_id` to avoid double-counting
- Formula: `ceil(total_tokens / 10000)` per tool call

---

## Error Handling

### Node Errors

-**Triage errors**: Default to `requires_research` to let agent handle

-**Agent errors**: Return error message, allow retry

-**Tool errors**: Re-raise to LangGraph for handling

-**Answer errors**: Return fallback answer

### Service Errors

-**Timeout**: Raises `TimeoutError` after configurable timeout

-**Thread errors**: Creates new thread if validation fails

-**Collection errors**: Logs warning, continues without collection

---

## Development Guidelines

### Adding a New Tool

1. Create tool function in `tools/` directory
2. Use `InjectedState` annotation for state access
3. Return `Command` object with state updates
4. Register in `tools/registry.py`
5. Update `AGENT_SYSTEM_PROMPT` with tool description

### Modifying State Schema

1. Update `ResearchState` in `schemas.py`
2. Use appropriate reducers (`add_messages`, `add`, or direct)
3. Update all nodes that read/write affected fields
4. Consider migration for existing checkpointer data

### Customizing Prompts

1. Edit prompts in `prompts.py`
2. Use Jinja2 templates for dynamic content
3. Test with various query types
4. Monitor token usage impact

---

## Testing

### Key Test Scenarios

1.**Direct Response**: Simple queries that don't need research

2.**Knowledge Search**: Queries requiring internal knowledge

3.**Web Search**: Queries needing external information

4.**Multi-Source**: Queries requiring both knowledge and web

5.**Max Tool Calls**: Queries that hit tool call limit

6.**Error Recovery**: Tool failures and retries

7.**Streaming**: Real-time updates during execution

---

## Performance Considerations

### Optimization Strategies

1.**Parallel Operations**: Collection fetching and message retrieval run concurrently

2.**Lazy Graph Compilation**: Graph compiled on first use, cached afterward

3.**Fast LLM for Triage**: Uses faster/cheaper model for classification

4.**Source Deduplication**: Prevents redundant source storage

5.**Token Tracking**: Efficient callback-based tracking

### Bottlenecks

1.**LLM Calls**: Primary performance bottleneck

2.**Web Search**: External API calls (Exa) can be slow

3.**Knowledge Synthesis**: Multiple LLM calls per search

4.**State Persistence**: Checkpointer writes after each node

---

## Future Enhancements

Potential improvements:

- Caching for repeated queries
- Parallel tool execution
- Incremental answer generation
- Advanced citation formatting
- Multi-language support
- Custom tool plugins

---

## Related Documentation

- LangGraph: https://langchain-ai.github.io/langgraph/
- LangChain: https://python.langchain.com/
- Milvus: https://milvus.io/docs
- Exa API: https://docs.exa.ai/
