"""
The bridge between the pages and the hiring process (graph/workflow.py).

Each candidate's place in the process is saved in their candidates row (current_step + decisions),
so the process can pause for days (e.g. waiting for the HOD) and continue later, even after a restart.

Only HR / Recruitment uses this platform, so HR completes every step. For HOD and interviewer steps,
HR records what the HOD / interviewer decided, and the app saves WHO gave the decision and WHICH HR user entered it.
"""
from functools import lru_cache

from config.steps import ROLE_RECRUITER, STEP_ORDER, STEPS
from graph.workflow import build_graph
from services import repository as repo


@lru_cache(maxsize=1)
def get_graph():
    """The graph is built once and then reused."""
    return build_graph()


def can_act(user, step):
    """True if this user may complete (or go back to) this step: any real step, and only HR."""
    return bool(step) and step in STEPS and user["role"] == ROLE_RECRUITER


def start_workflow(candidate_id):
    """Starts the process for a new candidate. It runs until the first step (approve shortlist) and waits there."""
    get_graph().invoke({"candidate_id": candidate_id})


def current_step(candidate_id):
    candidate = repo.get_candidate(candidate_id)
    return candidate["current_step"] if candidate else None


def complete_step(user, candidate_id, data, expected_step=None):
    """
    HR completes the candidate's current step with the data from the step's form.
    The graph saves it, moves on, and stops at the next step that needs HR.
    """
    candidate = repo.get_candidate(candidate_id)
    step = candidate["current_step"] if candidate else None
    if step is None:
        raise ValueError("This candidate's process is already closed.")
    if expected_step and step != expected_step:
        raise ValueError("This candidate is no longer at this step (it was completed or moved by someone else). "
                         "Please refresh the page.")
    if not can_act(user, step):
        raise PermissionError("You are not allowed to complete this step.")
    # Take the step first, so two people cannot complete it at the same time.
    if not repo.claim_step(candidate_id, step):
        raise ValueError("This step was just completed by someone else. Please refresh the page.")

    state = {
        "candidate_id": candidate["id"],
        "shortlist_decision": candidate["shortlist_decision"],
        "m1_decision": candidate["m1_decision"],
        "m2_decision": candidate["m2_decision"],
        "submission": {"step": step, "user_id": user["id"], "data": data},
    }
    try:
        get_graph().invoke(state)
    except Exception:
        repo.release_step(candidate_id, step)  # give the step back so HR can try again
        raise


def auto_shortlist(user, candidate_id, score, threshold, main_skills_missing, too_few_years=""):
    """
    Applies the job's shortlist rule to a new candidate. Shortlisted only when ALL are true:
    - the AI score >= the job's threshold,
    - no main skill is missing (a "Python Developer" CV without Python is never shortlisted automatically), and
    - enough experience (too_few_years is "" - e.g. "0.7 of 3+ years" when the candidate has far too few).
    Returns the decision, or None if there is no AI score (HR then decides in My Tasks).
    HR can still use "Shortlist anyway".
    """
    if score is None:
        return None
    if score >= threshold and not main_skills_missing and not too_few_years:
        decision = "Shortlisted"
    else:
        decision = "Not shortlisted"
    details = {"decision": decision, "automatic": True, "ai_score": score, "threshold": threshold}
    if main_skills_missing:
        details["main_skills_missing"] = main_skills_missing    # shown in the history (Dashboard, Home)
    if too_few_years:
        details["too_few_years"] = too_few_years
    complete_step(user, candidate_id, details, expected_step="approve_shortlist")
    return decision


def shortlist_anyway(user, candidate_id):
    """HR overrides a 'Not shortlisted' result: the candidate re-enters the process at the M1 round."""
    if not can_act(user, "approve_shortlist"):
        raise PermissionError("You are not allowed to change the shortlist.")
    if not repo.reopen_shortlist(candidate_id):
        raise ValueError("Only candidates who were not shortlisted can be shortlisted manually.")
    complete_step(user, candidate_id, {"decision": "Shortlisted", "override": True}, expected_step="approve_shortlist")


# ---------------------------------------------------------------- the steps of one candidate

def steps_of_stage(stage):
    """The steps of one stage, in order. 'M1 round' -> ['contact_hod', 'contact_interviewers', ..., 'record_m1']"""
    steps = []
    for step in STEP_ORDER:
        if STEPS[step]["stage"] == stage:
            steps.append(step)
    return steps


def process_path(candidate):
    """
    The steps this candidate's process goes through, following the decisions made so far:
    Screening -> (if shortlisted) M1 round -> (if M1 = Selected) M2 round.
    """
    path = steps_of_stage("Screening")
    if candidate["shortlist_decision"] != "Shortlisted":
        return path
    path = path + steps_of_stage("M1 round")
    if candidate["m1_decision"] != "Selected":
        return path
    return path + steps_of_stage("M2 round")


def completed_steps(candidate):
    """The steps already recorded for this candidate (the ones HR can go back to)."""
    path = process_path(candidate)
    current = candidate["current_step"]
    if current is None:  # process closed: every step on its path was recorded
        return path
    # Keep only the steps that come before the current step.
    done = []
    for step in path:
        if STEP_ORDER.index(step) < STEP_ORDER.index(current):
            done.append(step)
    return done


def go_back(user, candidate_id, to_step, reason):
    """
    HR sends the candidate back to an earlier step to change it (e.g. the HOD changed the interviewers).
    That step and the steps after it are recorded again. Nothing is removed from the history.
    """
    candidate = repo.get_candidate(candidate_id)
    if not candidate:
        raise ValueError("Candidate not found.")
    if to_step not in STEPS:
        raise ValueError("Unknown step.")
    if not can_act(user, to_step):
        raise PermissionError("You are not allowed to change this step.")
    if not reason or not reason.strip():
        raise ValueError("Please write the reason for going back.")
    if to_step not in completed_steps(candidate):
        raise ValueError("You can only go back to a step that was already recorded.")

    # This step and every step after it will be recorded again ("schedule_m1" -> schedule_m1, m1_interview, ...).
    position = STEP_ORDER.index(to_step)
    steps_to_redo = STEP_ORDER[position:]
    moved = repo.move_back(candidate_id, candidate["current_step"], candidate["status"],
                           to_step, STEPS[to_step]["stage"], steps_to_redo)
    if not moved:
        raise ValueError("This candidate was just updated by someone else. Please refresh the page.")
    repo.log_activity(candidate_id, "moved_back", user["id"], {
        "from": candidate["current_step"] or candidate["status"], "to": to_step, "reason": reason.strip(),
    })
