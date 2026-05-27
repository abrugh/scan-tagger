import base64
import io
import logging
import re
from pathlib import Path

from openai import AzureOpenAI
from pdf2image import convert_from_path

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a document classifier. You will be shown an image of a scanned document.
Provide a concise descriptive name for this document in {max_words} words or fewer.

Rules:
- Be specific and descriptive (e.g. "Car Insurance Declaration" not "Document")
- Use title case
- No dates, no numbers unless essential to the document type
- Respond with ONLY the summary words — no quotes, no punctuation, no explanation\
"""


class Tagger:
    def __init__(self, config):
        self.config = config
        self.client = AzureOpenAI(
            azure_endpoint=config.azure_openai_endpoint,
            api_key=config.azure_openai_api_key,
            api_version=config.azure_openai_api_version,
        )

    def _file_to_base64_image(self, file_path: Path) -> tuple[str, str]:
        """Convert file to base64-encoded image. Returns (b64_data, media_type)."""
        suffix = file_path.suffix.lower()

        if suffix == ".pdf":
            images = convert_from_path(
                str(file_path), first_page=1, last_page=1, dpi=200
            )
            if not images:
                raise ValueError(f"Could not convert PDF to image: {file_path}")
            buf = io.BytesIO()
            images[0].save(buf, format="PNG")
            return base64.b64encode(buf.getvalue()).decode(), "image/png"

        media_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".tiff": "image/tiff",
            ".tif": "image/tiff",
        }
        if suffix in media_types:
            data = file_path.read_bytes()
            return base64.b64encode(data).decode(), media_types[suffix]

        raise ValueError(f"Unsupported file type: {suffix}")

    def generate_name(self, file_path: Path) -> str:
        """Analyze document and return a sanitized summary for use as filename."""
        logger.info("Analyzing document: %s", file_path.name)

        b64_data, media_type = self._file_to_base64_image(file_path)

        response = self.client.chat.completions.create(
            model=self.config.azure_openai_deployment,
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT.format(
                        max_words=self.config.max_summary_words
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "What is this document? Provide a concise name.",
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{media_type};base64,{b64_data}",
                                "detail": "low",
                            },
                        },
                    ],
                },
            ],
            max_completion_tokens=50,
            temperature=0.1,
        )

        summary = response.choices[0].message.content.strip()
        logger.info("LLM response: %s", summary)
        return self._sanitize(summary)

    def _sanitize(self, name: str) -> str:
        """Turn LLM output into a filename-safe string."""
        name = name.strip("\"'.,;:!?")
        name = re.sub(r"[^a-zA-Z0-9\s]", "", name)
        words = name.split()[: self.config.max_summary_words]
        return "_".join(w.capitalize() for w in words) if words else "Unknown_Document"
