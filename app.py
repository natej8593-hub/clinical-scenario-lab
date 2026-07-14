import streamlit as st

st.title("Clinical Scenario Lab")

st.warning("Educational simulation only. Do not use during actual patient care.")

st.write("This program will eventually create interactive nursing patient scenarios.")

topic = st.selectbox(
    "Choose a nursing topic",
    ["Hypertensive Emergency", "Peripheral Arterial Disease", "Deep Vein Thrombosis"],
)

if st.button("Start Scenario"):
    st.write(f"You selected: {topic}")
    st.write("The interactive patient scenario will be added in the next step.")
