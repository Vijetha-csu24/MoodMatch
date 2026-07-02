"""
StunTronics-specific business rules for certificate generation.

Handles name formatting, cert number construction, expiration calculation,
file naming, and context building for template rendering.
"""

import re
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

CERT_TYPES = {
    "bandit_user": {
        "label": "Band-It User Certificate",
        "product": "BAND-IT SYSTEM",
        "suffix": "B",
        "has_instructor": False,
        "has_expiration": False,
    },
    "shield_user": {
        "label": "Ice Shield User Certificate",
        "product": "ICE SHIELD",
        "suffix": "SH",
        "has_instructor": False,
        "has_expiration": False,
    },
    "bandit_field_user": {
        "label": "Band-It User Recertification",
        "product": "BAND-IT SYSTEM",
        "suffix": "B",
        "has_instructor": True,
        "has_expiration": False,
    },
    "shield_field_user": {
        "label": "Ice Shield User Recertification",
        "product": "ICE SHIELD",
        "suffix": "SH",
        "has_instructor": True,
        "has_expiration": False,
    },
    "bandit_instructor": {
        "label": "User Training",
        "product": "BAND-IT SYSTEM",
        "suffix": "B",
        "has_instructor": True,
        "has_expiration": True,
    },
    "shield_instructor": {
        "label": "Instructor Training",
        "product": "ICE SHIELD",
        "suffix": "SH",
        "has_instructor": True,
        "has_expiration": True,
    },
    "both_user": {
        "label": "Both Band-It & Shield User",
        "product": "BAND-IT SYSTEM & ICE SHIELD",
        "suffix": "SHB",
        "has_instructor": False,
        "has_expiration": False,
    },
}


def format_name(first_name, last_name):
    """Format name as ALL CAPS with 2 spaces between first and last."""
    first = str(first_name).strip().upper()
    last = str(last_name).strip().upper()
    return f"{first}  {last}"


def build_cert_number(number, cert_type_key, is_instructor=False):
    """
    Build full certificate number with prefix and suffix.

    Examples: "6535-SH", "I-6534-SH"
    """
    config = CERT_TYPES[cert_type_key]
    suffix = config["suffix"]
    num = str(number).strip()

    if config["has_expiration"]:
        return f"I-{num}-{suffix}"
    return f"{num}-{suffix}"


def calculate_expiration(award_date, years=2):
    """Calculate expiration date as award_date + 2 years."""
    if isinstance(award_date, str):
        award_date = parse_date(award_date)
    return award_date + relativedelta(years=years)


def format_award_date(date_val):
    """Format date as 'Month Day, Year' (e.g., 'March 26, 2026')."""
    if isinstance(date_val, str):
        date_val = parse_date(date_val)
    return date_val.strftime("%B %d, %Y").replace(" 0", " ")


def format_expiration_date(date_val):
    """Format expiration date as 'M-DD-YYYY' (e.g., '3-26-2028')."""
    if isinstance(date_val, str):
        date_val = parse_date(date_val)
    return f"{date_val.month}-{date_val.day}-{date_val.year}"


