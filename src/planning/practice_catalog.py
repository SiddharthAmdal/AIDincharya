"""
practice_catalog.py - Authentic Ayurvedic Practice Catalog & Candidate Scoring Engine

Defines comprehensive, structured Dinacharya candidate practices across Morning, Midday,
and Evening blocks with explicit dosha affinities (Vata, Pitta, Kapha), timing rules,
contraindications, and deterministic candidate scoring.
"""

from typing import List, Dict, Any, Optional, Tuple
from src.models import Practice, DoshaProfile, UserContext, DoshaVector, VikritiFlags


CANDIDATE_PRACTICES: List[Dict[str, Any]] = [
    # ==================== MORNING BLOCK ====================
    # 1. Wake & Hydration
    {
        "id": "wake_vata",
        "name": "Brahma Muhurta Jagaran & Grounding Warm Hydration",
        "block": "morning_block",
        "time_slot": "06:00 - 06:15",
        "duration_minutes": 15,
        "dosha_affinity": {"vata": 1.0, "pitta": 0.2, "kapha": 0.1},
        "description": "Wake gently before sunrise. Sit quietly and drink a cup of warm water with a pinch of ginger.",
        "rationale": "Soothes Vata's volatile nervous system and initiates Apana Vayu downward peristalsis.",
        "contraindications": []
    },
    {
        "id": "wake_pitta",
        "name": "Brahma Muhurta Jagaran & Cooling Dawn Hydration",
        "block": "morning_block",
        "time_slot": "05:30 - 05:45",
        "duration_minutes": 15,
        "dosha_affinity": {"vata": 0.2, "pitta": 1.0, "kapha": 0.2},
        "description": "Wake early in the cool pre-dawn air. Sip room-temperature water stored in a copper vessel.",
        "rationale": "Captures cooling morning energy to prevent excess Pitta bile and digestive heat accumulation.",
        "contraindications": []
    },
    {
        "id": "wake_kapha",
        "name": "Brahma Muhurta Jagaran & Spiced Lemon Hydration",
        "block": "morning_block",
        "time_slot": "05:00 - 05:15",
        "duration_minutes": 15,
        "dosha_affinity": {"vata": 0.1, "pitta": 0.2, "kapha": 1.0},
        "description": "Rise decisively before 05:30 AM. Drink warm water infused with raw honey and lemon juice.",
        "rationale": "Waking before Kapha time (06:00 AM) clears lethargy and liquifies heavy morning mucus.",
        "contraindications": []
    },
    {
        "id": "wake_tridoshic",
        "name": "Brahma Muhurta Jagaran & Balanced Hydration",
        "block": "morning_block",
        "time_slot": "05:45 - 06:00",
        "duration_minutes": 15,
        "dosha_affinity": {"vata": 0.6, "pitta": 0.6, "kapha": 0.6},
        "description": "Wake in tranquility at dawn. Drink lukewarm pure water in mindful contemplation.",
        "rationale": "Maintains equanimity across all three biological humors during nature's sattvic period.",
        "contraindications": []
    },

    # 2. Body Oil / Massage (Snehana & Swedana)
    {
        "id": "abhyanga_vata",
        "name": "Abhyanga (Warm Sesame Oil Self-Massage)",
        "block": "morning_block",
        "time_slot": "06:20 - 06:40",
        "duration_minutes": 20,
        "dosha_affinity": {"vata": 1.0, "pitta": 0.3, "kapha": -0.2},
        "description": "Vigorously massage scalp, limbs, and joints using warm unrefined sesame oil.",
        "rationale": "Heavy, warm unctuous sesame oil directly neutralizes Vata's cold, dry, rough qualities.",
        "contraindications": ["fever", "acute_indigestion", "nava_jwara"]
    },
    {
        "id": "abhyanga_pitta",
        "name": "Abhyanga (Cooling Coconut & Brahmi Massage)",
        "block": "morning_block",
        "time_slot": "06:00 - 06:20",
        "duration_minutes": 20,
        "dosha_affinity": {"vata": 0.3, "pitta": 1.0, "kapha": 0.1},
        "description": "Gently massage the body using cold-pressed coconut oil or herbal Brahmi oil.",
        "rationale": "Cooling, sweet coconut oil pacifies systemic pitta inflammation, skin rashes, and irritation.",
        "contraindications": ["fever", "acute_indigestion", "nava_jwara"]
    },
    {
        "id": "udvartana_kapha",
        "name": "Udvartana (Dry Herbal Scrub & Lymphatic Stimulation)",
        "block": "morning_block",
        "time_slot": "05:30 - 05:50",
        "duration_minutes": 20,
        "dosha_affinity": {"vata": -0.2, "pitta": 0.1, "kapha": 1.0},
        "description": "Perform upward, brisk dry brushing or apply warming chickpea/triphala powder against hair follicles.",
        "rationale": "Stimulates sluggish lymphatic circulation, breaks down sub-cutaneous fat, and counters Kapha stagnation.",
        "contraindications": ["fever", "eczema_flare"]
    },
    {
        "id": "snehana_tridoshic",
        "name": "Pada & Mukha Abhyanga (Gentle Foot & Face Oil Massage)",
        "block": "morning_block",
        "time_slot": "06:15 - 06:30",
        "duration_minutes": 15,
        "dosha_affinity": {"vata": 0.5, "pitta": 0.5, "kapha": 0.5},
        "description": "Apply gentle sweet almond oil to soles of feet, temples, and face.",
        "rationale": "Grounds the senses without overloading any single dosha.",
        "contraindications": ["fever"]
    },

    # 3. Pranayama & Movement
    {
        "id": "pranayama_vata",
        "name": "Pranayama (Nadi Shodhana Balancing Breath)",
        "block": "morning_block",
        "time_slot": "07:00 - 07:15",
        "duration_minutes": 15,
        "dosha_affinity": {"vata": 1.0, "pitta": 0.4, "kapha": 0.3},
        "description": "Sit comfortably and practice 10-15 minutes of slow alternate nostril breathing without breath retention.",
        "rationale": "Calms mental instability, grounds scattered thoughts, and balances the sympathetic nervous system.",
        "contraindications": []
    },
    {
        "id": "pranayama_pitta",
        "name": "Pranayama (Sheetali & Sheetkari Cooling Breath)",
        "block": "morning_block",
        "time_slot": "06:45 - 07:00",
        "duration_minutes": 15,
        "dosha_affinity": {"vata": 0.1, "pitta": 1.0, "kapha": -0.1},
        "description": "Practice Sheetali breath through a curled tongue, exhaling slowly through both nostrils.",
        "rationale": "Traditional Ayurvedic rationale: Cooling Sheetali breath draws out excess internal Pitta heat and calms irritability.",
        "contraindications": ["cold_bronchitis"]
    },
    {
        "id": "pranayama_kapha",
        "name": "Pranayama (Kapalabhati & Bhastrika Breath of Fire)",
        "block": "morning_block",
        "time_slot": "06:15 - 06:30",
        "duration_minutes": 15,
        "dosha_affinity": {"vata": -0.3, "pitta": -0.3, "kapha": 1.0},
        "description": "Perform 3 rounds of active abdominal exhalations followed by deep yogic diaphragmatic breathing.",
        "rationale": "Ignites sluggish metabolic fire (Jatharagni) and burns systemic heaviness and congestion.",
        "contraindications": ["high_blood_pressure", "fever", "vertigo"]
    },
    {
        "id": "pranayama_dual_vp",
        "name": "Pranayama (Nadi Shodhana with Cooling Exhalation)",
        "block": "morning_block",
        "time_slot": "06:45 - 07:00",
        "duration_minutes": 15,
        "dosha_affinity": {"vata": 0.8, "pitta": 0.8, "kapha": 0.2},
        "description": "Harmonized alternate nostril breathing followed by soft mouth exhalations to relieve both anxiety and heat.",
        "rationale": "Dual-acting pranayama pacifying Vata restlessness while mitigating Pitta inflammatory pressure.",
        "contraindications": []
    },

    # ==================== MIDDAY BLOCK ====================
    # 1. Mitahara (Main Meal)
    {
        "id": "mitahara_vata",
        "name": "Mitahara (Snigdha & Warm Grounding Lunch)",
        "block": "midday_block",
        "time_slot": "12:15 - 12:55",
        "duration_minutes": 40,
        "dosha_affinity": {"vata": 1.0, "pitta": 0.3, "kapha": -0.2},
        "description": "Consume a warm, unctuous meal featuring cooked grains, roasted root vegetables, and a spoonful of ghee. Eat in quiet warmth.",
        "rationale": "Vata requires warm, heavy, sweet-sour-salty tastes to nourish depleted Dhatus and calm the nervous system.",
        "contraindications": []
    },
    {
        "id": "mitahara_pitta",
        "name": "Mitahara (Cooling, Sweet-Bitter Nourishing Lunch)",
        "block": "midday_block",
        "time_slot": "12:00 - 12:40",
        "duration_minutes": 40,
        "dosha_affinity": {"vata": 0.3, "pitta": 1.0, "kapha": 0.2},
        "description": "Enjoy a substantial plate of basmati rice, steamed greens, cucumber-dill raita, and cooling coconut broth.",
        "rationale": "Strong Pitta Agni peaks at noon; sweet, bitter, and astringent foods prevent hyperacidity and stomach burn.",
        "contraindications": []
    },
    {
        "id": "mitahara_kapha",
        "name": "Mitahara (Katu-Tikta Light & Spiced Lunch)",
        "block": "midday_block",
        "time_slot": "12:30 - 13:00",
        "duration_minutes": 30,
        "dosha_affinity": {"vata": -0.2, "pitta": 0.2, "kapha": 1.0},
        "description": "Eat a light, warm bowl of yellow split mung dal, bitter greens, quinoa, and digestive spices (ginger, black pepper).",
        "rationale": "Kapha requires pungent, bitter, and astringent qualities with low fat to accelerate sluggish metabolic breakdown.",
        "contraindications": []
    },
    {
        "id": "mitahara_tridoshic",
        "name": "Mitahara (Shad-Rasa Six Tastes Balanced Lunch)",
        "block": "midday_block",
        "time_slot": "12:15 - 12:50",
        "duration_minutes": 35,
        "dosha_affinity": {"vata": 0.6, "pitta": 0.6, "kapha": 0.6},
        "description": "Eat a freshly cooked meal incorporating all six Ayurvedic tastes in mindful moderation.",
        "rationale": "Balances all three doshas during the solar peak of Jatharagni without provoking any single humor.",
        "contraindications": []
    },

    # 2. Post-Meal Digestive Integration
    {
        "id": "postmeal_vata",
        "name": "Vajrasana Post-Meal Digestion",
        "block": "midday_block",
        "time_slot": "13:00 - 13:15",
        "duration_minutes": 15,
        "dosha_affinity": {"vata": 1.0, "pitta": 0.4, "kapha": 0.3},
        "description": "Kneel upright in Vajrasana (Thunderbolt pose) for 10-15 minutes immediately after eating.",
        "rationale": "Redirects pelvic circulation to the stomach, preventing Vata bloating and gas accumulation.",
        "contraindications": ["knee_injury"]
    },
    {
        "id": "postmeal_pitta",
        "name": "Shathapavali (Shaded Gentle 100 Steps)",
        "block": "midday_block",
        "time_slot": "12:45 - 13:00",
        "duration_minutes": 15,
        "dosha_affinity": {"vata": 0.4, "pitta": 1.0, "kapha": 0.3},
        "description": "Walk 100 gentle, meditative paces in a cool shaded corridor. Avoid bright sunlight.",
        "rationale": "Gentle movement assists gastric emptying without raising core temperature or agitating Pitta.",
        "contraindications": []
    },
    {
        "id": "postmeal_kapha",
        "name": "Active Shathapavali (Brisk 100 Steps & Upright Posture)",
        "block": "midday_block",
        "time_slot": "13:05 - 13:25",
        "duration_minutes": 20,
        "dosha_affinity": {"vata": 0.1, "pitta": 0.2, "kapha": 1.0},
        "description": "Take 100 brisk paces outdoors and remain strictly upright. Do not sit or lie down.",
        "rationale": "Prevents post-prandial Kapha torpor, somnolence, and metabolic sluggishness.",
        "contraindications": []
    },

    # ==================== EVENING BLOCK ====================
    # 1. Evening Nourishment
    {
        "id": "dinner_vata",
        "name": "Sandhya Ahara (Warm Grounding Soup & Stew)",
        "block": "evening_block",
        "time_slot": "19:00 - 19:35",
        "duration_minutes": 35,
        "dosha_affinity": {"vata": 1.0, "pitta": 0.3, "kapha": -0.2},
        "description": "Partake in a soothing bowl of warm pumpkin-sweet potato soup or nourishing khichdi with ghee.",
        "rationale": "Evening Vata elevation causes nighttime awakenings; warm unctuous nourishment supports sustained sleep.",
        "contraindications": []
    },
    {
        "id": "dinner_pitta",
        "name": "Sandhya Ahara (Cooling Mild Evening Meal)",
        "block": "evening_block",
        "time_slot": "19:15 - 19:45",
        "duration_minutes": 30,
        "dosha_affinity": {"vata": 0.2, "pitta": 1.0, "kapha": 0.2},
        "description": "Light barley soup or zucchini-rice medley seasoned with fennel and coriander. Avoid all chilis and garlic.",
        "rationale": "Eliminates nocturnal acid reflux and liver heat that disrupt deep stage-4 restorative sleep.",
        "contraindications": []
    },
    {
        "id": "dinner_kapha",
        "name": "Laghu Ahara (Ultra-Light Spiced Clear Broth)",
        "block": "evening_block",
        "time_slot": "18:30 - 19:00",
        "duration_minutes": 30,
        "dosha_affinity": {"vata": -0.2, "pitta": 0.2, "kapha": 1.0},
        "description": "Light clear vegetable broth with black pepper, cumin, and fenugreek. Completed early by 19:00.",
        "rationale": "Finishing food 3-4 hours before bedtime prevents midnight Ama accumulation and heavy morning mucus.",
        "contraindications": []
    },
    {
        "id": "dinner_tridoshic",
        "name": "Light Seasonal Dinner",
        "block": "evening_block",
        "time_slot": "19:00 - 19:30",
        "duration_minutes": 30,
        "dosha_affinity": {"vata": 0.6, "pitta": 0.6, "kapha": 0.6},
        "description": "Steamed seasonal vegetables and light khichdi consumed in quiet mindful appreciation.",
        "rationale": "Light evening digestion preserves gut integrity across all constitutions.",
        "contraindications": []
    },

    # 2. Wind-down & Nidra
    {
        "id": "winddown_vata",
        "name": "Pada Abhyanga (Warm Foot Massage) & Screen Curfew",
        "block": "evening_block",
        "time_slot": "21:15 - 21:35",
        "duration_minutes": 20,
        "dosha_affinity": {"vata": 1.0, "pitta": 0.3, "kapha": 0.2},
        "description": "Massage the soles of your feet with warm sesame oil or ghee. Power down all digital screens.",
        "rationale": "Directly pulls excessive mental Prana Vayu down to the earth, eliminating racing thoughts and insomnia.",
        "contraindications": []
    },
    {
        "id": "winddown_pitta",
        "name": "Chandra Bhedana & Cooling Rose Relaxation",
        "block": "evening_block",
        "time_slot": "21:30 - 21:45",
        "duration_minutes": 15,
        "dosha_affinity": {"vata": 0.3, "pitta": 1.0, "kapha": 0.1},
        "description": "Practice left-nostril breathing (Chandra Bhedana) and rest with cool rose water pads over eyes.",
        "rationale": "Releases screen glare eye-strain, calms Alochaka Pitta, and cools nighttime emotional intensity.",
        "contraindications": []
    },
    {
        "id": "winddown_kapha",
        "name": "Trataka (Candle Gazing) & Ginger-Tulsi Wind-Down",
        "block": "evening_block",
        "time_slot": "21:00 - 21:20",
        "duration_minutes": 20,
        "dosha_affinity": {"vata": 0.1, "pitta": -0.2, "kapha": 1.0},
        "description": "Engage in 5 minutes of focused candle gazing (Trataka) followed by warm ginger-tulsi herbal infusion.",
        "rationale": "Sharpens sluggish mental perception and ensures peaceful, non-lethargic morning awakening.",
        "contraindications": ["eye_inflammation"]
    },
    {
        "id": "winddown_tridoshic",
        "name": "Trataka / Mindful Evening Reflection",
        "block": "evening_block",
        "time_slot": "21:30 - 21:45",
        "duration_minutes": 15,
        "dosha_affinity": {"vata": 0.5, "pitta": 0.5, "kapha": 0.5},
        "description": "Dim lights, practice soft breathing, and prepare for rest in peaceful stillness.",
        "rationale": "Supports natural melatonin release and calms sensory organs for restorative sleep.",
        "contraindications": []
    }
]


