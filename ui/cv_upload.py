"""
Uploading CVs for one job (used by the Jobs page).

For each CV:  save the file -> read its text -> skip it if already uploaded -> score it with the AI
              -> save the candidate (the process starts) -> apply the shortlist rule (score >= threshold).
A CV that fails is fully undone, and the other CVs continue.

Scoring one CV takes minutes, so it runs in a background thread while the page shows a live timer.
"""
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import streamlit as st

from config.settings import UPLOAD_DIR
from services import cv_parser
from services import repository as repo
from services.job_requirements import extract_screening_criteria
from services.scoring import rank_cv
from services.workflow_service import auto_shortlist, start_workflow

# First guess of how long the AI needs for one CV on this computer. Replaced by the real
# measured time as soon as one CV has been scored.
TYPICAL_SECONDS_PER_CV = 240


def clock(seconds):
    """125 -> '2m 05s',  42 -> '42s'"""
    minutes, secs = divmod(int(seconds), 60)
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


# ---------------------------------------------------------------- the whole upload

def save_uploaded_cvs(job, files, user):
    """Processes every uploaded CV (see the steps at the top of this file) and returns a report for the page."""
    Path(UPLOAD_DIR).mkdir(exist_ok=True)
    report = {"shortlisted": [], "not_shortlisted": [], "review": [], "duplicates": [], "failed": []}
    total = len(files)
    done_seconds = []          # how long each CV took to score (for the time estimates)
    started = time.time()

    with st.status(f"Scoring {total} CV(s) with AI. Please keep this page open...", expanded=True) as status:
        st.caption("The AI reads each CV carefully, so one CV can take a few minutes on this computer. "
                   "Leaving or refreshing the page stops the upload.")
        overall = st.progress(0.0, text=f"CV 1 of {total}")
        if not job.get("screening_criteria"):
            ensure_screening_criteria(job, st.empty())

        for n, file in enumerate(files, start=1):
            line = st.empty()  # this CV's line on the page: its progress first, then its result
            overall.progress((n - 1) / total, text=f"CV {n} of {total}")
            path = Path(UPLOAD_DIR) / f"{uuid.uuid4().hex[:8]}_{Path(file.name).name}"   # random prefix: no name clashes
            candidate_id = None
            try:
                # 1. Save the file and read its text.
                line.markdown(f"📄 Reading {file.name}...")
                path.write_bytes(file.getbuffer())
                text = cv_parser.read_cv(str(path))
                if not text:
                    raise ValueError("no text found (is it a scanned image?)")

                # 2. Skip it if this exact CV is already in this job (checked BEFORE the slow AI step).
                same = repo.find_same_cv(job["id"], text)
                if same:
                    path.unlink(missing_ok=True)
                    report["duplicates"].append(f"{file.name} (already uploaded as {same['full_name']})")
                    line.markdown(f"⏭️ {file.name}: skipped, already uploaded as {same['full_name']}")
                    continue

                # 3. Score it with the AI.
                rank = score_cv(job, text, file.name, n, total, done_seconds, line, overall)
                # 4. Save the candidate. Their process starts and waits at "Approve shortlist".
                line.markdown(f"💾 Saving {file.name}...")
                name = rank["name"] or Path(file.name).stem
                candidate_id = repo.create_candidate(
                    job["id"], name, rank["email"], str(path), text, rank["score"], rank["reason"]
                )
                start_workflow(candidate_id)
            except Exception as error:      # something failed for this CV: undo it, then go on with the next CV
                undo_cv(candidate_id, path)
                report["failed"].append(f"{file.name}: {error}")
                line.markdown(f"❌ {file.name}: {error}")
                continue
            except BaseException:           # the upload was stopped (e.g. the page was left): undo this CV and stop
                undo_cv(candidate_id, path)
                raise

            # 5. Apply the job's rule: AI score >= threshold -> Shortlisted.
            if rank["score"] is not None:
                label = f"{name} ({rank['score']})"
            else:
                label = name
            try:
                decision = auto_shortlist(user, candidate_id, rank["score"], job["shortlist_threshold"])
            except Exception as error:
                print(f"[Shortlist] Could not apply the rule to candidate {candidate_id}: {error}")
                decision = None
            if done_seconds:
                took = clock(done_seconds[-1])     # how long the AI took for this CV
            else:
                took = ""
            if decision == "Shortlisted":
                report["shortlisted"].append(label)
                line.markdown(f"✅ {file.name} → **{label}** → Shortlisted ({took})")
            elif decision == "Not shortlisted":
                report["not_shortlisted"].append(label)
                line.markdown(f"➖ {file.name} → **{label}** → Not shortlisted ({took})")
            else:
                report["review"].append(label)
                line.markdown(f"⚠️ {file.name} → **{label}** → needs HR review, the AI could not score it ({took})")

        overall.progress(1.0, text=f"All {total} CV(s) done")
        report["seconds"] = time.time() - started
        status.update(label=f"Done: {total} CV(s) processed in {clock(report['seconds'])}", state="complete")
    return report


