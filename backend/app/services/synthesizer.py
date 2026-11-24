import json
import re
import logging
from typing import Optional
from pydantic import BaseModel
from llama_cpp import Llama
from backend.app.core.device import get_device_profile
from pathlib import Path

logger = logging.getLogger(__name__)
DEFAULT_MODEL_PATH = Path(__file__).resolve().parent.parent.parent / "weights" / "qwen" / "qwen2.5-3b-instruct-q4_k_m.gguf"

class EditorialDigest(BaseModel):
    takeaways: list[str]
    audio_script: str
    summary: str = ""

def clean_fallback_script(title: str, text: str) -> str:
    """Extract 1-2 complete sentences without ever cutting off mid-sentence."""
    if not text:
        return f"{title}."
    clean_text = re.sub(r'\s+', ' ', text).strip()
    # Split on sentence boundaries (. ! ?)
    raw_sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', clean_text) if s.strip()]
    
    selected = []
    word_count = 0
    for s in raw_sentences:
        # Ensure sentence ends with punctuation
        if not re.search(r'[.!?]$', s):
            s += "."
        words = s.split()
        if word_count + len(words) > 40 and selected:
            break
        selected.append(s)
        word_count += len(words)

    if selected:
        return " ".join(selected)
    
    # Safe word-boundary fallback
    words = clean_text.split()[:25]
    return " ".join(words).rstrip(' ,;:-') + "."

def _ensure_complete_sentence(text: str) -> str:
    """Trim any dangling incomplete clause and guarantee sentence-ending punctuation."""
    cleaned = text.strip()
    if not cleaned:
        return ""
    if not re.search(r'[.!?]["\']?$', cleaned):
        last_punct = max(cleaned.rfind('.'), cleaned.rfind('!'), cleaned.rfind('?'))
        if last_punct > 20:
            cleaned = cleaned[:last_punct + 1]
        else:
            cleaned += "."
    return cleaned


def _normalize_summary(raw_summary: object) -> str:
    """Preserve paragraph breaks while collapsing excess horizontal whitespace."""
    if not isinstance(raw_summary, str) or not raw_summary.strip():
        return ""
    paragraphs = [
        re.sub(r'[ \t]+', ' ', p).strip()
        for p in re.split(r'\n\s*\n', raw_summary.strip())
        if p.strip()
    ]
    return _ensure_complete_sentence("\n\n".join(paragraphs))


def _coerce_takeaways(raw_takeaways: object, fallback_title: str) -> list[str]:
    """Normalize takeaways into a non-empty list of clean strings."""
    if isinstance(raw_takeaways, str):
        raw_takeaways = [raw_takeaways]
    if isinstance(raw_takeaways, list):
        items = [str(item).strip() for item in raw_takeaways if str(item).strip()]
        if items:
            return items[:3]
    return [fallback_title]


_FEW_SHOT_USER = (
    "Title: James Webb Telescope Spots Unexpectedly Massive Galaxy From Cosmic Dawn\n\n"
    "Article Body:\n"
    "Astronomers analyzing deep-field infrared observations from NASA's James Webb Space Telescope (JWST) "
    "have identified a remarkably luminous galaxy, designated JADES-GS-z14-0, that formed roughly 300 million "
    "years after the Big Bang. Measured at a spectroscopic redshift above 14, the galaxy appears several times "
    "more massive and brighter than standard Lambda-CDM cosmological simulations predicted for that early era. "
    "Researchers used JWST's NIRCam and NIRSpec instruments to confirm its distance and rule out foreground dust distortion. "
    "Cosmologists say existing models assumed early star formation proceeded gradually inside smaller dark-matter halos, "
    "meaning either primordial stars burned far more efficiently or supermassive black holes accelerated early galaxy assembly. "
    "Follow-up observing cycles with ALMA and Webb will examine its chemical enrichment and oxygen signatures over the coming year."
)

