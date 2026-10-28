"""
wearable_interface.py - Stable Wearable Telemetry Interface (Fastrack Noir Charm / Health Connect)

Provides a clean, validated ingestion contract for wearable metrics exported via
Android Health Connect or compatible companions. Enforces timestamps, units, freshness checks,
provenance preservation, and handles incomplete or delayed data without fabricating missing metrics.
"""

import time
import datetime
import logging
import hashlib
from typing import Dict, Any, Optional, Tuple, List, Union
from pydantic import BaseModel, Field


logger = logging.getLogger("WearableInterface")

DEFAULT_MAX_FRESHNESS_HOURS = 36.0


class SleepRecord(BaseModel):
    duration_hours: float
    start_timestamp: Optional[float] = None
    end_timestamp: Optional[float] = None
    deep_sleep_hours: Optional[float] = None
    rem_sleep_hours: Optional[float] = None
    light_sleep_hours: Optional[float] = None
    awake_minutes: Optional[int] = None
    source: str = "android_health_connect"


class ActivitySummary(BaseModel):
    steps_total: int
    active_minutes: Optional[int] = None
    distance_meters: Optional[float] = None
    source: str = "android_health_connect"


class HeartRateRecord(BaseModel):
    resting_hr_bpm: Optional[float] = None
    heart_rate_bpm: Optional[float] = None
    timestamp: float
    hrv_rmssd_ms: Optional[float] = None
    source: str = "android_health_connect"


class TelemetryRecordItem(BaseModel):
    """
    Discrete measurement item from Health Connect or companion app.
    Retains stable source record ID and provenance.
    """
    record_id: Optional[str] = None
    metric_type: str  # "heart_rate", "resting_heart_rate", "steps", "spo2", "sleep", "body_temp"
    value: float
    unit: str  # "bpm", "count", "%", "hours", "celsius", "ms"
    timestamp: float
    source_package: str = "com.google.android.apps.healthdata"
    device_model: str = "Fastrack Noir Charm"
    acquisition_method: str = "health_connect_import"
    aggregation_type: Optional[str] = "interval"
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    duration_hours: Optional[float] = None
    stages: Optional[List[Dict[str, Any]]] = None


class HealthConnectPayload(BaseModel):
    device_model: str = "Fastrack Noir Charm"
    source_package: str = "com.google.android.apps.healthdata"
    recorded_at: float = Field(default_factory=time.time)
    record_id: Optional[str] = None
    acquisition_method: str = "health_connect_import"  # health_connect_import, device_measured, manual, synthetic
    heart_rate_bpm: Optional[float] = None
    resting_hr: Optional[float] = None
    spo2_pct: Optional[float] = None
    steps: Optional[int] = None
    hrv_ms: Optional[float] = None
    body_temp_c: Optional[float] = None
    sleep: Optional[SleepRecord] = None
    activity: Optional[ActivitySummary] = None
    records: Optional[List[TelemetryRecordItem]] = None


