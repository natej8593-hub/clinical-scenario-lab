import re

import streamlit as st


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

st.title("Clinical Scenario Lab")

st.warning("Educational simulation only. Do not use during actual patient care.")

st.write("This program will eventually create interactive nursing patient scenarios.")

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

            priority_categories = [
                ("Verify the blood pressure", bp_recognized),
                ("Perform a focused neurological assessment", neuro_recognized),
                ("Begin continuous monitoring", monitor_recognized),
                ("Escalate care", escalate_recognized),
            ]

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
                neuro_stage2_recognized = has_any_phrase(
                    padded_second_response, neuro_stage2_phrases
                )

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
                glucose_action_present = has_any_phrase(
                    padded_second_response, glucose_action_words
                )
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

                second_stage_categories = [
                    ("Activate the stroke response and escalate care", stroke_recognized),
                    (
                        "Perform an immediate focused neurological assessment",
                        neuro_stage2_recognized,
                    ),
                    (
                        "Confirm and document the last-known-well time",
                        last_known_well_recognized,
                    ),
                    ("Check bedside blood glucose", glucose_recognized),
                    ("Prepare for urgent brain imaging", imaging_recognized),
                    ("Protect airway and swallowing safety", airway_recognized),
                ]

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
    else:
        st.write(f"You selected: {topic}")
        st.write("The interactive patient scenario for this topic will be added later.")
