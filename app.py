import hashlib
import re

import streamlit as st


TOPIC_KEYWORDS = {
    "Hypertension": [
        "hypertension",
        "high blood pressure",
        "antihypertensive",
        "blood pressure",
    ],
    "Hypertensive Emergency": [
        "hypertensive emergency",
        "hypertensive crisis",
        "target-organ damage",
        "target organ damage",
        "blood pressure above 180/120",
        "180/120",
    ],
    "Stroke": [
        "stroke",
        "cerebrovascular accident",
        "CVA",
        "TIA",
        "facial droop",
        "unilateral weakness",
        "slurred speech",
        "last known well",
    ],
    "Peripheral Arterial Disease": [
        "peripheral arterial disease",
        "PAD",
        "arterial insufficiency",
        "intermittent claudication",
        "rest pain",
        "dependent rubor",
        "six Ps",
        "6 Ps",
    ],
    "Deep Vein Thrombosis": [
        "deep vein thrombosis",
        "DVT",
        "venous thrombosis",
        "Virchow",
        "unilateral edema",
        "calf tenderness",
    ],
    "Anticoagulation": [
        "heparin",
        "enoxaparin",
        "Lovenox",
        "warfarin",
        "Coumadin",
        "anticoagulant",
        "INR",
        "aPTT",
        "anti-Xa",
        "protamine",
    ],
    "Atherosclerosis and Coronary Artery Disease": [
        "atherosclerosis",
        "arteriosclerosis",
        "coronary artery disease",
        "CAD",
        "plaque",
        "atheroma",
        "HDL",
        "LDL",
        "cholesterol",
    ],
}


