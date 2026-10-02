"""
Stage 1: Screening.

1. Jobs list: every job and its candidate counts. Create a new job from here.
2. Open a job: upload CVs for THAT job. The AI scores each CV against the job,
   and candidates with a score >= the job's shortlist threshold are shortlisted automatically.
"""
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import streamlit as st

from config.settings import UPLOAD_DIR
from config.steps import STEPS
from services import ai_helpers, cv_parser
from services import repository as repo
from services.workflow_service import auto_shortlist, shortlist_anyway, start_workflow
from ui.auth import require_login

st.set_page_config(page_title="Jobs", layout="wide")
user = require_login()

DEFAULT_THRESHOLD = 70
# First guess of how long the AI needs for one CV on this computer. Replaced by the real
# measured time as soon as one CV has been scored.
TYPICAL_SECONDS_PER_CV = 240


def open_job(job_id):
    st.session_state["selected_job_id"] = job_id


def close_job():
    st.session_state.pop("selected_job_id", None)


def flash(message):
    """Shows a message once, after the next rerun."""
    st.session_state["flash"] = message


def show_flash():
    message = st.session_state.pop("flash", None)
    if message:
        st.success(message)


def shortlist_result(candidate):
    """Shortlisted / Not shortlisted / Needs HR review (no AI score yet)."""
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

    # Filters
    search_col, dept_col = st.columns([3, 2])
    search = search_col.text_input("Search", placeholder="Search by job title", label_visibility="collapsed")
    departments = ["All departments"] + sorted({j["department"] for j in jobs})
    department = dept_col.selectbox("Department", departments, label_visibility="collapsed")

    shown = [
        j for j in jobs
        if search.strip().lower() in j["title"].lower()
        and (department == "All departments" or j["department"] == department)
    ]
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

def clock(seconds):
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}m {secs:02d}s" if minutes else f"{secs}s"


def score_with_live_timer(job, text, f, n, total, done_seconds, line, overall):
    """
    Runs the AI scoring in the background and refreshes the loader every second
    (time spent, estimated time left for this CV and for the whole upload).
    """
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        future = pool.submit(ai_helpers.rank_cv, job["title"], job["description"], text, job.get("screening_criteria"))
        start = time.time()
        while not future.done():
            spent = time.time() - start
            per_cv = (sum(done_seconds) / len(done_seconds) if done_seconds
                      else st.session_state.get("seconds_per_cv", TYPICAL_SECONDS_PER_CV))
            left_this = max(per_cv - spent, 0)
            left_all = left_this + per_cv * (total - n)
            estimate = (f"about **{clock(left_this)}** left for this CV" if left_this
                        else "almost done, a little longer than usual")
            line.markdown(f"🤖 **AI is scoring** {f.name}  \n"
                          f"⏱️ {clock(spent)} so far · {estimate}"
                          + (f" · about {clock(left_all)} for all {total} CVs" if total > 1 else ""))
            overall.progress(min((n - 1 + min(spent / per_cv, 0.95)) / total, 1.0),
                             text=f"CV {n} of {total}")
            time.sleep(1)
        done_seconds.append(time.time() - start)
        st.session_state["seconds_per_cv"] = sum(done_seconds) / len(done_seconds)  # better estimate next time
        return future.result()
    finally:
        pool.shutdown(wait=False)  # never block the page if the upload is stopped


def ensure_screening_criteria(job, line):
    """Reads the job's required skills + minimum years ONCE (AI) and saves them, showing a live timer."""
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        future = pool.submit(ai_helpers.extract_screening_criteria, job["title"], job["description"])
        start = time.time()
        while not future.done():
            line.markdown(f"📋 **Reading the job description** to list the required skills (only once per job)  \n"
                          f"⏱️ {clock(time.time() - start)} so far")
            time.sleep(1)
        criteria = future.result()
    finally:
        pool.shutdown(wait=False)
    if criteria:
        repo.set_screening_criteria(job["id"], criteria)
        job["screening_criteria"] = criteria
        line.markdown(f"📋 Required skills for this job: {criteria_text(criteria)}")
    else:
        line.markdown("📋 Could not read the required skills (is Ollama running?). The AI will judge skills itself.")
    return criteria


def criteria_text(criteria):
    skills = " · ".join(" / ".join(g) for g in criteria.get("required_skills", []))
    years = criteria.get("min_years")
    return skills + (f" · minimum {years:g} years" if years else "")


