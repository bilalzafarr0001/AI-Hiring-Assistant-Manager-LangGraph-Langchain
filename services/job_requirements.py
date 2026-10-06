"""
What a job asks for, read from its description:
- the required skills and the minimum years of experience (read ONCE per job and saved on the job as
  "screening criteria", so every CV of the job is checked against the same list), and
- the degree fields the job asks for (used for the education points).

The app reads a simple "Required skills" list itself. Only when the list is written as sentences
(or there is no such list) does it ask the AI.

Saved criteria look like this (a group with 2+ names means "any one of these is enough"):
    {"required_skills": [["NestJS"], ["TypeScript"], ["PostgreSQL", "MongoDB"]], "min_years": 3}
"""
import re

from config.word_lists import NUMBER_WORDS
from services.llm import ask_llm, read_json, to_years
from services.prompts import required_skills_prompt

MAX_SKILL_GROUPS = 30

# Headings in a job description. Each one matches a line that STARTS with these words, in any case
# (\b means the word ends there: "Requirements:" matches, "Requirementsxyz" does not):
#   "Required Skills:", "Requirements", "Must-haves", "Required: React, Node.js" ...
REQUIRED_HEADING = re.compile(r"^\s*(required skills?|requirements?|must[- ]haves?|required)\b", re.I)
#   "Nice to have:", "Preferred", "Education", "Responsibilities", "Benefits" ...  (the end of the required list)
OTHER_HEADING = re.compile(r"^\s*(nice[- ]to[- ]haves?|preferred|bonus|good to have|plus|education|qualifications|"
                           r"responsibilities|benefits|what we offer|about|perks|salary)\b", re.I)
#   "Education:", "Qualifications", "Academic" ...
EDUCATION_HEADING = re.compile(r"^\s*(education|qualifications?|academic)\b", re.I)

# A number of years: "3 years", "3+ yrs", "2.5 years", "five years"  (the number is group 1)
NUMBER = r"(\d+(?:\.\d+)?|" + "|".join(NUMBER_WORDS) + r")"
YEARS = re.compile(NUMBER + r"\s*\+?\s*(?:years?|yrs?)\b", re.I)
# A range of years: "3-5 years", "3 to 5 years"  (the MINIMUM is group 1)
YEARS_RANGE = re.compile(NUMBER + r"\s*(?:-|–|to)\s*" + NUMBER + r"\s*\+?\s*(?:years?|yrs?)\b", re.I)

# Words that are not degree fields: "a related field", "or equivalent experience"...
NOT_A_FIELD = re.compile(r"related|equivalent|similar|relevant|field|discipline|experience|accepted", re.I)


# ---------------------------------------------------------------- required skills + minimum years

def extract_screening_criteria(job_title, job_description):
    """
    Reads the job description ONCE and lists the required skills and the minimum years of experience.
    Returns {"required_skills": [[...], ...], "min_years": n}, or None if they could not be read.

    1. The app finds the 'Required skills' section. If its lines are simple skill names, the app reads them itself.
    2. Otherwise the AI reads ONLY that section (or the whole description if there is no such section).
    """
    # 1. The app reads a simple list itself.
    section = required_section(job_description)
    years = min_years_from(section or job_description.splitlines())
    if section:
        groups = simple_skill_groups(section)
        if groups:
            return clean_criteria(groups, years)

    # 2. Otherwise the AI reads the required lines (or the whole description).
    if section:
        prompt = required_skills_prompt(job_title, "\n".join(section), only_required_lines=True,
                                        max_groups=MAX_SKILL_GROUPS)
    else:
        prompt = required_skills_prompt(job_title, job_description, only_required_lines=False,
                                        max_groups=MAX_SKILL_GROUPS)
    data = read_json(ask_llm(prompt, json_mode=True))
    if not data:
        return None
    if years is None:                 # the app found no years in the text: use the AI's number
        years = data.get("min_years")
    criteria = clean_criteria(data.get("required_skills"), years)
    if criteria["required_skills"]:
        return criteria
    return None


def required_section(job_description):
    """
    The lines under the job's 'Required skills' / 'Requirements' heading (until the next heading), or None.
    Bullets ("- ", "* ", "• ") are removed. "Requirements: React, Node.js" on one line gives ["React, Node.js"].
    """
    lines = []
    inside = False
    for line in (job_description or "").splitlines():
        if REQUIRED_HEADING.match(line):
            inside = True
            if ":" in line:                                  # skills written after the colon on the same line
                after_colon = line.split(":", 1)[1].strip()
                if after_colon:
                    lines.append(after_colon)
            continue
        if inside and OTHER_HEADING.match(line):
            break
        if inside and line.strip():
            lines.append(re.sub(r"^\s*[-*•·]\s*", "", line).strip())   # remove the bullet at the start
    return lines or None


