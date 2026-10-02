"""
The hiring workflow as a LangGraph graph (follows the PRD exactly).

Screening -> M1 round -> (Selected only) M2 round -> Close

Every run starts at the step HR is completing (or at the first step for a new candidate),
saves it, follows the arrows below, and stops at the next step that needs HR.
"""
from langgraph.graph import END, START, StateGraph

from config.steps import STEP_ORDER
from graph.nodes import close_candidate, make_human_step
from graph.state import HiringState


def start_at(state):
    """A new candidate starts at the first step; otherwise start at the step HR is completing."""
    submission = state.get("submission")
    return submission["step"] if submission else "approve_shortlist"


def then(next_step):
    """Go to next_step, unless the process stopped to wait for HR."""
    def route(state):
        return END if state.get("waiting_at") else next_step
    return route


def after_shortlist(state):
    if state.get("waiting_at"):
        return END
    return "contact_hod" if state.get("shortlist_decision") == "Shortlisted" else "close_candidate"


def after_m1_result(state):
    if state.get("waiting_at"):
        return END
    return "hod_slots" if state.get("m1_decision") == "Selected" else "close_candidate"


def build_graph():
    graph = StateGraph(HiringState)

    for step in STEP_ORDER:
        graph.add_node(step, make_human_step(step))
    graph.add_node("close_candidate", close_candidate)

    graph.add_conditional_edges(START, start_at, STEP_ORDER)

    # Stage 1: Screening
    graph.add_conditional_edges("approve_shortlist", after_shortlist, ["contact_hod", "close_candidate", END])

    # Stage 2: M1 round
    m1_round = [
        ("contact_hod", "contact_interviewers"),        # HR  -> HOD
        ("contact_interviewers", "interviewer_slots"),  # HOD -> HR
        ("interviewer_slots", "contact_candidate"),     # HR
        ("contact_candidate", "schedule_m1"),           # HR
        ("schedule_m1", "m1_interview"),                # HR  -> Interviewers
        ("m1_interview", "m1_feedback"),                # Interviewers
        ("m1_feedback", "record_m1"),                   # Interviewers -> HR
    ]
    # Stage 3: M2 round
    m2_round = [
        ("hod_slots", "schedule_m2"),                   # HR
        ("schedule_m2", "m2_interview"),                # HR  -> HOD
        ("m2_interview", "m2_feedback"),                # HOD
        ("m2_feedback", "close_process"),               # HOD -> HR
    ]
    for step, next_step in m1_round + m2_round:
        graph.add_conditional_edges(step, then(next_step), [next_step, END])

    graph.add_conditional_edges("record_m1", after_m1_result, ["hod_slots", "close_candidate", END])
    graph.add_edge("close_process", END)
    graph.add_edge("close_candidate", END)

    return graph.compile()