def criteria_editor(job):
    """Shows (and lets HR edit) exactly what every CV of this job is checked against."""
    criteria = job.get("screening_criteria")
    with st.expander("What CVs are checked against (required skills)", expanded=not criteria):
        if criteria:
            st.markdown("**Required skills** (each line is worth the same points; alternatives on one line: any one is enough)")
            st.markdown("\n".join(f"- {' / '.join(g)}" for g in criteria["required_skills"]))
            st.caption(f"Minimum experience: {criteria['min_years']:g} years" if criteria.get("min_years")
                       else "Minimum experience: not stated (2 years assumed)")
        else:
            st.info("Not read yet. It is read from the job description automatically before the first CV is scored, "
                    "or click 'Read from job description' now.")
        edit, read = st.columns([3, 1.4])
        with edit.popover("✏️ Edit"):
            with st.form(f"criteria-{job['id']}"):
                lines = "\n".join(" / ".join(g) for g in (criteria or {}).get("required_skills", []))
                text = st.text_area("Required skills, one per line (alternatives: separate with / )", value=lines, height=220,
                                    placeholder="NestJS\nTypeScript\nPostgreSQL / MongoDB\nTypeORM / Prisma / Mongoose")
                years = st.number_input("Minimum years of experience", 0.0, 30.0,
                                        float((criteria or {}).get("min_years") or 0), step=0.5)
                st.caption("Applies to CVs scored from now on. Earlier scores do not change.")
                if st.form_submit_button("Save skills", type="primary"):
                    groups = [[s.strip() for s in line.split("/") if s.strip()] for line in text.splitlines()]
                    new = ai_helpers.clean_criteria([g for g in groups if g], years)
                    if not new["required_skills"]:
                        st.error("Please enter at least one required skill.")
                    else:
                        repo.set_screening_criteria(job["id"], new)
                        flash("Required skills saved.")
                        st.rerun()
        if read.button("🔄 Read from job description", help="The AI reads the job description again (takes a minute or two)."):
            if ensure_screening_criteria(job, st.empty()):
                flash("Required skills read from the job description.")
                st.rerun()


def save_uploaded_cvs(job, files):
    """
    For each CV: read it, score it with AI, register the candidate, then apply the shortlist rule.
    A CV that fails is fully undone and the other CVs continue. Shows a live loader while working.
    """
    Path(UPLOAD_DIR).mkdir(exist_ok=True)
    report = {"shortlisted": [], "not_shortlisted": [], "review": [], "duplicates": [], "failed": []}
    total, done_seconds, started = len(files), [], time.time()

    with st.status(f"Scoring {total} CV(s) with AI. Please keep this page open...", expanded=True) as status:
        st.caption("The AI reads each CV carefully, so one CV can take a few minutes on this computer. "
                   "Leaving or refreshing the page stops the upload.")
        overall = st.progress(0.0, text=f"CV 1 of {total}")
        if not job.get("screening_criteria"):
            ensure_screening_criteria(job, st.empty())

        for n, f in enumerate(files, start=1):
            line = st.empty()  # this CV's live line; it becomes the CV's result line when done
            overall.progress((n - 1) / total, text=f"CV {n} of {total}")
            path = Path(UPLOAD_DIR) / f"{uuid.uuid4().hex[:8]}_{Path(f.name).name}"
            candidate_id = None
            try:
                line.markdown(f"📄 Reading {f.name}...")
                path.write_bytes(f.getbuffer())
                text = cv_parser.read_cv(str(path))
                if not text:
                    raise ValueError("no text found (is it a scanned image?)")
                same = repo.find_same_cv(job["id"], text)
                if same:  # checked BEFORE the slow AI step
                    path.unlink(missing_ok=True)
                    report["duplicates"].append(f"{f.name} (already uploaded as {same['full_name']})")
                    line.markdown(f"⏭️ {f.name}: skipped, already uploaded as {same['full_name']}")
                    continue
                rank = score_with_live_timer(job, text, f, n, total, done_seconds, line, overall)
                line.markdown(f"💾 Saving {f.name}...")
                name = rank["name"] or Path(f.name).stem
                candidate_id = repo.create_candidate(
                    job["id"], name, rank["email"], str(path), text, rank["score"], rank["reason"]
                )
                start_workflow(candidate_id)  # waits at "Approve shortlist"
            except BaseException as error:  # also when the upload is interrupted (e.g. the page is left)
                if candidate_id:
                    repo.delete_candidate(candidate_id)
                path.unlink(missing_ok=True)
                if not isinstance(error, Exception):
                    raise
                report["failed"].append(f"{f.name}: {error}")
                line.markdown(f"❌ {f.name}: {error}")
                continue

            # The candidate is saved. Now apply the rule: AI score >= threshold -> Shortlisted.
            label = f"{name} ({rank['score']})" if rank["score"] is not None else name
            try:
                decision = auto_shortlist(user, candidate_id, rank["score"], job["shortlist_threshold"])
            except Exception as error:
                print(f"[Shortlist] Could not apply the rule to candidate {candidate_id}: {error}")
                decision = None
            took = clock(done_seconds[-1]) if done_seconds else ""
            if decision == "Shortlisted":
                report["shortlisted"].append(label)
                line.markdown(f"✅ {f.name} → **{label}** → Shortlisted ({took})")
            elif decision == "Not shortlisted":
                report["not_shortlisted"].append(label)
                line.markdown(f"➖ {f.name} → **{label}** → Not shortlisted ({took})")
            else:
                report["review"].append(label)
                line.markdown(f"⚠️ {f.name} → **{label}** → needs HR review, the AI could not score it ({took})")

        overall.progress(1.0, text=f"All {total} CV(s) done")
        report["seconds"] = time.time() - started
        status.update(label=f"Done: {total} CV(s) processed in {clock(report['seconds'])}", state="complete")
    return report