def min_years_from(lines):
    """
    The minimum years of experience written in these lines, or None.
    '3+ years' -> 3,  '3-5 years' -> 3 (the minimum),  'five years' -> 5.
    Only lines that talk about experience / years are looked at.
    """
    for line in lines:
        lower = line.lower()
        if "experience" in lower or "year" in lower or "yrs" in lower:
            match = YEARS_RANGE.search(line) or YEARS.search(line)
            if match:
                return number_from(match.group(1))
    return None


def number_from(word):
    """'3' -> 3.0, '2.5' -> 2.5, 'five' -> 5.0"""
    word = word.lower()
    if word in NUMBER_WORDS:
        return float(NUMBER_WORDS[word])
    return float(word)


def simple_skill_groups(lines):
    """
    When every required line is just skill names, the app reads them itself (no AI needed):
      'React'                          -> [React]
      'MongoDB or PostgreSQL'          -> [MongoDB / PostgreSQL]   (alternatives: any one is enough)
      'TypeORM, Prisma or Mongoose'    -> [TypeORM / Prisma / Mongoose]
      'HTML, CSS'  or  'HTML and CSS'  -> [HTML], [CSS]            (both are needed)
    Lines about years ('3+ years of experience') are skipped: they give the minimum years instead.
    Returns the groups, or None if some line is a full sentence (more than 4 words per skill): then the AI reads them.
    """
    groups = []
    for line in lines:
        if YEARS.search(line):
            continue
        line = re.sub(r"\(.*?\)", "", line).strip(" .;:")              # remove "(...)"

        if re.search(r"\s+or\s+|\s+and/or\s+|\s+/\s+", line):
            # "X or Y", "X and/or Y", "X / Y" are alternatives: ONE group with all the names
            line_groups = [re.split(r"\s+and/or\s+|\s+or\s+|\s+/\s+|,", line)]
        else:
            # "X, Y", "X and Y", "X & Y": each skill is needed, so one group PER name
            line_groups = []
            for name in re.split(r",|\s+and\s+|\s+&\s+", line):
                line_groups.append([name])

        for group in line_groups:
            names = []
            for name in group:
                name = name.strip(" .;:")
                if name:
                    names.append(name)
            if not names:
                continue
            for name in names:
                if len(name.split()) > 4:     # a full sentence, not a skill name: let the AI read the list
                    return None
            groups.append(names)
    return groups or None


def clean_criteria(skills, min_years):
    """
    Tidies a criteria list (from the app, the AI, or HR's edit box):
    removes empty names and repeated groups, keeps at most 30 groups, and turns the years into a number.
    """
    groups = []
    for group in skills or []:
        if isinstance(group, str):
            group = [group]
        if not isinstance(group, list):
            continue
        names = []
        for name in group:
            name = str(name).strip()
            if name:
                names.append(name)
        if names and names not in groups:
            groups.append(names)
    years = to_years(min_years)
    return {"required_skills": groups[:MAX_SKILL_GROUPS], "min_years": years or 0}


# ---------------------------------------------------------------- degree fields

def education_fields(job_description):
    """
    The degree fields the job asks for, read from its Education section, e.g.
    "Bachelor's degree in Computer Science, Software Engineering or a related field"
        -> ["computer science", "software engineering"]
    Returns [] if the job does not name any field.
    """
    # 1. The lines under the "Education" heading (until the next heading).
    lines = []
    inside = False
    for line in (job_description or "").splitlines():
        if EDUCATION_HEADING.match(line):
            inside = True
            continue
        if inside and (OTHER_HEADING.match(line) or REQUIRED_HEADING.match(line)):
            break
        if inside and line.strip():
            lines.append(line)

    # 2. The field names written after "in": split at commas, "or", "and" and "/".
    fields = []
    for line in lines:
        line = re.sub(r"\(.*?\)", "", line)                  # remove "(...)"
        match = re.search(r"\bin\s+(.+)", line, re.I)        # everything after the word "in"
        if not match:
            continue
        for part in re.split(r",|\s+or\s+|\s+and\s+|/", match.group(1)):
            part = part.strip(" .;").lower()
            part = re.sub(r"^(a|an|the)\s+", "", part)       # "a related field" -> "related field"
            if part and not NOT_A_FIELD.search(part) and len(part.split()) <= 4 and part not in fields:
                fields.append(part)
    return fields
