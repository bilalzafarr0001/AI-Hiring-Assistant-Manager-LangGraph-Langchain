"""
Checks the app makes on a CV's text by itself (no AI):
- check_skills()         which of the job's required skills the CV mentions (anywhere in the CV)
- cv_stated_years()      the total years of experience the CV itself states ("4 years experience")
- cv_work_years()        the years the job dates in the CV's Experience section add up to ("Mar 2026 - May 2026")
- has_required_degree()  whether the CV shows a degree in one of the job's fields ("BS Computer Science", "BSCS")
"""
import re
from datetime import date

from config.word_lists import DEGREE_FIELD_ALIASES, FILLER_WORDS, RISKY_WORDS, SKILL_ALIASES

# A name followed by these words is a DIFFERENT skill: "React Native" is not "React", "Java Script" is not "Java".
NOT_FOLLOWED_BY = {"react": r"(?!\s*native)", "java": r"(?!\s*script)"}

# A total written in the CV: "4 years experience", "04 Years' Experience", "3+ years of professional experience"
STATED_YEARS = re.compile(r"(\d+(?:\.\d+)?)\s*\+?\s*years?['’]?\s*(?:of\s+)?(?:total\s+|professional\s+|work\s+|"
                          r"industry\s+|hands-on\s+)?(?:work\s+)?experience", re.I)

# The heading of the work history: "Experience", "Work Experience", "Professional Experience", "Employment History"...
# Alone on its line, or followed by ":" and text ("Experience: Software Engineer, XYZ (2021 - 2025)").
WORK_HEADING = (r"(?:work\s+|professional\s+|employment\s+|relevant\s+|industry\s+)?"
                r"(?:experience|employment(?:\s+history)?|work\s+history|career\s+history)")
EXPERIENCE_HEADING = re.compile(rf"^\s*{WORK_HEADING}\s*(?::\s*(.*))?$", re.I)
# Headings that end the work history: "Projects", "Education", "Skills", "Certifications"...
OTHER_CV_HEADING = re.compile(r"^\s*(?:personal\s+|academic\s+|key\s+|technical\s+|side\s+)?"
                              r"(?:projects?|education|skills|certifications?|courses|awards|achievements|languages|"
                              r"interests|hobbies|references|publications|summary|profile|objective|training)\s*(?::.*)?$",
                              re.I)
# One date: "Mar 2026", "March 2026", "Sept. 2021", "03/2026", "2026"
MONTHS = r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
ONE_DATE = rf"(?:(?:{MONTHS})\.?\s*,?\s*\d{{4}}|\d{{1,2}}[/.-]\d{{4}}|\b\d{{4}}\b)"
# A date range: "Mar 2026 – May 2026", "2021 - 2025", "Jul 2026 – Present", "03/2020 to 06/2022"
DATE_RANGE = re.compile(rf"({ONE_DATE})\s*(?:-|–|—|to|until|till)\s*({ONE_DATE}|present|current|now|today|ongoing|date)",
                        re.I)

# Words that mean "a degree": bachelor's, master, BS, BSc, MS, MBA, PhD, graduate...
DEGREE_WORDS = r"(?:bachelor'?s?|bachelors|master'?s?|masters|degree|bs|bsc|b\.sc|ba|be|b\.e|ms|msc|m\.sc|ma|mba|phd|graduate)"


# ---------------------------------------------------------------- skills

def check_skills(cv_text, required_skills):
    """
    Searches the WHOLE CV (skills section, experience, projects...) for each required skill group.
    A group counts as found when ANY of its names is mentioned, in any of the ways it can be written.
    Returns (found, missing) as labels, e.g. (["NestJS", "PostgreSQL / MongoDB"], ["Docker"]).
    """
    text = re.sub(r"\s+", " ", (cv_text or "").lower())
    found = []
    missing = []
    for group in required_skills:
        label = " / ".join(group)
        if group_is_mentioned(text, group):
            found.append(label)
        else:
            missing.append(label)
    return found, missing


