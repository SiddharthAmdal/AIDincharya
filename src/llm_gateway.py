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
def sanitize_secret_log(text: str) -> str:
    """Sanitizes sensitive tokens, API keys, and credentials from log messages."""
    if not text:
        return ""
    cleaned = re.sub(r'nvapi-[a-zA-Z0-9_\-]{8,}', 'nvapi-***REDACTED***', str(text))
    cleaned = re.sub(r'AIza[a-zA-Z0-9_\-]{8,}', 'AIza***REDACTED***', cleaned)
    cleaned = re.sub(r'Bearer\s+[a-zA-Z0-9_\-\.]{10,}', 'Bearer ***REDACTED***', cleaned)
    cleaned = re.sub(r'(api_key|apikey|token|password)=["\']?[a-zA-Z0-9_\-\.]{6,}["\']?', r'\1=***REDACTED***', cleaned, flags=re.IGNORECASE)
    return cleaned


def categorize_failure(exc: Exception) -> str:
    """Categorizes provider failure into standard diagnostic codes."""
    msg = str(exc).lower()
    if isinstance(exc, APITimeoutError) or "timeout" in msg or "timed out" in msg:
        return "TIMEOUT"
    if any(term in msg for term in ("unauthorized", "401", "forbidden", "403", "invalid api key", "authentication")):
        return "AUTH_ERROR"
    if any(term in msg for term in ("not found", "404", "model_not_found", "unknown model")):
        return "MODEL_NOT_FOUND"
    if isinstance(exc, RateLimitError) or any(term in msg for term in ("429", "rate limit", "too many requests", "quota exceeded")):
        return "RATE_LIMIT"
    if isinstance(exc, InternalServerError) or any(term in msg for term in ("500", "502", "503", "504", "bad gateway", "service unavailable")):
        return "SERVER_ERROR"
    if isinstance(exc, APIConnectionError) or any(term in msg for term in ("connection refused", "connection error", "network unreachable")):
        return "CONNECTION_ERROR"
    if "json" in msg or "expecting value" in msg:
        return "PARSE_ERROR"
    return "PROVIDER_ERROR"


