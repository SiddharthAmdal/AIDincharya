"""
prakriti_questions.py - 24-Question Prakriti Assessment Catalog and Validation

Provides the structured catalog of 24 classical Ayurvedic Prakriti assessment questions
divided into Physical, Physiological, and Psychological/Behavioral dimensions,
along with server-side validation and provisional scoring helpers.
"""

from typing import Dict, List, Any, Tuple, Optional


PRAKRITI_SECTIONS = [
    {
        "id": "A",
        "title": "Section A: Physical Characteristics",
        "description": "Natural anatomical frame, skin, hair, eyes, temperature, and weight tendencies.",
        "question_ids": ["q1", "q2", "q3", "q4", "q5", "q6"]
    },
    {
        "id": "B",
        "title": "Section B: Physiological Characteristics",
        "description": "Metabolism (Agni), appetite, digestion, bowel habits, thirst, heat tolerance, sleep, energy, and sweat.",
        "question_ids": ["q7", "q8", "q9", "q10", "q11", "q12", "q13", "q14", "q15", "q16"]
    },
    {
        "id": "C",
        "title": "Section C: Psychological and Behavioral Characteristics",
        "description": "Cognitive pace, learning style, memory, stress response, decision-making, speech, adaptability, and activity.",
        "question_ids": ["q17", "q18", "q19", "q20", "q21", "q22", "q23", "q24"]
    }
]


