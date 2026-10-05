"""
One form per step. HR / Recruitment fills every form.

HR contacts the HOD, interviewers and candidate OUTSIDE this platform
(Teams, email, phone...). These forms are where HR RECORDS what happened:
who was contacted, through which channel, and what they decided.

When HR goes back to a step that was recorded before, the form is pre-filled
with what was entered last time, so HR only changes what is different.

Each form returns the submitted data (a dict), or None if not submitted yet.
The FORMS table at the bottom says which function draws the form of each step.
"""
from datetime import datetime

import streamlit as st

from config.steps import CONTACT_CHANNELS, ROLE_HOD, ROLE_INTERVIEWER
from services import ai_helpers
from services import repository as repo


def render_step_form(step, candidate):
    """Draws the form of this step for this candidate. Returns what HR submitted, or None."""
    form = FORMS.get(step)
    if form is None:
        return None
    return form(candidate, step)


# ---------------------------------------------------------------- Stage 1: Screening

def approve_shortlist_form(candidate, step):
    score = candidate["ai_score"]
    if score is None:
        score = "N/A (the AI could not score this CV)"
    st.write(f"**AI score:** {score}  ·  Shortlist threshold for this job: **{candidate['shortlist_threshold']}**")
    st.text(candidate["ai_reason"] or "")
    prev = previous_entry(candidate, step)
    options = ["Shortlisted", "Not shortlisted"]
    with st.form(form_key(step, candidate)):
        decision = st.radio("Decision", options, index=index_of(options, prev.get("decision")), horizontal=True)
        if st.form_submit_button("Submit"):
            return {"decision": decision}
    return None


# ---------------------------------------------------------------- Stage 2: M1 round

def contact_hod_form(candidate, step):
    st.caption("Contact the department HOD (Teams / email / phone), then record it here.")
    hods = department_hods(candidate)
    if not hods:
        return None
    ai_message_button(step, candidate, "Share the shortlisted CV and request interviewers for the M1 round", "HOD")
    prev = previous_entry(candidate, step)
    key = form_key(step, candidate)
    with st.form(key):
        hod_id = person_box("HOD contacted", hods, prev.get("hod_id"), f"{key}-hod")
        channel = channel_box(prev)
        notes = st.text_area("What was shared / notes", value=prev.get("notes") or "")
        if st.form_submit_button("Record: HOD contacted"):
            return {"hod_id": hod_id, "channel": channel, "notes": notes}
    return None


def contact_interviewers_form(candidate, step):
    st.caption("HOD's step: the HOD contacts the interviewers. Record which interviewers the HOD assigned.")
    hods = department_hods(candidate)
    interviewers = repo.list_users(role=ROLE_INTERVIEWER, department_id=candidate["department_id"])
    if not hods:
        return None
    if not interviewers:
        st.warning("No interviewers found in this department. Add them on the People page.")
        return None
    prev = previous_entry(candidate, step)
    key = form_key(step, candidate)
    with st.form(key):
        interviewer_names = names_by_id(interviewers)
        hod_id = person_box("Assigned by HOD", hods, prev.get("hod_id"), f"{key}-hod")
        chosen_before = [i for i in prev.get("interviewer_ids") or [] if i in interviewer_names]
        chosen = st.multiselect("Interviewers assigned", list(interviewer_names), default=chosen_before,
                                format_func=interviewer_names.get, key=f"{key}-interviewers")
        notes = st.text_area("Notes (optional)", value=prev.get("notes") or "")
        if st.form_submit_button("Record: interviewers assigned"):
            if not is_filled(chosen, "Please choose at least one interviewer."):
                return None
            return {"hod_id": hod_id, "interviewer_ids": chosen, "notes": notes}
    return None


def interviewer_slots_form(candidate, step):
    assigned = [u["full_name"] for u in repo.get_assigned_interviewers(candidate["id"])]
    st.caption(f"Coordinate with the interviewers for available slots. Assigned: {', '.join(assigned) or 'None'}")
    ai_message_button(step, candidate, "Ask for available time slots for the M1 interview", "Interviewers")
    prev = previous_entry(candidate, step)
    with st.form(form_key(step, candidate)):
        channel = channel_box(prev)
        slots = st.text_area("Available slots from interviewers", value=prev.get("slots") or "",
                             placeholder="e.g. Mon 11am, Tue 3pm")
        if st.form_submit_button("Record: slots received"):
            if not is_filled(slots, "Please enter the available slots."):
                return None
            return {"channel": channel, "slots": slots}
    return None


def contact_candidate_form(candidate, step):
    st.caption("Coordinate with the candidate, then record their availability.")
    ai_message_button(step, candidate, "Invite the candidate for the M1 interview and ask for availability",
                      candidate["full_name"])
    prev = previous_entry(candidate, step)
    with st.form(form_key(step, candidate)):
        channel = channel_box(prev)
        notes = st.text_area("Candidate availability / notes", value=prev.get("candidate_availability") or "")
        if st.form_submit_button("Record: candidate contacted"):
            if not is_filled(notes, "Please enter the candidate's availability."):
                return None
            return {"channel": channel, "candidate_availability": notes}
    return None


