import re

# Constants for content cleaning
URL_LENGTH_LIMIT = 50

# Compile regex patterns once for better performance
NAV_PATTERNS = [
    re.compile(r"\[Skip to content\].*?\n", re.IGNORECASE),
    re.compile(r"\[Home\].*?».*?\n", re.IGNORECASE),
    re.compile(r"Table of Contents.*?\n", re.IGNORECASE),
    re.compile(r"\[Toggle\].*?\n", re.IGNORECASE),
    re.compile(r"Connect with us.*?\n", re.IGNORECASE),
    re.compile(r"Sign Up.*?\n", re.IGNORECASE),
    re.compile(r"Don\'t Miss.*?\n", re.IGNORECASE),
    re.compile(r"Up Next.*?\n", re.IGNORECASE),
    re.compile(r"You may also like.*?\n", re.IGNORECASE),
    re.compile(r"Related Topics:.*?\n", re.IGNORECASE),
    re.compile(r"Popular.*?\n", re.IGNORECASE),
]

AD_PATTERNS = [
    re.compile(r"\[!\[.*?\]\(.*?\)\]\(.*?\)"),  # Ad banner markdown
    re.compile(r'target="_blank".*?style=".*?"'),  # Ad styling
    re.compile(r"utm_source=.*?utm_campaign=.*?"),  # Tracking parameters
]

# Other compiled patterns
IMAGE_PATTERN_1 = re.compile(r"!\[.*?\]\(data:image/.*?\)")
IMAGE_PATTERN_2 = re.compile(r"!\[.*?\]\(.*?\)")
LONG_LINK_PATTERN = re.compile(f"\\[([^\\]]+)\\]\\(https?://[^\\s\\)]{{{URL_LENGTH_LIMIT},}}\\)")
LONG_URL_PATTERN = re.compile(f"https?://[^\\s]{{{URL_LENGTH_LIMIT},}}")
SOCIAL_PATTERN = re.compile(r"- \[?(Twitter|Facebook|LinkedIn|Reddit|Pinterest|Email)\]?.*?\n")
TABLE_PATTERN_1 = re.compile(r"\| --- \|")
TABLE_PATTERN_2 = re.compile(r"\|\s*\|\s*\|\s*\|")
NEWLINE_PATTERN = re.compile(r"\n\s*\n\s*\n+")


def clean_web_content(text: str) -> str:
    """
    Clean web content for better analysis.
    Optimized with pre-compiled regex patterns.

    Args:
        text: Raw web content

    Returns:
        Cleaned content suitable for analysis
    """
    if not text or not isinstance(text, str):
        return ""

    # Remove common navigation and UI elements
    for pattern in NAV_PATTERNS:
        text = pattern.sub("", text)

    # Remove image references and data URIs
    text = IMAGE_PATTERN_1.sub("", text)
    text = IMAGE_PATTERN_2.sub("", text)

    # Clean up links - keep text but remove URLs for long links
    text = LONG_LINK_PATTERN.sub(r"\1", text)

    # Remove standalone long URLs
    text = LONG_URL_PATTERN.sub("", text)

    # Remove email/social sharing elements
    text = SOCIAL_PATTERN.sub("", text)

    # Remove advertisement patterns
    for pattern in AD_PATTERNS:
        text = pattern.sub("", text)

    # Clean up table formatting - preserve but simplify
    text = TABLE_PATTERN_1.sub("|---|", text)
    text = TABLE_PATTERN_2.sub("|||", text)

    # Remove excessive newlines only
    text = NEWLINE_PATTERN.sub("\n\n", text)  # Max 2 consecutive newlines
    text = text.strip()

    return text


def clean_doc_chunk(text: str) -> str:
    """
    Simple cleanup for document chunks (PDFs, Word docs, etc.).
    Only handles basic formatting issues since document chunks are usually cleaner.

    Args:
        text: Document chunk content

    Returns:
        Cleaned content with basic formatting fixed
    """
    if not text or not isinstance(text, str):
        return ""

    # Remove image references (sometimes present in PDFs)
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
    text = re.sub(r"\[Image:.*?\]", "", text)
    text = re.sub(r"Figure \d+:.*?\n", "", text)

    # Fix excessive newlines (max 3 consecutive)
    text = re.sub(r"\n\s*\n\s*\n\s*\n+", "\n\n", text)

    return text.strip()


def clean_content(text: str, content_type: str = "web") -> str:
    """
    Generic content cleaning function that routes to appropriate cleaner.
    
    Args:
        text: Content to clean
        content_type: Type of content ("web", "doc", or "auto")
        
    Returns:
        Cleaned content
    """
    if not text or not isinstance(text, str):
        return ""
    
    if content_type == "doc":
        return clean_doc_chunk(text)
    elif content_type == "web":
        return clean_web_content(text)
    elif content_type == "auto":
        # Auto-detect based on content characteristics
        # If content has markdown-like patterns, treat as web content
        if any(pattern in text for pattern in ["[", "](", "###", "**"]):
            return clean_web_content(text)
        else:
            return clean_doc_chunk(text)
    else:
        # Default to web cleaning
        return clean_web_content(text)