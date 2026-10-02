"""
Company Hiring AI Assistant
Start the app with:  streamlit run app.py

Home page: what needs attention today, where every candidate is, and whether the system is ready.
"""
import json
import urllib.request
from datetime import datetime

import streamlit as st

from config.settings import APP_NAME, LLM_MODEL, OLLAMA_BASE_URL
from config.steps import ROLE_HOD, ROLE_INTERVIEWER, STEPS
from services import repository as repo
from services.security import verify_password
from ui.auth import require_login

st.set_page_config(page_title=APP_NAME, layout="wide")
user = require_login()

DEMO_PASSWORD = "ChangeMe@123"
OFFER = "Selected - Offer"
CLOSED_LABELS = {
    "Selected - Offer": "Offer made",
    "Rejected": "Rejected after M2",
    "Closed - M1 unselected": "Not selected in M1",
    "Closed - Not shortlisted": "Not shortlisted",
}


# ---------------------------------------------------------------- helpers

@st.cache_data(ttl=30, show_spinner=False)
def ai_status():
    """('ready' | 'no_model' | 'offline', detail). Checked at most every 30 seconds."""
    try:
        with urllib.request.urlopen(f"{OLLAMA_BASE_URL}/api/tags", timeout=3) as response:
            models = [m.get("name", "") for m in json.load(response).get("models", [])]
    except Exception:
        return "offline", ""
    wanted = LLM_MODEL if ":" in LLM_MODEL else f"{LLM_MODEL}:latest"
    return ("ready", LLM_MODEL) if wanted in models or LLM_MODEL in models else ("no_model", ", ".join(models))


def greeting():
    hour = datetime.now().hour
    return "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening"


def time_ago(moment):
    if not moment:
        return ""
    seconds = max(0, int((datetime.now() - moment).total_seconds()))
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60} min ago"
    if seconds < 86400:
        return f"{seconds // 3600} h ago"
    days = seconds // 86400
    return "yesterday" if days == 1 else f"{days} days ago"


def waiting_text(moment):
    days = (datetime.now() - moment).days if moment else 0
    return "since today" if days == 0 else "1 day" if days == 1 else f"{days} days"


def action_text(row):
    details = row["details"] or {}
    if row["step"] == "moved_back":
        to = STEPS.get(details.get("to"), {}).get("label", "an earlier step")
        return f"moved back to *{to}*"
    if row["step"] == "closed":
        return f"closed: {details.get('status', '')}"
    label = STEPS.get(row["step"], {}).get("label", row["step"])
    if details.get("automatic"):
        return f"{details.get('decision', 'decided')} automatically (AI score {details.get('ai_score')})"
    if details.get("override"):
        return "shortlisted manually by HR"
    return label


def using_demo_password():
    """Checked once per login (password checks are deliberately slow)."""
    key = f"demo-password-{user['id']}"
    if key not in st.session_state:
        st.session_state[key] = bool(user.get("password_hash")) and verify_password(DEMO_PASSWORD, user["password_hash"])
    return st.session_state[key]


# ---------------------------------------------------------------- data (5 queries)

jobs = repo.list_jobs()
candidates = repo.list_candidates()
people = repo.list_users()
departments = repo.list_departments()
activity = repo.recent_activity(8)

open_cases = [c for c in candidates if c["current_step"]]
needs_review = [c for c in open_cases if c["current_step"] == "approve_shortlist"]
in_m1 = [c for c in open_cases if STEPS[c["current_step"]]["stage"] == "M1 round"]
in_m2 = [c for c in open_cases if STEPS[c["current_step"]]["stage"] == "M2 round"]
closed = [c for c in candidates if not c["current_step"]]
offers = [c for c in closed if c["status"] == OFFER]

# ---------------------------------------------------------------- header

st.title(APP_NAME)
st.markdown(f"#### {greeting()}, {user['full_name'].split(' (')[0].split()[0]} 👋")
st.caption(f"{datetime.now():%A, %d %B %Y}  ·  Signed in as {user['email']}")

# ---------------------------------------------------------------- things that need fixing first

status, detail = ai_status()
if status == "offline":
    st.warning("**AI is offline.** CVs can still be uploaded, but they will not get a score (they go to *Needs HR review*). "
               "Start Ollama from the Start menu, then refresh.", icon="🤖")
elif status == "no_model":
    st.warning(f"**AI model '{LLM_MODEL}' is not installed** in Ollama. Run `ollama pull {LLM_MODEL}` "
               f"(installed: {detail or 'none'}).", icon="🤖")
if using_demo_password():
    st.error("**You are still using the demo password.** Change it now in **People → My password**.", icon="🔐")

job_departments = {j["department_id"]: j["department"] for j in jobs}
for dept_id, dept_name in sorted(job_departments.items(), key=lambda x: x[1]):
    has_hod = any(p["role"] == ROLE_HOD and p["department_id"] == dept_id for p in people)
    has_interviewer = any(p["role"] == ROLE_INTERVIEWER and p["department_id"] == dept_id for p in people)
    missing = [what for what, ok in (("a HOD", has_hod), ("interviewers", has_interviewer)) if not ok]
    if missing:
        st.warning(f"**{dept_name}** has open jobs but no {' and no '.join(missing)}. "
                   "Shortlisted candidates cannot start the M1 round until you add them in **People**.", icon="👥")

# ---------------------------------------------------------------- first-time setup

