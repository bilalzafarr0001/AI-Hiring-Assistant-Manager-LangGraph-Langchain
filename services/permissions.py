"""
Who can do what.

Only HR / Recruitment uses this platform. HR completes every step.
For HOD and interviewer steps, HR records what the HOD / interviewer decided,
and the app saves WHO gave the decision and WHICH HR user entered it.
"""
from config.steps import ROLE_HR, STEPS


def can_act(user, step, candidate=None):
    return bool(step) and step in STEPS and user["role"] == ROLE_HR
