import logging
from typing import List, Dict

logger = logging.getLogger("BehaviorEngine")


class AdherenceTracker:
    """
    Module 5b: Behavior Engine & Adherence Tracker.
    Tracks user adherence scores over a rolling window and adapts
    the generated schedule's complexity dynamically (Closed-Loop Adaptation).
    """

    @staticmethod
    def calculate_adherence_score(completed_count: int, recommended_count: int) -> float:
        """
        Computes the Adherence Score (S_adj) as the ratio of completed to recommended tasks.
        Returns a float between 0.0 and 1.0.
        """
        if recommended_count <= 0:
            return 1.0
        score = completed_count / recommended_count
        return round(min(max(score, 0.0), 1.0), 2)

    @staticmethod
    def determine_complexity(rolling_adherence_score: float) -> str:
        """
        Implements Closed-Loop Behavioral Adaptation:
        - When S_adj < 0.5: Simplify the routine to "Anchor Habits" (3-4 essential habits).
        - When S_adj > 0.8: Introduce advanced Sattva-enhancing practices.
        - Otherwise: Generate a "Moderate" complexity schedule.
        """
        if rolling_adherence_score < 0.5:
            logger.info(f"Adherence Score S_adj ({rolling_adherence_score}) is below 0.50. Scaling down to 'Anchor Habits'.")
            return "Anchor Habits"
        elif rolling_adherence_score >= 0.8:
            logger.info(f"Adherence Score S_adj ({rolling_adherence_score}) is >= 0.80. Scaling up to 'Advanced' Sattva practices.")
            return "Advanced"
        else:
            logger.info(f"Adherence Score S_adj ({rolling_adherence_score}) is stable. Maintaining 'Moderate' complexity.")
            return "Moderate"

    @staticmethod
    def generate_behavior_nudge(rolling_adherence_score: float) -> Dict[str, str]:
        """
        Generates EAST (Easy, Attractive, Social, Timely) aligned behavioral nudges.
        """
        if rolling_adherence_score < 0.5:
            return {
                "title": "Let's focus on the essentials",
                "message": "We've simplified your routine to just three simple Anchor Habits today. Small actions, big impact!"
            }
        elif rolling_adherence_score >= 0.8:
            return {
                "title": "Sattva Flow Unlocked!",
                "message": "Excellent consistency this week. We have introduced advanced Sattva-enhancing breathing practices to elevate your energy."
            }
        else:
            return {
                "title": "Great progress!",
                "message": "Keep going! Your daily routine is perfectly tuned to support your active Dosha balance today."
            }
class BehaviorEngine:
    pass