def group_is_mentioned(text, group):
    """True if ANY skill of the group is in the CV text, written in any of its ways (e.g. "PostgreSQL" or "postgres")."""
    for skill in group:
        for variant in skill_variants(skill):
            if is_mentioned(text, variant):
                return True
    return False


def skill_variants(skill):
    """
    All the ways a skill may be written on a CV (lower case), e.g.
      "Node.js"                    -> node.js, nodejs, node js, node
      "Authentication (JWT, RBAC)" -> authentication, auth0, oauth, ... and also jwt, rbac (the skills in brackets)
    """
    text = skill.lower().strip()
    in_brackets = re.findall(r"\((.*?)\)", text)                    # "authentication (jwt, rbac)" -> ["jwt, rbac"]
    text = re.sub(r"\(.*?\)", " ", text)                            # remove the brackets from the name

    # Remove filler words: "strong typescript knowledge" -> "typescript"
    words = []
    for word in text.split():
        if word not in FILLER_WORDS:
            words.append(word)
    text = " ".join(words).strip()

    variants = set()
    if text:
        variants.update(spellings(text))
        variants.update(SKILL_ALIASES.get(alias_key(text), []))
    for bracket_text in in_brackets:                               # the skills in brackets count too
        for piece in re.split(r",|/|\bor\b|\band\b", bracket_text):
            if piece.strip():
                variants.update(skill_variants(piece.strip()))

    # Risky everyday words ("rest", "go"...) are replaced by their safe forms ("rest api", "golang"...).
    # One-letter names are kept only when the skill itself is one letter ("C").
    safe = set()
    for variant in variants:
        variant = variant.strip()
        if variant in RISKY_WORDS:
            safe.update(RISKY_WORDS[variant])
        elif len(variant) >= 2 or variant == text:
            safe.add(variant)
    return safe


def spellings(text):
    """Common spellings of the same name: 'node.js' -> node.js, nodejs, node js;  'nextjs' -> next.js, next js"""
    forms = {text, text.replace(" ", ""), text.replace(".", ""), text.replace(".", " "), text.replace("-", " ")}
    if text.endswith(".js"):                    # "node.js" -> also "nodejs" and "node js"
        root = text[:-3]
        forms.add(root + "js")
        forms.add(root + " js")
    elif text.endswith("js") and len(text) > 4:  # "nextjs" -> also "next.js" and "next js"
        root = text[:-2].rstrip(". ")
        forms.add(root + ".js")
        forms.add(root + " js")
    return forms


def alias_key(text):
    """The key used in SKILL_ALIASES: lower case without spaces, dots, dashes, '_' or '/'.  'Node.js' -> 'nodejs'"""
    return re.sub(r"[\s._\-/]", "", text.lower())


def is_mentioned(text, variant):
    """
    True if the variant appears in the CV text as a whole name, not inside another word:
    "java" is not found in "javascript", "c" is not found in "c++" or "c#", "nx" is not found in "nx-ops-t-02".
    """
    if len(variant) <= 3:
        edge = r"a-z0-9\-_./+#"      # very short names must stand alone (no letter, digit or - _ . / + # around them)
    else:
        edge = r"a-z0-9"             # longer names: no letter or digit around them
    # The search pattern is built from 4 parts:
    nothing_before = rf"(?<![{edge}])"                      # 1. none of the edge characters just before the name
    name = re.escape(variant)                               # 2. the name itself ("node.js": the dot is a real dot)
    nothing_after = rf"(?![{edge}])"                        # 3. none of the edge characters just after the name
    not_followed_by = NOT_FOLLOWED_BY.get(variant, "")      # 4. "react" must not be followed by "native"
    pattern = nothing_before + name + nothing_after + not_followed_by
    return re.search(pattern, text) is not None


# ---------------------------------------------------------------- years

def cv_stated_years(cv_text):
    """The total years of experience the CV itself states (e.g. "04 Years' Experience" -> 4), or None."""
    values = []
    for match in STATED_YEARS.finditer(cv_text or ""):
        value = float(match.group(1))
        if 0 < value <= 50:
            values.append(value)
    if values:
        return max(values)
    return None


