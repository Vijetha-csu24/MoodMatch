"""
XML engine for fixing fragmented Jinja placeholders in Word documents.

Word often splits {{placeholder}} across multiple XML <w:r> runs,
especially inside textboxes and shapes. This module merges them back
so docxtpl can find and render them.
"""

import re
import copy
import zipfile
import hashlib
import io
from lxml import etree

WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
WPSHAPE_NS = "http://schemas.microsoft.com/office/word/2010/wordprocessingShape"
MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006"
VML_NS = "urn:schemas-microsoft-com:vml"

T_TAG = f"{{{WORD_NS}}}t"
R_TAG = f"{{{WORD_NS}}}r"
RPR_TAG = f"{{{WORD_NS}}}rPr"
BODY_TAG = f"{{{WORD_NS}}}body"

PLACEHOLDER_RE = re.compile(r"\{\{[\w]+\}\}")
PARTIAL_OPEN = re.compile(r"\{\{?$")
PARTIAL_CLOSE = re.compile(r"^[\w]*\}?\}?")


def extract_placeholders_from_docx(docx_path):
    """Extract all {{placeholder}} names from a .docx file, including textboxes."""
    with zipfile.ZipFile(docx_path, "r") as z:
        xml_bytes = z.read("word/document.xml")

    root = etree.fromstring(xml_bytes)
    all_text = _collect_all_text(root)
    joined = "".join(all_text)

    placeholders = re.findall(r"\{\{([\w]+)\}\}", joined)
    return list(dict.fromkeys(placeholders))


