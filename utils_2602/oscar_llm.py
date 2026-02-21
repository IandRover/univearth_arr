"""
OSCAR-aware ChatLLM for Earth Observation.

Supports two backend modes:
  1. API mode: Calls external LLM APIs (Gemini, OpenAI, Anthropic, etc.)
  2. DevMate mode: Uses file-based exchange to let DevMate (VS Code AI) act as the LLM.

Each OSCAR state has its own system/user prompt pair loaded from prompts_2602/.
"""

import os
import re
from copy import deepcopy
from typing import Dict, List, Optional

from utils_2602.devmate_backend import DevMateBackend


class OscarLLM:
    """LLM interface for OSCAR state machine.

    When llm="devmate", uses file-based exchange instead of API calls.
    Otherwise, calls external APIs (same providers as utils_2511/chatllm_bl.py).
    """

    VALID_MODELS = [
        # DevMate (file-based)
        "devmate",
        # Anthropic
        "claude-haiku-4-5-20251001", "claude-sonnet-4-5-20250929",
        # OpenAI
        "gpt-5", "gpt-4o", "gpt-4o-mini", "o3-mini", "o5-mini",
        # HuggingFace
        "Llama-3.1-8B-Instruct", "Llama-3.3-70B-Instruct",
        "Llama-3.2-3B-Instruct", "Llama-3.2-1B-Instruct",
        "Qwen2.5-Coder-32B-Instruct",
        # DeepSeek
        "deepseek-chat", "deepseek-reasoner",
        # Gemini
        "gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite",
        "gemini-2.0-flash", "gemini-3-pro-preview",
        # Kimi
        "kimi-k2-0905-preview",
    ]

    def __init__(self, args, llm: str):
        self.llm_name = llm
        self.language = args.language
        self.prompt_dir = "./prompts_2602"
        self.is_devmate = (llm == "devmate")

        # DevMate backend (file-based exchange)
        if self.is_devmate:
            self.devmate = DevMateBackend(
                exchange_dir=getattr(args, "exchange_dir", "./oscar_exchange")
            )
        else:
            self.devmate = None

        # Load all OSCAR prompts
        self._prompts = {}
        prompt_files = {
            "init_observe_system": "OSCAR_INIT_OBSERVE_SYSTEM.txt",
            "init_observe_user": "OSCAR_INIT_OBSERVE_USER.txt",
            "plan_system": "OSCAR_PLAN_SYSTEM.txt",
            "plan_user": "OSCAR_PLAN_USER.txt",
            "execute_system": "OSCAR_EXECUTE_SYSTEM.txt",
            "execute_user": "OSCAR_EXECUTE_USER.txt",
            "replan_system": "OSCAR_REPLAN_SYSTEM.txt",
            "replan_user": "OSCAR_REPLAN_USER.txt",
            "answer_system": "OSCAR_ANS_SYSTEM.txt",
            "answer_user": "OSCAR_ANS_USER.txt",
            "verify_system": "OSCAR_VERIFY_SYSTEM.txt",
            "verify_user": "OSCAR_VERIFY_USER.txt",
        }
        for key, filename in prompt_files.items():
            filepath = os.path.join(self.prompt_dir, filename)
            with open(filepath, "r") as f:
                self._prompts[key] = f.read()

        # Documentation support
        self.documentation = getattr(args, "documentation", "no")
        if self.documentation == "specific":
            self.spec_for_landsat = open("./prompts_2511/document_spec/landsat.txt").read()
            self.spec_for_modis = open("./prompts_2511/document_spec/modis.txt").read()
            self.spec_for_viirs = open("./prompts_2511/document_spec/viirs.txt").read()

        self.client = None
        self.model = None
        self.request_type = None

    def start_session(self, unique_id: str):
        """Start a new DevMate exchange session. Call before each question."""
        if self.devmate:
            self.devmate.start_session(unique_id)

    # ------------------------------------------------------------------ #
    #  API client setup (only used for non-DevMate backends)              #
    # ------------------------------------------------------------------ #

    def _get_client(self, model_name: str):
        """Initialize the API client for the given model."""
        if self.is_devmate:
            return  # No client needed

        # HuggingFace models
        hf_models = {
            "Qwen2.5-Coder-32B-Instruct": "Qwen/Qwen2.5-Coder-32B-Instruct",
            "Llama-3.3-70B-Instruct": "meta-llama/Llama-3.3-70B-Instruct",
            "Llama-3.2-3B-Instruct": "meta-llama/Llama-3.2-3B-Instruct",
            "Llama-3.2-1B-Instruct": "meta-llama/Llama-3.2-1B-Instruct",
            "Llama-3.1-8B-Instruct": "meta-llama/Llama-3.1-8B-Instruct",
        }
        if model_name in hf_models:
            self.model = hf_models[model_name]
            self.request_type = "huggingface"
            from huggingface_hub import InferenceClient
            self.client = InferenceClient(
                provider="hf-inference",
                api_key=os.environ.get("HUGGINGFACE_API_KEY"),
            )
            return

        # DeepSeek
        from openai import OpenAI
        ds_models = {"deepseek-chat": "deepseek-chat", "deepseek-reasoner": "deepseek-reasoner"}
        if model_name in ds_models:
            self.model = ds_models[model_name]
            self.request_type = "openai-deepseek"
            self.client = OpenAI(
                api_key=os.environ.get("DEEPSEEK_API_KEY"),
                base_url="https://api.deepseek.com",
            )
            return

        # OpenAI
        oai_models = {
            "gpt-4o-mini": "gpt-4o-mini", "gpt-4o": "gpt-4o",
            "o3-mini": "o3-mini", "o5-mini": "gpt-5-mini", "gpt-5": "gpt-5",
        }
        if model_name in oai_models:
            self.model = oai_models[model_name]
            self.request_type = "openai"
            self.client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
            return

        # Anthropic
        import anthropic
        anth_models = {
            "claude-haiku-4-5-20251001": "claude-haiku-4-5-20251001",
            "claude-sonnet-4-5-20250929": "claude-sonnet-4-5-20250929",
        }
        if model_name in anth_models:
            self.model = anth_models[model_name]
            self.request_type = "anthropic"
            self.client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
            return

        # Gemini
        from google import genai
        from google.genai import types
        gemini_models = {
            "gemini-2.0-flash": "gemini-2.0-flash",
            "gemini-2.5-pro": "gemini-2.5-pro",
            "gemini-2.5-flash": "gemini-2.5-flash",
            "gemini-2.5-flash-lite": "gemini-2.5-flash-lite",
            "gemini-3-pro-preview": "gemini-3-pro-preview",
        }
        if model_name in gemini_models:
            self.model = gemini_models[model_name]
            self.request_type = "gemini"
            self.client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
            return

        # Kimi
        if model_name == "kimi-k2-0905-preview":
            self.model = "kimi-k2-0905-preview"
            self.request_type = "kimi"
            self.client = OpenAI(
                api_key=os.environ.get("KIMI_API_KEY"),
                base_url="https://api.moonshot.ai/v1",
            )
            return

        raise ValueError(f"Unsupported model: {model_name}")

    # ------------------------------------------------------------------ #
    #  Unified call dispatcher                                             #
    # ------------------------------------------------------------------ #

    def _make_api_call(self, system_prompt: str, user_prompt: str,
                       state_name: str = "unknown") -> str:
        """
        Unified call dispatcher.

        - DevMate mode: writes prompt to file, waits for response file.
        - API mode: calls the appropriate provider's API.
        """
        if self.is_devmate:
            return self.devmate.call(system_prompt, user_prompt, state_name)

        # API mode
        self._get_client(self.llm_name)

        if self.request_type == "openai":
            from openai import OpenAI
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            response = self.client.chat.completions.create(
                model=self.model, messages=messages,
            )
            return response.choices[0].message.content

        elif self.request_type == "openai-deepseek":
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            response = self.client.chat.completions.create(
                model=self.model, messages=messages, stream=False,
            )
            return response.choices[0].message.content

        elif self.request_type == "huggingface":
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            response = self.client.chat.completions.create(
                model=self.model, messages=messages, max_tokens=4096,
            )
            return response.choices[0].message.content

        elif self.request_type == "anthropic":
            messages = [{"role": "user", "content": user_prompt}]
            response = self.client.messages.create(
                system=[{
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }],
                model=self.model,
                messages=messages,
                max_tokens=4096,
            )
            return response.content[0].text

        elif self.request_type == "gemini":
            from google.genai import types
            if self.model.startswith("gemini-2.5"):
                thinking_config = types.ThinkingConfig(thinking_budget=1024)
            elif self.model.startswith("gemini-3"):
                thinking_config = types.ThinkingConfig(thinking_level="low")
            else:
                thinking_config = None

            config_kwargs = {"system_instruction": system_prompt}
            if thinking_config:
                config_kwargs["thinking_config"] = thinking_config

            response = self.client.models.generate_content(
                model=self.model,
                config=types.GenerateContentConfig(**config_kwargs),
                contents=user_prompt,
            )
            return response.text

        elif self.request_type == "kimi":
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            response = self.client.chat.completions.create(
                model=self.model, messages=messages, temperature=1.0,
            )
            return response.choices[0].message.content

        raise ValueError(f"Unsupported request type: {self.request_type}")

    # ------------------------------------------------------------------ #
    #  Parsing helpers                                                     #
    # ------------------------------------------------------------------ #

    def _parse_tag(self, content: str, tag: str) -> Optional[str]:
        """Extract content between <tag>...</tag>."""
        pattern = f"<{tag}>(.*?)</{tag}>"
        match = re.search(pattern, content, re.DOTALL)
        return match.group(1).strip() if match else None

    def _parse_code(self, content: str) -> Optional[str]:
        """Extract code block from LLM response."""
        code_patterns = [
            r"<code>```python\s*(.*?)\s*```</code>",
            r"<Code>```python\s*(.*?)\s*```</Code>",
            r"```python\s*(.*?)\s*```",
            r"<code>```\s*(.*?)\s*```</code>",
            r"<Code>```\s*(.*?)\s*```</Code>",
            r"```\s*(.*?)\s*```",
            r"<code>(.*?)</code>",
            r"<Code>(.*?)</Code>",
        ]
        candidate = None
        for pattern in code_patterns:
            match = re.search(pattern, content, re.DOTALL)
            if match:
                text = match.group(1).strip()
                if candidate is None:
                    candidate = text
                elif text.startswith("import") and not text.endswith("```"):
                    if len(text) > len(candidate):
                        candidate = text
        return candidate

    def _parse_answer(self, content: str) -> Optional[str]:
        """Extract answer tag from response."""
        ans = self._parse_tag(content, "answer")
        if ans:
            return ans.strip()
        ans = self._parse_tag(content, "final_answer")
        if ans:
            return ans.strip()
        options = ["A", "B", "C1", "C2", "C3", "D"]
        found = [opt for opt in options if opt in content]
        return found[0] if len(found) == 1 else None

    # ------------------------------------------------------------------ #
    #  OSCAR State API Methods                                             #
    # ------------------------------------------------------------------ #

    def init_observe(self, info: dict) -> dict:
        """[Init → Observe] Capture initial environment state."""
        system = self._prompts["init_observe_system"]
        user = self._prompts["init_observe_user"].format_map(info)
        try:
            raw = self._make_api_call(system, user, state_name="init_observe")
            observation = self._parse_tag(raw, "observation")
            return {"raw_observation": raw, "observation": observation or raw}
        except Exception as e:
            return {"raw_observation": str(e), "observation": f"Observation failed: {e}"}

    def plan(self, info: dict) -> dict:
        """[Observe → Plan] Generate structured action plan."""
        system = self._prompts["plan_system"]
        user = self._prompts["plan_user"].format_map(info)
        try:
            raw = self._make_api_call(system, user, state_name="plan")
            plan = self._parse_tag(raw, "plan")
            return {"raw_plan": raw, "plan": plan or raw}
        except Exception as e:
            return {"raw_plan": str(e), "plan": f"Planning failed: {e}"}

    def execute(self, info: dict) -> dict:
        """[Plan → Execute] Generate executable Python code from plan."""
        system = self._prompts["execute_system"]
        user = self._prompts["execute_user"].format_map(info)
        try:
            raw = self._make_api_call(system, user, state_name="execute")
            code = self._parse_code(raw)
            if not code:
                return {"raw_code": raw, "code": None}
            return {"raw_code": raw, "code": code}
        except Exception as e:
            if "overloaded" in str(e).lower():
                return {}
            return {"raw_code": str(e), "code": None}

    def replan(self, info: dict) -> dict:
        """[Execute → Observe → Re-Plan] Targeted fix for failed execution."""
        system = self._prompts["replan_system"]
        user = self._prompts["replan_user"].format_map(info)
        try:
            raw = self._make_api_call(system, user, state_name="replan")
            code = self._parse_code(raw)
            diagnosis = self._parse_tag(raw, "diagnosis")
            return {
                "raw_code": raw,
                "code": code,
                "diagnosis": diagnosis or "No diagnosis parsed.",
            }
        except Exception as e:
            if "overloaded" in str(e).lower():
                return {}
            return {"raw_code": str(e), "code": None, "diagnosis": str(e)}

    def generate_answer(self, info: dict) -> dict:
        """[Observe → Answer] Classify execution output into A/B/C1/C2/C3/D."""
        system = self._prompts["answer_system"]
        if "at module$" in (info.get("exec_msg") or ""):
            info["exec_msg"] = info["exec_msg"].split("at module$")[0]
        user = self._prompts["answer_user"].format_map(info)
        try:
            raw = self._make_api_call(system, user, state_name="answer")
            answer = self._parse_answer(raw)
            thinking = self._parse_tag(raw, "thinking")
            return {"raw_answer": raw, "answer": answer, "answer_thinking": thinking}
        except Exception as e:
            return {"raw_answer": str(e), "answer": "D", "answer_thinking": str(e)}

    def verify(self, info: dict) -> dict:
        """[Verify → Done] Final verification with LLM self-consistency check."""
        system = self._prompts["verify_system"]
        user = self._prompts["verify_user"].format_map(info)
        try:
            raw = self._make_api_call(system, user, state_name="verify")
            verification = self._parse_tag(raw, "verification")
            final_answer = self._parse_answer(raw)
            confidence = self._parse_tag(raw, "confidence")
            return {
                "raw_verification": raw,
                "verification": verification,
                "verified_answer": final_answer,
                "confidence": confidence,
            }
        except Exception as e:
            return {
                "raw_verification": str(e),
                "verification": None,
                "verified_answer": None,
                "confidence": "low",
            }
