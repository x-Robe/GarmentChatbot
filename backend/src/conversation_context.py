"""Small text-only context boundary shared by HTTP and direct agent callers."""
import re
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

MAX_CONTEXT_MESSAGES = min(1000, max(1, int(os.getenv("MAX_CONTEXT_MESSAGES", "200"))))
MAX_CONTEXT_TEXT = 10000
MAX_CONTEXT_CHARS = min(1000000, max(10000, int(os.getenv("MAX_CONTEXT_CHARS", "60000"))))
MAX_CONTEXT_INPUT_MESSAGES = 1000


def context_text(text: str) -> str:
    """Drop old image markup, links/paths and explicit metadata lines, not products."""
    text = re.sub(r'!\[[^\]\n]*\]\([^\n)]*\)', '', text)
    text = re.sub(r'https?://\S+|file://\S+', '', text)
    text = re.sub(r'(?<!\S)(?:/|data/images/|[A-Za-z]:[\\/])\S+', '', text)
    text = re.sub(r'^.*\b(?:point_id|product_id|image_path|image_url)\b.*$', '', text, flags=re.M)
    text = re.sub(r"data:\S+", "", text)
    text = re.sub(r"^.*\b(?:embedding|vector|base64|api_key|authorization|tool_trace)\b.*$", "", text, flags=re.M | re.I)
    return text.strip()


def normalize_context(context):
    if context is None:
        return []
    if not isinstance(context, list) or len(context) > MAX_CONTEXT_INPUT_MESSAGES:
        raise ValueError('Context exceeds the hard input boundary.')
    clean = []
    for item in context:
        if (not isinstance(item, dict) or set(item) != {'role', 'text'}
                or item['role'] not in ('user', 'assistant')
                or not isinstance(item['text'], str)
                or not 1 <= len(item['text']) <= MAX_CONTEXT_TEXT):
            raise ValueError('Invalid context message.')
        text = context_text(item['text'])
        if text:
            clean.append({'role': item['role'], 'text': text})
    bounded = []
    remaining = MAX_CONTEXT_CHARS
    for item in reversed(clean[-MAX_CONTEXT_MESSAGES:]):
        if remaining <= 0:
            break
        text = item["text"][-remaining:]
        bounded.append({"role": item["role"], "text": text})
        remaining -= len(text)
    return list(reversed(bounded))
