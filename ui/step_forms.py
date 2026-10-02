"""
One form per step. HR / Recruitment fills every form.

HR contacts the HOD, interviewers and candidate OUTSIDE this platform
(Teams, email, phone...). These forms are where HR RECORDS what happened:
who was contacted, through which channel, and what they decided.

When HR goes back to a step that was recorded before, the form is pre-filled
with what was entered last time, so HR only changes what is different.

Each form returns the submitted data (a dict), or None if not submitted yet.
"""
from datetime import datetime

import streamlit as st

from config.steps import CONTACT_CHANNELS, ROLE_HOD, ROLE_INTERVIEWER
from services import ai_helpers
from services import repository as repo


def _names(people):
    return {p["id"]: p["full_name"] for p in people}


def _pick(options, value, default=0):
    """Index of the previously chosen value in a list of options (or the default if it is not there any more)."""
    return options.index(value) if value in options else default


def _previous(candidate, step):
    """What HR recorded for this step last time (when the candidate was sent back to it), or {} the first time."""
    record = repo.get_last_step_record(candidate["id"], step)
    if not record:
        return {}
    details = record["details"] or {}
    who = "automatically by the AI score" if details.get("automatic") else f"by {record['done_by'] or 'the system'}"
    st.info(f"✏️ **Editing a step that was recorded before** "
            f"(on {record['created_at']:%d %b %Y %H:%M} {who}). "
            "The fields show what was entered then. Change what is needed and save.")
    return details


def _ai_draft(step, candidate, purpose, recipient):
    """Optional AI-written message that HR can copy into Teams / email."""
    key = f"draft-{step}-{candidate['id']}"
    if st.button("Generate AI message to copy", key=f"btn-{key}"):
        with st.spinner("AI is writing a message..."):
            st.session_state[key] = ai_helpers.draft_message(purpose, candidate["full_name"], candidate["job_title"], recipient)
    if st.session_state.get(key):
        st.caption("Copy this message into Teams / email:")
        st.code(st.session_state[key], language=None, wrap_lines=True)


def _channel(prev, label="Contacted through"):
    return st.selectbox(label, CONTACT_CHANNELS, index=_pick(CONTACT_CHANNELS, prev.get("channel")))


def _person(label, people, prev_id, key):
    # A fixed key keeps HR's choice even if the list of people changes while the form is open.
    names = _names(people)
    ids = list(names)
    return st.selectbox(label, ids, index=_pick(ids, prev_id), format_func=names.get, key=key)


def _required(value, message):
    if not value or (isinstance(value, str) and not value.strip()):
        st.error(message)
        return False
    return True


def _department_hods(candidate):
    hods = repo.list_users(role=ROLE_HOD, department_id=candidate["department_id"])
    if not hods:
        st.warning(f"No HOD found for {candidate['department']}. Add one on the People page.")
    return hods


def _schedule_form(form_key, prev):
    previous_time = None
    if prev.get("scheduled_at"):
        try:
            previous_time = datetime.fromisoformat(prev["scheduled_at"])
        except ValueError:
            previous_time = None
    with st.form(form_key):
        date = st.date_input("Interview date", value=previous_time.date() if previous_time else "today")
        time = st.time_input("Interview time", value=previous_time.time() if previous_time else "now")
        location = st.text_input("Location / meeting link", value=prev.get("location") or "")
        notes = st.text_area("Notes (optional)", value=prev.get("notes") or "")
        if st.form_submit_button("Save schedule"):
            return {"scheduled_at": datetime.combine(date, time).isoformat(), "location": location, "notes": notes}
    return None


