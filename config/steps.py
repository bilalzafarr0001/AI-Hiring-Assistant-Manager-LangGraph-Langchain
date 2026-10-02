"""
The hiring process from the PRD.

Every step has ONE owner role. Only that role can complete the step.
The order here is the order of the process.
"""

ROLE_HR = "HR"
ROLE_HOD = "HOD"
ROLE_INTERVIEWER = "INTERVIEWER"

ROLE_LABELS = {
    ROLE_HR: "HR / Recruitment",
    ROLE_HOD: "HOD",
    ROLE_INTERVIEWER: "Interviewer",
}

STEPS = {
    # Stage 1: Screening
    "approve_shortlist":    {"label": "Approve shortlist",            "owner": ROLE_HR,          "stage": "Screening"},
    # Stage 2: M1 round
    "contact_hod":          {"label": "Contact department HOD",       "owner": ROLE_HR,          "stage": "M1 round"},
    "contact_interviewers": {"label": "Contact interviewers",         "owner": ROLE_HOD,         "stage": "M1 round"},
    "interviewer_slots":    {"label": "Coordinate interviewer slots", "owner": ROLE_HR,          "stage": "M1 round"},
    "contact_candidate":    {"label": "Coordinate with candidate",    "owner": ROLE_HR,          "stage": "M1 round"},
    "schedule_m1":          {"label": "Schedule M1 interview",        "owner": ROLE_HR,          "stage": "M1 round"},
    "m1_interview":         {"label": "M1 interview execution",       "owner": ROLE_INTERVIEWER, "stage": "M1 round"},
    "m1_feedback":          {"label": "Send M1 feedback to HR",       "owner": ROLE_INTERVIEWER, "stage": "M1 round"},
    "record_m1":            {"label": "Record M1 result",             "owner": ROLE_HR,          "stage": "M1 round"},
    # Stage 3: M2 round (only if M1 = Selected)
    "hod_slots":            {"label": "Coordinate HOD slots",         "owner": ROLE_HR,          "stage": "M2 round"},
    "schedule_m2":          {"label": "Schedule M2 interview",        "owner": ROLE_HR,          "stage": "M2 round"},
    "m2_interview":         {"label": "M2 interview execution",       "owner": ROLE_HOD,         "stage": "M2 round"},
    "m2_feedback":          {"label": "Send final feedback to HR",    "owner": ROLE_HOD,         "stage": "M2 round"},
    "close_process":        {"label": "Close the process",            "owner": ROLE_HR,          "stage": "M2 round"},
}

STEP_ORDER = list(STEPS.keys())

# HR contacts HODs, interviewers and candidates outside this platform
# (company chat, email, phone). HR records which channel was used.
CONTACT_CHANNELS = ["Microsoft Teams", "Email", "Phone call", "WhatsApp", "In person", "Other"]

# Candidate status when they are not shortlisted (by the AI score or by HR).
STATUS_NOT_SHORTLISTED = "Closed - Not shortlisted"
