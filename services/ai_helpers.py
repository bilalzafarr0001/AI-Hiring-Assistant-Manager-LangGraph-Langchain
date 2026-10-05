"""
Small AI helpers for HR on the step forms. The AI only HELPS: it drafts, suggests and summarizes.
It never makes a decision. If the AI is not available, a plain text is returned instead.

(The CV score is in services/scoring.py.)
"""
from services.llm import AI_UNAVAILABLE, ask_llm
from services.prompts import feedback_summary_prompt, interview_questions_prompt, message_prompt


def draft_message(purpose, candidate_name, job_title, recipient):
    """A short message HR can copy into Teams / email."""
    message = ask_llm(message_prompt(purpose, candidate_name, job_title, recipient))
    if message:
        return message
    return (f"Dear {recipient},\n\nRegarding {candidate_name} for the {job_title} position: {purpose}."
            f"\n\nThank you,\nHR / Recruitment")


def interview_questions(job_description, cv_text):
    """8 technical interview questions for this candidate."""
    return ask_llm(interview_questions_prompt(job_description, cv_text)) or AI_UNAVAILABLE


def summarize_feedback(feedback_rows):
    """A short summary of the interview feedback, for the HOD."""
    if not feedback_rows:
        return "No feedback recorded yet."
    lines = [f"- {f['given_by']} ({f['round']}): {f['decision']}. {f['comments'] or ''}" for f in feedback_rows]
    text = "\n".join(lines)
    return ask_llm(feedback_summary_prompt(text)) or text
