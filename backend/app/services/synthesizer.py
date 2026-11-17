import json
import re
import logging
from typing import Optional
from pydantic import BaseModel
# import torch
# from transformers import AutoModelForCausalLM, AutoTokenizer
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
                    "You are a news editor. Summarize the article into 2 to 3 concise key takeaways and a punchy 2-sentence conversational voice script, and generate a comprehensive, multi-paragraph analytical summary."
                    "Always finish complete sentences. Output strictly valid JSON with keys 'takeaways', 'summary' and 'audio_script'."
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
                    '"audio_script": "In space news today, NASA\'s James Webb Telescope has spotted one of the earliest galaxies ever seen. Astronomers say its incredible brightness is forcing scientists to rethink how the early universe evolved.", '
                    '"summary": "Astronomers operating the James Webb Space Telescope have identified an unexpectedly bright and mature galaxy originating a mere 300 million years after the Big Bang. This observation challenges prevailing theories of early cosmological structure formation, suggesting that primordial star clustering accelerated much faster than previous models predicted."}'
                )
            },
            {
                "role": "user",
                "content": f"Title: {title}\n\nArticle Body:\n{content[:2500]}"
            }
        ]
        # prompt_text = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        # model_inputs = self.tokenizer([prompt_text], return_tensors="pt").to(self.model.device)
        # generated_ids = self.model.generate(
        #     **model_inputs,
        #     max_new_tokens=256,
        #     temperature=0.3,
        #     do_sample=True
        # )
        # generated_ids = [
        #     out_ids[len(in_ids):] for in_ids, out_ids in zip(model_inputs.input_ids, generated_ids)
        # ]
        # response_text = self.tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0].strip()
        response = self.llm.create_chat_completion(
            messages=messages,
            max_tokens=800,
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        response_text = response["choices"][0]["message"]["content"]
        
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
                    audio_script=audio_script or clean_fallback_script(title, content),
                    summary=data.get("summary", "")
                )
        except Exception as e:
            logger.warning(f"[-] Failed to parse LLM JSON: {e}. Using clean fallback.")

        return EditorialDigest(
            takeaways=[title],
            audio_script=clean_fallback_script(title, content),
            summary=content[:500] + "..." if content else ""
        )

_synthesizer: Optional[QwenSynthesizer] = None

def get_synthesizer() -> QwenSynthesizer:
    global _synthesizer
    if _synthesizer is None:
        _synthesizer = QwenSynthesizer()
    return _synthesizer
