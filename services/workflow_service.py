"""
The bridge between the screens and the LangGraph workflow.
Each candidate's place in the process is saved in their candidates row (current_step + decisions),
so the process can pause for days (e.g. waiting for the HOD) and continue later, even after a restart.
"""
from functools import lru_cache

from config.steps import STEP_ORDER, STEPS
from graph.workflow import build_graph
from services import repository as repo
from services.permissions import can_act


@lru_cache(maxsize=1)
def get_graph():
    return build_graph()


def _state(candidate):
    """The workflow's view of a candidate, read from their candidates row."""
    return {
        "candidate_id": candidate["id"],
        "shortlist_decision": candidate["shortlist_decision"],
        "m1_decision": candidate["m1_decision"],
        "m2_decision": candidate["m2_decision"],
    }


def start_workflow(candidate_id):
    """Starts the process. It runs until the first step (approve shortlist) and waits there."""
    get_graph().invoke({"candidate_id": candidate_id})


def current_step(candidate_id):
    candidate = repo.get_candidate(candidate_id)
    return candidate["current_step"] if candidate else None


def complete_step(user, candidate_id, data, expected_step=None):
    """Completes the current step, but ONLY if this user is allowed to."""
    candidate = repo.get_candidate(candidate_id)
    step = candidate["current_step"] if candidate else None
    if step is None:
        raise ValueError("This candidate's process is already closed.")
    if expected_step and step != expected_step:
        raise ValueError("This candidate is no longer at this step (it was completed or moved by someone else). "
                         "Please refresh the page.")
    if not can_act(user, step, candidate):
        raise PermissionError("You are not allowed to complete this step.")
    if not repo.claim_step(candidate_id, step):
        raise ValueError("This step was just completed by someone else. Please refresh the page.")

    submission = {"step": step, "user_id": user["id"], "data": data}
    try:
        get_graph().invoke({**_state(candidate), "submission": submission})
    except Exception:
        repo.release_step(candidate_id, step)  # let HR try again
        raise


def auto_shortlist(user, candidate_id, score, threshold):
    """
    Applies the job's shortlist rule to a new candidate: AI score >= threshold -> Shortlisted.
    Returns the decision, or None if there is no AI score (HR then decides in My Tasks).
    """
    if score is None:
        return None
    decision = "Shortlisted" if score >= threshold else "Not shortlisted"
    complete_step(user, candidate_id, {
        "decision": decision, "automatic": True, "ai_score": score, "threshold": threshold,
    }, expected_step="approve_shortlist")
    return decision


def process_path(candidate):
    """
    The steps this candidate's process goes through, following the decisions made so far:
    Screening -> (if shortlisted) M1 round -> (if M1 = Selected) M2 round.
    """
    path = ["approve_shortlist"]
    if candidate["shortlist_decision"] != "Shortlisted":
        return path
    path += STEP_ORDER[STEP_ORDER.index("contact_hod"):STEP_ORDER.index("record_m1") + 1]
    if candidate["m1_decision"] != "Selected":
        return path
    return path + STEP_ORDER[STEP_ORDER.index("hod_slots"):]


def completed_steps(candidate):
    """The steps already recorded for this candidate (the ones HR can go back to)."""
    path = process_path(candidate)
    step = candidate["current_step"]
    if step is None:  # process closed: every step on its path was recorded
        return path
    return [s for s in path if STEP_ORDER.index(s) < STEP_ORDER.index(step)]


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
    if not can_act(user, to_step, candidate):
        raise PermissionError("You are not allowed to change this step.")
    if not reason or not reason.strip():
        raise ValueError("Please write the reason for going back.")
    if to_step not in completed_steps(candidate):
        raise ValueError("You can only go back to a step that was already recorded.")

    steps_to_redo = STEP_ORDER[STEP_ORDER.index(to_step):]
    moved = repo.move_back(candidate_id, candidate["current_step"], candidate["status"],
                           to_step, STEPS[to_step]["stage"], steps_to_redo)
    if not moved:
        raise ValueError("This candidate was just updated by someone else. Please refresh the page.")
    repo.log_activity(candidate_id, "moved_back", user["id"], {
        "from": candidate["current_step"] or candidate["status"], "to": to_step, "reason": reason.strip(),
    })


def shortlist_anyway(user, candidate_id):
    """HR overrides a 'Not shortlisted' result: the candidate re-enters the process at the M1 round."""
    if not can_act(user, "approve_shortlist"):
        raise PermissionError("You are not allowed to change the shortlist.")
    if not repo.reopen_shortlist(candidate_id):
        raise ValueError("Only candidates who were not shortlisted can be shortlisted manually.")
    complete_step(user, candidate_id, {"decision": "Shortlisted", "override": True}, expected_step="approve_shortlist")
