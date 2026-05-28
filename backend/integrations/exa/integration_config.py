exa = """
# Exa Integration Guide

## Overview

Exa is a web search API built for AI applications, enabling agents to retrieve high-quality, relevant web content using natural language queries. By integrating Exa, your AI agents can search the web in real time to find up-to-date information, product documentation, support articles, and other external knowledge to assist with customer queries. This guide covers configuration requirements, best practices, and step-by-step instructions to set up the Exa integration.

## Key Information

- **Integration Name**: Exa
- **Auth Type**: API Key
- **Base URL**: `https://api.exa.ai`
- **Endpoints**:
  - `https://api.exa.ai/search`
  - `https://api.exa.ai/findSimilar`
  - `https://api.exa.ai/contents`
- **Search Types**: auto, fast, instant, deep-lite, deep, deep-reasoning

### Prerequisites

- **Exa Account**: Sign up or log in at [Exa Dashboard](https://dashboard.exa.ai/).
- **API Key**: Generate an API key from the Exa dashboard.

## Best Practices for Managing API Keys and Usage

1. **Secure API Keys**:
   - Store your API keys in a secure environment, such as environment variables or a secrets manager.
   - Never hardcode API keys in your application code.
2. **Rate Limit Awareness**:
   - Monitor your usage to stay within Exa's rate limits.
   - Implement retry logic for handling rate limit errors.
3. **Optimize Search Queries**:
   - Use descriptive natural language queries for better relevance.
   - Choose the appropriate search type (`fast` for speed-sensitive agent workflows, `deep` for thorough research).
4. **Monitor Costs**:
   - Track search usage to manage costs effectively. Regularly review usage in the Exa dashboard.

## Steps to Obtain and Configure Exa API Credentials

### Step 1: Create an Exa Account

1. **Sign Up**:
   - Go to [Exa Dashboard](https://dashboard.exa.ai/) and create an account if you don't already have one.
2. **Verify Email**:
   - Verify your email address and log into the dashboard.

### Step 2: Generate an API Key

1. **Navigate to API Keys**:
   - In the Exa dashboard, go to the **API Keys** section at [https://dashboard.exa.ai/api-keys](https://dashboard.exa.ai/api-keys).
2. **Create a New Key**:
   - Click **Create API Key**.
   - **Copy and save the key immediately**, as it may only be displayed once.

### Step 3: Configure API Access in Your Application

1. **Environment Variables**:
   - Store the API key in an environment variable (e.g., `EXA_API_KEY`) to enhance security.
2. **API Base URL**:
   - Ensure your application uses the base URL `https://api.exa.ai` for all requests.
3. **Authentication Header**:
   - Pass the API key via the `x-api-key` header in all requests.

## Example Configuration

Here is a sample configuration for the Exa integration:

```json
{
    "API_KEY": "your-exa-api-key",
    "BASE_URL": "https://api.exa.ai",
    "DEFAULT_SEARCH_TYPE": "auto",
    "TIMEOUT": 30
}
```

## Frequently Asked Questions (FAQ)

### 1. What search types are available?
Exa offers several search types: `auto` (default, selects the best method automatically), `fast`, `instant`, `deep-lite`, `deep`, and `deep-reasoning`. Choose based on your speed vs. quality requirements.

### 2. How do I manage rate limits?
Exa enforces rate limits based on your account plan. Monitor usage in the dashboard and implement retry logic in your application.

### 3. What happens if my API key is compromised?
Immediately revoke the compromised key from the dashboard and generate a new one. Update your application with the new key.

## Troubleshooting Tips

- **Authentication Errors (401)**: Verify that the API key is correct and passed via the `x-api-key` header.
- **Rate Limit Errors (429)**: Implement exponential backoff and retry logic for rate limit handling.
- **Timeouts**: Configure appropriate timeout settings and consider using `fast` or `instant` search types for latency-sensitive workflows.
- **Empty Results**: Refine your natural language query for better relevance.

## Conclusion

By following this guide, you can integrate Exa's search capabilities into your platform, giving AI agents the ability to retrieve real-time web information when resolving customer queries. For further details, refer to the [Exa API documentation](https://docs.exa.ai/) and [dashboard](https://dashboard.exa.ai/).

"""
