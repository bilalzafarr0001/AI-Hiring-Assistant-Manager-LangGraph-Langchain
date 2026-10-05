"""
Pieces shared by the pages:
- flash() / show_flash(): a success message that is still shown after the page reloads
- render_progress():      where a candidate is in the process (used on My Tasks and the Dashboard)
- render_go_back():       sending a candidate back to an earlier step (used on My Tasks and the Dashboard)
"""
import streamlit as st

from config.steps import STEP_ORDER, STEPS
from services.workflow_service import completed_steps, go_back


def flash(message):
    """Shows a message once, after the next rerun."""
    st.session_state["flash"] = message


def show_flash():
    message = st.session_state.pop("flash", None)
    if message:
        st.success(message)


def step_name(step):
    """'schedule_m1' -> 'M1 round: Schedule M1 interview'"""
    return f"{STEPS[step]['stage']}: {STEPS[step]['label']}"


def render_progress(candidate):
    """Progress bar for the current step, plus the list of all steps (done / now / next)."""
    step = candidate["current_step"]
    done = completed_steps(candidate)
    total = len(STEP_ORDER)

    if step:
        number = STEP_ORDER.index(step) + 1
        st.progress(number / total, text=f"Step {number} of {total}  ·  Now: **{step_name(step)}**")
    else:
        st.progress(1.0, text=f"Process closed  ·  **{candidate['status']}**")

    with st.popover("All steps"):
        for each_step in STEP_ORDER:
            if each_step in done:
                st.markdown(f"✅ {step_name(each_step)}")
            elif each_step == step:
                st.markdown(f"▶️ **{step_name(each_step)}**  ← now")
            elif step and STEP_ORDER.index(each_step) > STEP_ORDER.index(step):
                st.markdown(f"⚪ {step_name(each_step)}")
            else:  # skipped: the process was closed before reaching this step
                st.markdown(f":gray[~~{step_name(each_step)}~~] (not needed)")


def render_go_back(user, candidate, key):
    """'Go back to an earlier step': pick a recorded step, give a reason, and the process restarts from there."""
    options = completed_steps(candidate)
    if not options:
        return
    with st.popover("↩ Go back to an earlier step"):
        with st.form(f"go-back-{key}-{candidate['id']}", clear_on_submit=True):
            # No default on purpose: if the candidate changed meanwhile (another recruiter moved them), the list
            # changes and the choice is cleared, so HR is asked again instead of going back to a wrong step.
            to_step = st.selectbox("Go back to", options, index=None, placeholder="Choose the step to go back to",
                                   format_func=step_name, key=f"go-back-step-{key}-{candidate['id']}")
            st.caption("The process continues again from this step, so this step and the steps after it "
                       "must be recorded again. Nothing is deleted from the history.")
            reason = st.text_area("Reason (required)", placeholder="e.g. Hamza and Hina are absent, the HOD assigned new interviewers")
            if st.form_submit_button("Go back", type="primary"):
                if not to_step:
                    st.error("Please choose the step to go back to. (If you chose one, this candidate was just "
                             "updated by someone else: check the steps list and choose again.)")
                    return
                if not reason.strip():
                    st.error("Please write the reason for going back.")
                    return
                try:
                    go_back(user, candidate["id"], to_step, reason)
                    flash(f"{candidate['full_name']} is back at '{STEPS[to_step]['label']}'. Record it again in My Tasks.")
                    st.rerun()
                except (PermissionError, ValueError) as error:
                    st.error(str(error))