def render_step_form(step, candidate):
    cid = candidate["id"]
    form_key = f"form-{step}-{cid}"

    # ---------------- Stage 1: Screening ----------------
    if step == "approve_shortlist":
        score = candidate["ai_score"]
        st.write(f"**AI score:** {score if score is not None else 'N/A (the AI could not score this CV)'}"
                 f"  ·  Shortlist threshold for this job: **{candidate['shortlist_threshold']}**")
        st.text(candidate["ai_reason"] or "")
        prev = _previous(candidate, step)
        options = ["Shortlisted", "Not shortlisted"]
        with st.form(form_key):
            decision = st.radio("Decision", options, index=_pick(options, prev.get("decision")), horizontal=True)
            if st.form_submit_button("Submit"):
                return {"decision": decision}

    # ---------------- Stage 2: M1 round ----------------
    elif step == "contact_hod":
        st.caption("Contact the department HOD (Teams / email / phone), then record it here.")
        hods = _department_hods(candidate)
        if not hods:
            return None
        _ai_draft(step, candidate, "Share the shortlisted CV and request interviewers for the M1 round", "HOD")
        prev = _previous(candidate, step)
        with st.form(form_key):
            hod_id = _person("HOD contacted", hods, prev.get("hod_id"), f"{form_key}-hod")
            channel = _channel(prev)
            notes = st.text_area("What was shared / notes", value=prev.get("notes") or "")
            if st.form_submit_button("Record: HOD contacted"):
                return {"hod_id": hod_id, "channel": channel, "notes": notes}

    elif step == "contact_interviewers":
        st.caption("HOD's step: the HOD contacts the interviewers. Record which interviewers the HOD assigned.")
        hods = _department_hods(candidate)
        interviewers = repo.list_users(role=ROLE_INTERVIEWER, department_id=candidate["department_id"])
        if not hods:
            return None
        if not interviewers:
            st.warning("No interviewers found in this department. Add them on the People page.")
            return None
        prev = _previous(candidate, step)
        with st.form(form_key):
            int_names = _names(interviewers)
            hod_id = _person("Assigned by HOD", hods, prev.get("hod_id"), f"{form_key}-hod")
            before = [i for i in prev.get("interviewer_ids") or [] if i in int_names]
            chosen = st.multiselect("Interviewers assigned", list(int_names), default=before, format_func=int_names.get,
                                    key=f"{form_key}-interviewers")
            notes = st.text_area("Notes (optional)", value=prev.get("notes") or "")
            if st.form_submit_button("Record: interviewers assigned"):
                if not _required(chosen, "Please choose at least one interviewer."):
                    return None
                return {"hod_id": hod_id, "interviewer_ids": chosen, "notes": notes}

    elif step == "interviewer_slots":
        names = ", ".join(u["full_name"] for u in repo.get_assigned_interviewers(cid)) or "None"
        st.caption(f"Coordinate with the interviewers for available slots. Assigned: {names}")
        _ai_draft(step, candidate, "Ask for available time slots for the M1 interview", "Interviewers")
        prev = _previous(candidate, step)
        with st.form(form_key):
            channel = _channel(prev)
            slots = st.text_area("Available slots from interviewers", value=prev.get("slots") or "",
                                 placeholder="e.g. Mon 11am, Tue 3pm")
            if st.form_submit_button("Record: slots received"):
                if not _required(slots, "Please enter the available slots."):
                    return None
                return {"channel": channel, "slots": slots}

    elif step == "contact_candidate":
        st.caption("Coordinate with the candidate, then record their availability.")
        _ai_draft(step, candidate, "Invite the candidate for the M1 interview and ask for availability", candidate["full_name"])
        prev = _previous(candidate, step)
        with st.form(form_key):
            channel = _channel(prev)
            notes = st.text_area("Candidate availability / notes", value=prev.get("candidate_availability") or "")
            if st.form_submit_button("Record: candidate contacted"):
                if not _required(notes, "Please enter the candidate's availability."):
                    return None
                return {"channel": channel, "candidate_availability": notes}

    elif step in ("schedule_m1", "schedule_m2"):
        st.caption("Fix the date and time, share it with everyone involved, then record it here.")
        return _schedule_form(form_key, _previous(candidate, step))

    elif step == "m1_interview":
        st.caption("Interviewers' step: they conduct the interview. Record when it is done.")
        key = f"questions-{cid}"
        if st.button("Suggest interview questions to share (AI)", key=f"btn-{key}"):
            with st.spinner("AI is preparing questions..."):
                st.session_state[key] = ai_helpers.interview_questions(candidate["job_description"], candidate["cv_text"] or "")
        if st.session_state.get(key):
            st.code(st.session_state[key], language=None, wrap_lines=True)
        prev = _previous(candidate, step)
        with st.form(form_key):
            done = st.checkbox("The interview has been conducted")  # always confirmed again, never pre-ticked
            notes = st.text_area("Notes (optional)", value=prev.get("notes") or "")
            if st.form_submit_button("Record: interview done"):
                if not done:
                    st.error("Please confirm the interview has been conducted.")
                    return None
                return {"completed": True, "notes": notes}

    elif step == "m1_feedback":
        st.caption("Interviewers' step: record the feedback they gave you (Selected / Unselected).")
        assigned = repo.get_assigned_interviewers(cid)
        if not assigned:
            st.warning("No interviewers assigned to this candidate.")
            return None
        prev = _previous(candidate, step)
        options = ["Selected", "Unselected"]
        with st.form(form_key):
            given_by = _person("Feedback given by", assigned, prev.get("given_by"), f"{form_key}-by")
            channel = _channel(prev, "Received through")
            decision = st.radio("Decision", options, index=_pick(options, prev.get("decision")), horizontal=True)
            comments = st.text_area("Comments", value=prev.get("comments") or "")
            if st.form_submit_button("Record feedback"):
                return {"given_by": given_by, "channel": channel, "decision": decision, "comments": comments}

    elif step == "record_m1":
        for f in repo.get_feedback(cid):
            st.write(f"- **{f['given_by']}** ({f['round']}): {f['decision']} - {f['comments'] or ''}")
        _previous(candidate, step)
        with st.form(form_key):
            confirm = st.checkbox("I have reviewed the M1 feedback")  # always confirmed again, never pre-ticked
            if st.form_submit_button("Record M1 result"):
                if not confirm:
                    st.error("Please confirm you reviewed the feedback.")
                    return None
                return {"confirmed": True}

    # ---------------- Stage 3: M2 round ----------------
    elif step == "hod_slots":
        st.caption("Coordinate with the HOD for available interview slots.")
        hods = _department_hods(candidate)
        if not hods:
            return None
        _ai_draft(step, candidate, "Ask for available time slots for the M2 interview", "HOD")
        prev = _previous(candidate, step)
        with st.form(form_key):
            hod_id = _person("HOD", hods, prev.get("hod_id"), f"{form_key}-hod")
            channel = _channel(prev)
            slots = st.text_area("HOD available slots", value=prev.get("slots") or "", placeholder="e.g. Wed 2pm, Thu 10am")
            if st.form_submit_button("Record: HOD slots received"):
                if not _required(slots, "Please enter the HOD's available slots."):
                    return None
                return {"hod_id": hod_id, "channel": channel, "slots": slots}

    elif step == "m2_interview":
        st.caption("HOD's step: the HOD conducts the interview. Record when it is done.")
        key = f"summary-{cid}"
        if st.button("M1 feedback summary to share with HOD (AI)", key=f"btn-{key}"):
            with st.spinner("AI is summarizing..."):
                st.session_state[key] = ai_helpers.summarize_feedback(repo.get_feedback(cid))
        if st.session_state.get(key):
            st.code(st.session_state[key], language=None, wrap_lines=True)
        prev = _previous(candidate, step)
        with st.form(form_key):
            done = st.checkbox("The interview has been conducted")  # always confirmed again, never pre-ticked
            notes = st.text_area("Notes (optional)", value=prev.get("notes") or "")
            if st.form_submit_button("Record: interview done"):
                if not done:
                    st.error("Please confirm the interview has been conducted.")
                    return None
                return {"completed": True, "notes": notes}

    elif step == "m2_feedback":
        st.caption("HOD's step: record the final feedback the HOD gave you (Selected / Rejected).")
        hods = _department_hods(candidate)
        if not hods:
            return None
        prev = _previous(candidate, step)
        options = ["Selected", "Rejected"]
        with st.form(form_key):
            given_by = _person("Feedback given by HOD", hods, prev.get("given_by"), f"{form_key}-by")
            channel = _channel(prev, "Received through")
            decision = st.radio("Final decision", options, index=_pick(options, prev.get("decision")), horizontal=True)
            comments = st.text_area("Comments", value=prev.get("comments") or "")
            if st.form_submit_button("Record final feedback"):
                return {"given_by": given_by, "channel": channel, "decision": decision, "comments": comments}

    elif step == "close_process":
        m2 = [f for f in repo.get_feedback(cid) if f["round"] == "M2"]
        if m2:
            st.write(f"**HOD final decision:** {m2[-1]['decision']}")
        prev = _previous(candidate, step)
        options = ["Offer", "Rejection"]
        default = 0 if (m2 and m2[-1]["decision"] == "Selected") else 1
        with st.form(form_key):
            outcome = st.radio("Outcome", options, index=_pick(options, prev.get("outcome"), default), horizontal=True)
            notes = st.text_area("Notes (optional)", value=prev.get("notes") or "")
            if st.form_submit_button("Close the process"):
                return {"outcome": outcome, "notes": notes}

    return None
