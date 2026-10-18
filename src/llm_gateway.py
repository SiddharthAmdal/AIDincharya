"""
Shared LLM Gateway for AI Dincharya.
Centralizes provider client management, model failovers, structured output parsing,
native tool-calling loops, and bounded retries.
"""

import os
import json
import logging
import re
import time
from typing import Dict, Any, List, Optional, Callable, Tuple
from dataclasses import dataclass, field
from openai import OpenAI, APITimeoutError, APIConnectionError, RateLimitError, InternalServerError

from src.config import (
    PUTER_BASE_URL, PUTER_API_KEY,
    NVIDIA_BASE_URL, NVIDIA_API_KEY,
    GEMINI_BASE_URL, GEMINI_API_KEY,
    LLM_PROVIDER, DEFAULT_MODEL, FALLBACK_MODEL,
    THIRD_FALLBACK_MODEL, get_valid_gemini_keys
)

logger = logging.getLogger("LLMGateway")


@dataclass
class LLMResponse:
    content: str
    reasoning_content: Optional[str] = None
    tool_calls: Optional[List[Any]] = None
    model_used: str = ""
    is_fallback: bool = False
    tokens_in: int = 0
    tokens_out: int = 0
    latency_s: float = 0.0


class LLMGateway:
    """
    Unified, reliable adapter for LLM calls across AI Dincharya workflows (Planner, Chat, Insights).
    Supports a 3-tier model/provider failover chain:
      1. Primary Model (e.g. nvidia/nemotron-3.5-lightning-30b-a3b on NVIDIA NIM)
      2. Secondary Fallback Model (e.g. openai/gpt-oss-20b on NVIDIA NIM)
      3. Third Fallback Provider (e.g. gemini-3.5-flash-lite on Google AI Studio Gemini API)
    """

    _instance: Optional["LLMGateway"] = None

    def __init__(self):
        self.llm_timeout = float(os.getenv("LLM_TIMEOUT", "22.0"))
        self._gemini_key_idx = 0

        if LLM_PROVIDER == "nvidia":
            self.client = OpenAI(
                base_url=NVIDIA_BASE_URL,
                api_key=NVIDIA_API_KEY,
                timeout=self.llm_timeout,
                max_retries=0  # Prevents invisible 3x retry multiplication inside OpenAI SDK
            )
        elif LLM_PROVIDER == "gemini":
            valid_keys = get_valid_gemini_keys()
            initial_key = valid_keys[0] if valid_keys else (GEMINI_API_KEY or "missing_gemini_key")
            self.client = OpenAI(
                base_url=GEMINI_BASE_URL,
                api_key=initial_key,
                timeout=self.llm_timeout,
                max_retries=0
            )
        else:
            self.client = OpenAI(
                base_url=PUTER_BASE_URL,
                api_key=PUTER_API_KEY,
                timeout=self.llm_timeout,
                max_retries=0
            )
        self.primary_model = DEFAULT_MODEL
        self.fallback_model = FALLBACK_MODEL
        self.third_fallback_model = THIRD_FALLBACK_MODEL
        self.gemini_client: Optional[OpenAI] = self._build_gemini_client()

    def _build_gemini_client(self) -> Optional[OpenAI]:
        """Builds an OpenAI-compatible client for Google AI Studio Gemini API if a key is available."""
        valid_keys = get_valid_gemini_keys()
        if not valid_keys:
            return None
        key = valid_keys[self._gemini_key_idx % len(valid_keys)]
        self._gemini_key_idx += 1
        return OpenAI(
            base_url=os.getenv("GEMINI_BASE_URL", GEMINI_BASE_URL),
            api_key=key,
            timeout=self.llm_timeout,
            max_retries=0
        )

    def _is_gemini_model(self, model_name: str) -> bool:
        """Returns True if the target model should be routed to Google AI Studio's Gemini API."""
        if not model_name:
            return False
        m = model_name.lower()
        return m.startswith("gemini-") or m == self.third_fallback_model.lower()

    def _get_client_for_model(self, target_model: str) -> OpenAI:
        """Selects the appropriate provider OpenAI client for the given target model."""
        if self._is_gemini_model(target_model) and LLM_PROVIDER != "gemini":
            client = self._build_gemini_client() or self.gemini_client
            if client is not None:
                self.gemini_client = client
                return client
        return self.client

    @classmethod
    def get_instance(cls) -> "LLMGateway":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _is_retryable(self, exc: Exception) -> bool:
        if isinstance(exc, (APITimeoutError, APIConnectionError, RateLimitError, InternalServerError)):
            return True
        msg = str(exc).lower()
        return any(term in msg for term in ("timeout", "rate limit", "too many requests", "quota", "503", "502", "500", "429", "connection"))

    def create_chat_completion(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: float = 0.1,
        response_format: Optional[Dict[str, str]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Any] = None,
        retries_per_model: int = 2
    ) -> LLMResponse:
        """
        Executes a chat completion with automatic 3-tier model/provider fallback and bounded retries.
        """
        models_to_try = [model or self.primary_model]
        if self.fallback_model and self.fallback_model not in models_to_try:
            models_to_try.append(self.fallback_model)
        if (
            self.third_fallback_model
            and self.third_fallback_model not in models_to_try
            and (get_valid_gemini_keys() or self.gemini_client is not None)
        ):
            models_to_try.append(self.third_fallback_model)

        last_error = None

        for idx, target_model in enumerate(models_to_try):
            is_fallback = (idx > 0) or (target_model in (self.fallback_model, self.third_fallback_model))
            for attempt in range(1, retries_per_model + 1):
                start_time = time.perf_counter()
                try:
                    active_client = self._get_client_for_model(target_model)
                    kwargs: Dict[str, Any] = {
                        "model": target_model,
                        "messages": messages,
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                    }
                    if response_format:
                        kwargs["response_format"] = response_format
                    if tools:
                        kwargs["tools"] = tools
                        if tool_choice:
                            kwargs["tool_choice"] = tool_choice
                        elif target_model.startswith("nvidia"):
                            # For Nemotron, allow model to decide or default to auto
                            kwargs["tool_choice"] = "auto"
                        else:
                            kwargs["tool_choice"] = "auto"

                    call_timeout = float(os.getenv("FALLBACK_LLM_TIMEOUT", "30.0")) if is_fallback else float(os.getenv("PRIMARY_LLM_TIMEOUT", "14.0"))
                    kwargs["timeout"] = call_timeout
                    resp = active_client.chat.completions.create(**kwargs)
                    elapsed = time.perf_counter() - start_time
                    choice = resp.choices[0]
                    msg = choice.message

                    tokens_in = resp.usage.prompt_tokens if resp.usage else 0
                    tokens_out = resp.usage.completion_tokens if resp.usage else 0

                    content = msg.content or ""
                    reasoning = getattr(msg, "reasoning_content", None)
                    # If model returned pure reasoning and no tool call, use reasoning text as response content
                    if not content and reasoning and not msg.tool_calls:
                        content = reasoning.strip()

                    self.last_model_used = target_model
                    return LLMResponse(
                        content=content,
                        reasoning_content=reasoning,
                        tool_calls=msg.tool_calls,
                        model_used=target_model,
                        is_fallback=is_fallback,
                        tokens_in=tokens_in,
                        tokens_out=tokens_out,
                        latency_s=round(elapsed, 3)
                    )

                except Exception as exc:
                    elapsed = time.perf_counter() - start_time
                    last_error = exc
                    logger.warning(
                        f"LLM request failed on model '{target_model}' (attempt {attempt}/{retries_per_model}) in {elapsed:.2f}s: {exc}"
                    )
                    # If current model timed out and a fallback model exists, fail over immediately
                    if (isinstance(exc, APITimeoutError) or "timeout" in str(exc).lower()) and (idx + 1 < len(models_to_try)):
                        logger.info(f"Model '{target_model}' timed out in {elapsed:.2f}s. Immediately failing over to '{models_to_try[idx+1]}'.")
                        break

                    if not self._is_retryable(exc) and "404" not in str(exc) and "410" not in str(exc):
                        break
                    if attempt < retries_per_model:
                        time.sleep(0.5 * attempt)

        raise RuntimeError(f"All LLM models and retries exhausted. Last error: {last_error}")

    def generate_structured_json(
        self,
        messages: List[Dict[str, Any]],
        max_tokens: int = 4096,
        temperature: float = 0.1,
        fallback_fn: Optional[Callable[[], Dict[str, Any]]] = None
    ) -> Tuple[Dict[str, Any], bool]:
        """
        Generates structured JSON data with robust markdown fence removal and fallback handling.
        Returns: (parsed_json_dict, is_fallback_boolean)
        """
        # Ensure system prompt contains the JSON and concise reasoning guidance
        enhanced_messages = list(messages)
        if not any("json" in m.get("content", "").lower() for m in enhanced_messages if m.get("role") == "system"):
            enhanced_messages.insert(0, {
                "role": "system",
                "content": "You are a precise data structuring agent. Output strict, valid JSON only. Keep internal reasoning concise."
            })

        try:
            res = self.create_chat_completion(
                messages=enhanced_messages,
                max_tokens=max_tokens,
                temperature=temperature,
                response_format={"type": "json_object"}
            )
            raw = res.content.strip()
            clean_json = raw

            # Try extracting from markdown blocks first
            if "```" in clean_json:
                match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", clean_json, flags=re.IGNORECASE)
                if match:
                    clean_json = match.group(1).strip()
            
            # If not cleanly enclosed in braces, search for outermost JSON object
            if not (clean_json.startswith("{") and clean_json.endswith("}")):
                match = re.search(r"(\{[\s\S]*\})", clean_json)
                if match:
                    clean_json = match.group(1).strip()

            # If content was empty or unparseable, check reasoning_content as secondary source
            if not clean_json and res.reasoning_content:
                match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", res.reasoning_content, flags=re.IGNORECASE)
                if match:
                    clean_json = match.group(1).strip()
                else:
                    match = re.search(r"(\{[\s\S]*\})", res.reasoning_content)
                    if match:
                        clean_json = match.group(1).strip()

            data = json.loads(clean_json)
            return data, res.is_fallback

        except Exception as exc:
            logger.error(f"Failed to generate structured JSON: {exc}")
            if fallback_fn:
                logger.info("Executing provided deterministic fallback function.")
                return fallback_fn(), True
            raise

    def execute_tool_loop(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        tool_executor_fn: Callable[[str, Dict[str, Any]], str],
        max_steps: int = 3
    ) -> LLMResponse:
        """
        Executes a multi-step native tool calling loop until the model returns a final text response.
        """
        history = list(messages)
        active_model = self.primary_model

        for step in range(max_steps):
            res = self.create_chat_completion(
                messages=history,
                model=active_model,
                tools=tools,
                max_tokens=4096,
                temperature=0.1,
                retries_per_model=1
            )
            # If fallback model answered successfully, pin it for the remainder of this multi-step loop
            if res.is_fallback and res.model_used:
                active_model = res.model_used

            # If no tool calls were requested, return final response
            if not res.tool_calls:
                return res

            # Tool call requested: record assistant turn with tool calls
            first_tool = res.tool_calls[0]
            assistant_turn = {
                "role": "assistant",
                "content": res.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in res.tool_calls
                ]
            }
            history.append(assistant_turn)

            # Execute all requested tool calls
            for tc in res.tool_calls:
                fn_name = tc.function.name
                fn_args = {}
                try:
                    fn_args = json.loads(tc.function.arguments)
                except Exception:
                    fn_args = {"raw_arguments": tc.function.arguments}

                logger.info(f"Dispatching tool '{fn_name}' with args {fn_args}")
                try:
                    tool_output_str = tool_executor_fn(fn_name, fn_args)
                except Exception as t_err:
                    logger.error(f"Tool '{fn_name}' execution threw exception: {t_err}")
                    tool_output_str = json.dumps({"error": f"Tool execution failed: {str(t_err)}"})

                history.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": tool_output_str
                })

        # If max steps exceeded without termination, execute one final non-tool turn
        return self.create_chat_completion(messages=history, max_tokens=1500)
