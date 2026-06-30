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
        "label": "Band-It User",
        "product": "BAND-IT SYSTEM",
        "suffix": "B",
        "has_instructor": False,
        "has_expiration": False,
    },
    "shield_user": {
        "label": "Ice Shield User",
        "product": "ICE SHIELD",
        "suffix": "SH",
        "has_instructor": False,
        "has_expiration": False,
    },
    "bandit_field_user": {
        "label": "Band-It User (Field Instructor)",
        "product": "BAND-IT SYSTEM",
        "suffix": "B",
        "has_instructor": True,
        "has_expiration": False,
    },
    "shield_field_user": {
        "label": "Ice Shield User (Field Instructor)",
        "product": "ICE SHIELD",
        "suffix": "SH",
        "has_instructor": True,
        "has_expiration": False,
    },
    "bandit_instructor": {
        "label": "Band-It Instructor",
        "product": "BAND-IT SYSTEM",
        "suffix": "B",
        "has_instructor": True,
        "has_expiration": True,
    },
    "shield_instructor": {
        "label": "Ice Shield Instructor",
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


def build_filename(first_name, last_name, cert_type_key):
    """
    Build output filename following StunTronics convention.

    Examples: LOWERY_S_SH.docx, MALDONADO_P_INSTR_SH.docx
    """
    config = CERT_TYPES[cert_type_key]
    last = str(last_name).strip().upper()
    first_init = str(first_name).strip()[0].upper()
    suffix = config["suffix"]

    if config["has_expiration"]:
        return f"{last}_{first_init}_INSTR_{suffix}.docx"

    if config["has_instructor"]:
        return f"{last}_{first_init}_{suffix}.docx"

    return f"{last}_{first_init}_{suffix}.docx"


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
}

_ALIAS_LOOKUP = {}
for _placeholder, _aliases in COLUMN_ALIASES.items():
    for _alias in _aliases:
        _ALIAS_LOOKUP[_alias] = _placeholder


def auto_match_columns(excel_columns, placeholders):
    """
    Auto-match Excel column names to template placeholder names.

    Returns dict: {placeholder_name: excel_column_name}
    Computed fields (name, expiration_date) are marked with "__computed__".
    """
    matches = {}
    normalized_excel = {normalize_column_name(c): c for c in excel_columns}

    for ph in placeholders:
        ph_norm = normalize_column_name(ph)
        if ph_norm in COMPUTED_FIELDS:
            matches[ph] = "__computed__"
        elif ph_norm in normalized_excel:
            matches[ph] = normalized_excel[ph_norm]
        else:
            for excel_norm, excel_orig in normalized_excel.items():
                resolved = _ALIAS_LOOKUP.get(excel_norm)
                if resolved == ph_norm:
                    matches[ph] = excel_orig
                    break

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
