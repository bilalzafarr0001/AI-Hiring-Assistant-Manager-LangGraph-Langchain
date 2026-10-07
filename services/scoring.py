"""
The CV score (0-100). rank_cv() is the function the Jobs page calls for every uploaded CV.

    Skills      40   the app looks for each required skill of the job in the whole CV     (services/cv_checks.py)
    Experience  30   30 x (candidate's relevant years / job's minimum years)              (years read by the AI)
    Role fit    15   the AI judges it, with fixed levels                                  (services/prompts.py)
    Education   15   the AI judges it; 15 when the CV has a degree in a field the job names

The AI only reads the CV and gives numbers. The app checks those numbers and adds up the score.

Main skills: the skills the job is really about (from the job title, e.g. Python for "Python Developer").
They do not change the score, but a CV without them is never shortlisted automatically (see auto_shortlist()).
"""
from services.cv_checks import check_skills, cv_stated_years, has_required_degree
from services.job_requirements import education_fields, main_skills_of
from services.llm import AI_UNAVAILABLE, ask_llm, read_json, to_points, to_years
from services.prompts import scoring_prompt

MAX_SKILLS = 40
MAX_EXPERIENCE = 30
MAX_ROLE_FIT = 15
MAX_EDUCATION = 15
DEFAULT_REQUIRED_YEARS = 2   # used when the job does not say how many years it needs


def rank_cv(job_title, job_description, cv_text, criteria=None):
    """
    Scores one CV against one job.
    criteria = the job's saved screening criteria ({"required_skills": [...], "min_years": n, "main_skills": [...]}),
    or None.
    Returns {name, email, score (0-100, or None if the AI could not score), reason, breakdown, matched, missing,
    main_missing (the main skills NOT in the CV: if any, the CV is not shortlisted automatically)}.
    """
    result = {"name": "", "email": "", "score": None, "reason": AI_UNAVAILABLE,
              "breakdown": {}, "matched": [], "missing": [], "main_missing": []}
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
    years = to_years(data.get("relevant_experience_years"))
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
    stated = cv_stated_years(cv_text)
    if stated is not None and years > stated:   # the AI may never claim more years than the CV itself states
        years = stated
    fields = education_fields(job_description)
    degree_found = bool(fields) and has_required_degree(cv_text, fields)
    if degree_found:                            # a degree in a field the job names: full education points
        education = MAX_EDUCATION

    # Step 6: add up the four parts.
    breakdown = {"skills": skills, "experience": experience_points(years, required_years),
                 "role_fit": role_fit, "education": education}
    score = sum(breakdown.values())
    reason = write_reason(data, breakdown, how, matched, not_found, years, required_years, degree_found, fields,
                          main_found, main_missing)

    result.update({
        "name": str(data.get("name", "")).strip(),
        "email": str(data.get("email", "")).strip(),
        "score": score, "reason": reason, "breakdown": breakdown, "matched": matched, "missing": not_found,
    })
    return result


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
                 main_found, main_missing):
    """The text HR reads under the score: the AI's summary, then how each part was scored."""
    reason = str(data.get("summary", "")).strip() or "No summary given."
    if main_missing:
        reason += (f"\nMAIN SKILL MISSING: {', '.join(main_missing)}. "
                   f"Not shortlisted automatically, whatever the score.")
    elif main_found:
        reason += f"\nMain skills found: {', '.join(main_found)}."
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
    reason += f"\nExperience: {years:g} relevant year(s), {asked}."
    if degree_found:
        reason += f"\nEducation: degree in a required field found ({', '.join(fields)})."
    return reason
