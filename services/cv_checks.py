"""
Checks the app makes on a CV's text by itself (no AI):
- check_skills()         which of the job's required skills the CV mentions (anywhere in the CV)
- cv_stated_years()      the total years of experience the CV itself states ("4 years experience")
- cv_work_years()        the years the job dates in the CV's Experience section add up to ("Mar 2026 - May 2026")
- has_required_degree()  whether the CV shows a degree in one of the job's fields ("BS Computer Science", "BSCS")
"""
import re
from datetime import date

from config.word_lists import DEGREE_FIELD_ALIASES, FILLER_WORDS, RISKY_WORDS, SHOWN_BY, SKILL_ALIASES

# A name followed by these words is a DIFFERENT skill: "React Native" is not "React", "Java Script" is not "Java".
NOT_FOLLOWED_BY = {"react": r"(?!\s*native)", "java": r"(?!\s*script)"}

# A total written in the CV: "4 years experience", "04 Years' Experience", "3+ years of professional experience",
# "Total Experience: 4.5 Years", "experience of over 6 years"
STATED_YEARS = [
    re.compile(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)['’]?\s*(?:of\s+)?(?:total\s+|professional\s+|work\s+|"
               r"industry\s+|hands-on\s+)?(?:work\s+)?experience", re.I),
    re.compile(r"experience\s*(?:of|:|-|–)?\s*(?:about|over|around|nearly|almost|more\s+than)?\s*"
               r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\b", re.I),
]

# The heading of the work history: "Experience", "Work Experience", "Professional Experience", "Employment History",
# "Career History", "Where I've worked"... Alone on its line (bullets, "##" or lines around it are fine),
# or followed by ":" and text ("Experience: Software Engineer, XYZ (2021 - 2025)").
WORK_HEADING = (r"(?:work\s+|professional\s+|employment\s+|relevant\s+|industry\s+|job\s+)?"
                r"(?:experiences?|employment(?:\s+history)?|work\s+history|career\s+history|professional\s+background|"
                r"where\s+i['’]?ve\s+worked|internships?)")
EXPERIENCE_HEADING = re.compile(rf"^[^\w]*{WORK_HEADING}\s*(?::\s*(.*)|[^\w:]*)$", re.I)
# Headings that end the work history: "Projects", "Education", "Skills", "Academic Qualification", "Education & Training"...
OTHER_CV_HEADING = re.compile(r"^[^\w]*(?:personal\s+|academic\s+|key\s+|technical\s+|side\s+|professional\s+|core\s+)?"
                              r"(?:projects?|education|skills|certifications?|courses|awards|achievements|languages|"
                              r"interests|hobbies|references|publications|summary|profile|objective|training|"
                              r"qualifications?|school|information|declaration|volunteering)"
                              r"(?:\s*(?:&|and|/)\s*[a-z ]+)?\s*(?::.*|[^\w:]*)$", re.I)
# One date: "Mar 2026", "March 2026", "Sept. 2021", "Mar-2026", "Jan '21", "03/2026", "2026-03", "2026"
MONTHS = r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
ONE_DATE = (rf"(?:(?:{MONTHS})\.?[\s,\-']*(?:\d{{4}}|'\d{{2}}\b)|\d{{1,2}}[/.-]\d{{4}}|\d{{4}}[/.-]\d{{1,2}}(?!\d)|"
            rf"\b\d{{4}}\b)")
# The words that mean "until today"
NOW_WORDS = r"present|current|now|today|ongoing|till\s+date|till\s+now|to\s+date|date"
# A date range: "Mar 2026 – May 2026", "2021 - 2025", "Jul 2026 – Present", "03/2020 to 06/2022", "Apr-2022 to Till Date"
DATE_RANGE = re.compile(rf"({ONE_DATE})\s*(?:-|–|—|to|until|till)\s*({ONE_DATE}|{NOW_WORDS})", re.I)
# A job that is still going on, without an end date: "Since 02/2024", "since March 2021"
SINCE_DATE = re.compile(rf"\bsince\s+({ONE_DATE})", re.I)

# Words that mean "a degree": bachelor's, master, BS, B.S., BSc, MS, MBA, PhD, B.Tech, graduate...
DEGREE_WORDS = (r"(?:bachelor'?s?|bachelors|master'?s?|masters|degree|bs|b\.s\.?|bsc|b\.sc|ba|be|b\.e|b\.?tech|b\.?eng|"
                r"ms|m\.s\.?|msc|m\.sc|ma|mba|m\.?tech|m\.?phil|phd|graduate)")


# ---------------------------------------------------------------- skills

def check_skills(cv_text, required_skills):
    """
    Searches the WHOLE CV (skills section, experience, projects...) for each required skill group.
    A group counts as found when ANY of its names is mentioned, in any of the ways it can be written.
    A skill also counts when a framework built on it is in the CV ("NestJS" shows Node.js, see SHOWN_BY).
    Returns (found, missing) as labels, e.g. (["NestJS", "PostgreSQL / MongoDB"], ["Docker"]).
    """
    text = searchable_text(cv_text)
    found = []
    missing = []
    for group in required_skills:
        label = " / ".join(group)
        if group_is_mentioned(text, group) or group_is_shown(text, group):
            found.append(label)
        else:
            missing.append(label)
    return found, missing


def searchable_text(cv_text):
    """
    The CV text the skills are searched in: lower case, single spaces, after two fixes:
    - "REST" written in capitals is the skill REST API ("Django REST Framework", "Flask (REST)").
      In small letters "rest" is an everyday word, so it is not searched for.
    - words a PDF glued together are ALSO searched split: "SkillsPython" -> "Skills Python".
      Only a capital followed by small letters starts a new word, so "NoSQL" and "MongoDB" stay whole.
    """
    text = re.sub(r"\bREST\b", "REST API", cv_text or "")
    split_text = re.sub(r"([a-z])([A-Z][a-z])", r"\1 \2", text)
    return re.sub(r"\s+", " ", (text + "\n" + split_text).lower())


def group_is_shown(text, group):
    """True if the CV names a framework that proves one of the group's skills: "NestJS" proves "Node.js"."""
    for skill in group:
        words = [word for word in skill.lower().split() if word not in FILLER_WORDS]
        for framework in SHOWN_BY.get(alias_key(" ".join(words)), []):
            if is_mentioned(text, framework):
                return True
    return False


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
        # very short names must stand alone: no letter, digit or - _ . / + # around them.
        # A full stop after the name is fine at the end of a sentence ("Docker, Git."), not inside a name ("nx.ops").
        before = r"(?<![a-z0-9\-_./+#])"
        after = r"(?![a-z0-9\-_/+#])(?!\.[a-z0-9])"
    else:
        before = r"(?<![a-z0-9])"    # longer names: no letter or digit around them
        after = r"(?![a-z0-9])"
    # The search pattern is built from 4 parts:
    nothing_before = before                                 # 1. none of the edge characters just before the name
    name = re.escape(variant)                               # 2. the name itself ("node.js": the dot is a real dot)
    nothing_after = after                                   # 3. none of the edge characters just after the name
    not_followed_by = NOT_FOLLOWED_BY.get(variant, "")      # 4. "react" must not be followed by "native"
    pattern = nothing_before + name + nothing_after + not_followed_by
    return re.search(pattern, text) is not None


# ---------------------------------------------------------------- years

def cv_stated_years(cv_text):
    """The total years of experience the CV itself states (e.g. "04 Years' Experience" -> 4), or None."""
    values = []
    for pattern in STATED_YEARS:
        for match in pattern.finditer(cv_text or ""):
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
        for match in SINCE_DATE.finditer(line):                 # "Since 02/2024": until today
            start = month_number(match.group(1), is_end=False, this_month=this_month)
            if start is not None and start <= this_month:
                periods.append([start, this_month])
    return years_of(periods)


def years_of(periods):
    """
    The years these periods add up to (each period = [first month, last month] as month numbers), or None if there
    are none. Overlapping jobs count once: [Jan-Jun] + [Mar-Sep] = Jan-Sep = 9 months = 0.8 years.
    """
    if not periods:
        return None
    periods = sorted(periods)
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
    Written as: "Mar 2021", "Mar-2021", "Jan '21", "03/2021", "2021-03", "2021" (words around it are fine:
    "Since 02/2024", "Present (3 yrs)").
    """
    text = " ".join(text.strip().lower().replace("’", "'").split())
    if re.match(rf"(?:{NOW_WORDS})\b", text):
        return this_month
    month = None
    with_name = re.search(rf"\b({MONTHS})\.?[\s,\-']*(\d{{4}}|'\d{{2}})(?!\d)", text)
    month_first = re.search(r"(?<!\d)(\d{1,2})[/.-](\d{4})(?!\d)", text)
    year_first = re.search(r"(?<!\d)(\d{4})[/.-](\d{1,2})(?!\d)", text)
    year_alone = re.search(r"(?<!\d)(\d{4})(?!\d)", text)
    if with_name:
        month = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"].index(with_name.group(1)[:3]) + 1
        year = with_name.group(2)
        if year.startswith("'"):                            # "'21" -> 2021, "'98" -> 1998
            year = 2000 + int(year[1:])
            if year > this_month // 12 + 1:
                year -= 100
        year = int(year)
    elif month_first:
        month = int(month_first.group(1))
        year = int(month_first.group(2))
    elif year_first:
        year = int(year_first.group(1))
        month = int(year_first.group(2))
    elif year_alone:
        year = int(year_alone.group(1))
    else:
        return None                                         # not a date ("", "unknown"...)
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
        # 2. the field name with a degree word just before it (within 60 characters): "bs computer science",
        #    or just after it (within 30 characters): "computer science (bs)", "computer science, bachelor of science"
        for match in re.finditer(r"(?<![a-z0-9])" + re.escape(field) + r"(?![a-z0-9])", text):
            around = text[max(0, match.start() - 60):match.start()] + " | " + text[match.end():match.end() + 30]
            if re.search(r"(?<![a-z])" + DEGREE_WORDS + r"(?![a-z])", around):
                return True
    return False
