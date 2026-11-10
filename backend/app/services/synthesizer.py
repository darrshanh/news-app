import json
import re
import logging
from typing import Optional
from pydantic import BaseModel
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from backend.app.core.device import get_device_profile

logger = logging.getLogger(__name__)

class EditorialDigest(BaseModel):
    takeaways: list[str]
    audio_script: str

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

class QwenSynthesizer:
    def __init__(self, model_id: str = "Qwen/Qwen2.5-0.5B-Instruct"):
        self.model_id = model_id
        self.model = None
        self.tokenizer = None

    def _ensure_loaded(self):
        if self.model is None:
            profile = get_device_profile()
            logger.info(f"[*] Loading local LLM ({self.model_id}) on {profile.summary()}...")
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_id, local_files_only=True)
            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_id,
                torch_dtype=profile.torch_dtype,
                device_map=profile.device_map,
                local_files_only=True
            )
            logger.info(f"[+] Qwen model loaded successfully on {self.model.device}!")

    def synthesize(self, title: str, content: str) -> EditorialDigest:
        self._ensure_loaded()
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a news editor. Summarize the article into 2 to 3 concise key takeaways and a punchy 2-sentence conversational voice script. "
                    "Always finish complete sentences. Output strictly valid JSON with keys 'takeaways' and 'audio_script'."
                )
            },
            {
                "role": "user",
                "content": (
                    "Title: James Webb Discovers Ancient Galaxy\n\n"
                    "Article Body:\n"
                    "Astronomers using the James Webb Space Telescope have spotted a galaxy that formed just 300 million years after the Big Bang. "
                    "It is surprisingly bright and massive, challenging current models of early cosmic evolution."
                )
            },
            {
                "role": "assistant",
                "content": (
                    '{"takeaways": ["JWST spotted a galaxy formed 300 million years after the Big Bang", '
                    '"The galaxy is surprisingly bright and massive", '
                    '"Findings challenge current cosmic evolution models"], '
                    '"audio_script": "In space news today, NASA\'s James Webb Telescope has spotted one of the earliest galaxies ever seen. Astronomers say its incredible brightness is forcing scientists to rethink how the early universe evolved."}'
                )
            },
            {
                "role": "user",
                "content": f"Title: {title}\n\nArticle Body:\n{content[:2500]}"
            }
        ]
        prompt_text = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        model_inputs = self.tokenizer([prompt_text], return_tensors="pt").to(self.model.device)
        generated_ids = self.model.generate(
            **model_inputs,
            max_new_tokens=256,
            temperature=0.3,
            do_sample=True
        )
        generated_ids = [
            out_ids[len(in_ids):] for in_ids, out_ids in zip(model_inputs.input_ids, generated_ids)
        ]
        response_text = self.tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0].strip()
        
        try:
            json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group(0))
                audio_script = data.get("audio_script", "").strip()
                # Ensure the script ends on a complete sentence punctuation
                if audio_script and not re.search(r'[.!?]["\']?$', audio_script):
                    # Strip dangling words and append period
                    last_period = max(audio_script.rfind('.'), audio_script.rfind('!'), audio_script.rfind('?'))
                    if last_period > 20:
                        audio_script = audio_script[:last_period + 1]
                    else:
                        audio_script += "."

                return EditorialDigest(
                    takeaways=data.get("takeaways", [title]),
                    audio_script=audio_script or clean_fallback_script(title, content)
                )
        except Exception as e:
            logger.warning(f"[-] Failed to parse LLM JSON: {e}. Using clean fallback.")

        return EditorialDigest(
            takeaways=[title],
            audio_script=clean_fallback_script(title, content)
        )

_synthesizer: Optional[QwenSynthesizer] = None

def get_synthesizer() -> QwenSynthesizer:
    global _synthesizer
    if _synthesizer is None:
        _synthesizer = QwenSynthesizer()
    return _synthesizer
