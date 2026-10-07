"""
All database reads and writes for the app: one small function per action, grouped by table.
(The tables are described in database/schema.sql.)
"""
from database.db import as_json, execute, fetch_all, fetch_one


# ---------- Users and departments ----------

def list_users(role=None, department_id=None):
    """All users, or only those with this role and/or in this department."""
    # "WHERE 1=1" is always true, so each filter below can simply add "AND ...".
    sql = "SELECT u.*, d.name AS department FROM users u LEFT JOIN departments d ON d.id = u.department_id WHERE 1=1"
    params = []
    if role:
        sql += " AND u.role = %s"
        params.append(role)
    if department_id:
        sql += " AND u.department_id = %s"
        params.append(department_id)
    return fetch_all(sql + " ORDER BY u.role, u.full_name", params)


def get_user(user_id):
    return fetch_one(
        "SELECT u.*, d.name AS department FROM users u LEFT JOIN departments d ON d.id = u.department_id WHERE u.id = %s",
        (user_id,),
    )


def list_departments():
    return fetch_all("SELECT * FROM departments ORDER BY name")


def get_login_user(email):
    """Only recruiters (role RECRUITER) with a password can sign in."""
    return fetch_one(
        "SELECT * FROM users WHERE LOWER(email) = LOWER(%s) AND role = 'RECRUITER' AND password_hash IS NOT NULL",
        (email.strip(),),
    )


def create_department(name):
    """Adds the department. Returns False if it already exists (in any case: "engineering" = "Engineering")."""
    row = execute(
        """INSERT INTO departments (name) SELECT %s
           WHERE NOT EXISTS (SELECT 1 FROM departments WHERE LOWER(name) = LOWER(%s))
           ON CONFLICT (name) DO NOTHING RETURNING id""",
        (name.strip(), name.strip()),
    )
    return row is not None


def create_user(full_name, email, role, department_id=None, password_hash=None):
    execute(
        "INSERT INTO users (full_name, email, role, department_id, password_hash) VALUES (%s, %s, %s, %s, %s)",
        (full_name.strip(), email.strip().lower(), role, department_id, password_hash),
    )


def set_password(user_id, password_hash):
    execute("UPDATE users SET password_hash = %s WHERE id = %s", (password_hash, user_id))


# ---------- Signed-in user (the tokens themselves are made in services/security.py) ----------

def get_signed_in_user(user_id):
    """The recruiter a token belongs to, or None if that user cannot sign in (not a recruiter, or no password)."""
    return fetch_one(
        """SELECT u.*, d.name AS department FROM users u LEFT JOIN departments d ON d.id = u.department_id
           WHERE u.id = %s AND u.role = 'RECRUITER' AND u.password_hash IS NOT NULL""",
        (user_id,),
    )


def bump_token_version(user_id):
    """Log out: every token made before for this user (on every device) stops working."""
    execute("UPDATE users SET token_version = token_version  + 1 WHERE id = %s", (user_id,))


# ---------- Jobs ----------

def create_job(title, description, department_id, created_by, shortlist_threshold=70):
    row = execute(
        """INSERT INTO jobs (title, description, department_id, created_by, shortlist_threshold)
           VALUES (%s, %s, %s, %s, %s) RETURNING id""",
        (title, description, department_id, created_by, shortlist_threshold),
    )
    return row["id"]


def set_screening_criteria(job_id, criteria):
    """criteria = {"required_skills": [[alternatives...], ...], "min_years": n}"""
    execute("UPDATE jobs SET screening_criteria = %s WHERE id = %s", (as_json(criteria), job_id))


def set_job_threshold(job_id, shortlist_threshold):
    execute("UPDATE jobs SET shortlist_threshold = %s WHERE id = %s", (shortlist_threshold, job_id))


def list_jobs():
    """Every job with its candidate counts (for the Jobs list)."""
    return fetch_all(
        """SELECT j.*, d.name AS department,
                  COUNT(c.id) AS candidate_count,
                  COUNT(c.id) FILTER (WHERE c.current_step = 'approve_shortlist') AS needs_review,
                  COUNT(c.id) FILTER (WHERE c.shortlist_decision = 'Shortlisted') AS shortlisted
           FROM jobs j
           JOIN departments d ON d.id = j.department_id
           LEFT JOIN candidates c ON c.job_id = j.id
           GROUP BY j.id, d.name
           ORDER BY j.created_at DESC"""
    )


def get_job(job_id):
    return fetch_one(
        "SELECT j.*, d.name AS department FROM jobs j JOIN departments d ON d.id = j.department_id WHERE j.id = %s",
        (job_id,),
    )


# ---------- Candidates ----------

# A candidate row plus what the pages need from the job, the department and the feedback givers.
CANDIDATE_SELECT = """
    SELECT c.*, j.title AS job_title, j.description AS job_description,
           j.department_id, j.shortlist_threshold, d.name AS department,
           m1u.full_name AS m1_feedback_by_name, m2u.full_name AS m2_feedback_by_name
    FROM candidates c
    JOIN jobs j ON j.id = c.job_id
    JOIN departments d ON d.id = j.department_id
    LEFT JOIN users m1u ON m1u.id = c.m1_feedback_by
    LEFT JOIN users m2u ON m2u.id = c.m2_feedback_by
"""


