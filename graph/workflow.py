"""
The hiring process as a LangGraph graph (follows the PRD exactly):

    Screening -> M1 round -> (only if M1 = Selected) M2 round -> Close

How the graph is used
- The graph does not stay running. Each candidate's place in the process is saved in their
  candidates row (current_step + the decisions), so the process can wait for days and continue later.
- Every run is short. It starts at the step HR is completing (or at the first step for a new candidate),
  saves it, follows the arrows below, and stops at the next step that needs HR.
- A step stops the run by marking itself as the candidate's current step and setting "waiting_at".
  Every arrow checks "waiting_at": if it is set, the run ends (END).
"""
from typing import TypedDict
from langgraph.graph import END, START, StateGraph
from config.steps import STATUS_NOT_SHORTLISTED, STEPS
from services import repository as repo


# ================================================================ 1. The data of one run

class HiringState(TypedDict, total=False):
    candidate_id: int
    submission: dict | None   # the step HR is completing now: {"step", "user_id", "data"}
    shortlist_decision: str   # "Shortlisted" / "Not shortlisted"
    m1_decision: str          # "Selected" / "Unselected"
    m2_decision: str          # "Selected" / "Rejected"
    waiting_at: str | None    # the step the run stopped at, waiting for HR


# ================================================================ 2. What every step node does

def run_step(state, step):
    """
    Every step node calls this with its own step name. It does one of two things:
    - HR is completing THIS step now: save what HR submitted, write the history, and let the run go on.
    - Otherwise the run has just reached this step: mark the candidate as waiting here, and stop the run.
    Returns the changes to the state (LangGraph adds them to the state).
    """
    candidate_id = state["candidate_id"]
    submission = state.get("submission")

    # 1. HR is completing this step: save it.
    if submission and submission["step"] == step:
        data = submission.get("data", {})
        decision = save_step(step, candidate_id, data)
        repo.log_activity(candidate_id, step, submission["user_id"], data)
        changes = {"submission": None, "waiting_at": None}   # the submission is used, the run goes on
        changes.update(decision)                              # e.g. {"shortlist_decision": "Shortlisted"}
        return changes

    # 2. The run has just reached this step: the candidate now waits here for HR.
    repo.set_current_step(candidate_id, step, STEPS[step]["stage"])
    return {"waiting_at": step}


def save_step(step, candidate_id, data):
    """Saves what HR submitted for this step on the candidate row. Returns the decision for the arrows, if any."""
    if step == "approve_shortlist":
        repo.save_shortlist_decision(candidate_id, data["decision"])
        return {"shortlist_decision": data["decision"]}

    if step == "contact_interviewers":
        repo.assign_interviewers(candidate_id, data["interviewer_ids"])
    elif step == "schedule_m1":
        repo.save_interview(candidate_id, "M1", data["scheduled_at"], data.get("location"))
    elif step == "schedule_m2":
        repo.save_interview(candidate_id, "M2", data["scheduled_at"], data.get("location"))
    elif step == "m1_feedback":
        repo.save_feedback(candidate_id, "M1", data["given_by"], data["decision"], data.get("comments"))
        return {"m1_decision": data["decision"]}
    elif step == "m2_feedback":
        repo.save_feedback(candidate_id, "M2", data["given_by"], data["decision"], data.get("comments"))
        return {"m2_decision": data["decision"]}
    elif step == "close_process":
        final_status = "Selected - Offer" if data["outcome"] == "Offer" else "Rejected"
        repo.close_candidate(candidate_id, final_status)
    # The other steps (contacts, slots, interview done...) only need the history row written by run_step().
    return {}


# ================================================================ 3. The graph nodes: one per step

# Stage 1: Screening
def approve_shortlist(state):
    return run_step(state, "approve_shortlist")


# Stage 2: M1 round
def contact_hod(state):
    return run_step(state, "contact_hod")


def contact_interviewers(state):
    return run_step(state, "contact_interviewers")


def interviewer_slots(state):
    return run_step(state, "interviewer_slots")


def contact_candidate(state):
    return run_step(state, "contact_candidate")


def schedule_m1(state):
    return run_step(state, "schedule_m1")


def m1_interview(state):
    return run_step(state, "m1_interview")


def m1_feedback(state):
    return run_step(state, "m1_feedback")


def record_m1(state):
    return run_step(state, "record_m1")


# Stage 3: M2 round
def hod_slots(state):
    return run_step(state, "hod_slots")


def schedule_m2(state):
    return run_step(state, "schedule_m2")


def m2_interview(state):
    return run_step(state, "m2_interview")


def m2_feedback(state):
    return run_step(state, "m2_feedback")


def close_process(state):
    return run_step(state, "close_process")


# Automatic close: the candidate was not shortlisted, or was not selected in M1.
def close_candidate(state):
    if state.get("shortlist_decision") != "Shortlisted":
        status = STATUS_NOT_SHORTLISTED
    else:
        status = "Closed - M1 unselected"
    repo.close_candidate(state["candidate_id"], status)
    repo.log_activity(state["candidate_id"], "closed", None, {"status": status})
    return {"waiting_at": None}


# ================================================================ 4. The arrows: where to go after each node

