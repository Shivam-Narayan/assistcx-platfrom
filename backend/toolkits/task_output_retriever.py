from logger import configure_logging
from toolkits.shared_utils import validate_uuid

from db_pool import DatabasePoolManager
from repository.agent_output_repository import AgentOutputRepository

import json


logger = configure_logging(__name__)


class TaskOutputRetriever:
    """Retrieves the latest output of an agent task by its task ID."""

    def __init__(self, organization_schema: str):
        self.organization_schema = organization_schema
        self.db_pool = DatabasePoolManager()

    def get_task_output(self, agent_task_id: str) -> str:
        """Retrieves the latest output for a given agent task ID.

        Args:
            agent_task_id: UUID string of the agent task to retrieve output for.

        Returns:
            JSON string containing the task output, or an error message.
        """
        task_uuid, error = validate_uuid(agent_task_id, "agent_task_id")
        if error:
            return json.dumps({"error": error}, ensure_ascii=False)

        try:
            with self.db_pool.get_session(self.organization_schema) as db:
                repo = AgentOutputRepository(db)
                result = repo.get_agent_output_by_agent_task(task_uuid)

                if not result or not result.get("agent_output"):
                    return json.dumps(
                        {
                            "error": f"No output found for agent_task_id: {agent_task_id}"
                        },
                        ensure_ascii=False,
                    )

                output = result["agent_output"].output

                if not output:
                    return json.dumps(
                        {
                            "error": f"Output is empty for agent_task_id: {agent_task_id}"
                        },
                        ensure_ascii=False,
                    )

                return output

        except Exception as e:
            logger.error(
                f"Error retrieving task output for {agent_task_id}: {e}",
                exc_info=True,
            )
            return json.dumps(
                {"error": f"Failed to retrieve task output: {str(e)}"},
                ensure_ascii=False,
            )


# Example usage and testing
if __name__ == "__main__":
    organization_schema = "public"
    retriever = TaskOutputRetriever(organization_schema)

    # Replace with an actual agent_task_id UUID from your database
    test_task_id = "5ce0e5a3-2483-442f-b1e5-083d14130b82"

    print("=== Testing Task Output Retriever ===\n")

    # Test 1: Retrieve task output with a valid UUID
    print("1. Testing get_task_output (valid UUID):")
    try:
        result = retriever.get_task_output(agent_task_id=test_task_id)
        print(
            f"  Result: {result[:200]}..."
            if len(result) > 200
            else f"  Result: {result}"
        )
    except Exception as e:
        print(f"  Error: {str(e)}")
    print()

    # Test 2: Invalid UUID format
    print("2. Testing get_task_output (invalid UUID):")
    try:
        result = retriever.get_task_output(agent_task_id="not-a-valid-uuid")
        print(f"  Result: {result}")
    except Exception as e:
        print(f"  Error: {str(e)}")
    print()

    # Test 3: Empty input
    print("3. Testing get_task_output (empty input):")
    try:
        result = retriever.get_task_output(agent_task_id="")
        print(f"  Result: {result}")
    except Exception as e:
        print(f"  Error: {str(e)}")
    print()

    print("=== Testing Complete ===")
