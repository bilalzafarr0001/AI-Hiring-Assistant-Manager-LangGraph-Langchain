"""
Stage 1: Screening.

1. Jobs list: every job and its candidate counts. Create a new job from here.
2. One job: upload CVs for THAT job. The AI scores each CV against the job (ui/cv_upload.py),
   and candidates with a score >= the job's shortlist threshold are shortlisted automatically.
"""
import streamlit as st

from config.steps import STEPS
from services import repository as repo
from services.job_requirements import clean_criteria
from services.workflow_service import shortlist_anyway
from ui.auth import require_login
from ui.cv_upload import ensure_screening_criteria, save_uploaded_cvs, show_upload_report
from ui.process_view import flash, show_flash

st.set_page_config(page_title="Jobs", layout="wide")
user = require_login()

DEFAULT_THRESHOLD = 70


def open_job(job_id):
    st.session_state["selected_job_id"] = job_id


def back_to_jobs():
    st.session_state.pop("selected_job_id", None)


def shortlist_result(candidate):
    """Shortlisted / Not shortlisted / Needs HR review (no decision yet, e.g. the AI could not score the CV)."""
    if candidate["current_step"] == "approve_shortlist" or not candidate["shortlist_decision"]:
        return "Needs HR review"
    return candidate["shortlist_decision"]


# ======================= Create job (pop-up) =======================

@st.dialog("Create a new job", width="large")
def create_job_dialog():
    departments = repo.list_departments()
    if not departments:
        st.warning("There are no departments yet. Add one first.")
        st.page_link("pages/4_People.py", label="Go to People → Departments")
        return
    dept_names = {d["id"]: d["name"] for d in departments}
    with st.form("new-job"):
        title = st.text_input("Job title", placeholder="e.g. Senior React Developer")
        dept_id = st.selectbox("Department", list(dept_names), format_func=dept_names.get, key="new-job-department")
        description = st.text_area(
            "Job description", height=220,
            placeholder="Responsibilities, required skills, years of experience, education... "
                        "The AI compares every CV with this text, so be specific.",
        )
        threshold = st.slider("Shortlist threshold (AI score)", 0, 100, DEFAULT_THRESHOLD,
                              help="CVs with an AI score equal to or above this number are shortlisted automatically.")
        if st.form_submit_button("Create job", type="primary"):
            if not title.strip() or not description.strip():
                st.error("Please enter a title and a description.")
            else:
                repo.create_job(title.strip(), description.strip(), dept_id, user["id"], threshold)
                flash(f"Job '{title.strip()}' created. Open it to upload CVs.")
                st.rerun()


# ======================= View 1: Jobs list =======================

def jobs_list_view():
    head, button = st.columns([4, 1], vertical_alignment="bottom")
    head.title("Jobs")
    if button.button("➕ Create job", type="primary", width="stretch"):
        create_job_dialog()
    show_flash()

    jobs = repo.list_jobs()
    if not jobs:
        st.info("No jobs yet. Click **Create job** to add your first one.")
        return

    # Filters: search by title, and department
    search_col, dept_col = st.columns([3, 2])
    search = search_col.text_input("Search", placeholder="Search by job title", label_visibility="collapsed")
    departments = ["All departments"] + sorted({j["department"] for j in jobs})
    department = dept_col.selectbox("Department", departments, label_visibility="collapsed")

    shown = []
    for job in jobs:
        title_matches = search.strip().lower() in job["title"].lower()
        department_matches = department == "All departments" or job["department"] == department
        if title_matches and department_matches:
            shown.append(job)
    st.caption(f"{len(shown)} of {len(jobs)} jobs")

    for job in shown:
        with st.container(border=True):
            info, total, short, action = st.columns([5, 1.3, 1.3, 1.2], vertical_alignment="center")
            info.markdown(f"**{job['title']}**")
            info.caption(f"{job['department']}  ·  Shortlist at {job['shortlist_threshold']}+  ·  "
                         f"Created {job['created_at']:%d %b %Y}")
            if job["needs_review"]:
                info.caption(f":orange[{job['needs_review']} CV(s) need HR review]")
            total.metric("Candidates", job["candidate_count"])
            short.metric("Shortlisted", job["shortlisted"])
            action.button("Open →", key=f"open-{job['id']}", on_click=open_job, args=(job["id"],), width="stretch")