def normalize_response_text(text):
    """Lowercase, strip hyphens/punctuation, and collapse whitespace."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def has_phrase(padded_text, phrase):
    return f" {phrase} " in padded_text


def has_any_phrase(padded_text, phrases):
    return any(has_phrase(padded_text, phrase) for phrase in phrases)


def detect_study_topics(text):
    """Scan text for whole-word keyword matches and group results by topic."""
    results = []

    for topic_name, keywords in TOPIC_KEYWORDS.items():
        matched_keywords = []
        total_matches = 0

        for keyword in keywords:
            pattern = r"\b" + re.escape(keyword) + r"\b"
            match_count = len(re.findall(pattern, text, flags=re.IGNORECASE))
            if match_count > 0:
                total_matches += match_count
                matched_keywords.append(keyword)

        if total_matches > 0:
            results.append((topic_name, total_matches, matched_keywords))

    results.sort(key=lambda result: result[1], reverse=True)
    return results


def compute_stage1_categories(padded_response):
    """Return the four initial Hypertensive Emergency priority categories."""

    # Category 1: verify the blood pressure needs a BP term AND a
    # recheck-style action word, in any order and with any words
    # between them (e.g. "repeat the blood pressure manually").
    bp_term_present = has_any_phrase(padded_response, ["blood pressure", "bp"])
    bp_action_words = ["repeat", "recheck", "retake", "verify", "confirm"]
    bp_action_present = has_any_phrase(padded_response, bp_action_words)
    check_again_present = has_phrase(padded_response, "check") and has_phrase(
        padded_response, "again"
    )
    take_again_present = has_phrase(padded_response, "take") and has_phrase(
        padded_response, "again"
    )
    bp_recognized = bp_term_present and (
        bp_action_present or check_again_present or take_again_present
    )

    # Category 2: focused neurological assessment.
    neuro_phrases = [
        "neurological assessment",
        "neurologic assessment",
        "neuro assessment",
        "neurological check",
        "neurologic check",
        "neurological checks",
        "neurologic checks",
        "neurological status",
        "neurologic status",
        "level of consciousness",
        "mental status",
        "check pupils",
        "assess pupils",
        "pupils",
        "assess for stroke",
        "stroke symptoms",
    ]
    neuro_recognized = has_any_phrase(padded_response, neuro_phrases)

    # Category 3: continuous monitoring.
    monitor_phrases = [
        "continuous monitoring",
        "cardiac monitoring",
        "telemetry",
        "monitor vital signs",
        "frequent vital signs",
        "place on monitor",
        "on the monitor",
        "cycle blood pressure",
        "cycle blood pressures",
    ]
    monitor_recognized = has_any_phrase(padded_response, monitor_phrases)

    # Category 4: escalate care, either via "notify/call ... provider"
    # (any words allowed between them) or any rapid response mention.
    communication_words = ["notify", "call", "contact", "page", "inform"]
    recipient_words = ["provider", "physician", "doctor"]
    communication_present = has_any_phrase(padded_response, communication_words)
    recipient_present = has_any_phrase(padded_response, recipient_words)
    escalate_via_provider = communication_present and recipient_present
    escalate_via_rapid_response = has_any_phrase(
        padded_response, ["rapid response", "rrt"]
    )
    escalate_recognized = escalate_via_provider or escalate_via_rapid_response

    return [
        ("Verify the blood pressure", bp_recognized),
        ("Perform a focused neurological assessment", neuro_recognized),
        ("Begin continuous monitoring", monitor_recognized),
        ("Escalate care", escalate_recognized),
    ]


def compute_stage2_categories(padded_second_response):
    """Return the six second-stage Hypertensive Emergency priority categories."""

    # Category 1: activate the stroke response / escalate care,
    # either via a direct phrase or a communication word paired
    # with a provider/team word anywhere in the response.
    stroke_phrases = [
        "stroke alert",
        "stroke code",
        "code stroke",
        "activate stroke team",
        "notify stroke team",
        "rapid response",
        "rrt",
        "call rapid response",
        "activate rrt",
        "notify provider",
        "call provider",
        "notify physician",
        "call physician",
        "escalate care",
    ]
    stroke_direct = has_any_phrase(padded_second_response, stroke_phrases)
    escalate_communication_words = [
        "notify",
        "call",
        "contact",
        "page",
        "inform",
        "activate",
    ]
    escalate_target_words = [
        "provider",
        "physician",
        "doctor",
        "stroke team",
        "rapid response",
        "rrt",
    ]
    escalate_communication_present = has_any_phrase(
        padded_second_response, escalate_communication_words
    )
    escalate_target_present = has_any_phrase(
        padded_second_response, escalate_target_words
    )
    stroke_recognized = stroke_direct or (
        escalate_communication_present and escalate_target_present
    )

    # Category 2: immediate focused neurological assessment.
    neuro_stage2_phrases = [
        "focused neurological assessment",
        "focused neurologic assessment",
        "focused neuro assessment",
        "neurological assessment",
        "neurologic assessment",
        "neuro assessment",
        "neurological checks",
        "neurologic checks",
        "neuro checks",
        "nihss",
        "stroke scale",
        "assess pupils",
        "assess mental status",
        "assess level of consciousness",
        "check level of consciousness",
        "assess strength",
        "assess speech",
        "assess facial droop",
        "assess for stroke symptoms",
    ]
    neuro_stage2_recognized = has_any_phrase(padded_second_response, neuro_stage2_phrases)

    # Category 3: confirm and document the last-known-well time.
    last_known_well_phrases = [
        "last known well",
        "last known normal",
        "time last known well",
        "document last known well",
        "note last known well",
        "determine symptom onset",
        "time symptoms began",
        "establish onset time",
        "document onset time",
    ]
    last_known_well_recognized = has_any_phrase(
        padded_second_response, last_known_well_phrases
    )

    # Category 4: check bedside blood glucose, either via a direct
    # phrase or a glucose-related word paired with an action word.
    glucose_phrases = [
        "blood glucose",
        "bedside glucose",
        "glucose level",
        "fingerstick glucose",
        "finger stick glucose",
        "point of care glucose",
        "poc glucose",
        "check glucose",
        "check blood sugar",
        "bedside blood sugar",
        "bg",
    ]
    glucose_direct = has_any_phrase(padded_second_response, glucose_phrases)
    glucose_words = ["glucose", "blood sugar", "bg"]
    glucose_action_words = ["check", "obtain", "measure", "assess", "perform"]
    glucose_word_present = has_any_phrase(padded_second_response, glucose_words)
    glucose_action_present = has_any_phrase(padded_second_response, glucose_action_words)
    glucose_recognized = glucose_direct or (
        glucose_word_present and glucose_action_present
    )

    # Category 5: prepare for urgent brain imaging.
    imaging_phrases = [
        "head ct",
        "ct head",
        "ct scan",
        "noncontrast ct",
        "non contrast ct",
        "brain ct",
        "urgent ct",
        "stat ct",
        "prepare for ct",
        "transport to ct",
        "prepare for brain imaging",
        "urgent brain imaging",
        "stroke imaging",
    ]
    imaging_recognized = has_any_phrase(padded_second_response, imaging_phrases)

    # Category 6: protect airway and swallowing safety.
    airway_phrases = [
        "maintain airway",
        "assess airway",
        "monitor airway",
        "protect airway",
        "suction available",
        "aspiration precautions",
        "keep npo",
        "npo",
        "nothing by mouth",
        "no food or fluids",
        "swallow screen",
        "swallowing screen",
        "dysphagia screen",
        "assess swallowing",
        "safety precautions",
        "elevate head of bed",
        "position safely",
    ]
    airway_recognized = has_any_phrase(padded_second_response, airway_phrases)

    return [
        ("Activate the stroke response and escalate care", stroke_recognized),
        ("Perform an immediate focused neurological assessment", neuro_stage2_recognized),
        ("Confirm and document the last-known-well time", last_known_well_recognized),
        ("Check bedside blood glucose", glucose_recognized),
        ("Prepare for urgent brain imaging", imaging_recognized),
        ("Protect airway and swallowing safety", airway_recognized),
    ]


st.title("Clinical Scenario Lab")

st.warning("Educational simulation only. Do not use during actual patient care.")

st.write("This program will eventually create interactive nursing patient scenarios.")

st.header("Upload Study Material")

st.write(
    "Start by uploading a plain-text nursing note or transcript. The program "
    "will confirm that it can read the file. PDF, PowerPoint, and Word support "
    "will be added later."
)

study_file = st.file_uploader("Choose a TXT study file", type=["txt"])

if study_file is None:
    st.session_state.pop("study_analysis_results", None)
    st.session_state.pop("study_analysis_file_id", None)
    st.write("No study file uploaded yet.")
else:
    study_file_bytes = study_file.getvalue()

    current_study_file_id = (
        f"{study_file.name}:{len(study_file_bytes)}:"
        f"{hashlib.md5(study_file_bytes).hexdigest()}"
    )
    if st.session_state.get("study_analysis_file_id") != current_study_file_id:
        st.session_state.study_analysis_results = None
        st.session_state.study_analysis_file_id = current_study_file_id

    if len(study_file_bytes) == 0:
        st.write("This TXT file is empty. Please upload a file containing study material.")
    else:
        try:
            study_file_text = study_file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            study_file_text = None
            st.write(
                "The file could not be read as plain text. Please upload a "
                "standard TXT file."
            )

        if study_file_text is not None:
            st.write("File uploaded successfully.")
            st.write(f"File name: {study_file.name}")
            st.write(f"Characters read: {len(study_file_text)}")
            st.write(f"Words read: {len(study_file_text.split())}")

            with st.expander("Preview uploaded text"):
                st.write(study_file_text[:2000])
                if len(study_file_text) > 2000:
                    st.write(
                        "Preview shortened. The complete text remains available "
                        "during this session."
                    )

            st.subheader("Study Topic Detection")

            if st.button("Analyze Uploaded Notes"):
                st.session_state.study_analysis_results = detect_study_topics(
                    study_file_text
                )

            if st.session_state.get("study_analysis_results") is not None:
                detected_topics = st.session_state.study_analysis_results

                if detected_topics:
                    for topic_name, match_count, _ in detected_topics:
                        st.write(f"✅ {topic_name} — {match_count} matches")
                    st.write(
                        "Detected topics are based on simple keyword matching. "
                        "AI-based understanding will be added later."
                    )
                    with st.expander("View matched terms"):
                        for topic_name, _, matched_keywords in detected_topics:
                            st.write(f"**{topic_name}**")
                            for keyword in matched_keywords:
                                st.write(f"- {keyword}")
                else:
                    st.write(
                        "No supported nursing topics were detected in this TXT "
                        "file yet."
                    )

st.write(
    "Privacy reminder: Do not upload real patient names, medical record numbers, "
    "dates of birth, addresses, or other protected health information."
)

topic = st.selectbox(
    "Choose a nursing topic",
    ["Hypertensive Emergency", "Peripheral Arterial Disease", "Deep Vein Thrombosis"],
)

if "scenario_started" not in st.session_state:
    st.session_state.scenario_started = False

if st.button("Start Scenario"):
    st.session_state.scenario_started = True
    st.session_state.he_submitted_action = None
    st.session_state.he_stage2_active = False
    st.session_state.he_submitted_second_action = None
    st.session_state.he_show_debrief = False
    st.session_state.pop("he_first_action_box", None)
    st.session_state.pop("he_second_action_box", None)

if st.session_state.scenario_started:
    if topic == "Hypertensive Emergency":
        st.header("Patient Handoff")

        st.write(
            "Mr. Jones is a 68-year-old patient admitted for uncontrolled "
            "hypertension. He suddenly reports a severe headache and blurred vision."
        )

        st.subheader("Vital signs")
        st.write("- Blood pressure: 214/122 mm Hg")
        st.write("- Heart rate: 94 beats/min")
        st.write("- Respiratory rate: 22 breaths/min")
        st.write("- Oxygen saturation: 96% on room air")

        st.write("What would you assess or do first?")

        nursing_action = st.text_area("Type your nursing action", key="he_first_action_box")

        if "he_submitted_action" not in st.session_state:
            st.session_state.he_submitted_action = None

        if "he_stage2_active" not in st.session_state:
            st.session_state.he_stage2_active = False

        if "he_submitted_second_action" not in st.session_state:
            st.session_state.he_submitted_second_action = None

        if "he_show_debrief" not in st.session_state:
            st.session_state.he_show_debrief = False

        if st.button("Submit Action"):
            if nursing_action.strip() == "":
                st.session_state.he_submitted_action = None
                st.write("Please enter an action before submitting.")
            else:
                st.session_state.he_submitted_action = nursing_action

        if st.session_state.he_submitted_action:
            submitted_action = st.session_state.he_submitted_action

            normalized_response = normalize_response_text(submitted_action)
            padded_response = f" {normalized_response} "

            st.write("Your action was recorded.")
            st.write(f"You entered: {submitted_action}")

            st.header("Initial Nursing Priorities")

            priority_categories = compute_stage1_categories(padded_response)

            recognized_count = 0

            for category_name, recognized in priority_categories:
                if recognized:
                    recognized_count += 1
                    st.write(f"✅ {category_name}")
                else:
                    st.write(f"⚠️ Consider: {category_name}")

            if recognized_count >= 3:
                st.write("Strong initial response. You recognized several immediate priorities.")
            else:
                st.write("Review the missing priorities before continuing.")

            st.write(
                "Blood pressure above 180/120 mm Hg with new neurological symptoms "
                "suggests a hypertensive emergency with possible target-organ damage."
            )

            if recognized_count >= 3:
                if st.button("Continue Scenario"):
                    st.session_state.he_stage2_active = True

        if st.session_state.he_stage2_active:
            st.header("Patient Update — 3 Minutes Later")

            st.write(
                "The repeat manual blood pressure is 218/124 mm Hg. Mr. Jones is now "
                "confused and has developed slurred speech, left-sided facial "
                "drooping, and weakness in his left arm. His oxygen saturation "
                "remains 96% on room air. His airway is currently open, and he is "
                "breathing without assistance."
            )

            st.subheader("Last known well")
            st.write(
                "Mr. Jones was speaking normally and moving all extremities "
                "approximately 10 minutes ago."
            )

            st.write("What would you assess or do next?")

            second_action = st.text_area(
                "Type your next nursing action", key="he_second_action_box"
            )

            if st.button("Submit Next Action"):
                if second_action.strip() == "":
                    st.session_state.he_submitted_second_action = None
                    st.write("Please enter an action before submitting.")
                else:
                    st.session_state.he_submitted_second_action = second_action

            if st.session_state.he_submitted_second_action:
                submitted_second_action = st.session_state.he_submitted_second_action

                normalized_second_response = normalize_response_text(submitted_second_action)
                padded_second_response = f" {normalized_second_response} "

                st.write("Your second action was recorded.")
                st.write("You entered:")
                st.write(submitted_second_action)

                st.header("Second-Stage Nursing Priorities")

                second_stage_categories = compute_stage2_categories(padded_second_response)

                second_stage_recognized_count = 0

                for category_name, recognized in second_stage_categories:
                    if recognized:
                        second_stage_recognized_count += 1
                        st.write(f"✅ {category_name}")
                    else:
                        st.write(f"⚠️ Consider: {category_name}")

                if second_stage_recognized_count >= 5:
                    st.write(
                        "Strong next response. You recognized the major "
                        "time-sensitive stroke priorities."
                    )
                elif second_stage_recognized_count >= 3:
                    st.write(
                        "You recognized several priorities, but review the "
                        "missing time-sensitive actions."
                    )
                else:
                    st.write("Review the missing priorities before the scenario continues.")

                st.write(
                    "Sudden facial drooping, unilateral weakness, slurred speech, "
                    "and confusion require an immediate stroke response. The "
                    "last-known-well time helps guide time-sensitive treatment "
                    "decisions. Bedside glucose checks for a possible stroke "
                    "mimic, and urgent brain imaging helps determine whether "
                    "bleeding is present. Keep the patient NPO until swallowing "
                    "safety is evaluated."
                )

                st.write(
                    "The nurse should continue monitoring airway, breathing, "
                    "circulation, vital signs, and neurological status while "
                    "following the facility's stroke protocol."
                )

                if st.button("View Final Debrief"):
                    st.session_state.he_show_debrief = True

                if st.session_state.he_show_debrief:
                    stage1_padded_response = (
                        f" {normalize_response_text(st.session_state.he_submitted_action)} "
                    )
                    stage1_categories = compute_stage1_categories(stage1_padded_response)

                    stage1_recognized = [
                        name for name, recognized in stage1_categories if recognized
                    ]
                    stage1_missing = [
                        name for name, recognized in stage1_categories if not recognized
                    ]
                    stage2_recognized = [
                        name for name, recognized in second_stage_categories if recognized
                    ]
                    stage2_missing = [
                        name for name, recognized in second_stage_categories if not recognized
                    ]

                    st.header("Scenario Debrief")

                    st.subheader("Patient Outcome")
                    st.write(
                        "The stroke response was activated, Mr. Jones remained NPO, "
                        "bedside glucose was checked, and he was transported for "
                        "urgent brain imaging while neurological status and vital "
                        "signs were continuously monitored. The scenario ends here "
                        "because further treatment depends on imaging results, "
                        "provider orders, facility protocols, and the patient's "
                        "eligibility for specific therapies."
                    )

                    st.subheader("What You Recognized")
                    st.write("Initial response")
                    for name in stage1_recognized:
                        st.write(f"✅ {name}")
                    st.write("Second response")
                    for name in stage2_recognized:
                        st.write(f"✅ {name}")

                    st.subheader("Priorities to Review")
                    if stage1_missing or stage2_missing:
                        if stage1_missing:
                            st.write("Initial response")
                            for name in stage1_missing:
                                st.write(f"⚠️ {name}")
                        if stage2_missing:
                            st.write("Second response")
                            for name in stage2_missing:
                                st.write(f"⚠️ {name}")
                    else:
                        st.write("You recognized every priority included in this scenario.")

                    st.subheader("Ideal Nursing Sequence")
                    st.markdown(
                        "1. Verify the severely elevated blood pressure and perform "
                        "an immediate focused assessment.\n"
                        "2. Begin continuous monitoring and rapidly escalate care "
                        "because neurological symptoms suggest target-organ damage.\n"
                        "3. Recognize the new facial drooping, unilateral weakness, "
                        "slurred speech, and confusion as an acute stroke warning.\n"
                        "4. Activate the facility's stroke response and communicate "
                        "the last-known-well time.\n"
                        "5. Perform focused neurological checks and obtain bedside "
                        "blood glucose.\n"
                        "6. Keep the patient NPO and protect airway, swallowing, and "
                        "general safety.\n"
                        "7. Prepare for urgent brain imaging while continuing airway, "
                        "breathing, circulation, vital-sign, and neurological "
                        "monitoring.\n"
                        "8. Follow provider orders and the facility's stroke "
                        "protocol after imaging results are available."
                    )

                    st.subheader("Why This Situation Was Dangerous")
                    st.write(
                        "A blood pressure above 180/120 mm Hg with new neurological "
                        "findings represents a hypertensive emergency because acute "
                        "target-organ damage may be occurring. Sudden facial "
                        "drooping, arm weakness, slurred speech, and confusion are "
                        "time-sensitive stroke warning signs. Delayed recognition or "
                        "escalation can delay imaging and treatment and may worsen "
                        "neurological injury."
                    )

                    st.subheader("Example SBAR")
                    st.markdown("**Situation:**")
                    st.write(
                        "Mr. Jones is a 68-year-old patient admitted with "
                        "uncontrolled hypertension. His repeat manual blood "
                        "pressure is 218/124 mm Hg, and he has developed sudden "
                        "confusion, slurred speech, left facial drooping, and left "
                        "arm weakness."
                    )
                    st.markdown("**Background:**")
                    st.write(
                        "He was speaking normally and moving all extremities "
                        "approximately 10 minutes ago. His oxygen saturation is 96% "
                        "on room air, and his airway is currently open."
                    )
                    st.markdown("**Assessment:**")
                    st.write(
                        "This is an acute neurological change concerning for "
                        "stroke during a hypertensive emergency. A focused "
                        "neurological assessment is being completed, bedside "
                        "glucose is being obtained, and he is being kept NPO with "
                        "continuous monitoring."
                    )
                    st.markdown("**Recommendation:**")
                    st.write(
                        "Activate the facility's stroke protocol immediately, "
                        "evaluate him urgently, and prepare for emergency brain "
                        "imaging and additional provider-directed treatment."
                    )

                    st.write(
                        "This debrief is for education only. Actual nursing "
                        "actions must follow the patient's condition, provider "
                        "orders, facility policy, emergency protocols, "
                        "supervision, and legal scope of practice."
                    )

                    if st.button("Restart Scenario"):
                        st.session_state.scenario_started = False
                        st.session_state.he_submitted_action = None
                        st.session_state.he_stage2_active = False
                        st.session_state.he_submitted_second_action = None
                        st.session_state.he_show_debrief = False
                        st.session_state.pop("he_first_action_box", None)
                        st.session_state.pop("he_second_action_box", None)
                        st.rerun()
    else:
        st.write(f"You selected: {topic}")
        st.write("The interactive patient scenario for this topic will be added later.")
