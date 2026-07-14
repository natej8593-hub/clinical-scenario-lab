import streamlit as st

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
            response_lower = submitted_action.lower()

            st.write("Your action was recorded.")
            st.write(f"You entered: {submitted_action}")

            st.header("Initial Nursing Priorities")

            priority_categories = [
                (
                    "Verify the blood pressure",
                    [
                        "repeat blood pressure",
                        "recheck blood pressure",
                        "manual blood pressure",
                        "verify blood pressure",
                        "take blood pressure again",
                    ],
                ),
                (
                    "Perform a focused neurological assessment",
                    [
                        "neurological assessment",
                        "neurologic assessment",
                        "neuro assessment",
                        "assess mental status",
                        "assess pupils",
                        "assess for stroke",
                        "check level of consciousness",
                    ],
                ),
                (
                    "Begin continuous monitoring",
                    [
                        "continuous monitoring",
                        "cardiac monitoring",
                        "telemetry",
                        "monitor vital signs",
                        "frequent vital signs",
                        "place on monitor",
                    ],
                ),
                (
                    "Escalate care",
                    [
                        "notify provider",
                        "call provider",
                        "notify physician",
                        "call physician",
                        "rapid response",
                        "activate rrt",
                        "call rrt",
                        "escalate care",
                    ],
                ),
            ]

            recognized_count = 0

            for category_name, phrases in priority_categories:
                recognized = any(phrase in response_lower for phrase in phrases)
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