def fix_fragmented_placeholders(docx_bytes):
    """
    Fix fragmented {{...}} placeholders in a .docx file's XML.

    Takes raw .docx bytes, returns fixed .docx bytes.
    Scans all <w:t> nodes including those inside textboxes/shapes,
    merges split placeholder runs while preserving formatting.
    """
    buffer_in = io.BytesIO(docx_bytes)
    buffer_out = io.BytesIO()

    with zipfile.ZipFile(buffer_in, "r") as zin:
        with zipfile.ZipFile(buffer_out, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename.startswith("word/") and item.filename.endswith(".xml"):
                    data = _fix_xml(data)
                zout.writestr(item, data)

    return buffer_out.getvalue()


def post_render_replace(docx_bytes, context):
    """
    Fallback replacement for any {{placeholder}} that docxtpl missed.

    Some placeholders inside textboxes (especially in mc:Fallback VML blocks)
    may survive docxtpl's Jinja rendering. This does a direct string replacement
    on all XML parts in the docx.
    """
    buffer_in = io.BytesIO(docx_bytes)
    buffer_out = io.BytesIO()

    with zipfile.ZipFile(buffer_in, "r") as zin:
        with zipfile.ZipFile(buffer_out, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename.endswith(".xml"):
                    text = data.decode("utf-8")
                    for key, value in context.items():
                        text = text.replace("{{" + key + "}}", str(value))
                    data = text.encode("utf-8")
                zout.writestr(item, data)

    return buffer_out.getvalue()


def apply_document_protection(docx_bytes, password="CERTEDIT"):
    """
    Apply read-only edit protection to a .docx file.

    Adds <w:documentProtection> to word/settings.xml with the given password.
    """
    buffer_in = io.BytesIO(docx_bytes)
    buffer_out = io.BytesIO()

    password_hash = _hash_password(password)

    with zipfile.ZipFile(buffer_in, "r") as zin:
        with zipfile.ZipFile(buffer_out, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename == "word/settings.xml":
                    data = _inject_protection(data, password_hash)
                zout.writestr(item, data)

    return buffer_out.getvalue()


def _fix_xml(xml_bytes):
    """Fix fragmented placeholders in document XML."""
    root = etree.fromstring(xml_bytes)
    _merge_fragmented_runs(root)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _merge_fragmented_runs(element):
    """
    Walk the XML tree and merge adjacent <w:r> runs that together form
    a {{placeholder}} but are individually fragmented.
    """
    for parent in element.iter():
        children = list(parent)
        if not children:
            continue

        runs = []
        for child in children:
            if child.tag == R_TAG:
                runs.append(child)
            else:
                if runs:
                    _try_merge_run_group(parent, runs)
                    runs = []
                _merge_fragmented_runs(child)

        if runs:
            _try_merge_run_group(parent, runs)


def _try_merge_run_group(parent, runs):
    """
    Given a sequence of adjacent <w:r> elements, check if their combined
    text contains fragmented placeholders and merge them.
    """
    texts = []
    for r in runs:
        t_el = r.find(T_TAG)
        texts.append(t_el.text if t_el is not None and t_el.text else "")

    combined = "".join(texts)

    if "{{" not in combined:
        return

    placeholders_found = re.findall(r"\{\{[\w]+\}\}", combined)
    if not placeholders_found:
        individual_has_all = all(
            re.search(r"\{\{[\w]+\}\}", t) for t in texts if "{{" in t
        )
        if individual_has_all:
            return

    fragments = _find_fragment_spans(texts)
    if not fragments:
        return

    for start_idx, end_idx in reversed(fragments):
        _merge_runs(parent, runs, start_idx, end_idx)


def _find_fragment_spans(texts):
    """
    Find spans of indices where text fragments together form {{placeholders}}.
    Returns list of (start_idx, end_idx) tuples.
    """
    spans = []
    i = 0
    while i < len(texts):
        if PARTIAL_OPEN.search(texts[i]) and not PLACEHOLDER_RE.search(texts[i]):
            j = i + 1
            accumulated = texts[i]
            while j < len(texts):
                accumulated += texts[j]
                if "}}" in accumulated:
                    if re.search(r"\{\{[\w]+\}\}", accumulated):
                        spans.append((i, j))
                    break
                j += 1
            i = j + 1
        else:
            i += 1
    return spans


def _merge_runs(parent, runs, start_idx, end_idx):
    """Merge runs[start_idx..end_idx] into a single run, preserving first run's formatting."""
    combined_text = ""
    for k in range(start_idx, end_idx + 1):
        t_el = runs[k].find(T_TAG)
        if t_el is not None and t_el.text:
            combined_text += t_el.text

    first_run = runs[start_idx]
    t_el = first_run.find(T_TAG)
    if t_el is None:
        t_el = etree.SubElement(first_run, T_TAG)
    t_el.text = combined_text
    t_el.set(f"{{{XML_SPACE}}}space", "preserve")

    for k in range(start_idx + 1, end_idx + 1):
        parent.remove(runs[k])


XML_SPACE = "http://www.w3.org/XML/1998/namespace"


def _collect_all_text(root):
    """Collect all <w:t> text content in document order."""
    texts = []
    for t_el in root.iter(T_TAG):
        if t_el.text:
            texts.append(t_el.text)
    return texts


def _hash_password(password):
    """
    Create a simple hash for Word document protection.
    This uses the legacy Word password hashing algorithm.
    """
    hash_val = 0
    for char in reversed(password):
        hash_val = ((hash_val >> 14) & 0x01) | ((hash_val << 1) & 0x7FFF)
        hash_val ^= ord(char)
    hash_val = ((hash_val >> 14) & 0x01) | ((hash_val << 1) & 0x7FFF)
    hash_val ^= len(password)
    hash_val ^= 0xCE4B
    return format(hash_val, "04X")


def _inject_protection(settings_xml_bytes, password_hash):
    """Inject documentProtection element into settings.xml."""
    root = etree.fromstring(settings_xml_bytes)
    nsmap = root.nsmap

    w_ns = nsmap.get("w", WORD_NS)
    prot_tag = f"{{{w_ns}}}documentProtection"

    existing = root.find(prot_tag)
    if existing is not None:
        root.remove(existing)

    prot = etree.SubElement(root, prot_tag)
    prot.set(f"{{{w_ns}}}edit", "readOnly")
    prot.set(f"{{{w_ns}}}enforcement", "1")
    prot.set(f"{{{w_ns}}}cryptProviderType", "rsaAES")
    prot.set(f"{{{w_ns}}}hash", password_hash)

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