PRAKRITI_QUESTIONS: List[Dict[str, Any]] = [
    # --- Section A: Physical Characteristics ---
    {
        "id": "q1",
        "number": 1,
        "section": "A",
        "section_title": "Physical Characteristics",
        "text": "What best describes your natural body frame?",
        "options": [
            {
                "value": "vata",
                "dosha": "vata",
                "text": "Slender, lean, or lighter bone structure; joints may be prominent or delicate."
            },
            {
                "value": "pitta",
                "dosha": "pitta",
                "text": "Moderate, symmetrical, athletic build with medium bone structure."
            },
            {
                "value": "kapha",
                "dosha": "kapha",
                "text": "Solid, sturdy, broad frame with heavier or well-cushioned bone structure."
            }
        ]
    },
    {
        "id": "q2",
        "number": 2,
        "section": "A",
        "section_title": "Physical Characteristics",
        "text": "How would you describe your skin texture?",
        "options": [
            {
                "value": "vata",
                "dosha": "vata",
                "text": "Tends toward dry, rough, thin, or cool to the touch; prone to chapping in dry weather."
            },
            {
                "value": "pitta",
                "dosha": "pitta",
                "text": "Warm, sensitive, reddish or prone to flushing, freckles, or mild irritation."
            },
            {
                "value": "kapha",
                "dosha": "kapha",
                "text": "Smooth, soft, cool, thick, well-hydrated, and naturally moisturized."
            }
        ]
    },
    {
        "id": "q3",
        "number": 3,
        "section": "A",
        "section_title": "Physical Characteristics",
        "text": "What best describes your hair?",
        "options": [
            {
                "value": "vata",
                "dosha": "vata",
                "text": "Dry, fine, brittle, or frizzy; tends toward darker or uneven texture."
            },
            {
                "value": "pitta",
                "dosha": "pitta",
                "text": "Fine, soft, silky; prone to early thinning, graying, or reddish/fair tones."
            },
            {
                "value": "kapha",
                "dosha": "kapha",
                "text": "Thick, lustrous, wavy, abundant, and naturally well-rooted and strong."
            }
        ]
    },
    {
        "id": "q4",
        "number": 4,
        "section": "A",
        "section_title": "Physical Characteristics",
        "text": "How would you describe your eyes?",
        "options": [
            {
                "value": "vata",
                "dosha": "vata",
                "text": "Small to medium, lively movement, often dry, quick or blinking frequently."
            },
            {
                "value": "pitta",
                "dosha": "pitta",
                "text": "Medium-sized, sharp, focused, piercing gaze; sensitive to bright sunlight."
            },
            {
                "value": "kapha",
                "dosha": "kapha",
                "text": "Large, wide, calm, deep, attractive gaze with thick, prominent eyelashes."
            }
        ]
    },
    {
        "id": "q5",
        "number": 5,
        "section": "A",
        "section_title": "Physical Characteristics",
        "text": "What is the usual temperature of your hands and feet?",
        "options": [
            {
                "value": "vata",
                "dosha": "vata",
                "text": "Tend to feel cold or cool frequently; sensitive to drafts and chilly weather."
            },
            {
                "value": "pitta",
                "dosha": "pitta",
                "text": "Consistently warm; hands and feet naturally generate noticeable heat."
            },
            {
                "value": "kapha",
                "dosha": "kapha",
                "text": "Comfortable and steady, though sometimes pleasantly cool and slightly moist."
            }
        ]
    },
    {
        "id": "q6",
        "number": 6,
        "section": "A",
        "section_title": "Physical Characteristics",
        "text": "What best describes your natural weight pattern?",
        "options": [
            {
                "value": "vata",
                "dosha": "vata",
                "text": "Difficult to gain weight; tends to fluctuate or lose weight easily during stress."
            },
            {
                "value": "pitta",
                "dosha": "pitta",
                "text": "Stable, moderate weight; gains or loses with deliberate effort and exercise."
            },
            {
                "value": "kapha",
                "dosha": "kapha",
                "text": "Tends to gain weight easily; loses weight slowly despite regular routine."
            }
        ]
    },

    # --- Section B: Physiological Characteristics ---
    {
        "id": "q7",
        "number": 7,
        "section": "B",
        "section_title": "Physiological Characteristics",
        "text": "How would you describe your appetite?",
        "options": [
            {
                "value": "vata",
                "dosha": "vata",
                "text": "Irregular and variable; sometimes very hungry and other times forgetting to eat."
            },
            {
                "value": "pitta",
                "dosha": "pitta",
                "text": "Strong, sharp, intense; feels distinct hunger at regular mealtimes and needs food."
            },
            {
                "value": "kapha",
                "dosha": "kapha",
                "text": "Steady, mild to moderate; can comfortably skip a meal without discomfort."
            }
        ]
    },
    {
        "id": "q8",
        "number": 8,
        "section": "B",
        "section_title": "Physiological Characteristics",
        "text": "How do you feel when a meal is delayed?",
        "options": [
            {
                "value": "vata",
                "dosha": "vata",
                "text": "Anxious, lightheaded, scattered, or experiencing mild shaky energy."
            },
            {
                "value": "pitta",
                "dosha": "pitta",
                "text": "Irritable, frustrated, impatient ('hangry'), or experiencing acid sensations."
            },
            {
                "value": "kapha",
                "dosha": "kapha",
                "text": "Generally calm, patient, unbothered, and able to wait comfortably."
            }
        ]
    },
    {
        "id": "q9",
        "number": 9,
        "section": "B",
        "section_title": "Physiological Characteristics",
        "text": "How would you describe your digestion?",
        "options": [
            {
                "value": "vata",
                "dosha": "vata",
                "text": "Variable or delicate (Vishama Agni); prone to gas, bloating, or inconsistent digestive speed."
            },
            {
                "value": "pitta",
                "dosha": "pitta",
                "text": "Quick and intense (Tikshna Agni); prone to hyperacidity, burning sensations, or quick transit."
            },
            {
                "value": "kapha",
                "dosha": "kapha",
                "text": "Slow and steady (Manda Agni); feeling heavy, full, or lethargic for several hours after eating."
            }
        ]
    },
    {
        "id": "q10",
        "number": 10,
        "section": "B",
        "section_title": "Physiological Characteristics",
        "text": "What best describes your usual bowel habits?",
        "options": [
            {
                "value": "vata",
                "dosha": "vata",
                "text": "Tends toward dry, hard, irregular, or prone to constipation."
            },
            {
                "value": "pitta",
                "dosha": "pitta",
                "text": "Regular, soft, loose, or occurring multiple times a day."
            },
            {
                "value": "kapha",
                "dosha": "kapha",
                "text": "Regular, thick, well-formed, steady, sometimes feeling slow or sluggish."
            }
        ]
    },
    {
        "id": "q11",
        "number": 11,
        "section": "B",
        "section_title": "Physiological Characteristics",
        "text": "How would you describe your thirst?",
        "options": [
            {
                "value": "vata",
                "dosha": "vata",
                "text": "Variable and unpredictable; fluctuates between dry mouth and forgetting to drink."
            },
            {
                "value": "pitta",
                "dosha": "pitta",
                "text": "High and frequent; strong natural preference for cool or refreshing beverages."
            },
            {
                "value": "kapha",
                "dosha": "kapha",
                "text": "Low to moderate; rarely feels intensely thirsty and prefers warm drinks."
            }
        ]
    },
    {
        "id": "q12",
        "number": 12,
        "section": "B",
        "section_title": "Physiological Characteristics",
        "text": "How do you usually respond to hot weather?",
        "options": [
            {
                "value": "vata",
                "dosha": "vata",
                "text": "Enjoys warmth and sunny weather; feels relaxed, limber, and energized by heat."
            },
            {
                "value": "pitta",
                "dosha": "pitta",
                "text": "Dislikes excessive heat; becomes quickly fatigued, irritable, or overheated."
            },
            {
                "value": "kapha",
                "dosha": "kapha",
                "text": "Tolerates heat well; prefers warm, dry weather over cold, damp environments."
            }
        ]
    },
    {
        "id": "q13",
        "number": 13,
        "section": "B",
        "section_title": "Physiological Characteristics",
        "text": "What is your usual sleep pattern?",
        "options": [
            {
                "value": "vata",
                "dosha": "vata",
                "text": "Light, easily disrupted by sounds; tends to wake up during the night."
            },
            {
                "value": "pitta",
                "dosha": "pitta",
                "text": "Sound, moderate (6–7 hours); wakes up alert and ready for the day."
            },
            {
                "value": "kapha",
                "dosha": "kapha",
                "text": "Deep, heavy, undisturbed (8+ hours); often difficult or slow to get out of bed."
            }
        ]
    },
    {
        "id": "q14",
        "number": 14,
        "section": "B",
        "section_title": "Physiological Characteristics",
        "text": "How easily do you fall asleep?",
        "options": [
            {
                "value": "vata",
                "dosha": "vata",
                "text": "Takes time; mind tends to race or wander with thoughts before falling asleep."
            },
            {
                "value": "pitta",
                "dosha": "pitta",
                "text": "Falls asleep easily within 15–20 minutes, unless mentally planning or intensely driven."
            },
            {
                "value": "kapha",
                "dosha": "kapha",
                "text": "Falls asleep almost immediately and effortlessly upon lying down."
            }
        ]
    },
    {
        "id": "q15",
        "number": 15,
        "section": "B",
        "section_title": "Physiological Characteristics",
        "text": "How would you describe your daytime energy?",
        "options": [
            {
                "value": "vata",
                "dosha": "vata",
                "text": "Comes in bursts of enthusiasm followed by sudden fatigue or energy crashes."
            },
            {
                "value": "pitta",
                "dosha": "pitta",
                "text": "Focused, purposeful, high stamina; tends to push through tasks until complete."
            },
            {
                "value": "kapha",
                "dosha": "kapha",
                "text": "Consistent, enduring, steady stamina that builds gradually over the day."
            }
        ]
    },
    {
        "id": "q16",
        "number": 16,
        "section": "B",
        "section_title": "Physiological Characteristics",
        "text": "How much do you usually sweat?",
        "options": [
            {
                "value": "vata",
                "dosha": "vata",
                "text": "Minimal perspiration, even during physical activity; low body odor."
            },
            {
                "value": "pitta",
                "dosha": "pitta",
                "text": "Profuse or easily induced perspiration; warm body temperature and distinct odor."
            },
            {
                "value": "kapha",
                "dosha": "kapha",
                "text": "Moderate, steady perspiration, primarily during prolonged exertion."
            }
        ]
    },

    # --- Section C: Psychological and Behavioral Characteristics ---
    {
        "id": "q17",
        "number": 17,
        "section": "C",
        "section_title": "Psychological and Behavioral Characteristics",
        "text": "What best describes your usual thinking pace?",
        "options": [
            {
                "value": "vata",
                "dosha": "vata",
                "text": "Quick, imaginative, branching in many creative directions simultaneously."
            },
            {
                "value": "pitta",
                "dosha": "pitta",
                "text": "Logical, analytical, precise, goal-directed, and structured."
            },
            {
                "value": "kapha",
                "dosha": "kapha",
                "text": "Calm, contemplative, thorough, methodical, and patient."
            }
        ]
    },
    {
        "id": "q18",
        "number": 18,
        "section": "C",
        "section_title": "Psychological and Behavioral Characteristics",
        "text": "How do you usually learn something new?",
        "options": [
            {
                "value": "vata",
                "dosha": "vata",
                "text": "Grasps concepts rapidly, but may forget details if not reinforced soon."
            },
            {
                "value": "pitta",
                "dosha": "pitta",
                "text": "Grasps clearly and critically, retaining practical, applicable principles."
            },
            {
                "value": "kapha",
                "dosha": "kapha",
                "text": "Takes longer to absorb, but once mastered, retains knowledge long-term."
            }
        ]
    },
    {
        "id": "q19",
        "number": 19,
        "section": "C",
        "section_title": "Psychological and Behavioral Characteristics",
        "text": "How would you describe your memory?",
        "options": [
            {
                "value": "vata",
                "dosha": "vata",
                "text": "Strong short-term recall; tends to forget past details or misplace items."
            },
            {
                "value": "pitta",
                "dosha": "pitta",
                "text": "Clear, articulate, sharp recall of relevant facts and chronological events."
            },
            {
                "value": "kapha",
                "dosha": "kapha",
                "text": "Slow to register, but exceptionally strong, deep, and enduring long-term memory."
            }
        ]
    },
    {
        "id": "q20",
        "number": 20,
        "section": "C",
        "section_title": "Psychological and Behavioral Characteristics",
        "text": "How do you usually react to stress?",
        "options": [
            {
                "value": "vata",
                "dosha": "vata",
                "text": "Feels anxious, fearful, overwhelmed, restless, or overthinks scenarios."
            },
            {
                "value": "pitta",
                "dosha": "pitta",
                "text": "Becomes assertive, demanding, frustrated, impatient, or argumentative."
            },
            {
                "value": "kapha",
                "dosha": "kapha",
                "text": "Remains calm on the surface, withdraws, avoids confrontation, or becomes inert."
            }
        ]
    },
    {
        "id": "q21",
        "number": 21,
        "section": "C",
        "section_title": "Psychological and Behavioral Characteristics",
        "text": "How do you typically make decisions?",
        "options": [
            {
                "value": "vata",
                "dosha": "vata",
                "text": "Can hesitate, second-guess, or change mind frequently when options abound."
            },
            {
                "value": "pitta",
                "dosha": "pitta",
                "text": "Decisive, direct, confident, and action-oriented based on available data."
            },
            {
                "value": "kapha",
                "dosha": "kapha",
                "text": "Deliberate, cautious, takes time to ponder, and dislikes rushed choices."
            }
        ]
    },
    {
        "id": "q22",
        "number": 22,
        "section": "C",
        "section_title": "Psychological and Behavioral Characteristics",
        "text": "How would you describe your speaking style?",
        "options": [
            {
                "value": "vata",
                "dosha": "vata",
                "text": "Fast, animated, expressive, sometimes jumping between different topics."
            },
            {
                "value": "pitta",
                "dosha": "pitta",
                "text": "Clear, persuasive, articulate, direct, and sometimes sharp or authoritative."
            },
            {
                "value": "kapha",
                "dosha": "kapha",
                "text": "Soft, resonant, calm, measured, gentle, and thoughtful."
            }
        ]
    },
    {
        "id": "q23",
        "number": 23,
        "section": "C",
        "section_title": "Psychological and Behavioral Characteristics",
        "text": "How do you usually respond to new activities or changes?",
        "options": [
            {
                "value": "vata",
                "dosha": "vata",
                "text": "Excited, spontaneous, welcomes variety, though may lose steam early."
            },
            {
                "value": "pitta",
                "dosha": "pitta",
                "text": "Embraces change if it serves a clear goal, plan, or improvement."
            },
            {
                "value": "kapha",
                "dosha": "kapha",
                "text": "Prefers familiar routines, steady habits, and resists sudden disruptions."
            }
        ]
    },
    {
        "id": "q24",
        "number": 24,
        "section": "C",
        "section_title": "Psychological and Behavioral Characteristics",
        "text": "What best describes your usual activity pattern?",
        "options": [
            {
                "value": "vata",
                "dosha": "vata",
                "text": "Restless, constantly moving, likes starting new projects and multitasking."
            },
            {
                "value": "pitta",
                "dosha": "pitta",
                "text": "Organized, driven, competitive, structured, and focused on milestones."
            },
            {
                "value": "kapha",
                "dosha": "kapha",
                "text": "Relaxed, unhurried, steady, prefers one task at a time with regular pacing."
            }
        ]
    }
]