def undo_cv(candidate_id, path):
    """Undoes everything done for one CV that failed: deletes the candidate (if it was created) and the file."""
    if candidate_id:
        repo.delete_candidate(candidate_id)
    path.unlink(missing_ok=True)


def show_upload_report(report, threshold):
    """The summary of the last upload, shown on the job page after it reloads."""
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


# ---------------------------------------------------------------- the slow AI steps, with a live timer

def score_cv(job, text, file_name, n, total, done_seconds, line, overall):
    """Scores one CV (services/scoring.py) in a background thread, refreshing the timer every second."""
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        future = pool.submit(rank_cv, job["title"], job["description"], text, job.get("screening_criteria"))
        start = time.time()
        while not future.done():
            show_scoring_progress(file_name, time.time() - start, n, total, done_seconds, line, overall)
            time.sleep(1)
        done_seconds.append(time.time() - start)
        st.session_state["seconds_per_cv"] = sum(done_seconds) / len(done_seconds)  # better estimate next time
        return future.result()
    finally:
        pool.shutdown(wait=False)  # never block the page if the upload is stopped


def show_scoring_progress(file_name, spent, n, total, done_seconds, line, overall):
    """Time spent on this CV, and about how long is left for it and for the whole upload."""
    if done_seconds:
        per_cv = sum(done_seconds) / len(done_seconds)      # average of the CVs already scored
    else:
        per_cv = st.session_state.get("seconds_per_cv", TYPICAL_SECONDS_PER_CV)
    left_this = max(per_cv - spent, 0)
    left_all = left_this + per_cv * (total - n)
    if left_this:
        estimate = f"about **{clock(left_this)}** left for this CV"
    else:
        estimate = "almost done, a little longer than usual"
    text = f"🤖 **AI is scoring** {file_name}  \n⏱️ {clock(spent)} so far · {estimate}"
    if total > 1:
        text += f" · about {clock(left_all)} for all {total} CVs"
    line.markdown(text)
    if per_cv > 0:
        this_cv_part = min(spent / per_cv, 0.95)    # how much of this CV is done (never shown as fully done)
    else:
        this_cv_part = 0.95                         # earlier CVs took no measurable time (e.g. the AI was off)
    overall.progress(min((n - 1 + this_cv_part) / total, 1.0), text=f"CV {n} of {total}")


def ensure_screening_criteria(job, line):
    """Reads the job's required skills + minimum years ONCE (services/job_requirements.py) and saves them."""
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        future = pool.submit(extract_screening_criteria, job["title"], job["description"])
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
    """{"required_skills": [["NestJS"], ["SQL", "NoSQL"]], "min_years": 3} -> 'NestJS · SQL / NoSQL · minimum 3 years'"""
    skills = " · ".join(" / ".join(group) for group in criteria.get("required_skills", []))
    years = criteria.get("min_years")
    if years:
        return skills + f" · minimum {years:g} years"
    return skills