_FEW_SHOT_ASSISTANT = json.dumps({
    "takeaways": [
        "NASA's James Webb Space Telescope confirmed galaxy JADES-GS-z14-0 formed roughly 300 million years after the Big Bang at redshift above 14.",
        "NIRCam and NIRSpec readings show it is several times brighter and more massive than standard Lambda-CDM models predict.",
        "Upcoming ALMA and Webb observations will test whether efficient primordial star formation or early black holes drove its rapid growth.",
    ],
    "summary": (
        "Astronomers analyzing deep-field infrared data from NASA's James Webb Space Telescope have confirmed the "
        "existence of JADES-GS-z14-0, an unusually luminous galaxy observed just 300 million years after the Big Bang. "
        "Using both the NIRCam imager and the NIRSpec spectrograph to rule out dust distortion, the team verified a "
        "spectroscopic redshift above 14 and found stellar mass and brightness levels several times higher than expected.\n\n"
        "The discovery places direct pressure on prevailing Lambda-CDM simulations of cosmic dawn, which generally "
        "assumed early galaxies assembled slowly inside modest dark-matter halos before lighting up the universe. "
        "Scientists now face two competing explanations: either zero-metallicity primordial stars converted gas into "
        "light far more efficiently than modern stars, or active supermassive black holes injected unexpected energy "
        "into galactic cores much earlier than modeled.\n\n"
        "Over the coming year, coordinated follow-up campaigns using Webb and the Atacama Large Millimeter Array will "
        "measure heavy-element traces such as oxygen inside the galaxy. Confirming whether mature stellar populations "
        "already existed at that epoch could prompt a broad recalibration of early-universe astrophysics."
    ),
    "audio_script": (
        "In space news today, NASA's James Webb Telescope has confirmed a surprisingly massive galaxy born just "
        "three hundred million years after the Big Bang. Scientists say its unexpected brightness challenges leading "
        "theories of how quickly the first galaxies formed, and upcoming observations will search its light for early "
        "chemical signatures."
    ),
})


class QwenSynthesizer:
    def __init__(self, model_id: str = DEFAULT_MODEL_PATH):
        self.model_id = str(model_id)
        self.llm = None

    def _ensure_loaded(self):
        if self.llm is None:
            profile = get_device_profile()
            n_gpu_layers = -1 if profile.device == "cuda" else 0
            logger.info(f"[*] Loading local LLM ({self.model_id}) on {profile.summary()}...")
            self.llm = Llama(
                model_path=self.model_id,
                n_gpu_layers=n_gpu_layers,
                n_ctx=4096,
                n_batch=512,
                verbose=False
            )
            logger.info(f"[+] Qwen model loaded successfully on {profile.device_name}!")

    def synthesize(self, title: str, content: str) -> EditorialDigest:
        self._ensure_loaded()
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a senior news editor and broadcast anchor writer. Given an article, output strictly valid JSON "
                    "with keys 'summary', 'takeaways', and 'audio_script'.\n"
                    "- 'summary': A comprehensive, analytical 2-to-3 paragraph briefing (~220 to 300 words total, paragraphs "
                    "separated by \\n\\n). Paragraph 1 covers core facts, figures, and entities; Paragraph 2 explains broader "
                    "industry, economic, or technical context; Paragraph 3 highlights implications or what to watch next. "
                    "Avoid filler phrases like 'In conclusion' or 'This article discusses'.\n"
                    "- 'takeaways': A JSON list of exactly 3 concise, high-signal factual sentences.\n"
                    "- 'audio_script': A 3-to-4 sentence conversational radio broadcast script (~55 to 75 words) written for "
                    "spoken text-to-speech: smooth opening hook, spelled-out numbers/currencies/percentages where natural, "
                    "and zero markdown, URLs, brackets, or abbreviations."
                ),
            },
            {"role": "user", "content": _FEW_SHOT_USER},
            {"role": "assistant", "content": _FEW_SHOT_ASSISTANT},
            {
                "role": "user",
                "content": f"Title: {title}\n\nArticle Body:\n{content[:4000]}",
            },
        ]
        response = self.llm.create_chat_completion(
            messages=messages,
            max_tokens=1100,
            temperature=0.35,
            stop=["<|im_end|>", "</s>"],
        )
        response_text = response["choices"][0]["message"]["content"].strip()
        # Strip optional markdown code fences if emitted around JSON
        response_text = re.sub(r'^```(?:json)?\s*|\s*```$', '', response_text, flags=re.IGNORECASE).strip()

        try:
            json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
                audio_script = _ensure_complete_sentence(str(data.get("audio_script", "")))
                summary = _normalize_summary(data.get("summary"))
                takeaways = _coerce_takeaways(data.get("takeaways"), title)

                return EditorialDigest(
                    takeaways=takeaways,
                    audio_script=audio_script or clean_fallback_script(title, content),
                    summary=summary or (content[:600].strip() + "..." if content else ""),
                )
        except Exception as e:
            logger.warning(f"[-] Failed to parse LLM JSON: {e}. Using clean fallback.")

        return EditorialDigest(
            takeaways=[title],
            audio_script=clean_fallback_script(title, content),
            summary=content[:600].strip() + "..." if content else "",
        )

_synthesizer: Optional[QwenSynthesizer] = None

def get_synthesizer() -> QwenSynthesizer:
    global _synthesizer
    if _synthesizer is None:
        _synthesizer = QwenSynthesizer()
    return _synthesizer