def score_candidate(
    candidate: Dict[str, Any],
    profile: DoshaProfile,
    vikriti_flags: VikritiFlags,
    completed_today: List[str]
) -> float:
    """
    Computes an explicit match score for a candidate practice given the user's
    Prakriti vector and active Vikriti aggravation flags.
    """
    # 1. Zero out if already completed today
    c_name_lower = candidate["name"].lower()
    if any(done.lower() in c_name_lower or c_name_lower in done.lower() for done in completed_today):
        return -999.0

    # 2. Check clinical contraindications
    contras = candidate.get("contraindications", [])
    if vikriti_flags.has_fever:
        if any(c in ("fever", "nava_jwara") for c in contras):
            return -999.0
        if "massage" in c_name_lower or "abhyanga" in c_name_lower:
            return -999.0
    if vikriti_flags.pitta_aggravated and "pitta_aggravated" in contras:
        return -999.0

    prakriti = profile.prakriti
    affinity = candidate.get("dosha_affinity", {})

    # 3. Base score derived from Prakriti dot product
    v_score = affinity.get("vata", 0.0) * prakriti.vata
    p_score = affinity.get("pitta", 0.0) * prakriti.pitta
    k_score = affinity.get("kapha", 0.0) * prakriti.kapha
    score = v_score + p_score + k_score

    # 4. Vikriti dynamic weighting (active imbalances get prioritized relief)
    if vikriti_flags.vata_aggravated and affinity.get("vata", 0.0) > 0.5:
        score += 0.5
    if vikriti_flags.pitta_aggravated and affinity.get("pitta", 0.0) > 0.5:
        score += 0.5
    if vikriti_flags.kapha_aggravated and affinity.get("kapha", 0.0) > 0.5:
        score += 0.5

    return round(score, 3)


