"""
The CV score (0-100). rank_cv() is the function the Jobs page calls for every uploaded CV.

    Skills      40   the app looks for each required skill of the job in the whole CV     (services/cv_checks.py)
    Experience  30   30 x (candidate's relevant years / job's minimum years)              (the AI copies each job's
                     dates from the CV and says if the job was relevant; the APP adds up the months)
    Role fit    15   the AI judges it, with fixed levels                                  (services/prompts.py)
    Education   15   the AI judges it; 15 when the CV has a degree in a field the job names

The AI only reads the CV and gives numbers. The app checks those numbers and adds up the score.

Two rules stop a CV from being shortlisted automatically, whatever its score (see auto_shortlist()):
- a main skill is missing: the skills the job is really about (from the job title, e.g. Python for "Python Developer")
- too few years: less than 3/4 of the job's minimum years (e.g. under 2.25 years for a "3+ years" job)
HR can still shortlist such a CV with "Shortlist anyway".
"""
import re
from datetime import date

from services.cv_checks import check_skills, cv_stated_years, cv_work_years, has_required_degree, month_number, years_of
from services.job_requirements import education_fields, main_skills_of
from services.llm import AI_UNAVAILABLE, ask_llm, read_json, to_points, to_years
from services.prompts import scoring_prompt

MAX_SKILLS = 40
MAX_EXPERIENCE = 30
MAX_ROLE_FIT = 15
MAX_EDUCATION = 15
DEFAULT_REQUIRED_YEARS = 2   # used when the job does not say how many years it needs
MIN_YEARS_SHARE = 0.75       # fewer relevant years than 3/4 of the job's minimum: not shortlisted automatically
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def rank_cv(job_title, job_description, cv_text, criteria=None):
    """
    Scores one CV against one job.
    criteria = the job's saved screening criteria ({"required_skills": [...], "min_years": n, "main_skills": [...]}),
    or None.
    Returns {name, email, score (0-100, or None if the AI could not score), reason, breakdown, matched, missing,
    main_missing (the main skills NOT in the CV), too_few_years (e.g. "0.7 of 3+ years", or "")}.
    If main_missing or too_few_years is set, the CV is not shortlisted automatically.
    """
    result = {"name": "", "email": email_in(cv_text), "score": None, "reason": AI_UNAVAILABLE,
              "breakdown": {}, "matched": [], "missing": [], "main_missing": [], "too_few_years": ""}
    criteria = criteria or {}
    skill_groups = criteria.get("required_skills") or []
    min_years = criteria.get("min_years")

    # Step 1: the app checks which required skills, and which main skills, the CV mentions.
    if skill_groups:
        found, missing = check_skills(cv_text, skill_groups)
        main_found, main_missing = check_skills(cv_text, main_skills_of(job_title, criteria))
    else:
        found, missing = [], []
        main_found, main_missing = [], []
    result["main_missing"] = main_missing

    # Step 2: the AI reads the CV once.
    prompt = scoring_prompt(job_title, job_description, cv_text, has_skill_list=bool(skill_groups),
                            found=found, missing=missing, min_years=min_years)
    answer = ask_llm(prompt, json_mode=True)
    if not answer:
        return result                    # the AI is not available: no score, HR reviews the CV
    data = read_json(answer)
    if not data:
        result["reason"] = "The AI gave an answer that could not be read. Please review this CV manually."
        return result

    # Step 3: the AI's numbers, kept inside their limits.
    role_fit = to_points(data.get("role_fit"), MAX_ROLE_FIT)
    education = to_points(data.get("education"), MAX_EDUCATION)
    years, years_note = relevant_years(data, cv_text)
    required_years = min_years or to_years(data.get("required_experience_years"))

    # Step 4: the skills points.
    if skill_groups:
        skills = round(MAX_SKILLS * len(found) / len(skill_groups))
        matched = found
        not_found = missing
        how = f"{len(found)} of {len(skill_groups)} required skills found in the CV"
    else:                                # the job has no saved skills list: the AI judged the skills
        skills = to_points(data.get("skills"), MAX_SKILLS)
        matched = names_from(data.get("matched_skills"))
        not_found = names_from(data.get("missing_skills"))
        how = "skills judged by the AI"

    if None in (role_fit, education, years, skills):
        result["reason"] = "The AI did not score every part of the CV. Please review this CV manually."
        return result

    # Step 5: the app's own rules.
    fields = education_fields(job_description)
    degree_found = bool(fields) and has_required_degree(cv_text, fields)
    if degree_found:                            # a degree in a field the job names: full education points
        education = MAX_EDUCATION
    if required_years and years < MIN_YEARS_SHARE * required_years:
        result["too_few_years"] = f"{years:g} of {required_years:g}+ years"

    # Step 6: add up the four parts.
    breakdown = {"skills": skills, "experience": experience_points(years, required_years),
                 "role_fit": role_fit, "education": education}
    score = sum(breakdown.values())
    reason = write_reason(data, breakdown, how, matched, not_found, years, required_years, degree_found, fields,
                          main_found, main_missing, years_note, result["too_few_years"])

    name = str(data.get("name", "")).strip()
    if name.isupper():                          # "HAMZA IQBAL" -> "Hamza Iqbal"
        name = name.title()
    result.update({
        "name": name,
        "score": score, "reason": reason, "breakdown": breakdown, "matched": matched, "missing": not_found,
    })
    return result