class LLMGateway:
    """
    Unified, reliable adapter for LLM calls across AI Dincharya workflows (Planner, Chat, Insights).
    Supports a 3-tier model/provider failover chain:
      1. Primary Model (e.g. nvidia/nemotron-3.5-lightning-30b-a3b on NVIDIA NIM)
      2. Secondary Fallback Model (e.g. openai/gpt-oss-20b on NVIDIA NIM)
      3. Third Fallback Provider (e.g. gemini-1.5-flash on Google AI Studio Gemini API)
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
        category = categorize_failure(exc)
        if category in ("AUTH_ERROR", "MODEL_NOT_FOUND"):
            return False
        if category in ("TIMEOUT", "RATE_LIMIT", "SERVER_ERROR", "CONNECTION_ERROR"):
            return True
        if isinstance(exc, (APITimeoutError, APIConnectionError, RateLimitError, InternalServerError)):
            return True
        msg = str(exc).lower()
        if any(term in msg for term in ("unauthorized", "401", "forbidden", "403", "not found", "404", "model_not_found", "invalid_argument", "410", "gone")):
            return False
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
        Executes a chat completion with automatic 3-tier model/provider fallback, bounded retries,
        and an end-to-end request budget preventing client-side timeouts.
        """
        import random
        models_to_try = [model or self.primary_model]
        if self.fallback_model and self.fallback_model not in models_to_try:
            models_to_try.append(self.fallback_model)
        if (
            self.third_fallback_model
            and self.third_fallback_model not in models_to_try
            and (get_valid_gemini_keys() or self.gemini_client is not None)
        ):
            models_to_try.append(self.third_fallback_model)

        total_deadline = time.perf_counter() + float(os.getenv("GATEWAY_TOTAL_TIMEOUT", "30.0"))
        last_error = None

        for idx, target_model in enumerate(models_to_try):
            remaining_total = total_deadline - time.perf_counter()
            if remaining_total <= 1.0:
                logger.warning(f"Gateway deadline budget exhausted before attempting model '{target_model}'.")
                break

            is_fallback = (idx > 0) or (target_model in (self.fallback_model, self.third_fallback_model))
            provider_tag = "Google AI Studio" if self._is_gemini_model(target_model) else ("NVIDIA NIM" if target_model.startswith("nvidia") else "Primary Provider")

            for attempt in range(1, retries_per_model + 1):
                remaining_attempt = total_deadline - time.perf_counter()
                if remaining_attempt <= 1.0:
                    logger.warning(f"Gateway deadline budget exhausted before attempt {attempt} on model '{target_model}'.")
                    break

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
                            kwargs["tool_choice"] = "auto"
                        else:
                            kwargs["tool_choice"] = "auto"

                    configured_timeout = float(os.getenv("FALLBACK_LLM_TIMEOUT", "18.0")) if is_fallback else float(os.getenv("PRIMARY_LLM_TIMEOUT", "14.0"))
                    kwargs["timeout"] = min(configured_timeout, max(0.5, remaining_attempt))
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
                    category = categorize_failure(exc)
                    safe_msg = sanitize_secret_log(str(exc))

                    logger.warning(
                        f"[NIM Diagnostic] Provider={provider_tag} Model={target_model} Category={category} "
                        f"Attempt={attempt}/{retries_per_model} Elapsed={elapsed:.2f}s Details={safe_msg}"
                    )

                    # Immediate failover for non-retryable errors (401, 403, 404, invalid model)
                    if not self._is_retryable(exc):
                        logger.info(f"Non-retryable {category} on model '{target_model}'. Failing over to next model.")
                        break

                    # Immediate failover on timeout if another model is available
                    if category == "TIMEOUT" and (idx + 1 < len(models_to_try)):
                        logger.info(f"Model '{target_model}' timed out in {elapsed:.2f}s. Immediately failing over to '{models_to_try[idx+1]}'.")
                        break

                    if attempt < retries_per_model:
                        jitter = random.uniform(0.05, 0.25)
                        sleep_s = min(1.5, max(0.1, (0.4 * (2 ** (attempt - 1))) + jitter))
                        sleep_s = min(sleep_s, max(0.05, total_deadline - time.perf_counter() - 1.0))
                        time.sleep(sleep_s)

        raise RuntimeError(f"All LLM models and retries exhausted. Last error: {sanitize_secret_log(str(last_error))}")

    @staticmethod
    def _extract_json_candidate(text: str) -> Optional[str]:
        """Safely extracts JSON from markdown fences, raw text, or reasoning content."""
        if not text:
            return None
        text = text.strip()
        # 1. Check for markdown code fences ```json ... ```
        fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, flags=re.IGNORECASE)
        if fence_match:
            candidate = fence_match.group(1).strip()
            if (candidate.startswith("{") and candidate.endswith("}")) or (candidate.startswith("[") and candidate.endswith("]")):
                return candidate
        # 2. Outermost JSON object { ... }
        first_brace = text.find("{")
        last_brace = text.rfind("}")
        if first_brace != -1 and last_brace > first_brace:
            return text[first_brace:last_brace + 1].strip()
        # 3. Outermost JSON array [ ... ]
        first_bracket = text.find("[")
        last_bracket = text.rfind("]")
        if first_bracket != -1 and last_bracket > first_bracket:
            return text[first_bracket:last_bracket + 1].strip()
        return None

    def generate_structured_json(
        self,
        messages: List[Dict[str, Any]],
        max_tokens: int = 4096,
        temperature: float = 0.1,
        fallback_fn: Optional[Callable[[], Dict[str, Any]]] = None
    ) -> Tuple[Dict[str, Any], bool]:
        """
        Generates structured JSON data with robust extraction from markdown fences,
        reasoning content, and outer brackets, plus deterministic fallback handling.
        Returns: (parsed_json_dict, is_fallback_boolean)
        """
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
            raw = (res.content or "").strip()
            
            clean_json = self._extract_json_candidate(raw)
            if not clean_json and res.reasoning_content:
                clean_json = self._extract_json_candidate(res.reasoning_content)

            if not clean_json:
                clean_json = raw

            data = json.loads(clean_json)
            return data, res.is_fallback

        except Exception as exc:
            safe_err = sanitize_secret_log(str(exc))
            logger.error(f"Failed to generate structured JSON: {safe_err}")
            if fallback_fn:
                logger.info("Executing provided deterministic fallback function.")
                return fallback_fn(), True
            raise

    def execute_tool_loop(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        tool_executor_fn: Callable[[str, Dict[str, Any]], str],
        max_steps: int = 3,
        trace_events: Optional[List[Dict[str, Any]]] = None,
        on_event: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> LLMResponse:
        """
        Executes a multi-step native tool calling loop until the model returns a final text response.
        Optionally records observable agent execution trace events and invokes on_event in real-time.
        """
        history = list(messages)
        active_model = self.primary_model

        friendly_tool_names = {
            "get_user_telemetry": "Accessing Wearable Biometrics Vault",
            "get_user_telemetry_reading": "Retrieving Real-Time Biometric Reading",
            "get_telemetry_history_range": "Querying Telemetry History Range",
            "compare_telemetry_periods": "Comparing Telemetry Across Periods",
            "get_activity_completion_evidence": "Verifying Smartwatch Interval Evidence",
            "review_schedule_adherence": "Reviewing Longitudinal Schedule Adherence",
            "query_ayurvedic_knowledge": "Consulting Classical Ayurvedic Knowledge Base",
            "get_current_schedule": "Reading Active Daily Routine",
            "validate_clinical_safety": "Validating Circadian & Digestive Principles",
            "propose_schedule_adaptation": "Formulating Clinical Schedule Adaptation",
            "persist_schedule_adaptation": "Persisting Routine Update to Vault",
            "get_adherence_history": "Reading Completion History & Nudges",
            "check_calendar_conflicts": "Checking Busy Calendar Events"
        }

        def _emit(evt: Dict[str, Any]):
            if trace_events is not None:
                trace_events.append(evt)
            if on_event is not None:
                try:
                    on_event(evt)
                except Exception as emit_err:
                    logger.debug(f"on_event handler error: {emit_err}")

        _emit({
            "stage": "understanding_question",
            "message": "Analyzing question, constitutional context, and biometric constraints",
            "timestamp": time.time()
        })

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
                _emit({
                    "stage": "preparing_response",
                    "message": "Synthesizing evidence-based Ayurvedic clinical recommendations",
                    "timestamp": time.time()
                })
                return res

            # Tool call requested: record assistant turn with tool calls
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

                friendly_name = friendly_tool_names.get(fn_name, fn_name.replace('_', ' ').title())

                safe_args = {k: v for k, v in fn_args.items() if k not in ("password", "token")}
                _emit({
                    "stage": "tool_call_start",
                    "tool": fn_name,
                    "friendly_name": friendly_name,
                    "args": safe_args,
                    "timestamp": time.time()
                })

                logger.info(f"Dispatching tool '{fn_name}' with args {fn_args}")
                t_tool_start = time.perf_counter()
                try:
                    tool_output_str = tool_executor_fn(fn_name, fn_args)
                    is_err = "error" in tool_output_str[:50].lower()
                except Exception as t_err:
                    logger.error(f"Tool '{fn_name}' execution threw exception: {t_err}")
                    tool_output_str = json.dumps({"error": f"Tool execution failed: {str(t_err)}"})
                    is_err = True

                duration_ms = round((time.perf_counter() - t_tool_start) * 1000.0, 1)

                # Create concise summary for UI
                summary_text = "Completed successfully"
                try:
                    parsed_out = json.loads(tool_output_str)
                    if isinstance(parsed_out, dict):
                        if "total_steps" in parsed_out:
                            summary_text = f"{parsed_out['total_steps']} steps verified"
                        elif "reading" in parsed_out:
                            r_val = parsed_out["reading"].get("value")
                            r_unit = parsed_out["reading"].get("unit", "")
                            summary_text = f"Latest reading: {r_val} {r_unit}"
                        elif "is_evidence_sufficient" in parsed_out:
                            summary_text = f"Steps: {parsed_out.get('interval_steps_measured')} (Threshold met: {parsed_out['is_evidence_sufficient']})"
                        elif "trend_direction" in parsed_out:
                            summary_text = f"Trend: {parsed_out['trend_direction']} ({parsed_out['percent_change']}%)"
                        elif "error" in parsed_out:
                            summary_text = f"Notice: {parsed_out['error']}"
                except Exception:
                    pass

                _emit({
                    "stage": "tool_call_complete",
                    "tool": fn_name,
                    "friendly_name": friendly_name,
                    "status": "error" if is_err else "success",
                    "summary": summary_text,
                    "duration_ms": duration_ms,
                    "timestamp": time.time()
                })

                history.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": tool_output_str
                })

        # If max steps exceeded without termination, execute one final non-tool turn
        return self.create_chat_completion(messages=history, max_tokens=1500)
