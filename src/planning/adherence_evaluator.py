"""
adherence_evaluator.py - Proactive Telemetry & Closed-Loop Adherence Evaluator

Periodically evaluates wearable biometrics and scheduled activities without requiring
the browser to be open or invoking LLM on every sync.

Responsibilities:
1. Synchronizes today's canonical schedule into the persistent activity_lifecycle table.
2. Performs evidence-based auto-completion (e.g., Active Shathapavali: ~100 brisk steps
   recorded during the scheduled window).
3. Evaluates closed activity windows, marking uncompleted activities as missed and scheduling
   constitutional, safe compensation linked to the original activity ID.
4. Alerts on due activities and upstream data staleness (>30m) with strict idempotency.
"""

import time
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

import src.database.db as db
from src.perception.wearable_interface import WearableTelemetryManager

logger = logging.getLogger("AdherenceEvaluator")


def evaluate_user_telemetry_and_adherence(
    user_id: int,
    current_ts: Optional[float] = None
) -> Dict[str, Any]:
    """
    Evaluates telemetry and adherence for the authenticated user at `current_ts` (default: now).
    Ensures idempotent state transitions and deduplicated notifications.
    """
    now = current_ts if current_ts is not None else time.time()
    today_str = datetime.fromtimestamp(now).strftime("%Y-%m-%d")

    results = {
        "user_id": user_id,
        "evaluation_timestamp": now,
        "schedule_date": today_str,
        "auto_completed_count": 0,
        "missed_count": 0,
        "compensations_scheduled_count": 0,
        "due_count": 0,
        "notifications_generated": 0,
        "upstream_stale": False,
        "details": []
    }

    # 1. Fetch user state & canonical schedule
    state = db.get_user_state(user_id)
    if not state:
        results["details"].append("No user state found.")
        return results

    last_sched = state.get("last_schedule")
    if last_sched and isinstance(last_sched, dict):
        # Sync schedule practices into activity_lifecycle idempotently
        db.sync_schedule_to_activity_lifecycle(user_id, last_sched, today_str)

    # 2. Retrieve today's activity lifecycle records
    activities = db.get_user_activities(user_id, date_str=today_str)
    if not activities:
        results["details"].append("No activities scheduled for today.")
        return results

    for act in activities:
        act_id = act["id"]
        status = act["status"]
        p_name = act["practice_name"]
        start_ts = act["start_time_ts"]
        end_ts = act["end_time_ts"]

        # Finalized states don't change
        if status in ("completed_by_user", "auto_completed_evidence", "compensation_completed", "cancelled"):
            continue

        # Case A: Window has passed (end_time_ts < now)
        if end_ts < now:
            # Check if this activity is step-based (Active Shathapavali ~100 steps)
            is_shathapavali = "shathapavali" in p_name.lower() or "walk" in p_name.lower()

            if is_shathapavali:
                # Query interval steps strictly within [start_ts, end_ts]
                interval_steps = db.get_interval_steps(user_id, start_ts, end_ts)
                if interval_steps >= 100:
                    # Auto-complete with wearable evidence
                    db.update_activity_lifecycle(
                        activity_id=act_id,
                        status="auto_completed_evidence",
                        completed_at=end_ts,
                        completion_source="wearable_step_interval",
                        evidence={"steps": interval_steps, "threshold_required": 100}
                    )
                    notif_msg = f"✓ {p_name} automatically completed from verified smartwatch interval steps ({interval_steps} steps recorded)."
                    db.create_notification(
                        user_id=user_id,
                        event_type="activity_auto_completed",
                        message=notif_msg,
                        activity_name=p_name,
                        severity="info",
                        idempotency_key=f"auto_comp_{act_id}"
                    )
                    results["auto_completed_count"] += 1
                    results["details"].append(f"Auto-completed {p_name} ({interval_steps} steps).")
                    continue
                else:
                    # Steps threshold not met or no interval data available
                    if status in ("scheduled", "due"):
                        db.update_activity_lifecycle(
                            activity_id=act_id,
                            status="missed",
                            evidence={"steps_measured": interval_steps, "threshold_required": 100, "reason": "window_closed_insufficient_steps"}
                        )
                        results["missed_count"] += 1

                        # Schedule safe, constitutional compensation:
                        # 10m restorative breathing / gentle walk that does not overload digestion or next day
                        comp_start = now + 900.0  # in 15 minutes
                        comp_end = comp_start + 600.0  # 10 minutes duration
                        comp_slot = f"{datetime.fromtimestamp(comp_start).strftime('%H:%M')} - {datetime.fromtimestamp(comp_end).strftime('%H:%M')}"
                        comp_practice = "Restorative Pranayama & Gentle Pavanmuktasana"
                        comp_rationale = (
                            f"Compensates for missed {p_name} to gently stimulate downward Apana Vayu and digestive lightness "
                            "without high physical exertion or metabolic strain."
                        )

                        comp_id = db.record_activity_compensation(
                            user_id=user_id,
                            original_activity_id=act_id,
                            compensation_practice=comp_practice,
                            time_slot=comp_slot,
                            start_ts=comp_start,
                            end_ts=comp_end,
                            rationale=comp_rationale
                        )
                        results["compensations_scheduled_count"] += 1

                        # Deduplicated notification
                        notif_msg = (
                            f"The scheduled window for {p_name} has concluded ({interval_steps} steps recorded vs 100 required). "
                            f"A 10-minute compensatory practice ({comp_practice}) has been scheduled at {comp_slot}."
                        )
                        db.create_notification(
                            user_id=user_id,
                            event_type="activity_missed_compensation",
                            message=notif_msg,
                            activity_name=p_name,
                            new_time_slot=comp_slot,
                            severity="info",
                            idempotency_key=f"missed_comp_{act_id}"
                        )
                        results["details"].append(f"Marked {p_name} as missed and scheduled compensation {comp_id}.")
            else:
                # Other practices (Pranayama, Meditation, etc.)
                if status in ("scheduled", "due"):
                    db.update_activity_lifecycle(
                        activity_id=act_id,
                        status="missed",
                        evidence={"reason": "window_closed_no_manual_confirmation"}
                    )
                    results["missed_count"] += 1

                    # Compensate if restorative
                    comp_start = now + 1200.0
                    comp_end = comp_start + 600.0
                    comp_slot = f"{datetime.fromtimestamp(comp_start).strftime('%H:%M')} - {datetime.fromtimestamp(comp_end).strftime('%H:%M')}"
                    comp_practice = "Short Restorative Meditation / Deep Breathing"
                    comp_rationale = f"Gentle compensation for missed {p_name} to restore circadian balance."

                    comp_id = db.record_activity_compensation(
                        user_id=user_id,
                        original_activity_id=act_id,
                        compensation_practice=comp_practice,
                        time_slot=comp_slot,
                        start_ts=comp_start,
                        end_ts=comp_end,
                        rationale=comp_rationale
                    )
                    results["compensations_scheduled_count"] += 1

                    notif_msg = f"The window for {p_name} has ended. A gentle 10-minute restorative pause has been added at {comp_slot}."
                    db.create_notification(
                        user_id=user_id,
                        event_type="activity_missed_compensation",
                        message=notif_msg,
                        activity_name=p_name,
                        new_time_slot=comp_slot,
                        severity="info",
                        idempotency_key=f"missed_comp_{act_id}"
                    )
                    results["details"].append(f"Marked {p_name} missed and scheduled compensation {comp_id}.")

        # Case B: Window is currently active (start_ts <= now <= end_ts)
        elif start_ts <= now <= end_ts:
            if status == "scheduled":
                db.update_activity_lifecycle(activity_id=act_id, status="due")
                results["due_count"] += 1
                notif_msg = f"Your scheduled practice **{p_name}** ({act['time_slot']}) is now due."
                db.create_notification(
                    user_id=user_id,
                    event_type="activity_due",
                    message=notif_msg,
                    activity_name=p_name,
                    new_time_slot=act["time_slot"],
                    severity="info",
                    idempotency_key=f"due_{act_id}"
                )
                results["details"].append(f"Marked {p_name} as due.")

    # 3. Upstream telemetry freshness evaluation
    summary = WearableTelemetryManager.get_user_telemetry_summary(user_id)
    if summary.get("is_upstream_stale"):
        results["upstream_stale"] = True
        # Hourly deduplication for upstream sync alert
        hour_slot = int(now / 3600)
        notif_msg = (
            "Upstream Fastrack Smart World data appears stale (>30 minutes since last watch measurement). "
            "Please open the Fastrack companion app on your phone to pull fresh records from your Noir Charm."
        )
        db.create_notification(
            user_id=user_id,
            event_type="upstream_sync_reminder",
            message=notif_msg,
            severity="warning",
            idempotency_key=f"stale_reminder_{user_id}_{hour_slot}"
        )
        results["details"].append("Generated upstream stale sync reminder.")

    return results
