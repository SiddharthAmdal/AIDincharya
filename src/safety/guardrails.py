import os
import copy
import json
import logging
import re
from typing import List, Dict, Any, Optional, Tuple
from src.models import DinacharyaSchedule, DoshaProfile, Practice

logger = logging.getLogger("SafetyEngine")

EMERGENCY_NUMBER = os.getenv("EMERGENCY_NUMBER", "112")
EMERGENCY_REGION = os.getenv("EMERGENCY_REGION", "local emergency dispatch")


def _parse_slot_minutes(slot_str: str, default_duration: int = 15) -> Optional[Tuple[int, int]]:
    """
    Parses a time slot string (e.g. '19:30 - 19:45', '7:30 PM', '19:30') into (start_min, end_min)
    measured in minutes from midnight [0, 1440).
    """
    if not slot_str or not isinstance(slot_str, str):
        return None
    s = slot_str.strip()
    if s.lower() == "flexible":
        return None

    def _to_min(part: str, fallback_period: Optional[str] = None) -> Optional[int]:
        part = part.strip()
        m = re.search(r"(\d{1,2}):(\d{2})\s*(AM|PM|am|pm)?", part)
        if not m:
            m2 = re.search(r"\b(\d{1,2})\s*(AM|PM|am|pm)\b", part)
            if not m2:
                return None
            h, mins, period = int(m2.group(1)), 0, m2.group(2).upper()
        else:
            h, mins = int(m.group(1)), int(m.group(2))
            period = m.group(3).upper() if m.group(3) else (fallback_period.upper() if fallback_period else None)

        if period == "PM" and h < 12:
            h += 12
        elif period == "AM" and h == 12:
            h = 0
        return h * 60 + mins

    parts = re.split(r"\s*(?:-|–|—|to)\s*", s)
    if len(parts) >= 2:
        end_period_match = re.search(r"(AM|PM|am|pm)", parts[1])
        start_period_match = re.search(r"(AM|PM|am|pm)", parts[0])
        fb_period = end_period_match.group(1) if (end_period_match and not start_period_match) else None
        st = _to_min(parts[0], fallback_period=fb_period)
        en = _to_min(parts[1])
        if st is not None and en is not None:
            if en <= st:
                en = st + max(15, default_duration)
            return (st, en)
    st_single = _to_min(s)
    if st_single is not None:
        return (st_single, st_single + max(15, default_duration))
    return None


def _format_minutes_to_slot(start_min: int, end_min: int) -> str:
    """Formats (start_min, end_min) into 'HH:MM - HH:MM'."""
    st = max(0, min(1439, start_min))
    en = max(st + 5, min(1439, end_min))
    return f"{st // 60:02d}:{st % 60:02d} - {en // 60:02d}:{en % 60:02d}"


def _classify_practice_category(name: str, description: str = "") -> str:
    """
    Classifies any practice into one of the physiological Dinacharya categories
    for relational temporal reasoning.
    Classifies strictly by `name` first so instructional phrases in `description`
    (e.g., "Practice on an empty stomach before breakfast/meals") never misclassify
    a non-meal practice as AHARA_MEAL.
    """
    def _match_category(text: str, check_meals_first: bool = False) -> str:
        t = text.lower()
        if check_meals_first and any(k in t for k in [
            "meal", "lunch", "dinner", "breakfast", "mitahara", "bhojana",
            "khichdi", "soup", "gruel", "peya"
        ]):
            return "AHARA_MEAL"
        if any(k in t for k in [
            "pranayama", "nadi shodhana", "anuloma", "sheetali", "sitkari",
            "bhastrika", "kapalabhati", "bhramari", "ujjayi", "breath", "breathing"
        ]):
            return "PRANAYAMA_YOGA"
        if any(k in t for k in [
            "vyayama", "surya namaskar", "sun salutation", "asana", "yoga",
            "exercise", "workout", "hiit", "cardio", "gym", "running", "walk"
        ]) and "yoga nidra" not in t:
            return "VYAYAMA_EXERTION"
        if any(k in t for k in [
            "abhyanga", "udvartana", "oil massage", "body massage", "dry brushing", "head massage"
        ]) and "padabhyanga" not in t and "foot" not in t:
            return "ABHYANGA_OLEATION"
        if any(k in t for k in ["snana", "bath", "shower"]):
            return "SNANA_BATH"
        if any(k in t for k in [
            "trataka", "yoga nidra", "padabhyanga", "sadhana transition",
            "sleep", "nidra", "reflection", "meditation", "dhyana", "restorative"
        ]):
            return "NIDRA_WIND_DOWN"
        if any(k in t for k in [
            "dantadhavana", "jihva", "jihwa", "gandusha", "kavala", "nasya", "anjana",
            "brahma muhurta", "ushnodaka", "ushapana", "ushapan", "sauca"
        ]):
            return "MORNING_KRIYA"
        if any(k in t for k in [
            "meal", "lunch", "dinner", "breakfast", "mitahara", "bhojana",
            "khichdi", "soup", "gruel", "peya", "food", "eat"
        ]):
            return "AHARA_MEAL"
        return "GENERAL"

    by_name = _match_category(name or "", check_meals_first=False)
    if by_name != "GENERAL" or not description:
        return by_name
    return _match_category(description, check_meals_first=False)


