import copy
import logging
from typing import List, Dict, Any, Optional
from src.models import DinacharyaSchedule, DoshaProfile, Practice

logger = logging.getLogger("SafetyEngine")


class ClinicalRuleEngine:
    """
    Module 5a: Safety Guardrail Domain.
    A symbolic rule engine enforcing strict clinical contraindications from classical Ayurvedic texts.
    Acts as a mandatory deterministic final filter on every generated or adapted schedule.
    No LLM output or user prompt can bypass this layer.
    """

    @staticmethod
    def validate(schedule: DinacharyaSchedule, profile: DoshaProfile) -> DinacharyaSchedule:
        """
        Validates schedule blocks for active contraindications based on the user's health profile.
        Removes contraindicated practices and replaces them with safe traditional alternatives.
        Backward-compatible interface returning the validated DinacharyaSchedule.
        """
        result = ClinicalRuleEngine.evaluate_safety(schedule, profile)
        return result["schedule"]

    @staticmethod
    def evaluate_safety(
        schedule: DinacharyaSchedule,
        profile: DoshaProfile,
        symptoms: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Executes the classical contraindication rule matrix against the schedule.
        Returns the validated schedule along with a structured audit trail of all applied overrides.
        """
        logger.info(f"Running comprehensive clinical safety checks for user {schedule.user_id}")
        overrides_applied: List[Dict[str, Any]] = []

        # Gather health triggers
        has_fever = False
        pitta_aggravated = False
        vata_aggravated = False
        indigestion_present = False

        if profile and profile.vikriti_flags:
            has_fever = bool(profile.vikriti_flags.has_fever)
            pitta_aggravated = bool(profile.vikriti_flags.pitta_aggravated)
            vata_aggravated = bool(profile.vikriti_flags.vata_aggravated)

        # Check symptoms list if provided
        symptom_text = " ".join([s.lower() for s in (symptoms or [])])
        if "fever" in symptom_text or "temp" in symptom_text or "jwara" in symptom_text:
            has_fever = True
        if any(term in symptom_text for term in ["acid", "reflux", "burning", "pitta", "heat", "inflammation"]):
            pitta_aggravated = True
        if any(term in symptom_text for term in ["insomnia", "sleepless", "anxiety", "restless", "vata"]):
            vata_aggravated = True
        if any(term in symptom_text for term in ["indigestion", "ajeerna", "bloating", "heaviness", "nausea", "ama"]):
            indigestion_present = True

        rules_checked = [
            "Rule 1: Nava Jwara (Acute Fever) Contraindications",
            "Rule 2: Pitta Prakopa (Heat / Hyperacidity) Contraindications",
            "Rule 3: Vata Vriddhi / Anidra (Severe Insomnia / Anxiety) Contraindications",
            "Rule 4: Ajeerna / Ama (Acute Indigestion / Heaviness) Contraindications"
        ]

        # Rule 1: Fever (Nava Jwara) Contraindications
        # Classical Source: Ashtanga Hridayam Sutrasthana Ch. 1 & Chikitsasthana Ch. 1
        # During acute fever, oil therapies (Abhyanga, Nasya) and heavy exertion are strictly contraindicated.
        if has_fever:
            logger.warning(f"Active Fever (Nava Jwara) detected for user {schedule.user_id}. Enforcing safety overrides.")
            
            fever_morning_rep = Practice(
                name="Nava Jwara Rest & Hydration",
                time_slot="06:30 - 07:00",
                duration_minutes=30,
                description="Rest in a comfortable room. Sip warm water infused with dry ginger or coriander seeds.",
                rationale="[SAFETY OVERRIDE] Abhyanga and Nasya are strictly contraindicated during acute fever (Nava Jwara) in Ashtanga Hridayam. Oil applications block channels and trap thermal deviations. Replaced with metabolic rest and mild agni-kindling hydration."
            )
            schedule.morning_block, morning_applied = ClinicalRuleEngine._override_contraindicated_practices(
                block=schedule.morning_block,
                contraindicated_names=["abhyanga", "nasya", "vyayama", "exercise", "workout"],
                replacement=fever_morning_rep,
                rule_name="Nava Jwara (Fever) Override",
                block_name="morning_block"
            )
            overrides_applied.extend(morning_applied)

            fever_midday_rep = Practice(
                name="Midu Langhana (Light Fasting Rest)",
                time_slot="12:00 - 12:30",
                duration_minutes=30,
                description="Consume light gruel (Manda/Peya) or warm herbal teas. Rest quietly.",
                rationale="[SAFETY OVERRIDE] Heavy physical exertion and dense meals are contraindicated during fever. Agni (digestion) is highly weakened during Nava Jwara."
            )
            schedule.midday_block, midday_applied = ClinicalRuleEngine._override_contraindicated_practices(
                block=schedule.midday_block,
                contraindicated_names=["abhyanga", "nasya", "workout", "gym", "heavy lunch"],
                replacement=fever_midday_rep,
                rule_name="Nava Jwara (Fever) Override",
                block_name="midday_block"
            )
            overrides_applied.extend(midday_applied)

            fever_evening_rep = Practice(
                name="Early Deep Rest",
                time_slot="20:00 - 20:30",
                duration_minutes=30,
                description="Avoid all stimulation, dim lights, sip lukewarm water, and sleep early.",
                rationale="[SAFETY OVERRIDE] Sleep and complete sensory withdrawal are primary traditional therapies for fever resolution."
            )
            schedule.evening_block, evening_applied = ClinicalRuleEngine._override_contraindicated_practices(
                block=schedule.evening_block,
                contraindicated_names=["abhyanga", "nasya", "late night", "exercise"],
                replacement=fever_evening_rep,
                rule_name="Nava Jwara (Fever) Override",
                block_name="evening_block"
            )
            overrides_applied.extend(evening_applied)

        # Rule 2: Pitta Aggravation & Hyperacidity Contraindications
        # Classical Source: Caraka Samhita Chikitsasthana Ch. 3
        # Heating yogic practices (Bhastrika, Kapalabhati) and direct intense sun exposure aggravate thermal pathology.
        if pitta_aggravated and not has_fever:
            pitta_rep = Practice(
                name="Sheetali Pranayama & Shaded Rest",
                time_slot="12:00 - 12:30",
                duration_minutes=20,
                description="Perform cooling Sheetali/Sitkari breathwork in a shaded room. Sip cool coriander-infused water.",
                rationale="[SAFETY OVERRIDE] Heating pranayama (Bhastrika/Kapalabhati) and direct midday solar exertion are contraindicated during active Pitta aggravation (Caraka Samhita). Replaced with cooling sheetali pranayama."
            )
            schedule.midday_block, pitta_applied = ClinicalRuleEngine._override_contraindicated_practices(
                block=schedule.midday_block,
                contraindicated_names=["bhastrika", "kapalabhati", "sun salutation", "surya namaskar", "hot sauna", "spicy"],
                replacement=pitta_rep,
                rule_name="Pitta Prakopa Override",
                block_name="midday_block"
            )
            overrides_applied.extend(pitta_applied)

        # Rule 3: Severe Vata Aggravation & Acute Insomnia Contraindications
        # Classical Source: Ashtanga Hridayam Sutrasthana Ch. 2
        # Cold baths, late evening cardio, and high stimulation aggravate Vata volatility and eliminate Nidra.
        if vata_aggravated and not has_fever:
            vata_rep = Practice(
                name="Padabhyanga (Foot Oil Massage) & Yoga Nidra",
                time_slot="21:00 - 21:30",
                duration_minutes=25,
                description="Gently massage warm sesame oil into the soles of the feet, followed by guided Yoga Nidra deep relaxation.",
                rationale="[SAFETY OVERRIDE] Cold showers and intense late-evening exercise aggravate Vata hyperactivity and destroy sleep architecture (Ashtanga Hridayam). Replaced with grounding Padabhyanga and Yoga Nidra."
            )
            schedule.evening_block, vata_applied = ClinicalRuleEngine._override_contraindicated_practices(
                block=schedule.evening_block,
                contraindicated_names=["cold shower", "cold bath", "hiit", "intense cardio", "screen time", "late workout"],
                replacement=vata_rep,
                rule_name="Vata / Insomnia Override",
                block_name="evening_block"
            )
            overrides_applied.extend(vata_applied)

        # Rule 4: Acute Indigestion (Ajeerna / Ama) Contraindications
        # Classical Source: Caraka Samhita Vimanasthana Ch. 2
        # Ingesting heavy solid breakfasts or cold liquids during acute indigestion creates toxic Ama.
        if indigestion_present and not has_fever:
            indigestion_rep = Practice(
                name="Ushnodaka (Warm Water Sips) & Agni Kindle",
                time_slot="07:00 - 07:30",
                duration_minutes=15,
                description="Sip freshly boiled hot water (Ushnodaka) with dry ginger. Refrain from heavy solids until appetite awakens.",
                rationale="[SAFETY OVERRIDE] Heavy breakfast and cold drinks during acute indigestion (Ajeerna) generate toxic Ama. Replaced with therapeutic Ushnodaka hot water sips."
            )
            schedule.morning_block, ajeerna_applied = ClinicalRuleEngine._override_contraindicated_practices(
                block=schedule.morning_block,
                contraindicated_names=["heavy breakfast", "cold smoothie", "cold milk", "buffet", "protein shake"],
                replacement=indigestion_rep,
                rule_name="Ajeerna (Indigestion) Override",
                block_name="morning_block"
            )
            overrides_applied.extend(ajeerna_applied)

        return {
            "schedule": schedule,
            "overrides_applied": overrides_applied,
            "is_safe": True,
            "rules_checked": rules_checked
        }

    @staticmethod
    def _override_contraindicated_practices(
        block: List[Practice],
        contraindicated_names: List[str],
        replacement: Practice,
        rule_name: str = "Safety Contraindication Override",
        block_name: str = "block"
    ) -> tuple[List[Practice], List[Dict[str, Any]]]:
        """
        Helper method that scans a list of practices, filters out any contraindicated ones,
        and injects a safe, deep-copied replacement practice.
        """
        cleaned_block = []
        replaced_practices: List[str] = []
        overrides_logged: List[Dict[str, Any]] = []
        first_replaced_slot: Optional[str] = None

        for practice in block:
            name_lower = practice.name.lower()
            if any(term in name_lower for term in contraindicated_names):
                replaced_practices.append(practice.name)
                if first_replaced_slot is None and practice.time_slot:
                    first_replaced_slot = practice.time_slot
                logger.info(f"Safety Override [{rule_name}]: Removed contraindicated practice '{practice.name}' from {block_name}")
                overrides_logged.append({
                    "rule": rule_name,
                    "block": block_name,
                    "removed_practice": practice.name,
                    "replacement_practice": replacement.name,
                    "rationale": replacement.rationale
                })
                continue
            cleaned_block.append(practice)

        # Inject the deep-copied replacement if we removed any item
        if replaced_practices:
            safe_replacement = copy.deepcopy(replacement)
            if first_replaced_slot:
                safe_replacement.time_slot = first_replaced_slot
            cleaned_block.append(safe_replacement)
            
            # Sort practices by time_slot string to maintain chronological order
            cleaned_block.sort(key=lambda x: x.time_slot or "")

        return cleaned_block, overrides_logged