def schedule_form(candidate, step):
    """The same form schedules the M1 interview and the M2 interview."""
    st.caption("Fix the date and time, share it with everyone involved, then record it here.")
    prev = previous_entry(candidate, step)
    previous_time = None
    if prev.get("scheduled_at"):
        try:
            previous_time = datetime.fromisoformat(prev["scheduled_at"])
        except ValueError:
            previous_time = None
    with st.form(form_key(step, candidate)):
        date = st.date_input("Interview date", value=previous_time.date() if previous_time else "today")
        time = st.time_input("Interview time", value=previous_time.time() if previous_time else "now")
        location = st.text_input("Location / meeting link", value=prev.get("location") or "")
        notes = st.text_area("Notes (optional)", value=prev.get("notes") or "")
        if st.form_submit_button("Save schedule"):
            return {"scheduled_at": datetime.combine(date, time).isoformat(), "location": location, "notes": notes}
    return None


def m1_interview_form(candidate, step):
    st.caption("Interviewers' step: they conduct the interview. Record when it is done.")
    key = f"questions-{candidate['id']}"
    if st.button("Suggest interview questions to share (AI)", key=f"btn-{key}"):
        with st.spinner("AI is preparing questions..."):
            st.session_state[key] = ai_helpers.interview_questions(candidate["job_description"], candidate["cv_text"] or "")
    if st.session_state.get(key):
        st.code(st.session_state[key], language=None, wrap_lines=True)
    return interview_done_form(candidate, step)


def m1_feedback_form(candidate, step):
    st.caption("Interviewers' step: record the feedback they gave you (Selected / Unselected).")
    assigned = repo.get_assigned_interviewers(candidate["id"])
    if not assigned:
        st.warning("No interviewers assigned to this candidate.")
        return None
    prev = previous_entry(candidate, step)
    options = ["Selected", "Unselected"]
    key = form_key(step, candidate)
    with st.form(key):
        given_by = person_box("Feedback given by", assigned, prev.get("given_by"), f"{key}-by")
        channel = channel_box(prev, "Received through")
        decision = st.radio("Decision", options, index=index_of(options, prev.get("decision")), horizontal=True)
        comments = st.text_area("Comments", value=prev.get("comments") or "")
        if st.form_submit_button("Record feedback"):
            return {"given_by": given_by, "channel": channel, "decision": decision, "comments": comments}
    return None


def record_m1_form(candidate, step):
    for f in repo.get_feedback(candidate["id"]):
        st.write(f"- **{f['given_by']}** ({f['round']}): {f['decision']} - {f['comments'] or ''}")
    previous_entry(candidate, step)
    with st.form(form_key(step, candidate)):
        confirm = st.checkbox("I have reviewed the M1 feedback")  # always confirmed again, never pre-ticked
        if st.form_submit_button("Record M1 result"):
            if not confirm:
                st.error("Please confirm you reviewed the feedback.")
                return None
            return {"confirmed": True}
    return None


# ---------------------------------------------------------------- Stage 3: M2 round

def hod_slots_form(candidate, step):
    st.caption("Coordinate with the HOD for available interview slots.")
    hods = department_hods(candidate)
    if not hods:
        return None
    ai_message_button(step, candidate, "Ask for available time slots for the M2 interview", "HOD")
    prev = previous_entry(candidate, step)
    key = form_key(step, candidate)
    with st.form(key):
        hod_id = person_box("HOD", hods, prev.get("hod_id"), f"{key}-hod")
        channel = channel_box(prev)
        slots = st.text_area("HOD available slots", value=prev.get("slots") or "", placeholder="e.g. Wed 2pm, Thu 10am")
        if st.form_submit_button("Record: HOD slots received"):
            if not is_filled(slots, "Please enter the HOD's available slots."):
                return None
            return {"hod_id": hod_id, "channel": channel, "slots": slots}
    return None


def m2_interview_form(candidate, step):
    st.caption("HOD's step: the HOD conducts the interview. Record when it is done.")
    key = f"summary-{candidate['id']}"
    if st.button("M1 feedback summary to share with HOD (AI)", key=f"btn-{key}"):
        with st.spinner("AI is summarizing..."):
            st.session_state[key] = ai_helpers.summarize_feedback(repo.get_feedback(candidate["id"]))
    if st.session_state.get(key):
        st.code(st.session_state[key], language=None, wrap_lines=True)
    return interview_done_form(candidate, step)