def show_upload_report(report, threshold):
    if report.get("seconds"):
        st.caption(f"Last upload took {clock(report['seconds'])}.")
    if report["shortlisted"]:
        st.success(f"**Shortlisted ({len(report['shortlisted'])})** with a score of {threshold}+: "
                   + ", ".join(report["shortlisted"]) + ". They moved to the M1 round.")
    if report["not_shortlisted"]:
        st.info(f"**Not shortlisted ({len(report['not_shortlisted'])})**, score below {threshold}: "
                + ", ".join(report["not_shortlisted"]))
    if report["review"]:
        st.warning(f"**Needs HR review ({len(report['review'])})**: the AI could not score "
                   + ", ".join(report["review"]) + ". Is Ollama running? Decide in **My Tasks**.")
    if report.get("duplicates"):
        st.info(f"**Skipped ({len(report['duplicates'])})**, this CV is already in this job: "
                + ", ".join(report["duplicates"]))
    for message in report["failed"]:
        st.error(f"Not uploaded: {message}")


def threshold_editor(job):
    with st.popover(f"Shortlist threshold: **{job['shortlist_threshold']}**"):
        with st.form(f"threshold-{job['id']}"):
            value = st.slider("Shortlist CVs with an AI score of at least", 0, 100, job["shortlist_threshold"])
            st.caption("Applies to CVs uploaded from now on. Earlier results do not change.")
            if st.form_submit_button("Save", type="primary"):
                repo.set_job_threshold(job["id"], value)
                flash(f"Shortlist threshold set to {value}.")
                st.rerun()


def job_detail_view(job_id):
    job = repo.get_job(job_id)
    if not job:
        close_job()
        st.rerun()

    st.button("← Back to jobs", on_click=close_job)
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

    # ---- Upload CVs for this job ----
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
        type=["pdf", "docx", "txt"], accept_multiple_files=True, key=f"cvs-{job_id}-{upload_round}", disabled=busy,
    )
    st.button("Scoring... please wait" if busy else "Upload and score with AI", type="primary",
              disabled=busy or not files, on_click=lambda: st.session_state.update(uploading=True))
    if busy:
        try:
            if files:
                st.session_state["upload_report"] = save_uploaded_cvs(job, files)
                st.session_state["upload_round"] = upload_round + 1
        finally:
            st.session_state["uploading"] = False
        st.rerun()

    # ---- Candidates for this job ----
    st.subheader("Candidates (ranked by AI score)")
    if not candidates:
        st.caption("No candidates yet. Upload CVs above.")
        return

    view = st.segmented_control("Show", ["All", "Shortlisted", "Not shortlisted", "Needs HR review"], default="All")
    rows = [(c, r) for c, r in zip(candidates, results) if view in (None, "All") or r == view]
    st.dataframe(
        [{
            "Name": c["full_name"],
            "Email": c["email"] or "",
            "AI score": c["ai_score"],
            "Result": {"Shortlisted": "✅ Shortlisted", "Not shortlisted": "❌ Not shortlisted"}.get(r, "⚠️ Needs HR review"),
            "Next step": STEPS[c["current_step"]]["label"] if c["current_step"] in STEPS else c["status"],
            "AI reason": c["ai_reason"],
        } for c, r in rows],
        column_config={"AI score": st.column_config.ProgressColumn("AI score", min_value=0, max_value=100, format="%d")},
        width="stretch", hide_index=True,
    )

    review = results.count("Needs HR review")
    if review:
        st.page_link("pages/2_My_Tasks.py", label=f"Review {review} CV(s) the AI could not score in My Tasks →")

    # ---- Override: the AI is only a helper, HR has the final say ----
    rejected = [c for c, r in zip(candidates, results) if r == "Not shortlisted"]
    if rejected:
        with st.expander(f"Shortlist a candidate anyway ({len(rejected)} not shortlisted)"):
            names = {c["id"]: f"{c['full_name']} (score {c['ai_score']})" for c in rejected}
            # No default + a fixed key: the choice is kept (or cleared) if the list changes, never swapped for another candidate.
            chosen = st.selectbox("Candidate", list(names), index=None, placeholder="Choose a candidate",
                                  format_func=names.get, key=f"anyway-{job_id}")
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
