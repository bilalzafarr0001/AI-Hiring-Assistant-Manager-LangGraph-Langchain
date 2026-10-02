"""Status of every candidate the user is allowed to see, plus the audit log."""
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


st.dataframe(
    [{"Candidate": c["full_name"], "Job": c["job_title"], "Department": c["department"],
      "AI score": c["ai_score"], "Status": c["status"], "Next step": waiting_for(c)} for c in candidates],
    width="stretch", hide_index=True,
)

st.subheader("Candidate history")
cid = st.selectbox("Select candidate", [c["id"] for c in candidates], key="dashboard-candidate",
                   format_func=lambda i: next(c["full_name"] for c in candidates if c["id"] == i))

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
        label = STEPS[a["step"]]["label"] if a["step"] in STEPS else a["step"]
        details = a["details"] or {}
        channel = f" via {details['channel']}" if details.get("channel") else ""
        if a["step"] == "moved_back":
            label = f"↩ Moved back to '{STEPS[details['to']]['label']}'" if details.get("to") in STEPS else "↩ Moved back"
            how = f": {details.get('reason', '')}"
        elif details.get("automatic"):
            how = f": {details['decision']} automatically (AI score {details['ai_score']}, threshold {details['threshold']})"
        elif details.get("override"):
            how = ": Shortlisted manually by HR (overrode the AI result)"
        else:
            how = ""
        st.write(f"- {a['created_at']:%d %b %Y %H:%M} - **{label}**{how}{channel} (recorded by {a['done_by'] or 'System'})")
with col2:
    st.markdown("**Interviews**")
    for i in repo.get_interviews(cid):
        st.write(f"- {i['round']}: {i['scheduled_at']:%d %b %Y %H:%M} - {i['location'] or ''}")
    st.markdown("**Feedback**")
    for f in repo.get_feedback(cid):
        st.write(f"- {f['round']} - given by {f['given_by']}: {f['decision']}. {f['comments'] or ''}")