EXPECTED_QUESTION_IDS = set(q["id"] for q in PRAKRITI_QUESTIONS)
ALLOWED_DOSHA_VALUES = {"vata", "pitta", "kapha"}


def get_prakriti_catalog() -> Dict[str, Any]:
    """Returns the full structured questionnaire catalog with sections and metadata."""
    return {
        "version": "24-question-v1",
        "total_questions": len(PRAKRITI_QUESTIONS),
        "sections": PRAKRITI_SECTIONS,
        "questions": PRAKRITI_QUESTIONS
    }


def validate_questionnaire_responses(responses: Any) -> Tuple[bool, Optional[str]]:
    """
    Validates questionnaire submission on the server:
    1. Must be a non-empty dictionary.
    2. Must contain exactly all 24 question identifiers (q1 through q24).
    3. No unknown question identifiers allowed.
    4. Each response value must be one of 'vata', 'pitta', 'kapha' (case-insensitive).
    """
    if not isinstance(responses, dict):
        return False, "Questionnaire responses must be provided as a key-value dictionary."

    received_keys = set(responses.keys())

    # Check for missing questions
    missing = sorted(list(EXPECTED_QUESTION_IDS - received_keys), key=lambda x: int(x[1:]) if x[1:].isdigit() else 999)
    if missing:
        return False, f"Incomplete questionnaire submission. Missing {len(missing)} question(s): {', '.join(missing)}."

    # Check for unknown question identifiers
    extra = sorted(list(received_keys - EXPECTED_QUESTION_IDS))
    if extra:
        return False, f"Invalid question identifier(s): {', '.join(extra)}. Expected q1 through q24."

    # Validate allowed values
    for q_id in sorted(list(EXPECTED_QUESTION_IDS), key=lambda x: int(x[1:])):
        val = responses.get(q_id)
        if not isinstance(val, str) or val.strip().lower() not in ALLOWED_DOSHA_VALUES:
            val_display = repr(val) if val is not None else "missing"
            return False, f"Invalid value {val_display} for question '{q_id}'. Allowed values are 'vata', 'pitta', or 'kapha'."

    return True, None
