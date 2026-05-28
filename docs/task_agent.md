# Task Agent Documentation

This document describes the Task Agent workflow, a LangGraph-based system for executing tasks using LLMs, tools, and optional Human-in-the-Loop (HITL) review.

## Overview

The Task Agent is a flexible, state-driven workflow that:
- Processes user requests using an LLM and tools
- Supports optional human review of sensitive tool calls
- Generates structured outputs based on task execution
- Persists state for resumable workflows

**Key Features:**
- LLM-driven task execution with tool calling
- Human-in-the-Loop (HITL) for tool approval/editing/rejection
- Structured output generation
- PostgreSQL-backed state persistence
- Command-based routing (LangGraph best practices)

---

## Architecture

### Graph Structure

The workflow is a directed graph with 4 core nodes:

```
┌─────────┐
│  START  │
└────┬────┘
     ↓
┌─────────┐
│  Agent  │ ← LLM generates responses or tool calls
└────┬────┘
     ↓
  [Router]
     ├─→ Human Review? → [Human Review Node] → Tool or Agent
     ├─→ Tool Call?    → [Tool Node] → Agent
     ├─→ Output?       → [Output Node] → END
     └─→ No action     → Agent (with reminder)
```

### Nodes

1. **Agent Node** (`agent`)
   - Invokes LLM with conversation history
   - Generates AIMessage with content or tool_calls
   - Handles retry logic for LLM failures
   - Injects reminder if no action taken

2. **Human Review Node** (`human_review`) - *Optional*
   - Pauses workflow with `interrupt()` for human input
   - Evaluates LLM rules first (auto-approve if safe)
   - Handles 4 human actions:
     - **Approve**: Execute tool as-is
     - **Edit**: Modify tool parameters, then execute
     - **Respond**: Skip tool, provide direct answer
     - **Reject**: Skip tool, continue without execution
   - Uses `Command` pattern for routing

3. **Tool Node** (`tool`)
   - Executes single tool call from last message
   - Creates ToolMessage with result or error
   - No queue management (reads from messages directly)

4. **Output Node** (`output`) - *Optional*
   - Extracts structured output from `generate_task_output` tool
   - Validates against output schema
   - Terminates workflow

### Router Logic

The `node_router()` determines next step based on last message:

```python
if has_generate_task_output_tool_call:
    return "output"
elif has_tool_call and requires_human_review:
    return "human_review"
elif has_tool_call:
    return "tool_call"
else:
    return "agent"  # Loop back with reminder
```

---

## State Management

### GraphState Schema

```python
class GraphState(BaseModel):
    messages: Annotated[list, add_messages]
    structured_output: Optional[Dict[str, Any]]
    human_review_history: List[HumanReviewRecord]
```

**Fields:**
- `messages`: Conversation history (HumanMessage, AIMessage, ToolMessage)
- `structured_output`: Final structured output (if output_schema provided)
- `human_review_history`: Audit trail of all human review actions

**Note:** The refactored design uses messages as the single source of truth. No manual queues (`pending_tool_calls`, `approved_tool_calls`) are needed.

### HumanReviewRecord

Tracks each human review action:

```python
class HumanReviewRecord(BaseModel):
    tool_name: str              # Tool that was reviewed
    tool_call_id: str           # Reference to message history
    action_taken: HITL_ACTION   # approve/reject/edit/respond
    feedback: Optional[str]     # Human's comment
    original_params: Optional[Dict]  # Before edit (for edits only)
    edited_params: Optional[Dict]    # After edit (for edits only)
    user_id: Optional[str]      # Who performed the review
    timestamp: str              # ISO format timestamp
```

---

## Human-in-the-Loop (HITL)

### Overview

HITL allows humans to review and control tool execution before it happens. It uses LangGraph's `interrupt()` mechanism to pause the workflow.

### How It Works

1. **Mark Tools for Review**
   ```python
   from agents.task_agent.human import with_human_approval

   # Wrap any tool requiring review
   reviewed_tool = with_human_approval(my_dangerous_tool)
   ```

2. **LLM Review (Optional)**
   - Before interrupt, optionally evaluate LLM rules
   - If rules approve, auto-proceed without human input
   - If rules require review or rules are empty, trigger interrupt

