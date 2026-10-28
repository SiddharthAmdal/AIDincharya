#!/usr/bin/env python3
"""
scripts/measure_system_latencies.py

Automated latency benchmarking for AI Dincharya:
1. Dashboard summary and wearable telemetry endpoints.
2. Routine loading and task completion.
3. Agent telemetry tools.
4. First streamed chat event and final response time.
5. Live NVIDIA NIM requests, timeout, and fallback behavior.
"""

import time
import json
import urllib.request
import urllib.error
from src.llm_gateway import LLMGateway
from src.planning.tools import execute_planner_tool


def benchmark():
    base_url = "http://localhost:8000"
    results = {}

    print("=" * 70)
    print("AI DINCHARYA — SYSTEM LATENCY & BEHAVIOR MEASUREMENTS")
    print(f"Target: {base_url}")
    print("=" * 70)

    # Step 0: Authenticate
    t0 = time.time()
    login_data = json.dumps({"username": "demo_user", "password": "DemoPass123!"}).encode()
    req = urllib.request.Request(f"{base_url}/api/auth/login", data=login_data, headers={"Content-Type": "application/json"})
    token = json.loads(urllib.request.urlopen(req).read().decode())["token"]
    auth_ms = (time.time() - t0) * 1000
    results["auth_latency_ms"] = round(auth_ms, 2)
    print(f"✓ Authentication (/api/auth/login): {auth_ms:.1f} ms")

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # 1. Dashboard Summary
    t0 = time.time()
    dash_req = urllib.request.Request(f"{base_url}/api/dashboard/summary", headers=headers)
    dash_resp = json.loads(urllib.request.urlopen(dash_req).read().decode())
    dash_ms = (time.time() - t0) * 1000
    results["dashboard_summary_ms"] = round(dash_ms, 2)
    print(f"✓ Dashboard Summary (/api/dashboard/summary): {dash_ms:.1f} ms")

    # 2. Wearable Telemetry Records & Dashboard Telemetry Bundle
    t0 = time.time()
    rec_req = urllib.request.Request(f"{base_url}/api/telemetry/records", headers=headers)
    rec_resp = json.loads(urllib.request.urlopen(rec_req).read().decode())
    rec_ms = (time.time() - t0) * 1000
    results["telemetry_records_ms"] = round(rec_ms, 2)
    telemetry_bundle = dash_resp.get("telemetry", {})
    metrics = telemetry_bundle.get("metrics", {})
    print(f"✓ Wearable Telemetry Records (/api/telemetry/records): {rec_ms:.1f} ms ({len(rec_resp.get('records', []))} records)")
    print(f"✓ Wearable Telemetry Bundle in Dashboard: has_wearable={telemetry_bundle.get('has_wearable')}, device={telemetry_bundle.get('device_model')}, metrics={list(metrics.keys())}")

    # 3. Routine Loading
    t0 = time.time()
    rout_req = urllib.request.Request(f"{base_url}/routine")
    urllib.request.urlopen(rout_req).read()
    rout_ms = (time.time() - t0) * 1000
    results["routine_page_ms"] = round(rout_ms, 2)
    print(f"✓ Routine Page Load (/routine HTML): {rout_ms:.1f} ms")

    t0 = time.time()
    act_req = urllib.request.Request(f"{base_url}/api/activities/today", headers=headers)
    act_resp = json.loads(urllib.request.urlopen(act_req).read().decode())
    act_ms = (time.time() - t0) * 1000
    results["routine_activities_ms"] = round(act_ms, 2)
    print(f"✓ Routine Activities Query (/api/activities/today): {act_ms:.1f} ms ({len(act_resp.get('activities', []))} tasks)")

    # 4. Task Completion
    t0 = time.time()
    comp_data = json.dumps({"practice_name": "Abhyanga", "activity_id": "Abhyanga"}).encode()
    comp_req = urllib.request.Request(f"{base_url}/api/activities/complete", data=comp_data, headers=headers)
    comp_resp = json.loads(urllib.request.urlopen(comp_req).read().decode())
    comp_ms = (time.time() - t0) * 1000
    results["task_completion_ms"] = round(comp_ms, 2)
    print(f"✓ Task Completion (/api/activities/complete): {comp_ms:.1f} ms (adherence: {comp_resp.get('adherence', {}).get('score')}%)")

    # 5. Agent Telemetry Tools Execution
    t0 = time.time()
    tool_hr = execute_planner_tool("get_user_telemetry_reading", {"user_id": "10633", "metric_type": "heart_rate"}, caller_user_id=10633)
    tool_hr_ms = (time.time() - t0) * 1000
    results["tool_telemetry_reading_hr_ms"] = round(tool_hr_ms, 2)
    print(f"✓ Agent Telemetry Tool (get_user_telemetry_reading - HR): {tool_hr_ms:.1f} ms")

    t0 = time.time()
    tool_step = execute_planner_tool("get_user_telemetry_reading", {"user_id": "10633", "metric_type": "steps"}, caller_user_id=10633)
    tool_step_ms = (time.time() - t0) * 1000
    results["tool_telemetry_reading_steps_ms"] = round(tool_step_ms, 2)
    print(f"✓ Agent Telemetry Tool (get_user_telemetry_reading - Steps): {tool_step_ms:.1f} ms")

    t0 = time.time()
    tool_sleep = execute_planner_tool("get_user_telemetry_reading", {"user_id": "10633", "metric_type": "sleep"}, caller_user_id=10633)
    tool_sleep_ms = (time.time() - t0) * 1000
    results["tool_telemetry_reading_sleep_ms"] = round(tool_sleep_ms, 2)
    print(f"✓ Agent Telemetry Tool (get_user_telemetry_reading - Sleep): {tool_sleep_ms:.1f} ms")

    t0 = time.time()
    tool_all = execute_planner_tool("get_user_telemetry", {"user_id": "10633"}, caller_user_id=10633)
    tool_all_ms = (time.time() - t0) * 1000
    results["tool_telemetry_summary_ms"] = round(tool_all_ms, 2)
    print(f"✓ Agent Telemetry Tool (get_user_telemetry - All): {tool_all_ms:.1f} ms")

    # 6. Streaming Chat Latency (TTFT & Total Stream Response)
    stream_url = f"{base_url}/api/chat/stream"
    chat_payload = json.dumps({"message": "What is my current step count today?"}).encode()
    stream_req = urllib.request.Request(stream_url, data=chat_payload, headers=headers)

    t0 = time.time()
    ttft_ms = None
    event_count = 0
    final_resp_text = ""

    with urllib.request.urlopen(stream_req) as s_resp:
        for raw_line in s_resp:
            line = raw_line.decode("utf-8").strip()
            if line.startswith("data: "):
                if ttft_ms is None:
                    ttft_ms = (time.time() - t0) * 1000
                event_count += 1
                try:
                    ev = json.loads(line[6:])
                    if ev.get("type") == "final_response":
                        final_resp_text = ev.get("response", "")
                except Exception:
                    pass

    total_stream_ms = (time.time() - t0) * 1000
    results["chat_stream_ttft_ms"] = round(ttft_ms or 0.0, 2)
    results["chat_stream_total_ms"] = round(total_stream_ms, 2)
    results["chat_stream_events_count"] = event_count
    print(f"✓ Chat Stream TTFT (Time to first event): {ttft_ms:.1f} ms")
    print(f"✓ Chat Stream Total Duration: {total_stream_ms:.1f} ms ({event_count} SSE events)")
    print(f"  • Final response length: {len(final_resp_text)} characters")

    # 7. Live NVIDIA NIM Direct Verification
    gateway = LLMGateway.get_instance()
    t0 = time.time()
    nim_resp = gateway.create_chat_completion(
        messages=[{"role": "user", "content": "Respond with 'NIM Active'"}],
        max_tokens=10
    )
    nim_direct_ms = (time.time() - t0) * 1000
    results["nim_direct_latency_ms"] = round(nim_direct_ms, 2)
    results["nim_direct_model"] = nim_resp.model_used
    results["nim_is_fallback"] = nim_resp.is_fallback
    print(f"✓ Live NVIDIA NIM Direct Request: {nim_direct_ms:.1f} ms")
    print(f"  • Model: {nim_resp.model_used}")
    print(f"  • Is Fallback: {nim_resp.is_fallback}")
    print(f"  • Content: {repr(nim_resp.content.strip())}")

    print("\n" + "=" * 70)
    print("ALL LATENCY BENCHMARKS COMPLETED")
    print("=" * 70)
    return results


if __name__ == "__main__":
    benchmark()