# ======================= View 2: One job =======================

def job_detail_view(job_id):
    job = repo.get_job(job_id)
    if not job:
        back_to_jobs()
        st.rerun()

    st.button("← Back to jobs", on_click=back_to_jobs)
    head, setting = st.columns([4, 1.4], vertical_alignment="bottom")
    head.title(job["title"])
    head.caption(f"{job['department']}  ·  Created {job['created_at']:%d %b %Y}")
    with setting:
        threshold_editor(job)
    show_flash()

    candidates = repo.list_candidates_for_job(job_id)
    results = [shortlist_result(c) for c in candidates]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Candidates", len(candidates))
    m2.metric(f"Shortlisted ({job['shortlist_threshold']}+)", results.count("Shortlisted"))
    m3.metric("Not shortlisted", results.count("Not shortlisted"))
    m4.metric("Needs HR review", results.count("Needs HR review"))

    with st.expander("Job description"):
        st.write(job["description"])
    criteria_editor(job)
    upload_section(job)
    candidates_section(job, candidates, results)


def threshold_editor(job):
    with st.popover(f"Shortlist threshold: **{job['shortlist_threshold']}**"):
        with st.form(f"threshold-{job['id']}"):
            value = st.slider("Shortlist CVs with an AI score of at least", 0, 100, job["shortlist_threshold"])
            st.caption("Applies to CVs uploaded from now on. Earlier results do not change.")
            if st.form_submit_button("Save", type="primary"):
                repo.set_job_threshold(job["id"], value)
                flash(f"Shortlist threshold set to {value}.")
                st.rerun()


def criteria_editor(job):
    """Shows (and lets HR edit) exactly what every CV of this job is checked against."""
    criteria = job.get("screening_criteria")
    with st.expander("What CVs are checked against (required skills)", expanded=not criteria):
        if criteria:
            st.markdown("**Required skills** (each line is worth the same points; alternatives on one line: any one is enough)")
            skill_lines = [f"- {' / '.join(group)}" for group in criteria["required_skills"]]
            st.markdown("\n".join(skill_lines))
            if criteria.get("min_years"):
                st.caption(f"Minimum experience: {criteria['min_years']:g} years")
            else:
                st.caption("Minimum experience: not stated (2 years assumed)")
        else:
            st.info("Not read yet. It is read from the job description automatically before the first CV is scored, "
                    "or click 'Read from job description' now.")

        edit, read = st.columns([3, 1.4])
        with edit.popover("✏️ Edit"):
            with st.form(f"criteria-{job['id']}"):
                current_groups = (criteria or {}).get("required_skills", [])
                current_text = "\n".join(" / ".join(group) for group in current_groups)
                text = st.text_area("Required skills, one per line (alternatives: separate with / )", value=current_text,
                                    height=220, placeholder="NestJS\nTypeScript\nPostgreSQL / MongoDB\nTypeORM / Prisma / Mongoose")
                years = st.number_input("Minimum years of experience", 0.0, 30.0,
                                        float((criteria or {}).get("min_years") or 0), step=0.5)
                st.caption("Applies to CVs scored from now on. Earlier scores do not change.")
                if st.form_submit_button("Save skills", type="primary"):
                    groups = []
                    for line in text.splitlines():      # "PostgreSQL / MongoDB" -> ["PostgreSQL", "MongoDB"]
                        names = [name.strip() for name in line.split("/") if name.strip()]
                        if names:
                            groups.append(names)
                    new_criteria = clean_criteria(groups, years)
                    if not new_criteria["required_skills"]:
                        st.error("Please enter at least one required skill.")
                    else:
                        repo.set_screening_criteria(job["id"], new_criteria)
                        flash("Required skills saved.")
                        st.rerun()
        if read.button("🔄 Read from job description", help="The AI reads the job description again (takes a minute or two)."):
            if ensure_screening_criteria(job, st.empty()):
                flash("Required skills read from the job description.")
                st.rerun()