class WearableTelemetryManager:
    """
    Ingests and normalizes real wearable telemetry without fabricating synthetic signals.
    Supports Fastrack Noir Charm, Health Connect, Amazfit, and generic companions.
    """

    SUPPORTED_DEVICES = [
        "Fastrack Noir Charm",
        "Fastrack Smart World",
        "Amazfit Bip 6",
        "Zepp Life",
        "Android Health Connect",
        "Health Connect",
        "Wear OS"
    ]

    SUPPORTED_PROVENANCE = [
        "health_connect_import",
        "device_measured",
        "manual",
        "synthetic"
    ]

    @staticmethod
    def check_freshness(timestamp: Any, max_age_hours: float = DEFAULT_MAX_FRESHNESS_HOURS) -> Tuple[bool, str]:
        """
        Validates whether a telemetry reading is fresh enough to inform daily planning.
        Accepts float timestamp or dictionary payload with a timestamp.
        Rejects stale records (>36h old) and future-dated records (>1h in future).
        """
        if isinstance(timestamp, dict):
            ts = timestamp.get("timestamp") or timestamp.get("recorded_at")
            if ts is None:
                return False, "missing_timestamp"
            try:
                timestamp = float(ts)
            except (ValueError, TypeError):
                return False, "invalid_timestamp_value"
        elif not isinstance(timestamp, (int, float)):
            return False, "invalid_timestamp_type"

        now = time.time()
        age_hours = (now - float(timestamp)) / 3600.0

        if age_hours < -1.0:
            return False, "future_dated_invalid"
        elif age_hours > max_age_hours:
            return False, f"stale_record ({round(age_hours, 1)}h old)"
        else:
            return True, f"fresh ({round(age_hours, 1)}h old)"

    @classmethod
    def ingest_payload(cls, raw_data: Any) -> Dict[str, Any]:
        """
        Ingests and validates raw telemetry from Health Connect or companion client.
        Accepts either a dictionary or a Pydantic HealthConnectPayload model.
        Does not substitute default readings for missing metrics.
        """
        if raw_data is None:
            return {
                "status": "no_data",
                "is_fresh": False,
                "freshness_description": "unavailable",
                "verified_signals": {},
                "signals": {},
                "consumed_metrics": [],
                "missing_metrics": ["resting_hr", "heart_rate_bpm", "spo2_pct", "steps", "sleep_hours"],
                "discrete_records": [],
                "sleep_status": "no_data_yet"
            }

        # Convert Pydantic model to dict if needed
        if hasattr(raw_data, "model_dump"):
            data_dict = raw_data.model_dump()
        elif isinstance(raw_data, dict):
            data_dict = raw_data
        else:
            return {
                "status": "invalid_payload_format",
                "is_fresh": False,
                "freshness_description": "invalid payload format",
                "verified_signals": {},
                "signals": {},
                "consumed_metrics": [],
                "missing_metrics": ["resting_hr", "steps", "spo2_pct"],
                "discrete_records": [],
                "sleep_status": "no_data_yet"
            }

        rec_time = data_dict.get("recorded_at") or data_dict.get("timestamp") or time.time()
        try:
            rec_time = float(rec_time)
        except (ValueError, TypeError):
            rec_time = time.time()

        is_fresh, freshness_desc = cls.check_freshness(rec_time)

        verified: Dict[str, float] = {}
        consumed: List[str] = []
        missing: List[str] = []
        discrete_records: List[Dict[str, Any]] = []

        device = data_dict.get("device_model", "Fastrack Noir Charm")
        source_pkg = data_dict.get("source_package", "com.google.android.apps.healthdata")
        acq_method = data_dict.get("acquisition_method", "health_connect_import")
        if acq_method not in cls.SUPPORTED_PROVENANCE:
            acq_method = "health_connect_import"

        # 1. Heart Rate / Resting Heart Rate (bpm)
        hr_val = data_dict.get("heart_rate_bpm")
        if hr_val is None:
            hr_val = data_dict.get("resting_hr")
        if hr_val is not None and isinstance(hr_val, (int, float)) and 30 <= hr_val <= 240:
            verified["resting_hr"] = float(hr_val)
            verified["heart_rate_bpm"] = float(hr_val)
            consumed.append("resting_hr")
            consumed.append("heart_rate_bpm")
            # Build discrete record
            rec_id = data_dict.get("record_id")
            if not rec_id:
                rec_id = hashlib.sha256(f"hr:{rec_time}:{hr_val}:{source_pkg}".encode()).hexdigest()[:24]
            discrete_records.append({
                "record_id": rec_id,
                "metric_type": "heart_rate",
                "value": float(hr_val),
                "unit": "bpm",
                "timestamp": rec_time,
                "source_package": source_pkg,
                "device_model": device,
                "acquisition_method": acq_method
            })
        else:
            missing.append("resting_hr")

        # 2. SpO2 / Blood Oxygen Saturation (%)
        spo2_val = data_dict.get("spo2_pct")
        if spo2_val is None:
            spo2_val = data_dict.get("spo2") or data_dict.get("blood_oxygen_pct")
        if spo2_val is not None and isinstance(spo2_val, (int, float)) and 70.0 <= spo2_val <= 100.0:
            verified["spo2_pct"] = float(spo2_val)
            consumed.append("spo2_pct")
            rec_id = hashlib.sha256(f"spo2:{rec_time}:{spo2_val}:{source_pkg}".encode()).hexdigest()[:24]
            discrete_records.append({
                "record_id": rec_id,
                "metric_type": "spo2",
                "value": float(spo2_val),
                "unit": "%",
                "timestamp": rec_time,
                "source_package": source_pkg,
                "device_model": device,
                "acquisition_method": acq_method
            })
        else:
            missing.append("spo2_pct")

        # 3. Steps Summary
        steps_val = data_dict.get("steps")
        if steps_val is None and isinstance(data_dict.get("activity"), dict):
            steps_val = data_dict["activity"].get("steps_total")
        elif steps_val is None and hasattr(data_dict.get("activity"), "steps_total"):
            steps_val = getattr(data_dict.get("activity"), "steps_total")

        if steps_val is not None and isinstance(steps_val, (int, float)) and 0 <= steps_val <= 150000:
            verified["steps_total"] = int(steps_val)
            consumed.append("steps_total")
            rec_id = hashlib.sha256(f"steps_daily:{rec_time}:{steps_val}:{source_pkg}".encode()).hexdigest()[:24]
            discrete_records.append({
                "record_id": rec_id,
                "metric_type": "steps_daily_summary",
                "value": float(steps_val),
                "unit": "count",
                "timestamp": rec_time,
                "source_package": source_pkg,
                "device_model": device,
                "acquisition_method": acq_method,
                "aggregation_type": "daily_total"
            })
        else:
            missing.append("steps")

        # 4. Heart Rate Variability (ms, RMSSD)
        hrv = data_dict.get("hrv_ms")
        if hrv is not None and isinstance(hrv, (int, float)) and 5 <= hrv <= 250:
            verified["hrv_ms"] = float(hrv)
            consumed.append("hrv_ms")
            discrete_records.append({
                "record_id": hashlib.sha256(f"hrv:{rec_time}:{hrv}:{source_pkg}".encode()).hexdigest()[:24],
                "metric_type": "hrv_ms",
                "value": float(hrv),
                "unit": "ms",
                "timestamp": rec_time,
                "source_package": source_pkg,
                "device_model": device,
                "acquisition_method": acq_method
            })
        else:
            missing.append("hrv_ms")

        # 5. Skin / Body Temperature (Celsius)
        temp = data_dict.get("body_temp_c")
        if temp is not None and isinstance(temp, (int, float)) and 34.0 <= temp <= 43.0:
            verified["body_temp_c"] = float(temp)
            consumed.append("body_temp_c")
            discrete_records.append({
                "record_id": hashlib.sha256(f"temp:{rec_time}:{temp}:{source_pkg}".encode()).hexdigest()[:24],
                "metric_type": "body_temp_c",
                "value": float(temp),
                "unit": "celsius",
                "timestamp": rec_time,
                "source_package": source_pkg,
                "device_model": device,
                "acquisition_method": acq_method
            })
        else:
            missing.append("body_temp_c")

        # 6. Sleep Duration (hours)
        # Note: Sleep is out of scope for initial demo until genuine overnight cycle is recorded.
        # If absent, status is 'no_data_yet' rather than zero or failure.
        sleep_val = data_dict.get("sleep_hours")
        sleep_obj = data_dict.get("sleep")
        if sleep_val is None and isinstance(sleep_obj, dict):
            sleep_val = sleep_obj.get("duration_hours")
        elif sleep_val is None and hasattr(sleep_obj, "duration_hours"):
            sleep_val = getattr(sleep_obj, "duration_hours")

        if sleep_val is not None and isinstance(sleep_val, (int, float)) and 0.5 <= sleep_val <= 18:
            verified["sleep_hours"] = float(sleep_val)
            consumed.append("sleep_hours")
            sleep_status = "available"

            sleep_rec_id = None
            if isinstance(sleep_obj, dict):
                sleep_rec_id = sleep_obj.get("record_id")
            elif hasattr(sleep_obj, "record_id"):
                sleep_rec_id = getattr(sleep_obj, "record_id")
            if not sleep_rec_id:
                sleep_rec_id = hashlib.sha256(f"sleep:{rec_time}:{sleep_val}:{source_pkg}".encode()).hexdigest()[:24]

            discrete_records.append({
                "record_id": sleep_rec_id,
                "metric_type": "sleep",
                "value": float(sleep_val),
                "unit": "hours",
                "timestamp": rec_time,
                "source_package": source_pkg,
                "device_model": device,
                "acquisition_method": acq_method,
                "aggregation_type": "session"
            })
        else:
            missing.append("sleep_hours")
            sleep_status = "no_data_yet"

        # 7. Discrete Records List (if explicitly provided in payload)
        extra_records = data_dict.get("records")
        if extra_records and isinstance(extra_records, list):
            for item in extra_records:
                if hasattr(item, "model_dump"):
                    item = item.model_dump()
                if not isinstance(item, dict):
                    continue
                m_type = item.get("metric_type")
                val = item.get("value")
                item_ts = item.get("timestamp", rec_time)
                item_pkg = item.get("source_package", source_pkg)
                item_unit = item.get("unit", "")

                # Validate freshness of individual record
                item_fresh, _ = cls.check_freshness(item_ts)
                if not item_fresh or val is None or not isinstance(val, (int, float)):
                    continue

                if m_type in ("sleep", "sleep_hours"):
                    if 0.5 <= float(val) <= 18:
                        verified["sleep_hours"] = float(val)
                        if "sleep_hours" in missing:
                            missing.remove("sleep_hours")
                        if "sleep_hours" not in consumed:
                            consumed.append("sleep_hours")
                        sleep_status = "available"

                item_id = item.get("record_id") or hashlib.sha256(f"{m_type}:{item_ts}:{val}:{item_pkg}".encode()).hexdigest()[:24]
                default_aggr = "interval" if m_type == "steps" else ("session" if m_type in ("sleep", "sleep_hours") else "instantaneous")
                item_aggr = item.get("aggregation_type", default_aggr)
                discrete_records.append({
                    "record_id": item_id,
                    "metric_type": m_type,
                    "value": float(val),
                    "unit": item_unit or ("hours" if m_type in ("sleep", "sleep_hours") else ""),
                    "timestamp": float(item_ts),
                    "source_package": item_pkg,
                    "device_model": item.get("device_model", device),
                    "acquisition_method": item.get("acquisition_method", acq_method),
                    "aggregation_type": item_aggr
                })

        logger.info(
            "Wearable telemetry ingestion summary: source=%s, records=%d, consumed=%s, missing=%s, sleep_status=%s",
            source_pkg, len(discrete_records), consumed, missing, sleep_status
        )

        return {
            "status": "valid" if (is_fresh and consumed) else ("stale" if (not is_fresh and consumed) else "no_data_yet"),
            "is_fresh": is_fresh,
            "freshness_description": freshness_desc,
            "device": device,
            "source_package": source_pkg,
            "acquisition_method": acq_method,
            "verified_signals": verified if is_fresh else {},
            "signals": verified if is_fresh else {},  # for full backward compatibility
            "consumed_metrics": consumed if is_fresh else [],
            "missing_metrics": missing,
            "discrete_records": discrete_records if is_fresh else [],
            "timestamp": rec_time,
            "sleep_status": sleep_status
        }

    @classmethod
    def get_user_telemetry_summary(cls, user_id: int) -> Dict[str, Any]:
        """
        Retrieves the authenticated user's latest wearable telemetry measurements,
        preserving measurement timestamps, units, provenance, and freshness.
        Distinguishes missing vs stale vs available metrics without fabricating data.
        """
        import src.database.db as db
        records = db.get_user_telemetry_records(user_id, limit=60)
        state = db.get_user_state(user_id)
        baselines = state.get("telemetry_baselines", {}) if state else {}

        # Organize by latest record for each metric_type
        latest_by_type: Dict[str, Dict[str, Any]] = {}
        for r in records:
            m_type = r.get("metric_type")
            if m_type and m_type not in latest_by_type:
                latest_by_type[m_type] = r

        # Helper to format a metric dict
        def _build_metric_entry(metric_name: str, preferred_types: List[str], baseline_keys: List[str], default_unit: str):
            rec = None
            for p in preferred_types:
                if p in latest_by_type:
                    rec = latest_by_type[p]
                    break

            # Fallback to targeted DB query if metric was starved out by high-frequency readings (e.g. sleep vs heart rate)
            if not rec:
                for p in preferred_types:
                    targeted_recs = db.get_user_telemetry_records(user_id, metric_type=p, limit=1)
                    if targeted_recs:
                        rec = targeted_recs[0]
                        latest_by_type[p] = rec
                        break

            if rec:
                val = rec["metric_value"]
                unit = rec["unit"] or default_unit
                rec_at = rec["recorded_at"]
                ing_at = rec.get("ingested_at", rec_at)
                is_fresh, freshness_desc = cls.check_freshness(rec_at)
                return {
                    "status": "available",
                    "value": val,
                    "unit": unit,
                    "recorded_at": rec_at,
                    "ingested_at": ing_at,
                    "is_fresh": is_fresh,
                    "freshness_description": freshness_desc,
                    "source_package": rec.get("source_package", "com.google.android.apps.healthdata"),
                    "device_model": rec.get("device_model", "Fastrack Noir Charm"),
                    "provenance": rec.get("provenance", "health_connect_import")
                }

            # Check baselines fallback if no discrete record
            for bk in baseline_keys:
                if bk in baselines and baselines[bk] is not None:
                    val = baselines[bk]
                    return {
                        "status": "baseline_available",
                        "value": val,
                        "unit": default_unit,
                        "recorded_at": None,
                        "ingested_at": None,
                        "is_fresh": True,
                        "freshness_description": "stored baseline",
                        "source_package": "com.fastrack.smartworld",
                        "device_model": "Fastrack Noir Charm",
                        "provenance": "health_connect_baseline"
                    }

            return {
                "status": "unavailable",
                "value": None,
                "unit": default_unit,
                "recorded_at": None,
                "ingested_at": None,
                "is_fresh": False,
                "freshness_description": "no_data",
                "source_package": None,
                "device_model": None,
                "provenance": None
            }

        hr_entry = _build_metric_entry("heart_rate", ["heart_rate", "resting_hr", "resting_heart_rate"], ["heart_rate_bpm", "resting_hr"], "bpm")
        spo2_entry = _build_metric_entry("spo2", ["spo2", "spo2_pct", "blood_oxygen"], ["spo2_pct"], "%")
        steps_entry = _build_metric_entry("steps", ["steps", "steps_daily_summary", "steps_total"], ["steps_total"], "count")
        
        # Compute verified canonical daily steps using single authoritative aggregation service
        from src.perception.step_aggregation import get_canonical_daily_steps
        latest_step_rec = next((r for r in records if r.get("metric_type") in ("steps", "steps_daily_summary", "steps_total")), None)
        target_step_date = None
        if latest_step_rec and latest_step_rec.get("recorded_at"):
            target_step_date = datetime.datetime.fromtimestamp(latest_step_rec["recorded_at"]).strftime("%Y-%m-%d")

        step_agg = get_canonical_daily_steps(user_id, date_str=target_step_date)
        verified_daily_steps = step_agg.get("steps", 0)
        if verified_daily_steps > 0:
            steps_entry["value"] = verified_daily_steps
            steps_entry["status"] = "available"
            steps_entry["daily_total"] = verified_daily_steps
            steps_entry["date"] = step_agg.get("date")
            if step_agg.get("measured_at"):
                steps_entry["recorded_at"] = step_agg["measured_at"]
            if step_agg.get("source_package"):
                steps_entry["provenance"] = step_agg["source_package"]


        # Check for latest interval record
        latest_interval_row = next((r for r in records if r.get("metric_type") == "steps" and (r.get("aggregation_type") == "interval" or r.get("metric_value", 0) < 1000)), None)
        if latest_interval_row:
            steps_entry["latest_interval"] = {
                "steps": int(latest_interval_row["metric_value"]),
                "recorded_at": latest_interval_row["recorded_at"],
                "unit": "count"
            }


        sleep_entry = _build_metric_entry("sleep", ["sleep", "sleep_hours"], ["sleep_hours"], "hours")
        stress_entry = _build_metric_entry("stress", ["stress"], ["stress"], "level")

        # Specific unavailability reasons for sleep and stress per requirements
        if sleep_entry["status"] == "unavailable":
            sleep_entry["reason"] = "No overnight sleep cycle recorded yet from companion app. Sleep tracking requires wearing the watch through the night."
        if stress_entry["status"] == "unavailable":
            stress_entry["reason"] = "Stress monitoring is not measured or provided by Fastrack Noir Charm / companion app. Metric is not fabricated or inferred."

        # Detect active device & sync status
        has_any_records = len(records) > 0
        latest_rec_time = max([r["recorded_at"] for r in records]) if records else None
        latest_ingest_time = max([r["ingested_at"] for r in records if r.get("ingested_at")]) if records else None

        active_device = "Fastrack Noir Charm"
        active_pkg = "com.fastrack.smartworld"
        if records:
            active_device = records[0].get("device_model", active_device)
            active_pkg = records[0].get("source_package", active_pkg)

        now = time.time()
        is_active_sync = False
        is_upstream_stale = False
        stale_warning_msg = None

        if latest_rec_time:
            is_active_sync, _ = cls.check_freshness(latest_rec_time, max_age_hours=36.0)
            age_sec = now - latest_rec_time
            if age_sec > 1800.0: # > 30 minutes old
                is_upstream_stale = True
                age_mins = int(age_sec / 60)
                stale_warning_msg = (
                    f"Upstream Fastrack Smart World data appears stale ({age_mins} minutes since last watch measurement). "
                    "Please open Fastrack Smart World companion app on your phone to pull fresh records from your Noir Charm."
                )

        return {
            "user_id": user_id,
            "has_wearable_data": has_any_records or bool(baselines),
            "record_count": len(records),
            "device_model": active_device,
            "source_package": active_pkg,
            "is_sync_active": is_active_sync,
            "is_upstream_stale": is_upstream_stale,
            "stale_warning_message": stale_warning_msg,
            "last_recorded_at": latest_rec_time,
            "last_ingested_at": latest_ingest_time,
            "metrics": {
                "heart_rate": hr_entry,
                "spo2": spo2_entry,
                "steps": steps_entry,
                "sleep": sleep_entry,
                "stress": stress_entry
            }
        }

    @classmethod
    def format_telemetry_for_prompt(cls, summary: Dict[str, Any]) -> str:
        """
        Formats a compact, high-signal Markdown context block for the AI reasoning prompt.
        """
        if not summary.get("has_wearable_data"):
            return (
                "AUTHENTICATED WEARABLE TELEMETRY:\n"
                "- Status: No wearable device has synced data to this account yet.\n"
                "- Guidance: If the user asks about heart rate, steps, or biometrics, explain that "
                "no smartwatch records have been synced yet, and advise syncing via the Fastrack companion app."
            )

        m = summary.get("metrics", {})
        dev = summary.get("device_model", "Fastrack Noir Charm")
        pkg = summary.get("source_package", "com.fastrack.smartworld")

        lines = [
            f"AUTHENTICATED WEARABLE TELEMETRY ({dev} via Android Health Connect):",
            f"- Device: {dev} (Source Package: {pkg})",
            f"- Sync Status: {'Active & Fresh' if summary.get('is_sync_active') else 'Last sync recorded previously'}"
        ]

        # Heart rate
        hr = m.get("heart_rate", {})
        if hr.get("status") in ("available", "baseline_available"):
            ts_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(hr['recorded_at'])) if hr.get('recorded_at') else "latest baseline"
            lines.append(f"- Heart Rate: {hr['value']} {hr['unit']} (Measured: {ts_str} | Freshness: {hr['freshness_description']})")
        else:
            lines.append("- Heart Rate: Unavailable (No readings synced yet)")

        # SpO2
        spo2 = m.get("spo2", {})
        if spo2.get("status") in ("available", "baseline_available"):
            ts_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(spo2['recorded_at'])) if spo2.get('recorded_at') else "latest baseline"
            lines.append(f"- Blood Oxygen (SpO₂): {spo2['value']}{spo2['unit']} (Measured: {ts_str} | Freshness: {spo2['freshness_description']})")
        else:
            lines.append("- Blood Oxygen (SpO₂): Unavailable (No readings synced yet)")

        # Steps
        steps = m.get("steps", {})
        if steps.get("status") in ("available", "baseline_available"):
            ts_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(steps['recorded_at'])) if steps.get('recorded_at') else "today's total"
            lines.append(f"- Daily Steps: {int(steps['value'])} steps (Recorded: {ts_str} | Freshness: {steps['freshness_description']})")
        else:
            lines.append("- Daily Steps: Unavailable (No step count synced yet)")

        # Sleep
        sleep = m.get("sleep", {})
        if sleep.get("status") == "available":
            lines.append(f"- Sleep Duration: {sleep['value']} hours (Measured: {time.strftime('%Y-%m-%d', time.localtime(sleep['recorded_at']))})")
        else:
            lines.append(f"- Sleep Data: UNAVAILABLE ({sleep.get('reason', 'Awaiting overnight cycle')})")

        # Stress
        stress = m.get("stress", {})
        if stress.get("status") == "available":
            lines.append(f"- Stress Level: {stress['value']}")
        else:
            lines.append(f"- Stress Data: UNAVAILABLE ({stress.get('reason', 'Not supported by device')})")

        lines.extend([
            "\nTELEMETRY GUIDELINES FOR ASSISTANT:",
            "1. You HAVE DIRECT ACCESS to the authenticated user's real-time biometrics above.",
            "2. When the user asks about heart rate, steps, or SpO2, give the exact recorded values and timestamps above.",
            "3. If the user asks 'Do you monitor my physical activity?', answer YES, confirm tracking from their Fastrack Noir Charm, and quote their latest step count and heart rate.",
            "4. If the user asks about sleep, explain that sleep monitoring is active but awaiting an overnight cycle; do NOT claim you lack wearable access.",
            "5. If the user asks about stress, explain that the Fastrack Noir Charm does not provide stress metrics; do NOT guess or infer stress from heart rate.",
            "6. NEVER state that you cannot access real-time biometrics when valid readings are listed above."
        ])

        return "\n".join(lines)