def select_personalized_practices(
    profile: DoshaProfile,
    complexity: str = "Moderate",
    completed_today: Optional[List[str]] = None
) -> Dict[str, List[Practice]]:
    """
    Deterministically selects and sorts personalized practices for all three blocks.
    Guarantees that Vata, Pitta, Kapha, Dual, and Tridoshic profiles receive distinct,
    tailored practices across morning, midday, and evening.
    """
    completed_today = completed_today or []
    flags = profile.vikriti_flags or VikritiFlags()

    # Fever emergency override (Nava Jwara protocol)
    if flags.has_fever:
        return {
            "morning_block": [
                Practice(
                    name="Ushnodaka & Rest (Warm Hydration)",
                    time_slot="07:00 - 07:20",
                    duration_minutes=20,
                    description="Sip warm boiled water and rest in a well-ventilated, quiet room.",
                    rationale="Nava Jwara protocol: Light warm water supports digestion and clears Ama without taxing Agni."
                )
            ],
            "midday_block": [
                Practice(
                    name="Mitahara (Light Peya / Rice Gruel)",
                    time_slot="12:30 - 13:00",
                    duration_minutes=30,
                    description="Consume light warm rice water or clear vegetable broth.",
                    rationale="Prevents digestive overload while sustaining basic metabolic strength."
                )
            ],
            "evening_block": [
                Practice(
                    name="Deep Rest & Early Sleep",
                    time_slot="20:30 - 21:00",
                    duration_minutes=30,
                    description="Dim lights completely and sleep early to support immune recovery.",
                    rationale="Deep sleep restores Ojas and allows the body to resolve pyrexia."
                )
            ]
        }

    # Group candidate practices by block
    blocks = {"morning_block": [], "midday_block": [], "evening_block": []}
    scored_candidates = []

    for cand in CANDIDATE_PRACTICES:
        blk = cand["block"]
        score = score_candidate(cand, profile, flags, completed_today)
        if score > -900.0:
            scored_candidates.append((score, cand))

    # Sort candidates by score descending
    scored_candidates.sort(key=lambda x: x[0], reverse=True)

    # Complexity limit:
    # Anchor Habits: 1 practice per block
    # Moderate: 2 morning, 1-2 midday, 1-2 evening
    # Advanced: 3 morning, 2 midday, 2 evening
    max_counts = {
        "Anchor Habits": {"morning_block": 1, "midday_block": 1, "evening_block": 1},
        "Moderate": {"morning_block": 2, "midday_block": 2, "evening_block": 2},
        "Advanced": {"morning_block": 3, "midday_block": 2, "evening_block": 2}
    }.get(complexity, {"morning_block": 2, "midday_block": 2, "evening_block": 2})

    selected = {"morning_block": [], "midday_block": [], "evening_block": []}
    for score, cand in scored_candidates:
        blk = cand["block"]
        if len(selected[blk]) < max_counts[blk]:
            # Avoid picking two practices of the same category (e.g. two wake practices)
            existing_names = [p.name.lower() for p in selected[blk]]
            is_wake = "wake" in cand["id"]
            if is_wake and any("wake" in n or "jagaran" in n for n in existing_names):
                continue
            selected[blk].append(Practice(
                name=cand["name"],
                time_slot=cand["time_slot"],
                duration_minutes=cand["duration_minutes"],
                description=cand["description"],
                rationale=cand["rationale"]
            ))

    # Ensure chronological sorting within each block
    from src.safety.guardrails import _parse_slot_minutes
    for blk in ["morning_block", "midday_block", "evening_block"]:
        selected[blk].sort(key=lambda p: (_parse_slot_minutes(p.time_slot, p.duration_minutes)[0] if _parse_slot_minutes(p.time_slot, p.duration_minutes) else 9999, p.name))

    return selected
