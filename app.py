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

        nursing_action = st.text_area("Type your nursing action")

        if "he_submitted_action" not in st.session_state:
            st.session_state.he_submitted_action = None

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
    else:
        st.write(f"You selected: {topic}")
        st.write("The interactive patient scenario for this topic will be added later.")
