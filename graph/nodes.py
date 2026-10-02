"""
Workflow steps (LangGraph nodes).

Each human step works in one of two ways:
- HR is completing THIS step now: save what HR submitted, write the history, and move on to the next step.
- Otherwise the process has just reached this step: mark the candidate as waiting here and stop.
  The candidates table remembers the step, so the process can wait for days and continue later.
"""
from config.steps import STATUS_NOT_SHORTLISTED, STEPS
from graph.state import HiringState
from services import repository as repo


def apply_step(step, candidate_id, data):
    """Saves what HR submitted for this step on the candidate row. Returns updates for the workflow state."""
    if step == "approve_shortlist":
        repo.save_shortlist_decision(candidate_id, data["decision"])
        return {"shortlist_decision": data["decision"]}

    if step == "contact_interviewers":
        repo.assign_interviewers(candidate_id, data["interviewer_ids"])

    elif step in ("schedule_m1", "schedule_m2"):
        round_name = "M1" if step == "schedule_m1" else "M2"
        repo.save_interview(candidate_id, round_name, data["scheduled_at"], data.get("location"))

    elif step == "m1_feedback":
        repo.save_feedback(candidate_id, "M1", data["given_by"], data["decision"], data.get("comments"))
        return {"m1_decision": data["decision"]}

    elif step == "m2_feedback":
        repo.save_feedback(candidate_id, "M2", data["given_by"], data["decision"], data.get("comments"))
        return {"m2_decision": data["decision"]}

    elif step == "close_process":
        final = "Selected - Offer" if data["outcome"] == "Offer" else "Rejected"
        repo.close_candidate(candidate_id, final)

    return {}


def make_human_step(step):
    def node(state: HiringState):
        candidate_id = state["candidate_id"]
        submission = state.get("submission")

        if submission and submission["step"] == step:
            data = submission.get("data", {})
            updates = apply_step(step, candidate_id, data)
            repo.log_activity(candidate_id, step, submission["user_id"], data)
            return {"submission": None, "waiting_at": None, **updates}

        # The process has reached this step: wait here until HR completes it.
        repo.set_current_step(candidate_id, step, STEPS[step]["stage"])
        return {"waiting_at": step}

    node.__name__ = step
    return node


def close_candidate(state: HiringState):
    """Automatic close when a candidate is not shortlisted or unselected in M1."""
    if state.get("shortlist_decision") != "Shortlisted":
        status = STATUS_NOT_SHORTLISTED
    else:
        status = "Closed - M1 unselected"
    repo.close_candidate(state["candidate_id"], status)
    repo.log_activity(state["candidate_id"], "closed", None, {"status": status})
    return {"waiting_at": None}