def create_candidate(job_id, full_name, email, cv_file, cv_text, ai_score, ai_reason):
    row = execute(
        """INSERT INTO candidates (job_id, full_name, email, cv_file, cv_text, ai_score, ai_reason)
           VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        (job_id, full_name, email, cv_file, cv_text, ai_score, ai_reason),
    )
    return row["id"]


def get_candidate(candidate_id):
    return fetch_one(CANDIDATE_SELECT + " WHERE c.id = %s", (candidate_id,))


def list_candidates():
    """Every candidate, most recently updated first (only HR uses the platform, so HR sees all)."""
    return fetch_all(CANDIDATE_SELECT + " ORDER BY c.updated_at DESC")


def list_candidates_for_job(job_id):
    """Candidates of one job, best AI score first."""
    return fetch_all(
        CANDIDATE_SELECT + " WHERE c.job_id = %s ORDER BY c.ai_score DESC NULLS LAST, c.created_at",
        (job_id,),
    )


def find_same_cv(job_id, cv_text):
    """Returns the candidate who already has exactly this CV text for this job, or None."""
    return fetch_one("SELECT id, full_name FROM candidates WHERE job_id = %s AND cv_text = %s LIMIT 1", (job_id, cv_text))


def delete_candidate(candidate_id):
    """Used only to undo a CV upload that failed halfway."""
    execute("DELETE FROM candidates WHERE id = %s", (candidate_id,))


# ---------- Where the process is ----------

def set_current_step(candidate_id, step, status):
    execute(
        "UPDATE candidates SET current_step = %s, status = %s, updated_at = NOW() WHERE id = %s",
        (step, status, candidate_id),
    )


def close_candidate(candidate_id, final_status):
    execute(
        "UPDATE candidates SET current_step = NULL, status = %s, updated_at = NOW() WHERE id = %s",
        (final_status, candidate_id),
    )


def claim_step(candidate_id, step):
    """
    Takes the step so nobody else can complete it at the same time.
    Returns False if the candidate is no longer waiting on this step (someone else already completed it).
    """
    row = execute(
        "UPDATE candidates SET current_step = NULL WHERE id = %s AND current_step = %s RETURNING id",
        (candidate_id, step),
    )
    return row is not None


def release_step(candidate_id, step):
    """Gives the step back if completing it failed, so it can be tried again."""
    execute(
        "UPDATE candidates SET current_step = %s WHERE id = %s AND current_step IS NULL",
        (step, candidate_id),
    )


# The candidate columns each step fills in. When HR goes back to a step, the columns of that step
# and every later step are emptied, because those steps are recorded again.
# (What was recorded before stays in the activity log.)
STEP_COLUMNS = {
    "approve_shortlist":    {"shortlist_decision": "NULL"},
    "contact_interviewers": {"interviewer_ids": "'{}'"},
    "schedule_m1":          {"m1_scheduled_at": "NULL", "m1_location": "NULL"},
    "m1_feedback":          {"m1_decision": "NULL", "m1_feedback_by": "NULL", "m1_comments": "NULL"},
    "schedule_m2":          {"m2_scheduled_at": "NULL", "m2_location": "NULL"},
    "m2_feedback":          {"m2_decision": "NULL", "m2_feedback_by": "NULL", "m2_comments": "NULL"},
}


def move_back(candidate_id, from_step, from_status, to_step, to_status, steps_to_redo):
    """
    Puts the candidate back on an earlier step and empties the data of the steps that will be redone.
    Only works if the candidate is still where HR saw them (from_step / from_status). Returns True if it worked.
    """
    # The extra SQL that empties the columns of the steps to redo,
    # e.g. ", m2_decision = NULL, m2_feedback_by = NULL, m2_comments = NULL"
    # (the column names and values come only from STEP_COLUMNS above, never from what a user typed)
    empty_columns_sql = ""
    for step in steps_to_redo:
        for column, value in STEP_COLUMNS.get(step, {}).items():
            empty_columns_sql += f", {column} = {value}"
    row = execute(
        f"""UPDATE candidates SET current_step = %s, status = %s, updated_at = NOW(){empty_columns_sql}
            WHERE id = %s AND current_step IS NOT DISTINCT FROM %s AND status = %s RETURNING id""",
        (to_step, to_status, candidate_id, from_step, from_status),
    )
    return row is not None


def reopen_shortlist(candidate_id):
    """Puts a 'Not shortlisted' candidate back on the shortlist step. Returns False if not possible."""
    row = execute(
        """UPDATE candidates SET current_step = 'approve_shortlist', status = 'Screening', updated_at = NOW()
           WHERE id = %s AND current_step IS NULL AND shortlist_decision = 'Not shortlisted' RETURNING id""",
        (candidate_id,),
    )
    return row is not None


# ---------- Decisions of the process (all saved on the candidate row) ----------

def save_shortlist_decision(candidate_id, decision):
    execute("UPDATE candidates SET shortlist_decision = %s, updated_at = NOW() WHERE id = %s", (decision, candidate_id))


def assign_interviewers(candidate_id, interviewer_ids):
    execute(
        "UPDATE candidates SET interviewer_ids = %s, updated_at = NOW() WHERE id = %s",
        ([int(i) for i in interviewer_ids], candidate_id),
    )


def get_assigned_interviewers(candidate_id):
    return fetch_all(
        """SELECT u.* FROM candidates c JOIN users u ON u.id = ANY(c.interviewer_ids)
           WHERE c.id = %s ORDER BY u.full_name""",
        (candidate_id,),
    )


def save_interview(candidate_id, round_name, scheduled_at, location):
    """round_name is "M1" or "M2"."""
    if round_name == "M1":
        sql = "UPDATE candidates SET m1_scheduled_at = %s, m1_location = %s, updated_at = NOW() WHERE id = %s"
    else:
        sql = "UPDATE candidates SET m2_scheduled_at = %s, m2_location = %s, updated_at = NOW() WHERE id = %s"
    execute(sql, (scheduled_at, location, candidate_id))


def save_feedback(candidate_id, round_name, given_by, decision, comments):
    """given_by = the HOD / interviewer who gave it. (The HR user who entered it is in the activity log.)"""
    if round_name == "M1":
        sql = "UPDATE candidates SET m1_decision = %s, m1_feedback_by = %s, m1_comments = %s, updated_at = NOW() WHERE id = %s"
    else:
        sql = "UPDATE candidates SET m2_decision = %s, m2_feedback_by = %s, m2_comments = %s, updated_at = NOW() WHERE id = %s"
    execute(sql, (decision, given_by, comments, candidate_id))


def get_interviews(candidate_id):
    """[{round, scheduled_at, location}] for each round that has been scheduled."""
    c = get_candidate(candidate_id)
    interviews = []
    if c and c["m1_scheduled_at"]:
        interviews.append({"round": "M1", "scheduled_at": c["m1_scheduled_at"], "location": c["m1_location"]})
    if c and c["m2_scheduled_at"]:
        interviews.append({"round": "M2", "scheduled_at": c["m2_scheduled_at"], "location": c["m2_location"]})
    return interviews


def get_feedback(candidate_id):
    """[{round, given_by, decision, comments}] for each round that has feedback."""
    c = get_candidate(candidate_id)
    feedback = []
    if c and c["m1_decision"]:
        feedback.append({"round": "M1", "given_by": c["m1_feedback_by_name"] or "Unknown",
                         "decision": c["m1_decision"], "comments": c["m1_comments"]})
    if c and c["m2_decision"]:
        feedback.append({"round": "M2", "given_by": c["m2_feedback_by_name"] or "Unknown",
                         "decision": c["m2_decision"], "comments": c["m2_comments"]})
    return feedback


# ---------- Activity log (history) ----------

def log_activity(candidate_id, step, user_id, details):
    execute(
        "INSERT INTO activity_log (candidate_id, step, user_id, details) VALUES (%s, %s, %s, %s)",
        (candidate_id, step, user_id, as_json(details)),
    )


def get_last_step_record(candidate_id, step):
    """What HR recorded for this step the last time (used to pre-fill the form when HR goes back to it), or None."""
    return fetch_one(
        """SELECT a.details, a.created_at, u.full_name AS done_by FROM activity_log a
           LEFT JOIN users u ON u.id = a.user_id
           WHERE a.candidate_id = %s AND a.step = %s ORDER BY a.created_at DESC, a.id DESC LIMIT 1""",
        (candidate_id, step),
    )


def get_activity(candidate_id):
    return fetch_all(
        """SELECT a.*, u.full_name AS done_by FROM activity_log a
           LEFT JOIN users u ON u.id = a.user_id WHERE a.candidate_id = %s ORDER BY a.created_at, a.id""",
        (candidate_id,),
    )


def activity_for_steps(steps):
    """Every history row of these steps, oldest first (for the statistics on the home page)."""
    return fetch_all(
        "SELECT candidate_id, step, details, created_at FROM activity_log WHERE step = ANY(%s) ORDER BY created_at, id",
        (list(steps),),
    )


def recent_activity(limit=8):
    """The latest actions across all candidates (for the home page)."""
    return fetch_all(
        """SELECT a.step, a.details, a.created_at, u.full_name AS done_by,
                  c.id AS candidate_id, c.full_name AS candidate, j.title AS job_title
           FROM activity_log a
           JOIN candidates c ON c.id = a.candidate_id
           JOIN jobs j ON j.id = c.job_id
           LEFT JOIN users u ON u.id = a.user_id
           ORDER BY a.created_at DESC, a.id DESC LIMIT %s""",
        (limit,),
    )
