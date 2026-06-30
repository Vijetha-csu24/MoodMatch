"""
StunTronics Certificate Generator — Flask Application

Upload a Word template (.docx) with {{placeholders}} and an Excel file (.xlsx)
with data rows. The app generates one certificate per row, applies StunTronics
business rules, and returns a downloadable ZIP.
"""

import os
import io
import uuid
import shutil
import zipfile
from pathlib import Path

import pandas as pd
from flask import Flask, request, jsonify, send_file, render_template


from engine import extract_placeholders_from_docx, fix_fragmented_placeholders, render_and_protect
from business_rules import (
    CERT_TYPES,
    COMPUTED_FIELDS,
    _ALIAS_LOOKUP,
    build_context,
    build_filename,
    auto_match_columns,
    normalize_column_name,
    validate_data,
    format_award_date,
    format_expiration_date,
)

app = Flask(__name__, template_folder="templates", static_folder="static")

UPLOAD_DIR = Path(__file__).parent / "uploads"
OUTPUT_DIR = Path(__file__).parent / "output"
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

MAX_CONTENT_LENGTH = 50 * 1024 * 1024
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH


def _check_direct_mode(template_placeholders, normalized_excel):
    """
    Check if all template placeholders can be satisfied directly by Excel columns.
    If so, bypass business rules and do direct replacement.
    """
    for ph in template_placeholders:
        ph_norm = normalize_column_name(ph)
        if ph_norm in normalized_excel:
            continue
        resolved = _ALIAS_LOOKUP.get(ph_norm, ph_norm)
        if resolved in normalized_excel:
            continue
        if ph_norm in COMPUTED_FIELDS:
            return False
        return False
    return True


@app.route("/")
def index():
    return render_template("index.html", cert_types=CERT_TYPES)


@app.route("/api/upload-template", methods=["POST"])
def upload_template():
    """Accept a .docx template, extract placeholders, return them."""
    if "template" not in request.files:
        return jsonify({"error": "No template file provided"}), 400

    file = request.files["template"]
    if not file.filename.endswith(".docx"):
        return jsonify({"error": "File must be a .docx document"}), 400

    job_id = str(uuid.uuid4())
    job_dir = UPLOAD_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    template_path = job_dir / "template.docx"
    file.save(str(template_path))

    try:
        placeholders = extract_placeholders_from_docx(str(template_path))
    except Exception as e:
        shutil.rmtree(job_dir)
        return jsonify({"error": f"Failed to parse template: {str(e)}"}), 400

    return jsonify({
        "job_id": job_id,
        "placeholders": placeholders,
        "message": f"Found {len(placeholders)} placeholder(s)",
    })


@app.route("/api/upload-data", methods=["POST"])
def upload_data():
    """Accept an .xlsx data file, return column names and row count."""
    if "data" not in request.files:
        return jsonify({"error": "No data file provided"}), 400

    job_id = request.form.get("job_id")
    if not job_id:
        return jsonify({"error": "Missing job_id"}), 400

    job_dir = UPLOAD_DIR / job_id
    if not job_dir.exists():
        return jsonify({"error": "Invalid job_id. Upload template first."}), 400

    file = request.files["data"]
    if not file.filename.endswith((".xlsx", ".xls", ".csv")):
        return jsonify({"error": "File must be .xlsx, .xls, or .csv"}), 400

    ext = Path(file.filename).suffix.lower()
    for old_ext in (".xlsx", ".xls", ".csv"):
        old_file = job_dir / f"data{old_ext}"
        if old_file.exists():
            old_file.unlink()
    data_path = job_dir / f"data{ext}"
    file.save(str(data_path))

    try:
        if ext == ".csv":
            df = pd.read_csv(str(data_path))
        else:
            df = pd.read_excel(str(data_path))

        df = df.dropna(how="all")
        columns = list(df.columns)
        row_count = len(df)
    except Exception as e:
        return jsonify({"error": f"Failed to parse data file: {str(e)}"}), 400

    template_path = job_dir / "template.docx"
    placeholders = extract_placeholders_from_docx(str(template_path))
    internal_matches = auto_match_columns(columns, placeholders)

    ui_matches = {}
    for ph in placeholders:
        ph_norm = normalize_column_name(ph)
        if ph_norm in COMPUTED_FIELDS:
            ui_matches[ph] = "__computed__"
        else:
            resolved = _ALIAS_LOOKUP.get(ph_norm, ph_norm)
            if resolved in internal_matches:
                ui_matches[ph] = internal_matches[resolved]
            elif ph in internal_matches:
                ui_matches[ph] = internal_matches[ph]

    return jsonify({
        "columns": columns,
        "row_count": row_count,
        "placeholders": placeholders,
        "auto_matches": ui_matches,
        "internal_matches": internal_matches,
        "message": f"Found {row_count} row(s) and {len(columns)} column(s)",
    })