def parse_date(date_str):
    """Parse a date string in various common formats."""
    date_str = str(date_str).strip()
    formats = [
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%m-%d-%Y",
        "%B %d, %Y",
        "%b %d, %Y",
        "%m/%d/%y",
        "%Y-%m-%d %H:%M:%S",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: '{date_str}'")


def build_filename(first_name, last_name, cert_type_key, award_date=None, name=None):
    """
    Build output filename with name and date.

    Uses first_name + last_name if available, falls back to combined name.
    Includes award date when provided.
    Examples: LOWERY_SCOTT_SH_03262026.docx, REED_JOHN_INSTR_SH_06252026.docx
    """
    config = CERT_TYPES[cert_type_key]
    suffix = config["suffix"]

    first_str = str(first_name).strip().upper() if first_name else ""
    last_str = str(last_name).strip().upper() if last_name else ""

    if not first_str and not last_str and name:
        parts = str(name).strip().upper().split()
        if len(parts) >= 2:
            first_str, last_str = parts[0], parts[-1]
        elif parts:
            last_str = parts[0]

    last_str = last_str or "UNKNOWN"
    first_str = first_str or "X"

    date_part = ""
    if award_date:
        try:
            dt = parse_date(str(award_date)) if isinstance(award_date, str) else award_date
            date_part = f"_{dt.strftime('%m%d%Y')}"
        except (ValueError, TypeError, AttributeError):
            pass

    if config["has_expiration"]:
        return f"{last_str}_{first_str}_INSTR_{suffix}{date_part}.docx"

    return f"{last_str}_{first_str}_{suffix}{date_part}.docx"


def build_context(row, cert_type_key):
    """
    Build the template rendering context from an Excel row and cert type.

    Takes a dict-like row (from pandas) and returns the context dict
    with all business rules applied.
    """
    config = CERT_TYPES[cert_type_key]

    first = str(row["first_name"]).strip()
    last = str(row["last_name"]).strip()

    context = {
        "first_name": first.upper(),
        "last_name": last.upper(),
        "name": format_name(first, last),
        "cert_number": build_cert_number(row["cert_number"], cert_type_key),
        "award_date": format_award_date(row["award_date"]),
    }

    if config["has_instructor"]:
        instructor = str(row.get("instructor_name", "")).strip()
        if instructor:
            context["instructor_name"] = instructor.upper()
        else:
            context["instructor_name"] = ""

    if config["has_expiration"]:
        award_dt = parse_date(str(row["award_date"]))
        exp_dt = calculate_expiration(award_dt)
        context["expiration_date"] = format_expiration_date(exp_dt)

    return context


def normalize_column_name(col):
    """Normalize a column name for matching: lowercase, underscores, stripped."""
    col = str(col).strip().lower()
    col = re.sub(r"[\s\-]+", "_", col)
    col = re.sub(r"[^a-z0-9_]", "", col)
    return col


COMPUTED_FIELDS = {
    "name": "Auto-generated from first_name + last_name",
    "expiration_date": "Auto-calculated from award_date + 2 years",
}

COLUMN_ALIASES = {
    "first_name": ["fname", "firstname", "first", "f_name"],
    "last_name": ["lname", "lastname", "last", "l_name", "surname"],
    "award_date": ["date", "awarddate", "award", "cert_date", "certdate", "training_date", "trainingdate"],
    "cert_number": ["certno", "certnumber", "cert_no", "cert_num", "certnum", "certificate_number", "certificatenumber", "number", "no"],
    "instructor_name": ["instructor", "instructorname", "trainer", "trainer_name"],
    "expiration_date": ["edate", "exp_date", "expdate", "expiry", "expiry_date"],
    "name": ["fullname", "full_name", "candidate_name", "student_name"],
}

_ALIAS_LOOKUP = {}
for _placeholder, _aliases in COLUMN_ALIASES.items():
    for _alias in _aliases:
        _ALIAS_LOOKUP[_alias] = _placeholder


REQUIRED_SOURCE_FIELDS = {"first_name", "last_name", "award_date", "cert_number", "instructor_name"}


def _match_field(field_norm, normalized_excel):
    if field_norm in normalized_excel:
        return normalized_excel[field_norm]
    for excel_norm, excel_orig in normalized_excel.items():
        if _ALIAS_LOOKUP.get(excel_norm) == field_norm:
            return excel_orig
    return None


def auto_match_columns(excel_columns, placeholders):
    """
    Auto-match Excel column names to internal field names.

    Returns dict: {internal_field_name: excel_column_name}
    Computed fields (name, expiration_date) are marked with "__computed__".

    Template placeholders are resolved to their internal field names
    via the alias system (e.g. FName -> first_name, Certno -> cert_number).
    """
    matches = {}
    normalized_excel = {normalize_column_name(c): c for c in excel_columns}

    all_fields = set(REQUIRED_SOURCE_FIELDS)
    for ph in placeholders:
        ph_norm = normalize_column_name(ph)
        resolved = _ALIAS_LOOKUP.get(ph_norm, ph_norm)
        direct_match = _match_field(ph_norm, normalized_excel) or _match_field(resolved, normalized_excel)
        if direct_match:
            all_fields.add(resolved)
        elif ph_norm in COMPUTED_FIELDS:
            matches[ph] = "__computed__"
        else:
            all_fields.add(resolved)

    for field in all_fields:
        if field in matches:
            continue
        found = _match_field(field, normalized_excel)
        if found:
            matches[field] = found

    return matches


def validate_data(rows, cert_type_key, required_placeholders):
    """
    Validate Excel data rows against requirements.

    Returns (is_valid, errors) where errors is a list of strings.
    """
    config = CERT_TYPES[cert_type_key]
    errors = []

    required_fields = {"first_name", "last_name", "award_date", "cert_number"}
    if config["has_instructor"]:
        required_fields.add("instructor_name")

    for i, row in enumerate(rows, start=2):
        for field in required_fields:
            val = row.get(field)
            if val is None or str(val).strip() == "" or str(val).strip().lower() == "nan":
                errors.append(f"Row {i}: missing '{field}'")

        if "award_date" in row and row["award_date"]:
            try:
                parse_date(str(row["award_date"]))
            except ValueError:
                errors.append(f"Row {i}: invalid date '{row['award_date']}'")

    return len(errors) == 0, errors
