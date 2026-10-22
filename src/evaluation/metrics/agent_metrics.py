"""
Agent Orchestration, Tool Calling, and Protocol Metrics.
Evaluates tool selection, confirmation compliance, mutation accuracy, and error recovery.
Separates tool-selection tests, tool-execution tests, and end-to-end agent tests in reports.
"""

import re
from typing import List, Dict, Any, Optional

PROPOSAL_REGEX = re.compile(
    r"I propose moving\s+(.+?)\s+from\s+(.+?)\s+to\s+(.+?)\.\s+Would you like me to confirm",
    re.IGNORECASE
)
RECALIBRATE_TAG = "[RECALIBRATE]"

def evaluate_agent_scenario(
    scenario: Dict[str, Any],
    actual_tool_called: Optional[str],
    actual_tool_args: Optional[Dict[str, Any]],
    assistant_response: str,
    schedule_mutated: bool,
    error_raised: bool = False,
    track: Optional[str] = None
) -> Dict[str, Any]:
    """
    Evaluates agent action against expected behavior for a scenario.
    """
    intent = scenario.get("intent")
    expected_action = scenario.get("expected_action")
    expected_tool = scenario.get("expected_tool")
    requires_confirmation = scenario.get("requires_confirmation", False)
    should_mutate = scenario.get("should_mutate_schedule", False)

    # Automatically infer track if not supplied
    if not track:
        if intent in ("conversational_greeting", "knowledge_retrieval", "schedule_inspection", "calendar_conflict_check", "notification_request", "adherence_history_query"):
            track = "tool_selection"
        elif intent in ("tool_argument_validation", "unknown_tool_recovery", "unauthorized_cross_user_access", "malformed_arguments_recovery", "failed_mutation_rollback", "routine_activity_proposal_direct"):
            track = "tool_execution"
        else:
            track = "end_to_end_agent"

    # 1. Tool Selection Check
    tool_selection_correct = (actual_tool_called == expected_tool)

    # 2. Confirmation Protocol Compliance
    has_proposal_text = bool(PROPOSAL_REGEX.search(assistant_response)) or "propose" in assistant_response.lower()
    has_recalibrate_tag = RECALIBRATE_TAG in assistant_response

    if requires_confirmation:
        confirmation_compliant = has_proposal_text and not schedule_mutated
    else:
        confirmation_compliant = True

    # 3. False Success Claim Check
    forbidden_pattern = scenario.get("forbidden_response_pattern")
    false_success_claim = False
    if forbidden_pattern:
        if re.search(forbidden_pattern, assistant_response, re.IGNORECASE):
            false_success_claim = True

    # 4. Schedule Mutation Accuracy
    mutation_correct = (schedule_mutated == should_mutate)

    # 5. Error Recovery Check
    if expected_action in ("handle_tool_validation_error", "return_unknown_tool_error", "permission_denied"):
        error_recovery_passed = not error_raised and (
            "error" in assistant_response.lower() or "denied" in assistant_response.lower() or "invalid" in assistant_response.lower()
        )
    else:
        error_recovery_passed = not error_raised

    overall_pass = (
        tool_selection_correct and
        confirmation_compliant and
        not false_success_claim and
        mutation_correct and
        error_recovery_passed
    )

    return {
        "scenario_id": scenario.get("id"),
        "intent": intent,
        "track": track,
        "tool_selection_correct": tool_selection_correct,
        "confirmation_compliant": confirmation_compliant,
        "false_success_claim": false_success_claim,
        "mutation_correct": mutation_correct,
        "error_recovery_passed": error_recovery_passed,
        "overall_pass": overall_pass
    }


def aggregate_agent_metrics(scenario_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Aggregates scenario results across an agent evaluation dataset run.
    Separates tool-selection tests, tool-execution tests, and end-to-end agent adaptation tests.
    """
    total = len(scenario_results)
    tool_correct = sum(1 for r in scenario_results if r.get("tool_selection_correct", True))
    conf_compliant = sum(1 for r in scenario_results if r.get("confirmation_compliant", r.get("confirmation_protocol_compliant", True)))
    false_claims = sum(1 for r in scenario_results if r.get("false_success_claim", False))
    mutation_acc = sum(1 for r in scenario_results if r.get("mutation_correct", True))
    err_recovery = sum(1 for r in scenario_results if r.get("error_recovery_passed", True))
    all_passed = sum(1 for r in scenario_results if r.get("overall_pass", r.get("passed", True)))

    # Separate tracks
    selection_scenarios = [r for r in scenario_results if r.get("track") in ("tool_selection", "tool_selection_tests") or r.get("eval_track") in ("tool_selection", "tool_selection_tests")]
    execution_scenarios = [r for r in scenario_results if r.get("track") in ("tool_execution", "tool_execution_tests") or r.get("eval_track") in ("tool_execution", "tool_execution_tests")]
    e2e_scenarios = [r for r in scenario_results if r.get("track") in ("end_to_end_agent", "end_to_end_agent_tests") or r.get("eval_track") in ("end_to_end_agent", "end_to_end_agent_tests")]

    selection_acc = (
        sum(1 for r in selection_scenarios if r.get("overall_pass", r.get("passed", True))) / len(selection_scenarios)
        if selection_scenarios else 1.0
    )
    execution_acc = (
        sum(1 for r in execution_scenarios if r.get("overall_pass", r.get("passed", True))) / len(execution_scenarios)
        if execution_scenarios else 1.0
    )
    e2e_acc = (
        sum(1 for r in e2e_scenarios if r.get("overall_pass", r.get("passed", True))) / len(e2e_scenarios)
        if e2e_scenarios else 1.0
    )

    return {
        "total_scenarios": total,
        "tool_selection_accuracy": round(tool_correct / total, 4) if total > 0 else 0.0,
        "confirmation_protocol_compliance": round(conf_compliant / total, 4) if total > 0 else 0.0,
        "unsupported_success_claim_rate": round(false_claims / total, 4) if total > 0 else 0.0,
        "schedule_mutation_accuracy": round(mutation_acc / total, 4) if total > 0 else 0.0,
        "error_recovery_rate": round(err_recovery / total, 4) if total > 0 else 0.0,
        "scenario_pass_rate": round(all_passed / total, 4) if total > 0 else 0.0,
        "tracks": {
            "tool_selection_tests": {
                "count": len(selection_scenarios),
                "accuracy": round(selection_acc, 4)
            },
            "tool_execution_tests": {
                "count": len(execution_scenarios),
                "accuracy": round(execution_acc, 4)
            },
            "end_to_end_agent_tests": {
                "count": len(e2e_scenarios),
                "accuracy": round(e2e_acc, 4)
            }
        }
    }