def start_upload():
    st.session_state["uploading"] = True


def upload_section(job):
    st.subheader("Upload CVs")
    st.caption(f"The AI scores each CV against this job (0-100). "
               f"A score of **{job['shortlist_threshold']} or more** is shortlisted automatically.")
    report = st.session_state.pop("upload_report", None)
    if report:
        show_upload_report(report, job["shortlist_threshold"])

    # A new key after each upload clears the file picker, so the same CVs are not uploaded twice.
    upload_round = st.session_state.get("upload_round", 0)
    # While CVs are being scored, the uploader and the button are locked, so a second click cannot start it again.
    busy = st.session_state.get("uploading", False)
    files = st.file_uploader(
        f"CVs for **{job['title']}** (PDF, DOCX or TXT, one or many)",
        type=["pdf", "docx", "txt"], accept_multiple_files=True, key=f"cvs-{job['id']}-{upload_round}", disabled=busy,
    )
    st.button("Scoring... please wait" if busy else "Upload and score with AI", type="primary",
              disabled=busy or not files, on_click=start_upload)
    if busy:
        try:
            if files:
                st.session_state["upload_report"] = save_uploaded_cvs(job, files, user)
                st.session_state["upload_round"] = upload_round + 1
        finally:
            st.session_state["uploading"] = False
        st.rerun()


def candidates_section(job, candidates, results):
    st.subheader("Candidates (ranked by AI score)")
    if not candidates:
        st.caption("No candidates yet. Upload CVs above.")
        return

    view = st.segmented_control("Show", ["All", "Shortlisted", "Not shortlisted", "Needs HR review"], default="All")
    result_labels = {"Shortlisted": "✅ Shortlisted", "Not shortlisted": "❌ Not shortlisted"}
    rows = []
    for c, result in zip(candidates, results):
        if view in (None, "All") or result == view:
            if c["current_step"] in STEPS:
                next_step = STEPS[c["current_step"]]["label"]
            else:
                next_step = c["status"]
            rows.append({
                "Name": c["full_name"],
                "Email": c["email"] or "",
                "AI score": c["ai_score"],
                "Result": result_labels.get(result, "⚠️ Needs HR review"),
                "Next step": next_step,
                "AI reason": c["ai_reason"],
            })
    st.dataframe(
        rows,
        column_config={"AI score": st.column_config.ProgressColumn("AI score", min_value=0, max_value=100, format="%d")},
        width="stretch", hide_index=True,
    )

    review = results.count("Needs HR review")
    if review:
        st.page_link("pages/2_My_Tasks.py", label=f"Review {review} CV(s) the AI could not score in My Tasks →")

    # Override: the AI is only a helper, HR has the final say.
    rejected = [c for c, result in zip(candidates, results) if result == "Not shortlisted"]
    if rejected:
        with st.expander(f"Shortlist a candidate anyway ({len(rejected)} not shortlisted)"):
            names = {c["id"]: f"{c['full_name']} (score {c['ai_score']})" for c in rejected}
            # No default + a fixed key: the choice is kept (or cleared) if the list changes, never swapped for another candidate.
            chosen = st.selectbox("Candidate", list(names), index=None, placeholder="Choose a candidate",
                                  format_func=names.get, key=f"anyway-{job['id']}")
            if st.button("Shortlist anyway", disabled=chosen is None):
                try:
                    shortlist_anyway(user, chosen)
                    flash(f"{names[chosen]} shortlisted. They moved to the M1 round.")
                    st.rerun()
                except (PermissionError, ValueError) as error:
                    st.error(str(error))


# ======================= Page =======================

selected = st.session_state.get("selected_job_id")
if selected:
    job_detail_view(selected)
else:
    jobs_list_view()
