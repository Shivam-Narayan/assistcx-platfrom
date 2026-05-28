import os
from dotenv import load_dotenv
load_dotenv()
# Retrieve the environment type from the environment variables
environment = os.getenv("ENVIRONMENT")

# Conditionally set additional variables if in debug mode
if os.getenv("AGENT_DEBUGGER"):
    os.environ["LANGCHAIN_TRACING_V2"] = os.getenv("LANGCHAIN_TRACING_V2")
    os.environ["LANGCHAIN_ENDPOINT"] = os.getenv("LANGCHAIN_ENDPOINT")
    os.environ["LANGCHAIN_API_KEY"] = os.getenv("LANGCHAIN_API_KEY")
    os.environ["LANGCHAIN_PROJECT"] = os.getenv("LANGCHAIN_PROJECT")
