-- Moves data from the tables used by older versions of this app into the 5-table design.
-- setup_db.py runs this ONLY if the old tables still exist, inside one transaction,
-- and then removes the old tables.

-- Interviewers assigned by the HOD -> candidates.interviewer_ids
UPDATE candidates c
SET interviewer_ids = ci.ids
FROM (SELECT candidate_id, array_agg(user_id ORDER BY user_id) AS ids
      FROM candidate_interviewers GROUP BY candidate_id) ci
WHERE ci.candidate_id = c.id;

-- Interview schedules -> candidates.m1_* / m2_* (the latest schedule of each round)
UPDATE candidates c
SET m1_scheduled_at = i.scheduled_at, m1_location = i.location
FROM (SELECT DISTINCT ON (candidate_id) candidate_id, scheduled_at, location
      FROM interviews WHERE round = 'M1' ORDER BY candidate_id, created_at DESC) i
WHERE i.candidate_id = c.id;

UPDATE candidates c
SET m2_scheduled_at = i.scheduled_at, m2_location = i.location
FROM (SELECT DISTINCT ON (candidate_id) candidate_id, scheduled_at, location
      FROM interviews WHERE round = 'M2' ORDER BY candidate_id, created_at DESC) i
WHERE i.candidate_id = c.id;

-- Feedback -> candidates.m1_* / m2_* (the first M1 feedback is the one that moved the process forward)
UPDATE candidates c
SET m1_decision = f.decision, m1_feedback_by = f.user_id, m1_comments = f.comments
FROM (SELECT DISTINCT ON (candidate_id) candidate_id, decision, user_id, comments
      FROM feedback WHERE round = 'M1' AND decision IN ('Selected', 'Unselected')
      ORDER BY candidate_id, created_at) f
WHERE f.candidate_id = c.id;

UPDATE candidates c
SET m2_decision = f.decision, m2_feedback_by = f.user_id, m2_comments = f.comments
FROM (SELECT DISTINCT ON (candidate_id) candidate_id, decision, user_id, comments
      FROM feedback WHERE round = 'M2' AND decision IN ('Selected', 'Rejected')
      ORDER BY candidate_id, created_at DESC) f
WHERE f.candidate_id = c.id;

-- Shortlist decision (older versions kept it only inside LangGraph's own tables)
UPDATE candidates
SET shortlist_decision = CASE
        WHEN status = 'Closed - Not shortlisted' THEN 'Not shortlisted'
        ELSE 'Shortlisted'
    END
WHERE shortlist_decision IS NULL
  AND current_step IS DISTINCT FROM 'approve_shortlist'
  AND NOT (current_step IS NULL AND status = 'Screening');