3. **Interrupt & Wait**
   - Graph pauses at `human_review` node
   - State saved to PostgreSQL checkpointer
   - Interrupt payload contains tool call details

4. **Human Input Submission**
   - External system submits decision via API
   - Input validated against `HumanInput` model
   - Graph resumes with `Command` routing

5. **Resume & Execute**
   - Based on action:
     - **Approve** → Execute tool as-is
     - **Edit** → Replace tool call args, then execute
     - **Respond** → Skip tool, send ToolMessage with human response
     - **Reject** → Skip tool, send ToolMessage with rejection notice

### Human Actions

#### 1. Approve
Executes the tool call without modifications.

**Example Input:**
```json
{
  "action": "approve",
  "feedback": "Looks good to proceed",
  "user_id": "user_123"
}
```

**Result:** Tool executes → ToolMessage added → continues to agent

---

#### 2. Edit
Modifies tool call parameters before execution.

**Example Input:**
```json
{
  "action": "edit",
  "feedback": "Changed query to be more specific",
  "edited_params": {"query": "tech news 2025"},
  "user_id": "user_123"
}
```

**Result:**
- Original params stored in audit trail
- AIMessage replaced with edited tool call
- Tool executes with new params

---

#### 3. Respond
Skips tool execution, provides direct answer.

**Example Input:**
```json
{
  "action": "respond",
  "feedback": "I already have that information: [data here]",
  "user_id": "user_123"
}
```

**Result:**
- Tool NOT executed
- ToolMessage created with human's response
- Agent continues with human's answer

---

#### 4. Reject
Skips tool execution, no alternative provided.

**Example Input:**
```json
{
  "action": "reject",
  "feedback": "This is too risky to execute",
  "user_id": "user_123"
}
```

**Result:**
- Tool NOT executed
- ToolMessage created with rejection notice
- Agent continues without tool result

---

### LLM Review Rules

Optionally configure rules for automatic approval:

```python
agent = TaskAgentGraph(
    tools=[...],
    human_review=True,
    review_rules=[
        "Approve if query is for public information",
        "Require review if accessing user data",
        "Approve if amount is less than $100"
    ]
)
```

**How it works:**
1. Before interrupt, LLM evaluates tool call against rules
2. LLM returns: `{"requires_review": bool, "reason": str}`
3. If `requires_review=False`, auto-approve (skip interrupt)
4. If `requires_review=True`, proceed to interrupt

---

## API Integration

### Submitting Human Input

**Endpoint:** `POST /api/human-review/submit`

**Request:**
```json
{
  "thread_id": "thread-abc123",
  "action": "approve",
  "feedback": "Approved after review",
  "edited_params": null,
  "user_id": "user_456"
}
```

**Response (Success):**
```json
{
  "status": "success",
  "message": "Human input processed",
  "thread_id": "thread-abc123"
}
```

**Response (Error):**
```json
{
  "status": "error",
  "message": "Invalid action or missing required fields"
}
```

### Implementation Example

```python
from fastapi import FastAPI, HTTPException
from agents.task_agent.schemas import HumanInput

app = FastAPI()

@app.post("/api/human-review/submit")
async def submit_human_input(
    thread_id: str,
    input: HumanInput
):
    try:
        # Resume graph with human input
        await graph.ainvoke(
            Command(resume=input.dict()),
            config={"configurable": {"thread_id": thread_id}}
        )
        return {
            "status": "success",
            "message": "Human input processed",
            "thread_id": thread_id
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
```

---

## Configuration

### TaskAgentGraph Constructor

```python
from agents.task_agent.graph import TaskAgentGraph

agent = TaskAgentGraph(
    llm=llm,                    # Required: LLM instance
    tools=tools,                # Required: List of tools
    checkpointer=checkpointer,  # Required: AsyncPostgresSaver
    human_review=True,          # Optional: Enable HITL
    review_rules=[...],         # Optional: LLM auto-approval rules
    output_schema=MySchema,     # Optional: Structured output schema
    agent_kwargs={              # Optional: Additional config
        "agent_name": "My Agent",
        "success_criteria": "...",
        "max_llm_call_retries": 3
    }
)
```

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `llm` | BaseLanguageModel | ✅ | LLM for task processing |
| `tools` | List[BaseTool] | ✅ | Available tools for agent |
| `checkpointer` | AsyncPostgresSaver | ✅ | State persistence |
| `human_review` | bool | ❌ | Enable HITL (default: False) |
| `review_rules` | List[str] | ❌ | LLM auto-approval rules |
| `output_schema` | BaseModel | ❌ | Schema for structured output |
| `agent_kwargs` | Dict | ❌ | Additional configuration |