if not jobs:
    st.info("**Welcome! Let's set up your first hiring process.**", icon="🚀")
    step1, step2, step3 = st.columns(3)
    with step1.container(border=True):
        st.markdown("**1. People**")
        st.caption(f"{len(departments)} departments · "
                   f"{sum(p['role'] == ROLE_HOD for p in people)} HODs · "
                   f"{sum(p['role'] == ROLE_INTERVIEWER for p in people)} interviewers")
        st.page_link("pages/4_People.py", label="Check departments and people →")
    with step2.container(border=True):
        st.markdown("**2. Create a job**")
        st.caption("Write the title and description with a clear *Required skills* list.")
        st.page_link("pages/1_Jobs.py", label="Go to Jobs →")
    with step3.container(border=True):
        st.markdown("**3. Upload CVs**")
        st.caption("Open the job and upload CVs. The AI scores them and shortlists the best ones.")
        st.page_link("pages/1_Jobs.py", label="Open a job →")
    st.stop()

# ---------------------------------------------------------------- today at a glance

m1, m2, m3, m4, m5, m6 = st.columns(6)
m1.metric("Open jobs", len(jobs))
m2.metric("Candidates", len(candidates))
m3.metric("Waiting for a step", len(open_cases), help="Candidates whose next step must be recorded in My Tasks")
m4.metric("Needs HR review", len(needs_review), help="CVs the AI could not score, or sent back to the shortlist step")
m5.metric("In interviews", len(in_m1) + len(in_m2), help=f"M1 round: {len(in_m1)} · M2 round: {len(in_m2)}")
m6.metric("Offers made", len(offers))

st.divider()
left, right = st.columns([3, 2], gap="large")

# ---------------------------------------------------------------- what needs attention (longest waiting first)

with left:
    st.subheader("Needs your attention")
    if not open_cases:
        st.success("Nothing is waiting. Every candidate's process is up to date. 🎉")
    else:
        longest = sorted(open_cases, key=lambda c: c["updated_at"] or datetime.now())[:6]
        for c in longest:
            step = STEPS[c["current_step"]]
            days = (datetime.now() - c["updated_at"]).days if c["updated_at"] else 0
            flag = "🔴" if days >= 3 else "🟠" if days >= 1 else "🟢"
            with st.container(border=True):
                name, when = st.columns([4, 1.3], vertical_alignment="center")
                name.markdown(f"{flag} **{c['full_name']}** · {c['job_title']}  \n"
                              f"<small>{step['stage']}: {step['label']}</small>", unsafe_allow_html=True)
                when.caption(f"waiting {waiting_text(c['updated_at'])}")
        more = len(open_cases) - len(longest)
        st.page_link("pages/2_My_Tasks.py",
                     label=f"Open My Tasks ({len(open_cases)} waiting{f', {more} more not shown' if more > 0 else ''}) →")

# ---------------------------------------------------------------- where every candidate is

with right:
    st.subheader("Hiring pipeline")
    total = max(len(candidates), 1)
    for label, count in (("Screening (needs HR review)", len(needs_review)), ("M1 round", len(in_m1)),
                         ("M2 round", len(in_m2)), ("Closed", len(closed))):
        st.progress(count / total, text=f"{label}: **{count}**")
    if closed:
        outcomes = {}
        for c in closed:
            outcomes[CLOSED_LABELS.get(c["status"], c["status"])] = outcomes.get(CLOSED_LABELS.get(c["status"], c["status"]), 0) + 1
        st.caption("Closed: " + " · ".join(f"{k} {v}" for k, v in sorted(outcomes.items(), key=lambda x: -x[1])))
    scored = [c["ai_score"] for c in candidates if c["ai_score"] is not None]
    if scored:
        st.caption(f"Average AI score: **{sum(scored) / len(scored):.0f}** · best: **{max(scored)}** · "
                   f"{len(candidates) - len(scored)} CV(s) without a score")
    st.page_link("pages/3_Dashboard.py", label="Full status and history in Dashboard →")

st.divider()
jobs_col, activity_col = st.columns([3, 2], gap="large")

# ---------------------------------------------------------------- jobs at a glance

with jobs_col:
    st.subheader("Jobs at a glance")
    st.dataframe(
        [{"Job": j["title"], "Department": j["department"], "Candidates": j["candidate_count"],
          "Shortlisted": j["shortlisted"], "Needs review": j["needs_review"],
          "Threshold": j["shortlist_threshold"],
          "Skills list": "ready" if j.get("screening_criteria") else "read on first upload"} for j in jobs[:10]],
        hide_index=True, width="stretch",
    )
    st.page_link("pages/1_Jobs.py", label=f"Manage jobs and upload CVs ({len(jobs)} job(s)) →")

# ---------------------------------------------------------------- recent activity

with activity_col:
    st.subheader("Recent activity")
    if not activity:
        st.caption("No activity yet.")
    for a in activity:
        st.markdown(f"**{a['candidate']}** — {action_text(a)}  \n"
                    f"<small>{a['job_title']} · {a['done_by'] or 'System'} · {time_ago(a['created_at'])}</small>",
                    unsafe_allow_html=True)

# ---------------------------------------------------------------- how it works

with st.expander("How the hiring process works"):
    st.markdown("""
**Only HR / Recruitment uses this platform.** You contact HODs, interviewers and candidates through the usual channels
(Teams, email, phone) and record each step here.

1. **Screening:** create a job, open it and upload CVs. The app scores every CV out of 100
   (skills 40 · experience 30 · role fit 15 · education 15). A score at or above the job's threshold is shortlisted
   automatically; you can always *Shortlist anyway*.
2. **M1 round:** contact the HOD → record the interviewers → interviewer slots → candidate availability → schedule →
   interview done → interviewer feedback → M1 result.
3. **M2 round** (only if M1 = Selected): HOD slots → schedule → HOD interview → final feedback → close with an offer or rejection.

Made a mistake or plans changed? Use **↩ Go back** on any candidate: earlier answers are pre-filled and the full history is kept.
""")
