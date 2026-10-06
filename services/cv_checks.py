"""
Checks the app makes on a CV's text by itself (no AI):
- check_skills()         which of the job's required skills the CV mentions (anywhere in the CV)
- cv_stated_years()      the total years of experience the CV itself states ("4 years experience")
- has_required_degree()  whether the CV shows a degree in one of the job's fields ("BS Computer Science", "BSCS")
"""
import re

from config.word_lists import DEGREE_FIELD_ALIASES, FILLER_WORDS, RISKY_WORDS, SKILL_ALIASES

# A name followed by these words is a DIFFERENT skill: "React Native" is not "React", "Java Script" is not "Java".
NOT_FOLLOWED_BY = {"react": r"(?!\s*native)", "java": r"(?!\s*script)"}

# A total written in the CV: "4 years experience", "04 Years' Experience", "3+ years of professional experience"
STATED_YEARS = re.compile(r"(\d+(?:\.\d+)?)\s*\+?\s*years?['’]?\s*(?:of\s+)?(?:total\s+|professional\s+|work\s+|"
                          r"industry\s+|hands-on\s+)?(?:work\s+)?experience", re.I)

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


# ---------------------------------------------------------------- degree

def has_required_degree(cv_text, fields):
    """
    True when the CV shows a degree in one of the job's fields, e.g. for "computer science":
    "BS Computer Science", "Bachelor's degree in Computer Science", or a short form like "BSCS".
    """
    text = re.sub(r"\s+", " ", (cv_text or "").lower())
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
