import logging
from typing import List
from src.models import DinacharyaSchedule, DoshaProfile, Practice

logger = logging.getLogger("SafetyEngine")


class ClinicalRuleEngine:
    """
    Module 5a: Safety Guardrail Domain.
    A symbolic rule engine enforcing strict clinical contraindications from classical Ayurvedic texts.
    Acts as a mandatory final filter on every generated schedule. No LLM output can bypass this layer.
    """

    @staticmethod
    def validate(schedule: DinacharyaSchedule, profile: DoshaProfile) -> DinacharyaSchedule:
        """
        Validates the schedule blocks for active contraindications based on the user's health profile.
        Removes contraindicated practices and replaces them with safe traditional alternatives.
        """
        logger.info(f"Running clinical safety checks for user {schedule.user_id}")
        
        has_fever = profile.vikriti_flags.has_fever

        # Rule 1: Fever (Nava Jwara) Contraindications
        # During acute fever, Abhyanga (oil massage) and Nasya (nasal administration) are strictly forbidden
        # as they block channels (Srotas) and suppress the body's natural heat-expelling mechanism.
        if has_fever:
            logger.warning(f"Active Fever (Nava Jwara) detected for user {schedule.user_id}. Enforcing Abhyanga and Nasya overrides.")
            
            schedule.morning_block = ClinicalRuleEngine._override_contraindicated_practices(
                block=schedule.morning_block,
                contraindicated_names=["abhyanga", "nasya"],
                replacement=Practice(
                    name="Nava Jwara Rest & Hydration",
                    time_slot="06:30 - 07:00",
                    duration_minutes=30,
                    description="Rest in a comfortable room. Sip warm water infused with dry ginger or coriander seeds.",
                    rationale="[SAFETY OVERRIDE] Abhyanga and Nasya are strictly contraindicated during acute fever (Nava Jwara) in Ashtanga Hridayam. Oil applications block channels and lock in thermal deviations. Replacing with metabolic rest and mild agni-kindling hydration."
                )
            )

            # Check other blocks just in case the LLM placed Abhyanga/Nasya elsewhere
            schedule.midday_block = ClinicalRuleEngine._override_contraindicated_practices(
                block=schedule.midday_block,
                contraindicated_names=["abhyanga", "nasya"],
                replacement=Practice(
                    name="Midu Langhana (Light Fasting Rest)",
                    time_slot="12:00 - 12:30",
                    duration_minutes=30,
                    description="Consume light gruel (Manda/Peya) or warm herbal teas. Rest quietly.",
                    rationale="[SAFETY OVERRIDE] Heavy physical exertion and dense meals are contraindicated during fever. Agni (digestion) is highly weakened during Nava Jwara."
                )
            )
            
            schedule.evening_block = ClinicalRuleEngine._override_contraindicated_practices(
                block=schedule.evening_block,
                contraindicated_names=["abhyanga", "nasya"],
                replacement=Practice(
                    name="Early Deep Rest",
                    time_slot="20:00 - 20:30",
                    duration_minutes=30,
                    description="Avoid all stimulation, dim lights, sip lukewarm water, and sleep early.",
                    rationale="[SAFETY OVERRIDE] Sleep and complete sensory withdrawal are primary traditional therapies for fever resolution."
                )
            )

        return schedule

    @staticmethod
    def _override_contraindicated_practices(
        block: List[Practice],
        contraindicated_names: List[str],
        replacement: Practice
    ) -> List[Practice]:
        """
        Helper method that scans a list of practices, filters out any contraindicated ones,
        and injects a safe replacement practice.
        """
        cleaned_block = []
        replaced = False

        for practice in block:
            name_lower = practice.name.lower()
            # If any contraindicated term is a substring of the practice name, we trigger override
            if any(term in name_lower for term in contraindicated_names):
                replaced = True
                logger.info(f"Safety Override: Removed contraindicated practice '{practice.name}'")
                continue
            cleaned_block.append(practice)

        # Inject the replacement if we removed any item
        if replaced:
            # Sync replacement time slot with typical morning blocks
            replacement.time_slot = "06:30 - 07:00" if block and block == cleaned_block else replacement.time_slot
            cleaned_block.append(replacement)
            
            # Sort practices by time_slot string to keep chronological order
            cleaned_block.sort(key=lambda x: x.time_slot)

        return cleaned_block
