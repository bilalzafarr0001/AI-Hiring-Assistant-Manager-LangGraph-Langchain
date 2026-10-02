"""Every candidate waiting for the next step. Each one opens on its CURRENT step."""
import streamlit as st

from config.steps import ROLE_LABELS, STEPS
from services import repository as repo
from services.permissions import can_act
from services.workflow_service import complete_step
from ui.auth import require_login
from ui.process_view import flash, render_go_back, render_progress, show_flash
from ui.step_forms import render_step_form

st.set_page_config(page_title="My Tasks", layout="wide")
user = require_login()
st.title("My Tasks")
show_flash()

tasks = [c for c in repo.list_candidates() if can_act(user, c["current_step"], c)]

if not tasks:
    st.success("No tasks waiting for you.")
    st.stop()

for candidate in tasks:
    step = candidate["current_step"]
    owner = ROLE_LABELS[STEPS[step]["owner"]]
    title = f"{candidate['full_name']} - {candidate['job_title']}  |  {STEPS[step]['stage']}: {STEPS[step]['label']}  ({owner} step)"
    with st.expander(title, expanded=True):
        where, back = st.columns([5, 2])
        with where:
            render_progress(candidate)
        with back:
            render_go_back(user, candidate, key="tasks")
        st.divider()

        data = render_step_form(step, candidate)
        if data is not None:
            try:
                complete_step(user, candidate["id"], data, expected_step=step)
                flash(f"{candidate['full_name']}: '{STEPS[step]['label']}' recorded. The process moved to the next step.")
                st.rerun()
            except (PermissionError, ValueError) as error:
                st.error(str(error))
