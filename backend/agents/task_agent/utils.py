"""This file contains the graph utilities for the application."""

from typing import List, Optional, Dict, Any
from langchain_core.messages import BaseMessage, SystemMessage, ToolMessage


def optimize_messages(
    messages: List[BaseMessage],
    system_prompt: Optional[str] = None,
    max_content_length: int = 8000,
) -> List[BaseMessage]:
    """Optimize messages by trimming content of ToolMessages except for the most recent one.

    Args:
        messages (List[BaseMessage]): List of messages to process
        system_prompt (Optional[str]): System prompt to prepend to the messages
        max_content_length (int): Maximum character length for ToolMessage content

    Returns:
        List[BaseMessage]: List of messages with optional system prompt prepended and trimmed historical ToolMessage content
    """
    if not messages:
        return [SystemMessage(content=system_prompt)] if system_prompt else []

    processed_messages = []
    last_message_index = len(messages) - 1

    # Process each message
    for i, message in enumerate(messages):
        if isinstance(message, ToolMessage):
            # Don't trim if this is the last message in the sequence
            if i == last_message_index:
                processed_messages.append(message)
            else:
                # Trim content if it exceeds max length
                if (
                    isinstance(message.content, str)
                    and len(message.content) > max_content_length
                ):
                    truncated_content = message.content[:max_content_length] + "..."
                    trimmed_message = ToolMessage(
                        content=truncated_content,
                        tool_call_id=message.tool_call_id,
                        name=getattr(message, "name", None),
                        **{
                            k: v
                            for k, v in message.__dict__.items()
                            if k not in ["content", "tool_call_id", "name"]
                        },
                    )
                    processed_messages.append(trimmed_message)
                else:
                    processed_messages.append(message)
        else:
            processed_messages.append(message)

    # Return with optional system prompt prepended
    if system_prompt:
        return [SystemMessage(content=system_prompt)] + processed_messages
    return processed_messages


def format_task_plan(task_plan: List[Dict[str, Any]]) -> str:
    """Format a task plan into a well-structured markdown format.

    Args:
        task_plan (List[Dict[str, Any]]): List of plan step objects containing:
            - step_name (str): The name of the step
            - condition (str, optional): Execution condition (empty string if none)
            - action (str or List[str]): The action(s) to be performed
            - tool (str or List[str], optional): Tool(s) to be used (empty string if none)
            - rules (List[str]): List of rules/constraints for the step

    Returns:
        str: Formatted markdown plan with execution instructions
    """
    if not task_plan:
        return ""

    total_steps = len(task_plan)
    formatted_lines = []

    for i, step in enumerate(task_plan, 1):
        # Extract step data with defaults
        step_name = step.get("step_name", "").strip()
        condition = step.get("condition", "").strip()
        action = step.get("action", "")
        tool = step.get("tool", None)
        rules = step.get("rules", [])

        # Determine step type based on tool presence
        has_tool = (isinstance(tool, list) and any(t.strip() for t in tool)) or (
            tool and not isinstance(tool, list)
        )
        step_type = "Action" if has_tool else "Analysis"

        # Format step header with total count, type, and final step marker
        header = f"**Step {i} of {total_steps} [{step_type}]: {step_name}**"
        if i == total_steps:
            header += " [FINAL STEP]"
        formatted_lines.append(header)

        # Format tool
        if isinstance(tool, list) and any(t.strip() for t in tool):
            tools_str = ", ".join([f"`{t.strip()}`" for t in tool if t.strip()])
            formatted_lines.append(f"- **Tool**: {tools_str}")
        elif tool and not isinstance(tool, list):
            formatted_lines.append(f"- **Tool**: `{tool}`")

        # Format condition only when present
        if condition:
            formatted_lines.append(f"- **Condition**: {condition}")

        # Format actions - handle both string and list
        if isinstance(action, list):
            if len(action) == 1:
                formatted_lines.append(f"- **Actions**: {action[0]}")
            elif len(action) > 1:
                formatted_lines.append(f"- **Actions**:")
                for j, act in enumerate(action, 1):
                    formatted_lines.append(f"  {j}. {act}")
        else:
            # action is a string
            if action:
                formatted_lines.append(f"- **Actions**: {action}")

        # Format rules
        if rules:
            formatted_lines.append("- **Rules**:")
            for rule in rules:
                formatted_lines.append(f"  - {rule}")

        # Add spacing between steps
        if i < total_steps:
            formatted_lines.append("")

    return "\n".join(formatted_lines)


def format_knowledge_collections(
    collections: List[Dict[str, Any]], include_details: bool = True
) -> Optional[str]:
    """Format knowledge collections for LLM prompt consumption.

    Args:
        collections: List of collection dictionaries
        include_details: If True, includes metadata fields and knowledge topics. If False, shows only basic collection info.

    Returns:
        Formatted string ready for LLM prompt inclusion
    """
    if not collections:
        return None

    formatted_collections = []

    for collection in collections:
        if include_details:
            # Detailed format with all information
            collection_info = [
                f"### {collection['name']}",
                f"- **Collection ID:** {collection['id']}",
                f"- **Collection Index:** {collection['index_name']}",
                f"- **Description:** {collection['description']}",
                f"- **Documents:** {collection['document_count']} documents",
            ]

            # Format metadata fields
            if collection.get("metadata_fields"):
                collection_info.append("- **Metadata Fields:**")
                for field in collection["metadata_fields"]:
                    field_line = f"  - {field['name']} (type: {field.get('data_type', 'text')}): {field['description']} "
                    field_line += f"Keywords: [{', '.join(field.get('keywords', []))}]"
                    collection_info.append(field_line)
            else:
                collection_info.append("- **Metadata Fields:** N/A")

            # Format knowledge topics
            if collection.get("knowledge_topics"):
                collection_info.append("- **Knowledge Topics:**")
                for topic in collection["knowledge_topics"]:
                    topic_line = f"  - {topic['name']}: {topic['description']} Keywords: [{', '.join(topic.get('keywords', []))}]"
                    collection_info.append(topic_line)
            else:
                collection_info.append("- **Knowledge Topics:** N/A")

            formatted_collections.append("\n".join(collection_info))
        else:
            # Basic format - just essential info with same structure
            collection_info = [
                f"### {collection['name']}",
                f"- **Collection ID:** {collection['id']}",
                f"- **Collection Index:** {collection['index_name']}",
                f"- **Description:** {collection['description']}",
                f"- **Documents:** {collection['document_count']} documents",
            ]
            formatted_collections.append("\n".join(collection_info))

    return "\n".join(formatted_collections)
