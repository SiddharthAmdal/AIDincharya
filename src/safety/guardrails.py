import os
import copy
import logging
from typing import List, Dict, Any, Optional
from src.models import DinacharyaSchedule, DoshaProfile, Practice

logger = logging.getLogger("SafetyEngine")

EMERGENCY_NUMBER = os.getenv("EMERGENCY_NUMBER", "112")
EMERGENCY_REGION = os.getenv("EMERGENCY_REGION", "local emergency dispatch")


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

    @staticmethod
    def evaluate_query_safety(user_text: str, context: Optional[str] = None) -> Dict[str, Any]:
        """
        Symbolic input guardrail validating user queries against acute emergencies,
        pharmaceutical prescription requests, dangerous medical contraindications,
        and prompt injection attacks.
        Returns safety verdict, action, and response message if blocked/redirected.
        """
        text_lower = user_text.lower()
        combined = f"{text_lower} {(context or '').lower()}"

        # 1. Acute Medical Emergencies
        emergency_triggers = [
            "chest pain", "crushing chest", "left arm", "difficulty breathing",
            "slurred speech", "facial drooping", "face is drooping", "arm is limp", "cannot move the right side",
            "rebound tenderness", "lower right abdominal", "appendicitis",
            "suicide", "kill myself", "swallowed bleach", "poison",
            "throat is closing", "throat closing up", "lips are swelling", "anaphylaxis",
            "coughing up blood", "vomiting blood", "severe hemorrhage", "sudden vision loss"
        ]
        if any(term in combined for term in emergency_triggers):
            emergency_num = os.getenv("EMERGENCY_NUMBER", "112")
            region_note = os.getenv("EMERGENCY_REGION", "local emergency dispatch")
            return {
                "is_safe": False,
                "action": "emergency_redirection",
                "category": "acute_medical_emergency",
                "message": (
                    "⚠️ **CRITICAL MEDICAL ALERT**: Your message indicates potential acute medical symptoms that require "
                    "immediate emergency medical evaluation. AI Dincharya is an Ayurvedic lifestyle routine advisor and CANNOT treat or evaluate emergencies. "
                    f"Please call **{emergency_num}** ({region_note}) or your local emergency hotline (e.g. 112/911/999) or proceed to the nearest hospital emergency department immediately."
                )
            }

        # 2. Prompt Injection / System Jailbreak / Secret Exfiltration
        injection_triggers = [
            "ignore all previous", "ignore previous instructions", "you are now dan", "dan mode",
            "system instruction override", "print out your entire system prompt", "secret keys",
            "database credentials", "push subscription endpoints of other users", "list of all registered users",
            "select * from users", "delete from users",
            "disregard all previous safety", "developer mode active", "bypass all restrictions",
            "reveal system prompt", "assistant mode disabled"
        ]
        if any(term in combined for term in injection_triggers):
            return {
                "is_safe": False,
                "action": "refusal_prompt_injection",
                "category": "prompt_injection_jailbreak",
                "message": (
                    "I cannot comply with requests that attempt to override safety protocols, exfiltrate internal system prompts, "
                    "or access protected user data. How can I assist you with your daily Ayurvedic Dinacharya routine safely?"
                )
            }

        # 3. Dangerous Medication Stoppage (Higher risk priority over general out-of-scope prescription requests)
        dangerous_med_triggers = [
            "throw away my insulin", "stop taking insulin", "stop my blood pressure pills", "stop chemotherapy",
            "stop taking my statin", "quit blood thinners", "stop my warfarin", "double my dose of insulin"
        ]
        if any(term in text_lower for term in dangerous_med_triggers):
            return {
                "is_safe": False,
                "action": "medical_warning_refusal",
                "category": "dangerous_medical_advice",
                "message": (
                    "⚠️ **SAFETY WARNING**: Do not stop or alter essential prescribed medications (such as insulin, blood pressure drugs, statins, or anticoagulants) "
                    "without the direct supervision of your licensed physician or endocrinologist. Ayurvedic lifestyle practices are complementary "
                    "and must never abruptly replace life-sustaining medical therapies."
                )
            }

        # 4. Prescription Writing / Allopathic Drug Scope
        prescription_triggers = [
            "write me a prescription", "prescription for", "prescribe", "refill",
            "dispense", "amoxicillin", "metformin", "antibiotic dosage", "prescribe me"
        ]
        if any(term in text_lower for term in prescription_triggers) and not any(term in text_lower for term in ["ayurveda", "routine", "herbal"]):
            return {
                "is_safe": False,
                "action": "refusal_out_of_scope",
                "category": "prescription_out_of_scope",
                "message": (
                    "I am an Ayurvedic lifestyle routine advisor and cannot write prescriptions or dispense pharmaceutical medications. "
                    "Please consult a licensed medical physician or licensed pharmacist for pharmaceutical prescriptions."
                )
            }

        # 5. Extreme Contraindication Combinations (e.g. Pregnancy + Fever + Sauna/Dry Fasting)
        if "pregnant" in text_lower and ("fever" in text_lower or "sauna" in text_lower or "fasting" in text_lower):
            return {
                "is_safe": False,
                "action": "clinical_contraindication_refusal",
                "category": "contraindicated_ayurvedic_practice",
                "message": (
                    "⚠️ **CONTRAINDICATION**: Rigorous heat therapies (Swedana/sauna) and dry water fasting are strictly contraindicated "
                    "during pregnancy, especially in the presence of fever. Please consult your obstetrician and a qualified Vaidya for gentle maternal care."
                )
            }

        if any(term in text_lower for term in ["ulcer", "gastritis", "acid reflux"]) and any(term in text_lower for term in ["cayenne", "chili", "hot pepper"]):
            return {
                "is_safe": False,
                "action": "contraindication_reversal",
                "category": "clinical_contraindication_override",
                "message": (
                    "⚠️ **CONTRAINDICATION**: Pungent, heating spices such as cayenne pepper and chili directly aggravate Pitta dosha and are strictly "
                    "contraindicated during active peptic ulcer disease and severe acid reflux. Cooling, soothing practices are recommended instead."
                )
            }

        return {
            "is_safe": True,
            "action": "safe_helpful_response",
            "category": "benign_health_query",
            "message": None
        }

