import time
from typing import List, Dict, Any
from src.models import DinacharyaSchedule

class NotificationScheduler:
    """
    Schedules habit reminder notifications based on daily Dinacharya schedule blocks
    and user adherence history (EAST behavioral nudges).
    """

    @staticmethod
    def generate_pending_notifications(schedule: DinacharyaSchedule, user_id: str) -> List[Dict[str, Any]]:
        notifications = []
        now = time.time()

        # Morning notifications
        for practice in schedule.morning_block:
            notifications.append({
                "id": f"notif_{user_id}_{practice.name.replace(' ', '_')}_morning",
                "title": f"⏰ Morning Routine: {practice.name}",
                "body": f"Time: {practice.time_slot}. {practice.description}",
                "scheduled_time": practice.time_slot,
                "type": "morning_reminder",
                "practice_name": practice.name,
                "created_at": now
            })

        # Midday notifications
        for practice in schedule.midday_block:
            notifications.append({
                "id": f"notif_{user_id}_{practice.name.replace(' ', '_')}_midday",
                "title": f"☀️ Midday Practice: {practice.name}",
                "body": f"Time: {practice.time_slot}. {practice.description}",
                "scheduled_time": practice.time_slot,
                "type": "midday_reminder",
                "practice_name": practice.name,
                "created_at": now
            })

        # Evening notifications
        for practice in schedule.evening_block:
            notifications.append({
                "id": f"notif_{user_id}_{practice.name.replace(' ', '_')}_evening",
                "title": f"🌙 Evening Wind-down: {practice.name}",
                "body": f"Time: {practice.time_slot}. {practice.description}",
                "scheduled_time": practice.time_slot,
                "type": "evening_reminder",
                "practice_name": practice.name,
                "created_at": now
            })

        return notifications
