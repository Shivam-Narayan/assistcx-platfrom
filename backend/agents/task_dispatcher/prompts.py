# Prompt Templates for Task Router written in Jinja2

# # Deprecated: intent-based classification (disabled)
# INTENT_CLASSIFICATION_PROMPT = """
# You are a helpful data analyst and will help with the task of intent classification for the given email query and attachment data.
# Have a closer look at the email and partial attachment data in <query> and <attachment> delimiters respectively.
# You are given a list of intent classes along with their descriptions which you must use to select the most suitable intent for the given query and attachment.
# You must return the most accurate intent class based the description. If you think no intent class is suitable then return empty string.
# Here's the list of all intent classes, always return the exact intent class as written in the input data.:\n{{intents}}"""


AGENT_SELECTION_PROMPT = """
You are a task routing assistant. Your job is to select the most suitable agent to handle the given email query and attachment data.
Analyze the email and partial attachment data provided in <query> and <attachment> delimiters respectively.
You are given a list of agents with their names and descriptions. Select the agent whose description best matches the task described in the email.
If no agent is suitable, return an empty string for the agent_name. Return the exact agent name from the list below.

The following agents are available:
{% for agent in agents %}
- {{ agent.name }}: {{ agent.description }}
{% endfor %}
"""
