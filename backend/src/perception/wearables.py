import time
from typing import Dict, Any, Optional

class WearableSyncEngine:
    """
    Ingest & normalize telemetry payloads from Apple HealthKit (HKQuantityType),
    Google Health Connect, and Garmin/Oura Cloud APIs into standard Dinacharya telemetry.
    """

    @staticmethod
    def parse_apple_healthkit(payload: Dict[str, Any]) -> Dict[str, float]:
        """
        Parses Apple HealthKit JSON payload:
        - HKQuantityTypeIdentifierHeartRateVariabilitySDNN -> hrv_ms
        - HKQuantityTypeIdentifierRestingHeartRate -> resting_hr
        - HKCategoryTypeIdentifierSleepAnalysis -> sleep_hours
        - HKQuantityTypeIdentifierBodyTemperature -> body_temp_c
        """
        hrv = payload.get("HKQuantityTypeIdentifierHeartRateVariabilitySDNN", {}).get("value", 55.0)
        rhr = payload.get("HKQuantityTypeIdentifierRestingHeartRate", {}).get("value", 70.0)
        sleep = payload.get("HKCategoryTypeIdentifierSleepAnalysis", {}).get("value", 7.5)
        temp = payload.get("HKQuantityTypeIdentifierBodyTemperature", {}).get("value", 36.8)

        return {
            "hrv_ms": float(hrv),
            "resting_hr": float(rhr),
            "sleep_hours": float(sleep),
            "body_temp_c": float(temp),
            "synced_at": time.time()
        }

    @staticmethod
    def parse_google_health_connect(payload: Dict[str, Any]) -> Dict[str, float]:
        """
        Parses Google Health Connect JSON payload:
        - HeartRateVariabilityRmssdRecord -> hrv_ms
        - RestingHeartRateRecord -> resting_hr
        - SleepSessionRecord -> sleep_hours
        - BodyTemperatureRecord -> body_temp_c
        """
        hrv = payload.get("hrv_rmssd_ms", payload.get("hrv", 55.0))
        rhr = payload.get("resting_hr_bpm", payload.get("rhr", 70.0))
        sleep = payload.get("sleep_duration_hours", payload.get("sleep", 7.5))
        temp = payload.get("body_temperature_celsius", payload.get("temp", 36.8))

        return {
            "hrv_ms": float(hrv),
            "resting_hr": float(rhr),
            "sleep_hours": float(sleep),
            "body_temp_c": float(temp),
            "synced_at": time.time()
        }

    @staticmethod
    def normalize_vendor_payload(provider: str, raw_payload: Dict[str, Any]) -> Dict[str, float]:
        provider_lower = provider.lower()
        if "apple" in provider_lower or "healthkit" in provider_lower:
            return WearableSyncEngine.parse_apple_healthkit(raw_payload)
        elif "google" in provider_lower or "healthconnect" in provider_lower:
            return WearableSyncEngine.parse_google_health_connect(raw_payload)
        else:
            # Standard Dinacharya dictionary fallback
            return {
                "hrv_ms": float(raw_payload.get("hrv_ms", 55.0)),
                "resting_hr": float(raw_payload.get("resting_hr", 70.0)),
                "sleep_hours": float(raw_payload.get("sleep_hours", 7.5)),
                "body_temp_c": float(raw_payload.get("body_temp_c", 36.8)),
                "synced_at": time.time()
            }