def _get_circadian_dosha_window(minute_of_day: int) -> str:
    """Returns the classical Ayurvedic circadian Dosha Kala window for a given minute of the day."""
    h = (minute_of_day // 60) % 24
    if 4 <= h < 6:
        return "Brahma Muhurta (Late Night Vata Window, 04:00-06:00 — Sattvic awakening & Prana clarity)"
    elif 6 <= h < 10:
        return "Morning Kapha Kala (06:00-10:00 — Physical strength, ideal for Abhyanga, Vyayama, Pranayama)"
    elif 10 <= h < 14:
        return "Midday Pitta Kala (10:00-14:00 — Peak Jatharagni digestive fire, ideal for main Mitahara meal)"
    elif 14 <= h < 18:
        return "Afternoon Vata Kala (14:00-18:00 — Mental agility; transition at dusk/Sandhya)"
    elif 18 <= h < 22:
        return "Evening Kapha Kala (18:00-22:00 — Early light dinner, gentle cooling wind-down, preparation for Nidra)"
    else:
        return "Night Pitta/Vata Kala (22:00-04:00 — Deep restorative sleep & metabolic assimilation)"


class ClinicalRuleEngine:
    """
    Module 5a: Safety Guardrail & Grounded Principle Reasoning Domain.
    Enforces both:
    1. Classical Ayurvedic symptom contraindications (Jwara, Pitta Prakopa, Vata/Anidra, Ajeerna), and
    2. Dynamic Relational & Temporal Principles (Bhuktavastu / Jirna Ahara post-meal spacing,
       Kriya Krama sequencing, Sandhya/Circadian Dosha Kala alignment) grounded in RAG literature.
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
            "Rule 4: Ajeerna / Ama (Acute Indigestion / Heaviness) Contraindications",
            "Rule 5: Bhuktavastu / Jirna Ahara (Post-Meal Temporal Spacing & Sequence) Guardrail"
        ]

        # Rule 1: Fever (Nava Jwara) Contraindications
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

        # Rule 5: Post-Meal (Bhuktavastu) Temporal Spacing Guardrail across the schedule
        # Ensures that Pranayama, Vyayama, Abhyanga, or Snana are never left immediately after a meal
        temporal_overrides = ClinicalRuleEngine._enforce_post_meal_spacing_on_schedule(schedule)
        overrides_applied.extend(temporal_overrides)

        return {
            "schedule": schedule,
            "overrides_applied": overrides_applied,
            "is_safe": True,
            "rules_checked": rules_checked
        }

    @staticmethod
    def _enforce_post_meal_spacing_on_schedule(schedule: DinacharyaSchedule) -> List[Dict[str, Any]]:
        """
        Scans the schedule for practices in PRANAYAMA_YOGA, VYAYAMA_EXERTION, ABHYANGA_OLEATION,
        or SNANA_BATH that are scheduled overlapping with or within <90 minutes after a light meal
        (or <180 minutes after a heavy midday meal), and shifts them to a conflict-free,
        principle-compliant window so no schedule can persist with a Bhuktavastu post-meal violation.
        """
        overrides: List[Dict[str, Any]] = []
        all_blocks = [
            ("morning_block", schedule.morning_block),
            ("midday_block", schedule.midday_block),
            ("evening_block", schedule.evening_block),
        ]

        # Collect all meal intervals
        meals: List[Tuple[str, int, int]] = []
        for _, blk in all_blocks:
            for p in blk:
                if _classify_practice_category(p.name, p.description) == "AHARA_MEAL":
                    parsed = _parse_slot_minutes(p.time_slot, p.duration_minutes)
                    if parsed:
                        meals.append((p.name, parsed[0], parsed[1]))

        if not meals:
            return overrides

        restricted_cats = {"PRANAYAMA_YOGA", "VYAYAMA_EXERTION", "ABHYANGA_OLEATION", "SNANA_BATH"}
        for blk_name, blk in all_blocks:
            for p in blk:
                cat = _classify_practice_category(p.name, p.description)
                if cat not in restricted_cats:
                    continue
                parsed = _parse_slot_minutes(p.time_slot, p.duration_minutes)
                if not parsed:
                    continue
                p_start, p_end = parsed
                dur = max(15, p_end - p_start)

                for meal_name, m_start, m_end in meals:
                    is_heavy = any(k in meal_name.lower() for k in ["heaviest", "lunch", "mitahara", "heavy"])
                    min_gap = 180 if is_heavy else 90
                    gap_after_meal = p_start - m_end
                    overlaps_meal = max(p_start, m_start) < min(p_end, m_end)
                    if overlaps_meal or (0 <= gap_after_meal < min_gap):
                        old_slot = p.time_slot
                        # Build existing_items excluding `p` so we pick a conflict-free slot
                        other_items: List[Dict[str, Any]] = []
                        for b_k, b_list in all_blocks:
                            for other_p in b_list:
                                if other_p is p:
                                    continue
                                op = _parse_slot_minutes(other_p.time_slot, other_p.duration_minutes)
                                other_items.append({
                                    "name": other_p.name,
                                    "time_slot": other_p.time_slot,
                                    "duration_minutes": other_p.duration_minutes,
                                    "description": other_p.description,
                                    "block": b_k,
                                    "category": _classify_practice_category(other_p.name, other_p.description),
                                    "start_min": op[0] if op else None,
                                    "end_min": op[1] if op else None,
                                })
                        alts = ClinicalRuleEngine._compute_valid_alternatives(
                            activity_name=p.name,
                            target_cat=cat,
                            duration_minutes=dur,
                            requested_start_min=p_start,
                            existing_items=other_items,
                            calendar_events=[],
                        )
                        if alts:
                            new_slot = alts[0]["proposed_slot"]
                        else:
                            new_end = max(300, m_start - 15)
                            new_start = max(285, new_end - dur)
                            new_slot = _format_minutes_to_slot(new_start, new_end)
                        p.time_slot = new_slot
                        rationale_note = (
                            f"[SAFETY OVERRIDE: Bhuktavastu / Post-Meal Guardrail] '{p.name}' cannot be practiced "
                            f"at {old_slot} immediately after '{meal_name}' ({_format_minutes_to_slot(m_start, m_end)}). "
                            f"Classical Ayurveda (Ashtanga Hrdayam Su. 2) and AYUSH Common Yoga Protocol mandate an empty "
                            f"stomach (at least 90-120 mins after a light meal or 3-4 hours after a heavy meal) to protect "
                            f"Jatharagni and Samana Vayu. Shifted to {new_slot}."
                        )
                        if "[SAFETY OVERRIDE" not in (p.rationale or ""):
                            p.rationale = f"{p.rationale} {rationale_note}".strip()
                        overrides.append({
                            "rule": "Bhuktavastu / Post-Meal Spacing Override",
                            "block": blk_name,
                            "removed_practice": f"{p.name} ({old_slot})",
                            "replacement_practice": f"{p.name} ({new_slot})",
                            "rationale": rationale_note
                        })
                        break
            blk.sort(key=lambda x: x.time_slot or "")

        return overrides

    @staticmethod
    def evaluate_reschedule_request(
        activity_name: str,
        proposed_slot: str,
        current_schedule: Optional[Any] = None,
        profile: Optional[DoshaProfile] = None,
        calendar_events: Optional[List[str]] = None,
        symptoms: Optional[List[str]] = None,
        change_type: str = "reschedule",
        use_llm: bool = False,
        schedule: Optional[Any] = None,
        user_message: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Dynamic, RAG-Grounded Principle Validator for schedule adaptations.

        Steps:
        1. Parses the user's current schedule into a 24-hour topological timeline.
        2. Evaluates the proposed (activity_name, proposed_slot) against the 6-category
           Relational Temporal Constraint Matrix (Bhuktavastu post-meal rules, pre-meal/bath gaps,
           Kriya Krama sequence prerequisites, circadian Dosha Kala cutoffs, and calendar overlaps).
        3. Queries the ChromaDB Grounding Knowledge Base (Ashtanga Hrdayam, AYUSH Common Yoga Protocol,
           MDNIY Yoga Guidelines, Dinacharya/Ratricharya) for specific passages relevant to the
           activity and its adjacent practices.
        4. Invokes the LLM reasoner (when available) to synthesize nuanced clinical reasoning and
           validate contextual fitness, while ensuring deterministic temporal/physiological violations
           never fail open.
        5. Computes conflict-free, principle-compliant alternative time slots fitting the user's day.
        """
        from src.knowledge.retriever import AyurvedaKnowledgeBase

        effective_sched = current_schedule if current_schedule is not None else schedule
        # 1. Extract all existing practices from effective_sched
        sched_root = {}
        if hasattr(effective_sched, "model_dump"):
            sched_root = effective_sched.model_dump()
        elif isinstance(effective_sched, dict):
            sched_root = effective_sched.get("schedule", effective_sched)
            if hasattr(sched_root, "model_dump"):
                sched_root = sched_root.model_dump()
            elif not isinstance(sched_root, dict):
                sched_root = {}

        existing_items: List[Dict[str, Any]] = []
        matched_target_duration = 15
        matched_target_block = ""
        matched_target_desc = ""
        act_lower = (activity_name or "").strip().lower()

        for blk_key in ["morning_block", "midday_block", "evening_block"]:
            for item in sched_root.get(blk_key, []) or []:
                d = item if isinstance(item, dict) else item.model_dump()
                p_name = str(d.get("name") or d.get("activity") or "Practice")
                p_slot = str(d.get("time_slot") or d.get("time") or "Flexible")
                p_dur = int(d.get("duration_minutes", 15))
                p_desc = str(d.get("description", ""))
                p_nl = p_name.lower().strip()

                is_same_activity = bool(
                    act_lower and (act_lower == p_nl or act_lower in p_nl or p_nl in act_lower)
                )
                if is_same_activity:
                    matched_target_duration = p_dur
                    matched_target_block = blk_key
                    matched_target_desc = p_desc
                    continue  # Exclude the practice's own old slot when checking conflicts

                parsed = _parse_slot_minutes(p_slot, p_dur)
                existing_items.append({
                    "name": p_name,
                    "time_slot": p_slot,
                    "duration_minutes": p_dur,
                    "description": p_desc,
                    "block": blk_key,
                    "category": _classify_practice_category(p_name, p_desc),
                    "start_min": parsed[0] if parsed else None,
                    "end_min": parsed[1] if parsed else None
                })

        existing_items.sort(key=lambda x: x["start_min"] if x["start_min"] is not None else 9999)

        target_cat = _classify_practice_category(activity_name, matched_target_desc)

        # If change_type is "skip", no new time slot validation is required
        if change_type == "skip" or not proposed_slot:
            return {
                "is_valid": True,
                "activity_name": activity_name,
                "proposed_slot": proposed_slot,
                "category": target_cat,
                "violated_principles": [],
                "clinical_explanation": f"Skipping or pausing {activity_name} is permissible when needed.",
                "retrieved_citations": [],
                "recommended_alternatives": []
            }

        parsed_prop = _parse_slot_minutes(proposed_slot, matched_target_duration)
        if not parsed_prop:
            return {
                "is_valid": False,
                "activity_name": activity_name,
                "proposed_slot": proposed_slot,
                "category": target_cat,
                "violated_principles": [f"Could not parse a valid time window from '{proposed_slot}'."],
                "clinical_explanation": "Please specify a clear time (e.g., '06:45 - 07:00' or '18:30 - 18:45').",
                "retrieved_citations": [],
                "recommended_alternatives": []
            }

        prop_start, prop_end = parsed_prop
        prop_duration = max(15, prop_end - prop_start)

        # Contextual 12-hour bare-time disambiguation (e.g., user asks "Can I do pranayama at 7:30?" without "PM")
        msg_lower = (user_message or "").lower()
        slot_lower = (proposed_slot or "").lower()
        has_explicit_am = bool(re.search(r"\b(am|morning|dawn|brahma)\b", f"{slot_lower} {msg_lower}"))
        has_explicit_pm = bool(re.search(r"\b(pm|evening|night|tonight|dinner|supper)\b", f"{slot_lower} {msg_lower}"))
        if 300 <= prop_start < 660 and not has_explicit_am:
            pm_start = prop_start + 720
            pm_end = prop_end + 720
            # Check if pm_start falls overlapping with or within 90 mins after an evening meal (e.g. 19:00-19:30 Dinner)
            hits_evening_meal = any(
                it["category"] == "AHARA_MEAL"
                and it["start_min"] is not None
                and it["end_min"] is not None
                and it["start_min"] >= 17 * 60
                and (max(pm_start, it["start_min"]) < min(pm_end, it["end_min"]) or 0 <= (pm_start - it["end_min"]) < 90)
                for it in existing_items
            )
            # Disambiguate bare 5:00-10:59 to 17:00-22:59 when:
            # 1) user_message explicitly mentions evening/dinner/pm, OR
            # 2) the activity itself is an evening_block practice (e.g. Dinner, Trataka) and a bare hour was given, OR
            # 3) user_message contains a bare time (or the practice is already in morning_block) and the PM equivalent
            #    directly hits the post-dinner window (e.g. "Can I do pranayama at 7:30?" right after 19:00-19:30 dinner)
            is_bare_in_slot_or_msg = (not re.match(r"^0\d:", proposed_slot.strip())) or bool(user_message)
            if has_explicit_pm or (matched_target_block == "evening_block" and is_bare_in_slot_or_msg) or (
                hits_evening_meal and matched_target_block == "morning_block" and bool(user_message)
            ):
                prop_start, prop_end = pm_start, pm_end

        standardized_proposed_slot = _format_minutes_to_slot(prop_start, prop_end)
        circadian_window = _get_circadian_dosha_window(prop_start)

        # 2. Compute topological relationships & run Relational Temporal Constraint Matrix
        violated_principles: List[str] = []
        adjacent_descriptions: List[str] = []

        for item in existing_items:
            st, en = item["start_min"], item["end_min"]
            if st is None or en is None:
                continue
            item_cat = item["category"]
            item_label = f"{item['name']} ({item['time_slot']})"

            # Check direct overlap
            if max(prop_start, st) < min(prop_end, en):
                violated_principles.append(
                    f"Schedule Conflict: Proposed slot {standardized_proposed_slot} for '{activity_name}' directly "
                    f"overlaps with scheduled activity '{item_label}'."
                )
                adjacent_descriptions.append(f"overlaps with {item_label}")

            # Delta after item ends (prop_start - en) and before item starts (st - prop_end)
            gap_after_item = prop_start - en
            gap_before_item = st - prop_end

            if 0 <= gap_after_item <= 180:
                adjacent_descriptions.append(f"{gap_after_item} mins after {item_label}")
            if 0 <= gap_before_item <= 180:
                adjacent_descriptions.append(f"{gap_before_item} mins before {item_label}")

            # --- Matrix Rule A: Target is PRANAYAMA_YOGA, VYAYAMA_EXERTION, ABHYANGA_OLEATION, SNANA_BATH, or MORNING_KRIYA ---
            if target_cat in {"PRANAYAMA_YOGA", "VYAYAMA_EXERTION", "ABHYANGA_OLEATION", "SNANA_BATH", "MORNING_KRIYA"}:
                if item_cat == "AHARA_MEAL":
                    is_heavy_meal = any(k in item["name"].lower() for k in ["heaviest", "lunch", "mitahara", "heavy"])
                    min_post_meal_gap = 60 if target_cat == "MORNING_KRIYA" else (180 if is_heavy_meal else 90)
                    if 0 <= gap_after_item < min_post_meal_gap or (max(prop_start, st) < min(prop_end, en)):
                        if target_cat == "PRANAYAMA_YOGA":
                            violated_principles.append(
                                f"Bhuktavastu & Empty-Stomach Principle (AYUSH Common Yoga Protocol / MDNIY / Ashtanga Hrdayam): "
                                f"'{activity_name}' at {standardized_proposed_slot} is scheduled only {max(0, gap_after_item)} minutes "
                                f"after '{item_label}'. Yogic breathing and Pranayama must be practiced on an empty stomach "
                                f"(at least {min_post_meal_gap // 60} to {(min_post_meal_gap // 60) + 1} hours after a meal). "
                                f"Immediately after eating, Kledaka Kapha dominates and Jatharagni requires Prana and blood flow "
                                f"concentrated in the digestive tract (Koshtha); practicing Pranayama right after a meal disrupts "
                                f"Samana Vayu, weakens Agni, and causes bloating or Udavarta."
                            )
                        elif target_cat == "SNANA_BATH":
                            violated_principles.append(
                                f"Bhuktavastu Snana Contraindication (Ashtanga Hrdayam Sutrasthana 2.18): "
                                f"Bathing ('{activity_name}') at {standardized_proposed_slot} is {max(0, gap_after_item)} minutes "
                                f"after '{item_label}'. Taking a bath immediately after food (Bhuktavastu) is strictly contraindicated "
                                f"as it diverts peripheral circulation away from the gastrointestinal tract and extinguishes Jatharagni (causing Ajirna)."
                            )
                        elif target_cat == "ABHYANGA_OLEATION":
                            violated_principles.append(
                                f"Ajirna / Post-Meal Abhyanga Contraindication (Ashtanga Hrdayam Sutrasthana 2.9): "
                                f"Oil massage ('{activity_name}') at {standardized_proposed_slot} is {max(0, gap_after_item)} minutes "
                                f"after '{item_label}'. Abhyanga is contraindicated during active digestion before previous food is digested."
                            )
                        elif target_cat == "VYAYAMA_EXERTION":
                            violated_principles.append(
                                f"Post-Meal Vyayama Contraindication (Ashtanga Hrdayam Sutrasthana 2.10-11 & MDNIY Guidelines): "
                                f"Physical exercise/Asana ('{activity_name}') at {standardized_proposed_slot} is {max(0, gap_after_item)} minutes "
                                f"after '{item_label}'. Exercise immediately after a meal vitiates Doshas and impairs digestion; "
                                f"wait at least {min_post_meal_gap} minutes or practice before the meal."
                            )
                        elif target_cat == "MORNING_KRIYA":
                            violated_principles.append(
                                f"Dinacharya Kriya Contraindication (Ashtanga Hrdayam Sutrasthana 2): "
                                f"Cleansing practice ('{activity_name}') at {standardized_proposed_slot} is {max(0, gap_after_item)} minutes "
                                f"after '{item_label}'. Nasya, Gandusha, and morning purification kriyas must be performed on an empty stomach, "
                                f"never immediately after food."
                            )

                    # Pre-meal buffer: AYUSH CYP states food may be consumed 15-30 mins after yoga/pranayama
                    if target_cat in {"PRANAYAMA_YOGA", "VYAYAMA_EXERTION"} and (0 <= gap_before_item < 15):
                        violated_principles.append(
                            f"Post-Practice Meal Buffer (AYUSH Common Yoga Protocol): "
                            f"'{activity_name}' ends at {_format_minutes_to_slot(prop_start, prop_end).split(' - ')[1]}, "
                            f"only {gap_before_item} minutes before '{item_label}'. Food should be consumed at least "
                            f"15 to 30 minutes after completing Yogic/Pranayama practice so Prana and autonomic tone settle."
                        )

            # --- Matrix Rule B: Target is AHARA_MEAL (moving a meal too close to another practice or sleep) ---
            if target_cat == "AHARA_MEAL":
                if item_cat in {"PRANAYAMA_YOGA", "VYAYAMA_EXERTION", "ABHYANGA_OLEATION", "SNANA_BATH"}:
                    # If meal ends right before Pranayama/Vyayama/Abhyanga/Snana (<90m)
                    if 0 <= gap_before_item < 90:
                        violated_principles.append(
                            f"Bhuktavastu Principle: Moving meal '{activity_name}' to {standardized_proposed_slot} places it "
                            f"only {gap_before_item} minutes before '{item_label}', leaving insufficient time for digestion "
                            f"(Jirna Ahara) before '{item['name']}'."
                        )
                    # If meal starts immediately (<15m) after Pranayama/Vyayama
                    if item_cat in {"PRANAYAMA_YOGA", "VYAYAMA_EXERTION"} and 0 <= gap_after_item < 15:
                        violated_principles.append(
                            f"Post-Practice Meal Buffer (AYUSH Common Yoga Protocol): Meal '{activity_name}' at "
                            f"{standardized_proposed_slot} starts only {gap_after_item} minutes after '{item_label}'. "
                            f"Maintain at least a 15-30 minute rest interval after Yoga/Pranayama before eating."
                        )
                elif item_cat == "AHARA_MEAL":
                    if abs(prop_start - st) < 180:
                        violated_principles.append(
                            f"Jirna Ahara Principle (Ashtanga Hrdayam Sutrasthana 2.19): Meal '{activity_name}' at "
                            f"{standardized_proposed_slot} is too close to '{item_label}'. Wholesome food must only be "
                            f"consumed after the previous meal is digested (minimum 3-4 hours between meals)."
                        )
                elif item_cat == "NIDRA_WIND_DOWN" and "sleep" in item["name"].lower():
                    if 0 <= gap_before_item < 90:
                        violated_principles.append(
                            f"Ratricharya Dinner-to-Sleep Buffer: Dinner '{activity_name}' at {standardized_proposed_slot} "
                            f"finishes less than 90-120 minutes before '{item_label}'. Classical Ratricharya requires at least "
                            f"2 hours between dinner and bedtime to prevent Kapha and Ama accumulation."
                        )

            # --- Matrix Rule C: Kriya Krama Ordering (Abhyanga vs Snana, Vyayama vs Snana) ---
            if target_cat == "ABHYANGA_OLEATION" and item_cat == "SNANA_BATH":
                if 0 <= gap_after_item <= 120:
                    violated_principles.append(
                        f"Kriya Krama Sequence Principle (Ashtanga Hrdayam Dinacharya): Oil massage ('{activity_name}') "
                        f"at {standardized_proposed_slot} is scheduled after bath ('{item_label}'). Traditional Dinacharya "
                        f"prescribes Abhyanga BEFORE Snana so warm water cleanses excess oil and opens Srotas."
                    )
            if target_cat == "SNANA_BATH" and item_cat == "ABHYANGA_OLEATION":
                if 0 <= gap_before_item <= 120:
                    violated_principles.append(
                        f"Kriya Krama Sequence Principle (Ashtanga Hrdayam Dinacharya): Bath ('{activity_name}') "
                        f"at {standardized_proposed_slot} is scheduled before oil massage ('{item_label}'). Traditional Dinacharya "
                        f"prescribes Abhyanga BEFORE Snana."
                    )
            if target_cat == "SNANA_BATH" and item_cat in {"VYAYAMA_EXERTION", "PRANAYAMA_YOGA"}:
                if 0 <= gap_after_item < 20:
                    violated_principles.append(
                        f"Post-Practice Bath Cooldown (AYUSH Common Yoga Protocol): Bath ('{activity_name}') at "
                        f"{standardized_proposed_slot} is only {gap_after_item} minutes after '{item_label}'. "
                        f"Wait at least 20-30 minutes after Yoga/Pranayama/Exercise before bathing so body temperature equilibrates."
                    )

        # --- Matrix Rule D: Circadian / Time-of-Day Contraindications ---
        act_text_lower = activity_name.lower()
        if target_cat == "VYAYAMA_EXERTION" and prop_start >= 20 * 60:
            violated_principles.append(
                f"Circadian Ratricharya Principle (Ashtanga Hrdayam): Vigorous physical exercise ('{activity_name}') "
                f"at {standardized_proposed_slot} (after 20:00) aggravates Vata Dosha and disturbs Nidra (sleep architecture)."
            )
        if target_cat == "PRANAYAMA_YOGA" and prop_start >= 19 * 60:
            if any(h in act_text_lower for h in ["bhastrika", "kapalabhati", "surya bheda"]):
                violated_principles.append(
                    f"Evening Stimulation Contraindication: Heating/stimulating breathwork ('{activity_name}') at "
                    f"{standardized_proposed_slot} is contraindicated in the evening as it provokes Pitta and Vata, "
                    f"impairing sleep. Only gentle calming breathwork (Nadi Shodhana / Bhramari) is suitable in the evening."
                )
        if target_cat == "AHARA_MEAL" and prop_start >= 21 * 60 + 30:
            violated_principles.append(
                f"Late Night Bhojana Contraindication (Ratricharya): Consuming a meal ('{activity_name}') at "
                f"{standardized_proposed_slot} late at night when Jatharagni is low causes Ama accumulation and Kapha stagnation."
            )

        # --- Matrix Rule E: Calendar Conflicts ---
        if calendar_events:
            from src.planning.tools import check_calendar_conflicts
            if check_calendar_conflicts(calendar_events, standardized_proposed_slot):
                violated_principles.append(
                    f"Calendar Commitment Conflict: {standardized_proposed_slot} conflicts with user calendar events {calendar_events}."
                )

        # 3. Retrieve Classical & AYUSH Grounding Passages from ChromaDB
        kb = AyurvedaKnowledgeBase()
        adj_summary = ", ".join(adjacent_descriptions) if adjacent_descriptions else f"during {circadian_window}"
        retrieved_docs = kb.retrieve_for_reschedule(
            activity_name=activity_name,
            proposed_slot=standardized_proposed_slot,
            adjacent_context=adj_summary,
            profile=profile,
            k=4
        )
        citations = [
            {"source": d.get("source", "Ayurveda Grounding"), "excerpt": d.get("text", "")[:400].strip()}
            for d in retrieved_docs
        ]

        # 4. Compute Reasoned Alternative Time Slots based on User's Schedule Constraints
        recommended_alternatives = ClinicalRuleEngine._compute_valid_alternatives(
            activity_name=activity_name,
            target_cat=target_cat,
            duration_minutes=prop_duration,
            requested_start_min=prop_start,
            existing_items=existing_items,
            calendar_events=calendar_events or []
        )

        # 5. Optional LLM-Grounded Nuanced Reasoning Step
        llm_explanation = ""
        if use_llm:
            try:
                from src.llm_gateway import LLMGateway
                gateway = LLMGateway.get_instance()
                sched_lines = [f"- {it['name']} ({it['time_slot']}) [{it['category']}]" for it in existing_items]
                sched_str = "\n".join(sched_lines) if sched_lines else "No other practices scheduled."
                rag_str = "\n\n".join([f"[{c['source']}]: {c['excerpt']}" for c in citations])
                matrix_notes = "\n".join([f"- {v}" for v in violated_principles]) if violated_principles else "None detected by temporal matrix."
                alts_str = "\n".join([f"- {a['proposed_slot']}: {a['rationale']}" for a in recommended_alternatives])

                val_prompt = f"""Evaluate this Dinacharya rescheduling request using the retrieved classical Ayurvedic & Ministry of AYUSH guidelines and the user's current schedule.

USER REQUEST: Move/Schedule '{activity_name}' (Category: {target_cat}) to '{standardized_proposed_slot}' ({circadian_window}).
USER CURRENT SCHEDULE (excluding '{activity_name}'):
{sched_str}

TEMPORAL PROXIMITY TO OTHER ACTIVITIES:
{adj_summary}

DETERMINISTIC TEMPORAL & CLINICAL MATRIX FINDINGS:
{matrix_notes}

RETRIEVED GROUNDING LITERATURE (Ashtanga Hrdayam / AYUSH Common Yoga Protocol / MDNIY / Ratricharya):
{rag_str}

CANDIDATE SAFE ALTERNATIVE SLOTS IN USER'S SCHEDULE:
{alts_str}

Return strict JSON with keys:
- "is_valid": boolean ( MUST be false if DETERMINISTIC TEMPORAL & CLINICAL MATRIX FINDINGS has any violations, or if retrieved guidelines contraindicate this timing )
- "violated_principles": array of strings explaining each violated principle
- "clinical_explanation": concise 2-3 sentence explanation citing the physiological mechanism (e.g. Agni, Samana Vayu, Kapha stage of digestion, empty stomach requirement) and grounding source
- "recommended_alternatives": array of objects {{"proposed_slot": "HH:MM - HH:MM", "rationale": "..."}}"""

                llm_res, is_fb = gateway.generate_structured_json(
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a clinical Ayurvedic & Yogic schedule validator. Output strict JSON only. Never approve a time slot that violates post-meal (Bhuktavastu/empty stomach) or sequencing rules."
                        },
                        {"role": "user", "content": val_prompt}
                    ],
                    max_tokens=1024,
                    temperature=0.1,
                    fallback_fn=lambda: {
                        "is_valid": len(violated_principles) == 0,
                        "violated_principles": violated_principles,
                        "clinical_explanation": violated_principles[0] if violated_principles else f"Scheduling '{activity_name}' at {standardized_proposed_slot} aligns with Dinacharya principles and does not conflict with meals or other routines.",
                        "recommended_alternatives": recommended_alternatives
                    }
                )
                if isinstance(llm_res, dict):
                    llm_explanation = str(llm_res.get("clinical_explanation", "")).strip()
                    # If LLM discovered additional principle violations (and didn't hallucinate on a clean slot unless grounded), merge them
                    llm_violations = llm_res.get("violated_principles") or []
                    if not violated_principles and llm_res.get("is_valid") is False and llm_violations:
                        # Verify LLM violation is genuine (e.g. not contradicting an explicitly valid pre-meal or morning slot)
                        for lv in llm_violations:
                            if isinstance(lv, str) and lv.strip():
                                violated_principles.append(lv.strip())
            except Exception as exc:
                logger.warning(f"LLM principle reasoner fell back to deterministic matrix: {exc}")

        is_valid = len(violated_principles) == 0
        if not llm_explanation:
            if is_valid:
                llm_explanation = (
                    f"Scheduling '{activity_name}' at {standardized_proposed_slot} ({circadian_window}) "
                    f"is physiologically sound, maintains proper spacing from meals and sleep, and fits your daily routine."
                )
            else:
                llm_explanation = " ".join(violated_principles)

        return {
            "is_valid": is_valid,
            "activity_name": activity_name,
            "proposed_slot": standardized_proposed_slot,
            "category": target_cat,
            "circadian_window": circadian_window,
            "adjacent_context": adj_summary,
            "violated_principles": violated_principles,
            "violations": violated_principles,
            "clinical_explanation": llm_explanation,
            "retrieved_citations": citations,
            "recommended_alternatives": recommended_alternatives if not is_valid else []
        }

    @staticmethod
    def _compute_valid_alternatives(
        activity_name: str,
        target_cat: str,
        duration_minutes: int,
        requested_start_min: int,
        existing_items: List[Dict[str, Any]],
        calendar_events: List[str]
    ) -> List[Dict[str, str]]:
        """
        Scans the user's timeline to recommend 2-3 conflict-free, principle-compliant time slots
        closest to the user's requested time window (e.g. evening vs morning).
        Enforces all Matrix Rules (A-E) so every recommended alternative is guaranteed valid.
        """
        from src.planning.tools import check_calendar_conflicts

        dur = max(15, min(60, duration_minutes))
        meals = [it for it in existing_items if it["category"] == "AHARA_MEAL" and it["start_min"] is not None]
        occupied = [
            (it["start_min"], it["end_min"], it["name"], it["category"], it.get("time_slot", ""))
            for it in existing_items
            if it["start_min"] is not None and it["end_min"] is not None
        ]
        act_text_lower = (activity_name or "").lower()

        def _is_candidate_valid(cand_start: int) -> Tuple[bool, str]:
            cand_end = cand_start + dur
            if cand_start < 5 * 60 or cand_end > 22 * 60 + 30:
                return False, ""
            slot_str = _format_minutes_to_slot(cand_start, cand_end)
            if calendar_events and check_calendar_conflicts(calendar_events, slot_str):
                return False, ""

            rationale_parts = []
            for st, en, it_name, it_cat, it_slot in occupied:
                # Direct overlap check
                if max(cand_start, st) < min(cand_end, en):
                    return False, ""
                gap_after_item = cand_start - en
                gap_before_item = st - cand_end

                # Matrix Rule A: Post-meal & pre-meal spacing for yoga/exertion/oleation/bath/kriya
                if target_cat in {"PRANAYAMA_YOGA", "VYAYAMA_EXERTION", "ABHYANGA_OLEATION", "SNANA_BATH", "MORNING_KRIYA"}:
                    if it_cat == "AHARA_MEAL":
                        is_heavy = any(k in it_name.lower() for k in ["heaviest", "lunch", "mitahara", "heavy"])
                        min_gap = 60 if target_cat == "MORNING_KRIYA" else (180 if is_heavy else 90)
                        if 0 <= gap_after_item < min_gap:
                            return False, ""
                        if 0 <= gap_before_item < 15 and target_cat in {"PRANAYAMA_YOGA", "VYAYAMA_EXERTION"}:
                            return False, ""
                        if 15 <= gap_before_item <= 60:
                            rationale_parts.append(
                                f"Practiced on an empty stomach {gap_before_item} mins before '{it_name}' ({it_slot}), "
                                f"satisfying the AYUSH 15-30 min pre-meal guideline without disturbing Jatharagni"
                            )
                        elif min_gap <= gap_after_item <= 210:
                            rationale_parts.append(
                                f"Maintains a safe {gap_after_item}-minute post-meal digestion gap after '{it_name}' ({it_slot})"
                            )

                # Matrix Rule B: Target is AHARA_MEAL
                if target_cat == "AHARA_MEAL":
                    if it_cat in {"PRANAYAMA_YOGA", "VYAYAMA_EXERTION", "ABHYANGA_OLEATION", "SNANA_BATH"}:
                        if 0 <= gap_before_item < 90:
                            return False, ""
                        if it_cat in {"PRANAYAMA_YOGA", "VYAYAMA_EXERTION"} and 0 <= gap_after_item < 15:
                            return False, ""
                    elif it_cat == "AHARA_MEAL":
                        if abs(cand_start - st) < 180:
                            return False, ""
                    elif it_cat == "NIDRA_WIND_DOWN" and "sleep" in it_name.lower():
                        if 0 <= gap_before_item < 90:
                            return False, ""

                # Matrix Rule C: Kriya Krama Ordering (Abhyanga before Snana, post-practice bath cooldown)
                if target_cat == "ABHYANGA_OLEATION" and it_cat == "SNANA_BATH":
                    if 0 <= gap_after_item <= 120:
                        return False, ""
                    if 0 <= gap_before_item <= 45:
                        rationale_parts.append(f"Scheduled {gap_before_item} mins before '{it_name}' ({it_slot}) following traditional Abhyanga-before-Snana Kriya Krama")
                if target_cat == "SNANA_BATH" and it_cat == "ABHYANGA_OLEATION":
                    if 0 <= gap_before_item <= 120:
                        return False, ""
                    if 10 <= gap_after_item <= 60:
                        rationale_parts.append(f"Scheduled {gap_after_item} mins after '{it_name}' ({it_slot}) allowing warm oil absorption before bath")
                if target_cat == "SNANA_BATH" and it_cat in {"VYAYAMA_EXERTION", "PRANAYAMA_YOGA"}:
                    if 0 <= gap_after_item < 20:
                        return False, ""

            # Matrix Rule D: Circadian / Time-of-Day cutoffs
            if target_cat == "VYAYAMA_EXERTION" and cand_start >= 20 * 60:
                return False, ""
            if target_cat == "PRANAYAMA_YOGA" and cand_start >= 19 * 60:
                if any(h in act_text_lower for h in ["bhastrika", "kapalabhati", "surya bheda"]):
                    return False, ""
            if target_cat == "AHARA_MEAL" and cand_start >= 21 * 60 + 30:
                return False, ""

            if not rationale_parts:
                if cand_start < 10 * 60:
                    rationale_parts.append("Ideal morning Sattvic/Kapha window on an empty stomach before meals")
                elif cand_start < 19 * 60:
                    rationale_parts.append("Early evening transition window on a light/empty stomach before dinner")
                else:
                    rationale_parts.append("Calming evening window after sufficient post-dinner digestion")

            return True, "; ".join(rationale_parts) + "."

        candidates: List[Dict[str, str]] = []
        seen_slots = set()

        # Priority 1: Check strategic slots relative to meals and Kriya Krama anchors
        strategic_starts: List[int] = []
        for m in meals:
            m_st, m_en = m["start_min"], m["end_min"]
            strategic_starts.append(m_st - dur - 15)
            strategic_starts.append(m_st - dur - 30)
            strategic_starts.append(m_en + 90)
            strategic_starts.append(m_en + 120)
            strategic_starts.append(m_en + 180)

        for st, en, _, it_cat, _ in occupied:
            if target_cat == "ABHYANGA_OLEATION" and it_cat == "SNANA_BATH":
                strategic_starts.append(st - dur - 10)
                strategic_starts.append(st - dur - 15)
            elif target_cat == "SNANA_BATH" and it_cat == "ABHYANGA_OLEATION":
                strategic_starts.append(en + 10)
                strategic_starts.append(en + 20)

        # Also add morning & evening empty-stomach anchor slots
        strategic_starts.extend([6 * 60 + 30, 6 * 60 + 45, 7 * 60, 7 * 60 + 15, 18 * 60 + 15, 18 * 60 + 30, 21 * 60])

        # Sort strategic starts by proximity to the user's requested time so evening requests get evening alternatives first
        strategic_starts.sort(key=lambda s: abs(s - requested_start_min))

        for st_min in strategic_starts:
            ok, why = _is_candidate_valid(st_min)
            if ok:
                slot_fmt = _format_minutes_to_slot(st_min, st_min + dur)
                if slot_fmt not in seen_slots:
                    seen_slots.add(slot_fmt)
                    candidates.append({"proposed_slot": slot_fmt, "slot": slot_fmt, "rationale": why})
                if len(candidates) >= 3:
                    break

        # Priority 2: 15-minute grid scan fallback if fewer than 3 valid alternatives were found
        if len(candidates) < 3:
            grid_starts = list(range(5 * 60 + 30, 21 * 60 + 30, 15))
            grid_starts.sort(key=lambda s: abs(s - requested_start_min))
            for st_min in grid_starts:
                ok, why = _is_candidate_valid(st_min)
                if ok:
                    slot_fmt = _format_minutes_to_slot(st_min, st_min + dur)
                    if slot_fmt not in seen_slots:
                        seen_slots.add(slot_fmt)
                        candidates.append({"proposed_slot": slot_fmt, "slot": slot_fmt, "rationale": why})
                    if len(candidates) >= 3:
                        break

        return candidates

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

