gemini = """
# Google Gemini API Integration Guide

## Overview

Google provides powerful APIs for leveraging their state-of-the-art Gemini models, enabling developers to integrate advanced AI capabilities for text generation, multimodal understanding (text, image, audio, video), function calling, embedding generation, and more into their applications. This guide offers a comprehensive overview of the configuration requirements, best practices, and steps to integrate the Gemini API.

## Key Information

-   **Integration Name**: Google Gemini API (via Google AI or Vertex AI)
-   **Auth Type**: API Key (via Google AI Studio) or OAuth 2.0 / Service Account (via Google Cloud Vertex AI)
-   **Base URL (Google AI API)**: `https://generativelanguage.googleapis.com/v1beta`
-   **Base URL (Vertex AI API)**: `https://{REGION}-aiplatform.googleapis.com/v1` (e.g., `us-central1-aiplatform.googleapis.com`)
-   **Common Endpoints (Google AI API)**:
    -   `models/gemini-2.0-pro-latest:generateContent`
    -   `models/gemini-2.0-flash-latest:generateContent`
    -   `models/gemini-2.0-pro-latest:streamGenerateContent` (for streaming)
    -   `models/text-embedding-004:embedContent`
-   **Supported Models (Examples)**: Gemini 2.0 Pro, Gemini 2.0 Flash, Text Embedding models. (Check documentation for the latest list and capabilities).

### Prerequisites

-   **Google Account**: Required for accessing Google AI Studio or Google Cloud Platform.
-   **API Key (Google AI Studio)**: Generate an API key via [Google AI Studio](https://aistudio.google.com/). *Note: This is suitable for prototyping and development.*
-   **OR Google Cloud Project & Credentials (Vertex AI)**: For production applications, set up a Google Cloud project, enable the Vertex AI API, and configure authentication (OAuth 2.0 or Service Accounts). See [Google Cloud Authentication](https://cloud.google.com/docs/authentication).

## Best Practices for Managing API Keys and Usage

1.  **Secure Credentials**:
    * Store API keys or service account keys securely using environment variables, secrets management services (like Google Secret Manager), or secure configuration files.
    * Never embed credentials directly in your source code.
    * Restrict API key usage by IP address or application if possible (via Google Cloud Console).
2.  **Quota Awareness**:
    * Gemini APIs have usage quotas (e.g., requests per minute). Monitor your usage in the Google Cloud Console associated with your API key or project.
    * Implement exponential backoff and retry logic for handling quota-related errors (e.g., `429 Resource Exhausted`).
3.  **Optimize API Calls**:
    * Use streaming responses (`streamGenerateContent`) for interactive applications or long generations.
    * Structure prompts clearly and concisely to improve response quality and potentially reduce token usage.
    * Batch requests where appropriate (e.g., batch embeddings).
4.  **Monitor Costs**:
    * Track token usage and API calls, as pricing is typically based on input/output tokens. Review billing reports in the Google Cloud Console.
5.  **Model Versioning**:
    * Use specific model versions (e.g., `gemini-2.0-pro-001`) for stability or `-latest` tags (e.g., `gemini-2.0-pro-latest`) for automatic updates. Be aware of potential changes when using `-latest`.

## Steps to Obtain and Configure Google AI API Credentials (API Key)

*This focuses on the simpler API Key method via Google AI Studio.*

### Step 1: Access Google AI Studio

1.  **Go to Google AI Studio**: Navigate to [https://aistudio.google.com/](https://aistudio.google.com/).
2.  **Sign In**: Log in with your Google Account.

### Step 2: Generate an API Key

1.  **Navigate to API Keys**: Click on "Get API key" in the left-hand menu.
2.  **Create or Select Project**: You might be prompted to create or select an associated Google Cloud project. API keys generated here are managed within that Cloud project.
3.  **Create API Key**: Click the button to "Create API key in new project" or "Create API key in existing project".
4.  **Copy and Secure Key**: Your API key will be generated and displayed. **Copy this key immediately and store it securely.** It will not be shown again.

### Step 3: Configure API Access in Your Application

1.  **Environment Variables**: Store the API key in an environment variable (e.g., `GOOGLE_API_KEY`). Most Google client libraries will automatically look for this.
2.  **API Base URL**: Ensure your application uses the correct base URL (`https://generativelanguage.googleapis.com/v1beta`) when making direct HTTP requests. If using client libraries, this is often handled automatically.

## Example Configuration (Conceptual)

```json
{
    "API_KEY": "YOUR_GOOGLE_API_KEY", // Best practice: Load from env variable
    "BASE_URL": "[https://generativelanguage.googleapis.com/v1beta](https://generativelanguage.googleapis.com/v1beta)",
    "DEFAULT_MODEL": "gemini-2.0-pro-latest",
    "REQUEST_TIMEOUT": 60 // Timeout in seconds
}
"""