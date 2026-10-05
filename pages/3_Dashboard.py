"""Status of every candidate, plus the full history of one candidate."""
import streamlit as st

from config.steps import ROLE_LABELS, STEPS
from services import repository as repo
from ui.auth import require_login
from ui.process_view import render_go_back, render_progress, show_flash

st.set_page_config(page_title="Dashboard", layout="wide")
user = require_login()
st.title("Dashboard")
show_flash()

candidates = repo.list_candidates()
if not candidates:
    st.info("No candidates to show.")
    st.stop()


def waiting_for(c):
    step = c["current_step"]
    if not step:
        return "-"
    return f"{STEPS[step]['label']} ({ROLE_LABELS[STEPS[step]['owner']]} step)"


def describe_activity(a):
    """One line of the activity log: when, what, how, through which channel, and who recorded it."""
    details = a["details"] or {}
    label = STEPS[a["step"]]["label"] if a["step"] in STEPS else a["step"]
    how = ""
    if a["step"] == "moved_back":
        if details.get("to") in STEPS:
            label = f"↩ Moved back to '{STEPS[details['to']]['label']}'"
        else:
            label = "↩ Moved back"
        how = f": {details.get('reason', '')}"
    elif details.get("automatic"):
        how = f": {details['decision']} automatically (AI score {details['ai_score']}, threshold {details['threshold']})"
    elif details.get("override"):
        how = ": Shortlisted manually by HR (overrode the AI result)"
    channel = f" via {details['channel']}" if details.get("channel") else ""
    return f"- {a['created_at']:%d %b %Y %H:%M} - **{label}**{how}{channel} (recorded by {a['done_by'] or 'System'})"


# ---------------------------------------------------------------- every candidate

st.dataframe(
    [{"Candidate": c["full_name"], "Job": c["job_title"], "Department": c["department"],
      "AI score": c["ai_score"], "Status": c["status"], "Next step": waiting_for(c)} for c in candidates],
    width="stretch", hide_index=True,
)

# ---------------------------------------------------------------- one candidate's history

st.subheader("Candidate history")
names = {c["id"]: c["full_name"] for c in candidates}
cid = st.selectbox("Select candidate", list(names), key="dashboard-candidate", format_func=names.get)

candidate = repo.get_candidate(cid)
where, back = st.columns([5, 2])
with where:
    render_progress(candidate)
with back:
    render_go_back(user, candidate, key="dashboard")

col1, col2 = st.columns(2)
with col1:
    st.markdown("**Activity log (what happened, when, recorded by whom)**")
    for a in repo.get_activity(cid):
        st.write(describe_activity(a))
with col2:
    st.markdown("**Interviews**")
    for i in repo.get_interviews(cid):
        st.write(f"- {i['round']}: {i['scheduled_at']:%d %b %Y %H:%M} - {i['location'] or ''}")
    st.markdown("**Feedback**")
    for f in repo.get_feedback(cid):
        st.write(f"- {f['round']} - given by {f['given_by']}: {f['decision']}. {f['comments'] or ''}")