def cv_work_years(cv_text, today=None):
    """
    The years the job dates in the CV's Experience section add up to, or None if the CV has no dated work history.
      "Jul 2026 – Present" + "Mar 2026 – May 2026"  ->  0.6 years (4 + 3 months)
    Only the Experience section counts: university dates ("Feb 2022 – Jan 2026" under Education) and project dates
    are not work. Jobs at the same time are counted once.
    """
    today = today or date.today()
    this_month = today.year * 12 + today.month - 1            # months counted from year 0, e.g. Oct 2026 -> 24321
    periods = []
    for line in experience_lines(cv_text):
        for match in DATE_RANGE.finditer(line):
            start = month_number(match.group(1), is_end=False, this_month=this_month)
            end = month_number(match.group(2), is_end=True, this_month=this_month)
            if start is None or end is None or start > end or start > this_month:
                continue
            periods.append([start, min(end, this_month)])
    if not periods:
        return None

    # Add up the months; overlapping jobs count once: [Jan-Jun] + [Mar-Sep] = Jan-Sep = 9 months
    periods.sort()
    merged = [periods[0]]
    for start, end in periods[1:]:
        if start <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    months = sum(end - start + 1 for start, end in merged)
    return round(months / 12, 1)


def experience_lines(cv_text):
    """The lines of the CV's Experience section: from its heading until the next heading (Projects, Education...)."""
    lines = []
    inside = False
    for line in (cv_text or "").splitlines():
        heading = EXPERIENCE_HEADING.match(line)
        if heading:
            inside = True
            if heading.group(1):                                # "Experience: Software Engineer (2021 - 2025)"
                lines.append(heading.group(1))
            continue
        if inside and OTHER_CV_HEADING.match(line):
            inside = False
            continue
        if inside:
            lines.append(line)
    return lines


def month_number(text, is_end, this_month):
    """
    A date as a month count (year * 12 + month - 1), or None if it is not a real date.
    "Present" -> this month.  A year alone: the start of a job counts from January, the end counts up to December
    (so "2021 - 2025" can never count fewer months than the person really worked).
    """
    text = text.strip().lower()
    if text in ("present", "current", "now", "today", "ongoing", "date"):
        return this_month
    month = None
    with_name = re.match(rf"({MONTHS})\.?\s*,?\s*(\d{{4}})", text)
    with_number = re.match(r"(\d{1,2})[/.-](\d{4})", text)
    if with_name:
        month = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"].index(with_name.group(1)[:3]) + 1
        year = int(with_name.group(2))
    elif with_number:
        month = int(with_number.group(1))
        year = int(with_number.group(2))
    else:
        year = int(text)
    if month is None:
        month = 12 if is_end else 1
    if not (1 <= month <= 12) or not (1970 <= year <= this_month // 12 + 1):
        return None
    return year * 12 + month - 1


# ---------------------------------------------------------------- degree

def has_required_degree(cv_text, fields):
    """
    True when the CV shows a degree in one of the job's fields, e.g. for "computer science":
    "BS Computer Science", "Bachelor's degree in Computer Science", or a short form like "BSCS".
    """
    # PDFs sometimes glue words together: "Computer ScienceFeb 2022" -> "Computer Science Feb 2022"
    # (a small letter followed directly by a capital letter). Only done here: "JavaScript" must stay one word for skills.
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", cv_text or "")
    text = re.sub(r"\s+", " ", text.lower())
    for field in fields:
        # 1. a short form of the degree: "bscs", "bs(cs)", "bs se"...
        for short_form in DEGREE_FIELD_ALIASES.get(field, []):
            if re.search(r"(?<![a-z0-9])" + re.escape(short_form) + r"(?![a-z0-9])", text):
                return True
        # 2. the field name with a degree word just before it (within 60 characters): "bs computer science"
        for match in re.finditer(r"(?<![a-z0-9])" + re.escape(field) + r"(?![a-z0-9])", text):
            just_before = text[max(0, match.start() - 60):match.start()]
            if re.search(r"(?<![a-z])" + DEGREE_WORDS + r"(?![a-z])", just_before):
                return True
    return False