---

## Workflow Example

**Task:** "Search for latest tech news"

### Without HITL

1. **Agent:** LLM generates `tool_calls=[{"name": "search_web", "args": {"query": "tech news"}}]`
2. **Router:** Has tool_call → routes to `tool`
3. **Tool:** Executes `search_web("tech news")`, returns results
4. **Agent:** Processes results, generates final response
5. **Output:** (If schema provided) Extracts structured output
6. **END**

### With HITL

1. **Agent:** LLM generates `tool_calls=[{"name": "search_web", "args": {"query": "tech news"}}]`
2. **Router:** Requires review → routes to `human_review`
3. **Human Review:**
   - LLM rules evaluate (optional auto-approve)
   - If review needed: `interrupt()` pauses workflow
   - Wait for human input via API
4. **Human Input:** `{"action": "edit", "edited_params": {"query": "tech news 2025"}}`
5. **Resume:** Replace tool call with edited params
6. **Router:** Routes to `tool`
7. **Tool:** Executes `search_web("tech news 2025")`, returns results
8. **Agent:** Processes results
9. **Output:** Structured output
10. **END**

---

## Key Differences from Old Design

### What Changed (Simplified)

| Aspect | Old Design | New Design |
|--------|-----------|------------|
| **State Fields** | 6 HITL fields | 1 field (`human_review_history`) |
| **Queue Management** | Manual (`pending_tool_calls`, `approved_tool_calls`) | None (reads from messages) |
| **LLM Review** | Separate `llm_review` node | Helper function in `human_review` |
| **Routing** | State flags (`next_action`, `human_review_pending`) | LangGraph `Command` pattern |
| **Tool Execution** | Batch processing from queue | Single tool from last message |
| **Audit Trail** | Nested `HumanReviewRecord` | Flat, lightweight records |
| **Nodes** | 7 nodes (agent, tool, llm_review, human_review, etc.) | 4 nodes (agent, tool, human_review, output) |

### Benefits

✅ **Simpler:** 83% fewer state fields, no manual queues
✅ **LangGraph Native:** Uses `interrupt()` and `Command` properly
✅ **Easier to Debug:** Linear flow, single source of truth (messages)
✅ **Better Audit:** Flattened records, original params tracked for edits
✅ **Less Code:** 40% reduction in HITL complexity

---

## Troubleshooting

### Common Issues

**1. Error: `'GraphState' object has no attribute 'pending_tool_calls'`**
- **Cause:** Old code trying to access removed state field
- **Fix:** Ensure all code uses `state.messages[-1].tool_calls` instead of queues

**2. Interrupt doesn't pause workflow**
- **Cause:** Checkpointer not configured
- **Fix:** Pass `AsyncPostgresSaver` to `TaskAgentGraph` constructor

**3. Human input rejected**
- **Cause:** Invalid action or missing required fields
- **Fix:** Validate against `HumanInput` model schema

**4. Tool not requiring review**
- **Cause:** Tool not wrapped with `with_human_approval()`
- **Fix:** Wrap tool before passing to `TaskAgentGraph`

---

## Dependencies

- **LangGraph:** Graph orchestration, state management
- **LangChain:** LLM integration, tool calling
- **PostgreSQL:** State persistence via `AsyncPostgresSaver`
- **Pydantic:** Schema validation

## Related Files

- `backend/agents/task_agent/graph.py` - Main graph implementation
- `backend/agents/task_agent/schemas.py` - State and model definitions
- `backend/agents/task_agent/human.py` - HITL logic and helpers
- `backend/agents/task_agent/prompts.py` - System prompts and templates

---

## Summary

The Task Agent provides a flexible, production-ready workflow for LLM-powered task execution with optional human oversight. The refactored design emphasizes simplicity, maintainability, and alignment with LangGraph best practices, making it easier to understand, debug, and extend.