def first_step(state):
    """Where a run starts: a new candidate at the first step, otherwise at the step HR is completing."""
    submission = state.get("submission")
    if submission:
        return submission["step"]
    return "approve_shortlist"


def stop_or_go_to(state, next_step):
    """If the step before stopped to wait for HR, the run ends (END). Otherwise it goes on to next_step."""
    if state.get("waiting_at"):
        return END
    return next_step


# Stage 1: Screening -> M1 round (Shortlisted), or close (Not shortlisted)
def after_approve_shortlist(state):
    if state.get("waiting_at"):
        return END
    if state.get("shortlist_decision") == "Shortlisted":
        return "contact_hod"
    return "close_candidate"


# Stage 2: M1 round, one step after the other
def after_contact_hod(state):
    return stop_or_go_to(state, "contact_interviewers")


def after_contact_interviewers(state):
    return stop_or_go_to(state, "interviewer_slots")


def after_interviewer_slots(state):
    return stop_or_go_to(state, "contact_candidate")


def after_contact_candidate(state):
    return stop_or_go_to(state, "schedule_m1")


def after_schedule_m1(state):
    return stop_or_go_to(state, "m1_interview")


def after_m1_interview(state):
    return stop_or_go_to(state, "m1_feedback")


def after_m1_feedback(state):
    return stop_or_go_to(state, "record_m1")


# End of M1: -> M2 round (M1 Selected), or close (M1 Unselected)
def after_record_m1(state):
    if state.get("waiting_at"):
        return END
    if state.get("m1_decision") == "Selected":
        return "hod_slots"
    return "close_candidate"


# Stage 3: M2 round, one step after the other
def after_hod_slots(state):
    return stop_or_go_to(state, "schedule_m2")


def after_schedule_m2(state):
    return stop_or_go_to(state, "m2_interview")


def after_m2_interview(state):
    return stop_or_go_to(state, "m2_feedback")


def after_m2_feedback(state):
    return stop_or_go_to(state, "close_process")


# ================================================================ 5. Putting the graph together

def build_graph():
    graph = StateGraph(HiringState)

    # ---------------- The nodes ----------------

    # Stage 1: Screening
    graph.add_node("approve_shortlist", approve_shortlist)

    # Stage 2: M1 round
    graph.add_node("contact_hod", contact_hod)
    graph.add_node("contact_interviewers", contact_interviewers)
    graph.add_node("interviewer_slots", interviewer_slots)
    graph.add_node("contact_candidate", contact_candidate)
    graph.add_node("schedule_m1", schedule_m1)
    graph.add_node("m1_interview", m1_interview)
    graph.add_node("m1_feedback", m1_feedback)
    graph.add_node("record_m1", record_m1)

    # Stage 3: M2 round
    graph.add_node("hod_slots", hod_slots)
    graph.add_node("schedule_m2", schedule_m2)
    graph.add_node("m2_interview", m2_interview)
    graph.add_node("m2_feedback", m2_feedback)
    graph.add_node("close_process", close_process)

    # Automatic close (not shortlisted, or not selected in M1)
    graph.add_node("close_candidate", close_candidate)

    # ---------------- The arrows ----------------
    # Each line: after this node -> the arrow function decides -> one of these places.

    # Where a run starts: a new candidate at approve_shortlist, otherwise at the step HR is completing.
    graph.add_conditional_edges(START, first_step, [
        "approve_shortlist",
        "contact_hod", "contact_interviewers", "interviewer_slots", "contact_candidate",
        "schedule_m1", "m1_interview", "m1_feedback", "record_m1",
        "hod_slots", "schedule_m2", "m2_interview", "m2_feedback", "close_process",
    ])

    # Stage 1: Screening
    graph.add_conditional_edges("approve_shortlist", after_approve_shortlist, ["contact_hod", "close_candidate", END])

    # Stage 2: M1 round
    graph.add_conditional_edges("contact_hod", after_contact_hod, ["contact_interviewers", END])
    graph.add_conditional_edges("contact_interviewers", after_contact_interviewers, ["interviewer_slots", END])
    graph.add_conditional_edges("interviewer_slots", after_interviewer_slots, ["contact_candidate", END])
    graph.add_conditional_edges("contact_candidate", after_contact_candidate, ["schedule_m1", END])
    graph.add_conditional_edges("schedule_m1", after_schedule_m1, ["m1_interview", END])
    graph.add_conditional_edges("m1_interview", after_m1_interview, ["m1_feedback", END])
    graph.add_conditional_edges("m1_feedback", after_m1_feedback, ["record_m1", END])
    graph.add_conditional_edges("record_m1", after_record_m1, ["hod_slots", "close_candidate", END])

    # Stage 3: M2 round
    graph.add_conditional_edges("hod_slots", after_hod_slots, ["schedule_m2", END])
    graph.add_conditional_edges("schedule_m2", after_schedule_m2, ["m2_interview", END])
    graph.add_conditional_edges("m2_interview", after_m2_interview, ["m2_feedback", END])
    graph.add_conditional_edges("m2_feedback", after_m2_feedback, ["close_process", END])

    # The end
    graph.add_edge("close_process", END)
    graph.add_edge("close_candidate", END)

    return graph.compile()