def m2_feedback_form(candidate, step):
    st.caption("HOD's step: record the final feedback the HOD gave you (Selected / Rejected).")
    hods = department_hods(candidate)
    if not hods:
        return None
    prev = previous_entry(candidate, step)
    options = ["Selected", "Rejected"]
    key = form_key(step, candidate)
    with st.form(key):
        given_by = person_box("Feedback given by HOD", hods, prev.get("given_by"), f"{key}-by")
        channel = channel_box(prev, "Received through")
        decision = st.radio("Final decision", options, index=index_of(options, prev.get("decision")), horizontal=True)
        comments = st.text_area("Comments", value=prev.get("comments") or "")
        if st.form_submit_button("Record final feedback"):
            return {"given_by": given_by, "channel": channel, "decision": decision, "comments": comments}
    return None


def close_process_form(candidate, step):
    m2_feedback = [f for f in repo.get_feedback(candidate["id"]) if f["round"] == "M2"]
    if m2_feedback:
        st.write(f"**HOD final decision:** {m2_feedback[-1]['decision']}")
    prev = previous_entry(candidate, step)
    options = ["Offer", "Rejection"]
    if m2_feedback and m2_feedback[-1]["decision"] == "Selected":
        suggested = 0   # Offer
    else:
        suggested = 1   # Rejection
    with st.form(form_key(step, candidate)):
        outcome = st.radio("Outcome", options, index=index_of(options, prev.get("outcome"), suggested), horizontal=True)
        notes = st.text_area("Notes (optional)", value=prev.get("notes") or "")
        if st.form_submit_button("Close the process"):
            return {"outcome": outcome, "notes": notes}
    return None


# Which function draws the form of each step.
FORMS = {
    "approve_shortlist": approve_shortlist_form,
    "contact_hod": contact_hod_form,
    "contact_interviewers": contact_interviewers_form,
    "interviewer_slots": interviewer_slots_form,
    "contact_candidate": contact_candidate_form,
    "schedule_m1": schedule_form,
    "m1_interview": m1_interview_form,
    "m1_feedback": m1_feedback_form,
    "record_m1": record_m1_form,
    "hod_slots": hod_slots_form,
    "schedule_m2": schedule_form,
    "m2_interview": m2_interview_form,
    "m2_feedback": m2_feedback_form,
    "close_process": close_process_form,
}


# ---------------------------------------------------------------- pieces shared by the forms

def form_key(step, candidate):
    return f"form-{step}-{candidate['id']}"


def interview_done_form(candidate, step):
    """M1 and M2 interview steps: HR confirms the interview has been conducted."""
    prev = previous_entry(candidate, step)
    with st.form(form_key(step, candidate)):
        done = st.checkbox("The interview has been conducted")  # always confirmed again, never pre-ticked
        notes = st.text_area("Notes (optional)", value=prev.get("notes") or "")
        if st.form_submit_button("Record: interview done"):
            if not done:
                st.error("Please confirm the interview has been conducted.")
                return None
            return {"completed": True, "notes": notes}
    return None


def previous_entry(candidate, step):
    """What HR recorded for this step last time (when the candidate was sent back to it), or {} the first time."""
    record = repo.get_last_step_record(candidate["id"], step)
    if not record:
        return {}
    details = record["details"] or {}
    if details.get("automatic"):
        who = "automatically by the AI score"
    else:
        who = f"by {record['done_by'] or 'the system'}"
    st.info(f"✏️ **Editing a step that was recorded before** "
            f"(on {record['created_at']:%d %b %Y %H:%M} {who}). "
            "The fields show what was entered then. Change what is needed and save.")
    return details


def ai_message_button(step, candidate, purpose, recipient):
    """Optional AI-written message that HR can copy into Teams / email."""
    key = f"draft-{step}-{candidate['id']}"
    if st.button("Generate AI message to copy", key=f"btn-{key}"):
        with st.spinner("AI is writing a message..."):
            st.session_state[key] = ai_helpers.draft_message(purpose, candidate["full_name"], candidate["job_title"], recipient)
    if st.session_state.get(key):
        st.caption("Copy this message into Teams / email:")
        st.code(st.session_state[key], language=None, wrap_lines=True)


def department_hods(candidate):
    hods = repo.list_users(role=ROLE_HOD, department_id=candidate["department_id"])
    if not hods:
        st.warning(f"No HOD found for {candidate['department']}. Add one on the People page.")
    return hods


def person_box(label, people, previous_id, key):
    """A list to choose a person. A fixed key keeps HR's choice even if the list of people changes while the form is open."""
    names = names_by_id(people)
    ids = list(names)
    return st.selectbox(label, ids, index=index_of(ids, previous_id), format_func=names.get, key=key)


def channel_box(prev, label="Contacted through"):
    return st.selectbox(label, CONTACT_CHANNELS, index=index_of(CONTACT_CHANNELS, prev.get("channel")))


def names_by_id(people):
    return {p["id"]: p["full_name"] for p in people}


def index_of(options, value, default=0):
    """Position of the previously chosen value in the options (or the default if it is not there any more)."""
    if value in options:
        return options.index(value)
    return default


def is_filled(value, message):
    """False (and shows the message) when a required field is empty."""
    if not value or (isinstance(value, str) and not value.strip()):
        st.error(message)
        return False
    return True