@app.route("/api/generate", methods=["POST"])
def generate():
    """Generate certificates from template + data."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON body provided"}), 400

    job_id = data.get("job_id")
    cert_type_key = data.get("cert_type")
    column_mapping = data.get("column_mapping", {})

    if not job_id:
        return jsonify({"error": "Missing job_id"}), 400
    if cert_type_key not in CERT_TYPES:
        return jsonify({"error": f"Invalid cert_type: {cert_type_key}"}), 400

    job_dir = UPLOAD_DIR / job_id
    template_path = job_dir / "template.docx"

    data_path = None
    for ext in (".xlsx", ".xls", ".csv"):
        candidate = job_dir / f"data{ext}"
        if candidate.exists():
            data_path = candidate
            break

    if not template_path.exists() or not data_path:
        return jsonify({"error": "Template or data file missing. Re-upload."}), 400

    try:
        if data_path.suffix == ".csv":
            df = pd.read_csv(str(data_path))
        else:
            df = pd.read_excel(str(data_path))
        df = df.dropna(how="all")
    except Exception as e:
        return jsonify({"error": f"Failed to read data: {str(e)}"}), 400

    template_placeholders = extract_placeholders_from_docx(str(template_path))
    excel_columns = list(df.columns)
    normalized_excel = {normalize_column_name(c): c for c in excel_columns}

    direct_mode = _check_direct_mode(template_placeholders, normalized_excel)

    if direct_mode:
        rows = df.to_dict("records")
        placeholder_to_col = {}
        for ph in template_placeholders:
            ph_norm = normalize_column_name(ph)
            if ph_norm in normalized_excel:
                placeholder_to_col[ph] = normalized_excel[ph_norm]
            else:
                resolved = _ALIAS_LOOKUP.get(ph_norm, ph_norm)
                if resolved in normalized_excel:
                    placeholder_to_col[ph] = normalized_excel[resolved]

        missing = [ph for ph in template_placeholders if ph not in placeholder_to_col]
        if missing:
            return jsonify({"error": f"No matching Excel columns for: {', '.join(missing)}"}), 400
    else:
        if column_mapping:
            reverse_map = {v: k for k, v in column_mapping.items()}
            df = df.rename(columns=reverse_map)
        else:
            df.columns = [normalize_column_name(c) for c in df.columns]

        rows = df.to_dict("records")
        config = CERT_TYPES[cert_type_key]
        is_valid, errors = validate_data(rows, cert_type_key, template_placeholders)
        if not is_valid:
            return jsonify({"error": "Data validation failed", "details": errors[:20]}), 400

    with open(template_path, "rb") as f:
        template_bytes = f.read()

    fixed_template_bytes = fix_fragmented_placeholders(template_bytes)

    output_job_dir = OUTPUT_DIR / job_id
    output_job_dir.mkdir(parents=True, exist_ok=True)

    generated = []
    generation_errors = []

    for i, row in enumerate(rows):
        try:
            if direct_mode:
                render_context = {}
                for ph, col in placeholder_to_col.items():
                    val = row.get(col, "")
                    if val is None:
                        render_context[ph] = ""
                        continue
                    val_str = str(val).strip()
                    ph_norm = normalize_column_name(ph)
                    resolved = _ALIAS_LOOKUP.get(ph_norm, ph_norm)
                    if resolved == "award_date":
                        try:
                            render_context[ph] = format_award_date(val)
                        except (ValueError, TypeError):
                            render_context[ph] = val_str
                    elif resolved == "expiration_date":
                        try:
                            render_context[ph] = format_expiration_date(val)
                        except (ValueError, TypeError):
                            render_context[ph] = val_str
                    else:
                        render_context[ph] = val_str

                name_val = render_context.get("Name") or render_context.get("name") or ""
                first_val = render_context.get("FName") or render_context.get("first_name") or ""
                last_val = render_context.get("LName") or render_context.get("last_name") or ""
                award_date_val = None
                for ph, col in placeholder_to_col.items():
                    ph_norm = normalize_column_name(ph)
                    resolved = _ALIAS_LOOKUP.get(ph_norm, ph_norm)
                    if resolved == "award_date":
                        award_date_val = row.get(col, "")
                        break
                cert_num = render_context.get("Certno") or render_context.get("cert_number") or ""
                filename = build_filename(first_val, last_val, cert_type_key, award_date=award_date_val, name=name_val)
            else:
                context = build_context(row, cert_type_key)
                filename = build_filename(row["first_name"], row["last_name"], cert_type_key, award_date=row.get("award_date"))

                render_context = dict(context)
                if column_mapping:
                    for internal_name, excel_col in column_mapping.items():
                        if internal_name in context:
                            render_context[excel_col] = context[internal_name]

                for ph in template_placeholders:
                    if ph in render_context:
                        continue
                    ph_norm = normalize_column_name(ph)
                    resolved = _ALIAS_LOOKUP.get(ph_norm, ph_norm)
                    if resolved in context:
                        render_context[ph] = context[resolved]

                name_val = context.get("name", "")
                cert_num = context.get("cert_number", "")

            counter = 1
            original_filename = filename
            while filename in [g["filename"] for g in generated]:
                name_part = original_filename.rsplit(".", 1)[0]
                filename = f"{name_part}_{counter}.docx"
                counter += 1

            doc_bytes = render_and_protect(fixed_template_bytes, render_context)

            output_path = output_job_dir / filename
            with open(output_path, "wb") as f:
                f.write(doc_bytes)

            generated.append({
                "filename": filename,
                "name": name_val,
                "cert_number": cert_num,
            })

        except Exception as e:
            generation_errors.append(f"Row {i + 2}: {str(e)}")

    manifest_df = pd.DataFrame(generated)
    manifest_path = output_job_dir / "manifest.xlsx"
    manifest_df.to_excel(str(manifest_path), index=False)

    zip_path = OUTPUT_DIR / f"{job_id}.zip"
    with zipfile.ZipFile(str(zip_path), "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in output_job_dir.rglob("*"):
            if file_path.is_file():
                zf.write(file_path, arcname=file_path.name)

    shutil.rmtree(output_job_dir, ignore_errors=True)

    result = {
        "job_id": job_id,
        "total_generated": len(generated),
        "total_errors": len(generation_errors),
        "generated": generated,
    }
    if generation_errors:
        result["errors"] = generation_errors[:20]

    return jsonify(result)


@app.route("/api/download/<job_id>")
def download(job_id):
    """Download the generated ZIP file."""
    zip_path = OUTPUT_DIR / f"{job_id}.zip"
    if not zip_path.exists():
        return jsonify({"error": "File not found. Generate certificates first."}), 404

    return send_file(
        str(zip_path),
        mimetype="application/zip",
        as_attachment=True,
        download_name="certificates.zip",
    )


@app.route("/api/cert-types")
def cert_types():
    """Return available certificate types."""
    return jsonify({
        key: {"label": val["label"], "has_instructor": val["has_instructor"], "has_expiration": val["has_expiration"]}
        for key, val in CERT_TYPES.items()
    })


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
