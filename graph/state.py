"""The data the workflow works with for one candidate (loaded from the candidates table on every run)."""
from typing import TypedDict


class HiringState(TypedDict, total=False):
    candidate_id: int
    submission: dict | None   # the step HR is completing now: {"step", "user_id", "data"}
    shortlist_decision: str   # "Shortlisted" / "Not shortlisted"
    m1_decision: str          # "Selected" / "Unselected"
    m2_decision: str          # "Selected" / "Rejected"
    waiting_at: str | None    # the step the process stopped at, waiting for HR
