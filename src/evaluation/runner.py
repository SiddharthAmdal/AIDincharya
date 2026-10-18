"""
CLI Benchmark Runner for AI Dincharya Evaluation Suite.
Usage:
    python -m src.evaluation.runner [--group all|rag|grounding|agent|safety|schedule] [--live] [--compare baseline.json]
"""

import os
import sys
import json
import argparse
from typing import Dict, Any, Optional

from src.evaluation.evaluator import EvaluationEngine

DEFAULT_REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "reports", "eval")


def compare_with_baseline(current_report: Dict[str, Any], baseline_path: str) -> bool:
    """
    Compares current run metrics against stored baseline report.
    Returns True if any hard regression or baseline integrity failure is detected:
      - missing baseline file
      - corrupt baseline JSON or invalid structure
      - missing evaluation group or tracked metric
      - status regression (PASS -> FAIL)
      - metric drop > 0.05
    Returns False ONLY when baseline comparison completely succeeds without regressions.
    """
    if not os.path.exists(baseline_path):
        print(f"[ERROR] Baseline file not found at: {baseline_path}")
        return True

    try:
        with open(baseline_path, "r", encoding="utf-8") as f:
            baseline = json.load(f)
        if not isinstance(baseline, dict) or "groups" not in baseline:
            print(f"[ERROR] Invalid baseline structure at {baseline_path}: missing root 'groups' mapping.")
            return True
    except Exception as exc:
        print(f"[ERROR] Failed to load baseline from {baseline_path}: {exc}")
        return True

    print("\n" + "=" * 60)
    print(" 📊 REGRESSION COMPARISON AGAINST BASELINE")
    print("=" * 60)
    print(f"Baseline Run ID : {baseline.get('run_id', 'unknown')}")
    print(f"Current Run ID  : {current_report.get('run_id', 'unknown')}")
    print("-" * 60)

    has_regression = False
    metric_keys_to_track = {
        "rag": ["hit_rate_at_k", "mean_reciprocal_rank", "abstention_accuracy"],
        "grounding": ["grounding_classification_accuracy"],
        "agent": ["confirmation_protocol_compliance", "scenario_pass_rate"],
        "safety": ["attack_block_rate", "benign_pass_rate"],
        "schedule": ["pass_rate"]
    }

    current_groups = current_report.get("groups", {})
    if not current_groups:
        print("[ERROR] Current evaluation report has no groups evaluated.")
        return True

    for group_name, curr_g in current_groups.items():
        if group_name not in baseline.get("groups", {}):
            print(f"[ERROR] Baseline is missing required evaluation group: '{group_name}'")
            has_regression = True
            continue

        base_g = baseline["groups"][group_name]

        c_pass = "PASS" if curr_g.get("passed") else "FAIL"
        b_pass = "PASS" if base_g.get("passed") else "FAIL"
        
        status_regressed = (b_pass == "PASS" and c_pass == "FAIL")
        if status_regressed:
            has_regression = True
            diff_status = f"❌ REGRESSION ({b_pass} -> {c_pass})"
        else:
            diff_status = "✓ OK" if c_pass == b_pass else f"⚠️ STATUS ({b_pass} -> {c_pass})"

        print(f"Group: {group_name.upper():<12} | Baseline: {b_pass:<5} | Current: {c_pass:<5} | {diff_status}")

        # Check numerical metric deltas
        curr_summary = curr_g.get("summary", {})
        base_summary = base_g.get("summary", {})
        for m_key in metric_keys_to_track.get(group_name, []):
            if m_key not in curr_summary or m_key not in base_summary:
                print(f"   ❌ Missing Metric: '{m_key}' missing in {'current' if m_key not in curr_summary else 'baseline'} report!")
                has_regression = True
                continue

            c_val = curr_summary[m_key]
            b_val = base_summary[m_key]
            if not isinstance(c_val, (int, float)) or not isinstance(b_val, (int, float)):
                print(f"   ❌ Non-numerical metric value for '{m_key}': current={c_val}, baseline={b_val}")
                has_regression = True
                continue

            delta = round(c_val - b_val, 4)
            if delta < -0.05:
                has_regression = True
                print(f"   ⚠️ Metric Drop: {m_key} degraded by {delta:.4f} ({b_val} -> {c_val})")
            elif delta != 0.0:
                sign = "+" if delta > 0 else ""
                print(f"   ℹ️ Metric Shift: {m_key} {sign}{delta:.4f} ({b_val} -> {c_val})")

    print("=" * 60)
    return has_regression