def email_in(cv_text):
    """The first email address written in the CV, or "" (read by the app: exact, wherever it is in the CV)."""
    match = EMAIL.search(cv_text or "")
    if match:
        return match.group(0).strip(".")
    return ""


def relevant_years(data, cv_text):
    """
    The candidate's relevant years of experience, and a note for HR on how they were counted.
    1. The AI copied every job with its dates and said if it was relevant. The app adds up the months of the
       relevant jobs (jobs at the same time count once). A job whose years are not written in the CV is skipped,
       so a date the AI invented never counts.
    2. If the CV gives no job dates: the AI's total, but never more than the CV itself states ("4 years experience"),
       nor more than the dates in its Experience section add up to.
    Returns (years, note), or (None, "") if the AI gave no number.
    """
    today = date.today()
    this_month = today.year * 12 + today.month - 1
    dated_jobs = 0
    relevant = []
    jobs = data.get("jobs")
    if not isinstance(jobs, list):
        jobs = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        start = month_number(str(job.get("start") or ""), is_end=False, this_month=this_month)
        end = month_number(str(job.get("end") or ""), is_end=True, this_month=this_month)
        if start is None or end is None:
            continue
        end = min(end, this_month)
        if start > end or not year_in_cv(start, cv_text):
            continue
        if end < this_month - 1 and not year_in_cv(end, cv_text):      # an end date that is not in the CV
            continue
        dated_jobs += 1
        if str(job.get("relevant")).lower() == "true":
            relevant.append([start, end])
    if dated_jobs:
        return years_of(relevant) or 0.0, " (added up from the job dates in the CV)"

    years = to_years(data.get("relevant_experience_years"))
    if years is None:
        return None, ""
    note = ""
    stated = cv_stated_years(cv_text)
    if stated is not None and years > stated:   # the AI may never claim more years than the CV itself states
        years = stated
    worked = cv_work_years(cv_text)
    if worked is not None and years > worked:   # ... nor more than the job dates in the CV add up to
        years = worked
        note = " (counted from the job dates in the CV)"
    return years, note


def year_in_cv(month, cv_text):
    """True if the year of this month number is written in the CV: as "2021", or as "'21" ("Jan '21")."""
    year = month // 12
    return re.search(rf"(?<!\d){year}(?!\d)|['’]{year % 100:02d}(?!\d)", cv_text or "") is not None


def experience_points(years, required_years):
    """30 points when the candidate has at least the required years, less in proportion when they have fewer."""
    if required_years and required_years > 0:
        required = required_years
    else:
        required = DEFAULT_REQUIRED_YEARS
    return round(MAX_EXPERIENCE * min(years / required, 1.0))


def names_from(value):
    """The AI's list of skill names, without empty ones: ["React", " ", "Node"] -> ["React", "Node"]"""
    return [str(name).strip() for name in value or [] if str(name).strip()]


def write_reason(data, breakdown, how, matched, not_found, years, required_years, degree_found, fields,
                 main_found, main_missing, years_note, too_few_years):
    """The text HR reads under the score: the AI's summary, then how each part was scored."""
    reason = str(data.get("summary", "")).strip() or "No summary given."
    if main_missing:
        reason += (f"\nMAIN SKILL MISSING: {', '.join(main_missing)}. "
                   f"Not shortlisted automatically, whatever the score.")
    elif main_found:
        reason += f"\nMain skills found: {', '.join(main_found)}."
    if too_few_years:
        reason += (f"\nTOO LITTLE EXPERIENCE: {too_few_years} (less than 3/4 of the job's minimum). "
                   f"Not shortlisted automatically, whatever the score.")
    reason += (f"\nScore: Skills {breakdown['skills']}/{MAX_SKILLS}, Experience {breakdown['experience']}/{MAX_EXPERIENCE}, "
               f"Role Fit {breakdown['role_fit']}/{MAX_ROLE_FIT}, Education {breakdown['education']}/{MAX_EDUCATION}.")
    reason += f"\nSkills: {how}."
    if matched:
        reason += f"\nFound: {', '.join(matched)}."
    if not_found:
        reason += f"\nNot found: {', '.join(not_found)}."
    if required_years:
        asked = f"{required_years:g}+ required"
    else:
        asked = f"no minimum stated, {DEFAULT_REQUIRED_YEARS}+ assumed"
    reason += f"\nExperience: {years:g} relevant year(s){years_note}, {asked}."
    if degree_found:
        reason += f"\nEducation: degree in a required field found ({', '.join(fields)})."
    return reason