def print_human_readable_summary(report: Dict[str, Any]):
    """Prints a beautiful, formatted evaluation summary to stdout."""
    print("\n" + "=" * 65)
    print("       🌿 AI DINCHARYA — RAG & AGENT EVALUATION BENCHMARK")
    print("=" * 65)
    print(f" Run ID       : {report['run_id']}")
    print(f" Timestamp    : {report['timestamp']}")
    print(f" Dataset Ver  : {report['dataset_version']}")
    print(f" Mode         : {report.get('mode', 'deterministic').upper()}")
    print(f" Total Time   : {report['elapsed_seconds']}s")
    print("-" * 65)

    groups = report.get("groups", {})
    all_passed = report.get("overall_passed", False)

    for g_name, g_data in groups.items():
        status = "✓ PASS" if g_data["passed"] else "✗ FAIL"
        summary = g_data.get("summary", {})
        print(f"\n[{status}] GROUP: {g_name.upper()}")
        for k, v in summary.items():
            print(f"    - {k:<32}: {v}")

    print("\n" + "=" * 65)
    if all_passed:
        print(" 🎯 OVERALL BENCHMARK VERDICT: PASS (All Hard Gates Satisfied)")
    else:
        print(" ❌ OVERALL BENCHMARK VERDICT: FAIL (Hard Gate Not Satisfied)")
    print("=" * 65 + "\n")


def main():
    parser = argparse.ArgumentParser(description="AI Dincharya RAG & Agent Evaluation Benchmark Runner")
    parser.add_argument(
        "--group",
        choices=["all", "rag", "grounding", "agent", "safety", "schedule"],
        default="all",
        help="Evaluation group to execute (default: all)"
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Enable optional live LLM calls (default: deterministic offline suite)"
    )
    parser.add_argument(
        "--dataset-version",
        default="v1",
        help="Dataset version to evaluate (default: v1)"
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_REPORTS_DIR,
        help=f"Directory to save JSON reports (default: {DEFAULT_REPORTS_DIR})"
    )
    parser.add_argument(
        "--compare",
        default=None,
        help="Path to baseline JSON report for regression comparison"
    )

    args = parser.parse_args()

    engine = EvaluationEngine(dataset_version=args.dataset_version)

    if args.group == "all":
        report = engine.run_all(use_live_model=args.live)
    elif args.group == "rag":
        res = engine.evaluate_rag()
        report = {
            "run_id": f"rag_{int(time.time())}",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "dataset_version": args.dataset_version,
            "overall_passed": res["passed"],
            "elapsed_seconds": 0.0,
            "groups": {"rag": res}
        }
    elif args.group == "grounding":
        res = engine.evaluate_grounding()
        report = {
            "run_id": f"grounding_{int(time.time())}",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "dataset_version": args.dataset_version,
            "overall_passed": res["passed"],
            "elapsed_seconds": 0.0,
            "groups": {"grounding": res}
        }
    elif args.group == "agent":
        res = engine.evaluate_agent(use_live_model=args.live)
        report = {
            "run_id": f"agent_{int(time.time())}",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "dataset_version": args.dataset_version,
            "overall_passed": res["passed"],
            "elapsed_seconds": 0.0,
            "groups": {"agent": res}
        }
    elif args.group == "safety":
        res = engine.evaluate_safety(use_live_model=args.live)
        report = {
            "run_id": f"safety_{int(time.time())}",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "dataset_version": args.dataset_version,
            "overall_passed": res["passed"],
            "elapsed_seconds": 0.0,
            "groups": {"safety": res}
        }
    elif args.group == "schedule":
        res = engine.evaluate_schedule()
        report = {
            "run_id": f"schedule_{int(time.time())}",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "dataset_version": args.dataset_version,
            "overall_passed": res["passed"],
            "elapsed_seconds": 0.0,
            "groups": {"schedule": res}
        }

    # Print summary
    print_human_readable_summary(report)

    # Compare with baseline if requested
    has_regression = False
    if args.compare:
        has_regression = compare_with_baseline(report, args.compare)

    # Save JSON report
    os.makedirs(args.output_dir, exist_ok=True)
    report_filename = f"{report['run_id']}.json"
    output_path = os.path.join(args.output_dir, report_filename)
    
    # Baseline protection safeguard
    if args.compare and os.path.abspath(output_path) == os.path.abspath(args.compare):
        raise RuntimeError(
            f"Baseline Integrity Violation: Runner cannot overwrite frozen baseline at '{args.compare}'"
        )

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"💾 Full machine-readable report saved to: {output_path}")

    # Return exit code based on hard gates and baseline regressions
    if not report["overall_passed"] or has_regression:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    import time
    main()
