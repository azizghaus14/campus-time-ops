"""Passport MRZ (ICAO Doc 9303, TD3: 2 lines x 44 chars) parsing + check-digit validation.

Image -> MRZ text: Gemini multimodal (google-genai, Vertex AI) when configured. Offline demo fallback: the generated
SPECIMEN images carry their MRZ in a PNG text chunk; anything else needs `mrz_text`.
"""
from __future__ import annotations

import base64
import io
import re
from datetime import date
from typing import Optional

from ..config import settings
from .errors import ToolError

_W = (7, 3, 1)


def char_value(c: str) -> int:
    if c.isdigit():
        return int(c)
    if "A" <= c <= "Z":
        return ord(c) - 55
    if c == "<":
        return 0
    raise ValueError(f"invalid MRZ char {c!r}")


def check_digit(s: str) -> str:
    return str(sum(char_value(c) * _W[i % 3] for i, c in enumerate(s)) % 10)


def _yymmdd(s: str, future: bool) -> Optional[str]:
    if not re.fullmatch(r"\d{6}", s):
        return None
    yy, mm, dd = int(s[:2]), int(s[2:4]), int(s[4:])
    if future:
        year = 2000 + yy
    else:
        year = 1900 + yy if yy > date.today().year % 100 else 2000 + yy
    try:
        return date(year, mm, dd).isoformat()
    except ValueError:
        return None


def build_td3(doc_type: str, country: str, surname: str, given: str, number: str, nationality: str, dob: str, sex: str,
              expiry: str, personal: str = "") -> tuple[str, str]:
    """Build a valid TD3 MRZ (used by the specimen generator and tests). dob/expiry 'YYYY-MM-DD'."""
    def f(s: str, n: int) -> str:
        s = re.sub(r"[^A-Z0-9<]", "<", s.upper().replace(" ", "<").replace("-", "<"))
        return (s + "<" * n)[:n]

    name = f(f"{surname}<<{given}", 39)
    l1 = f(doc_type, 2) + f(country, 3) + name
    num = f(number, 9)
    b = date.fromisoformat(dob).strftime("%y%m%d")
    e = date.fromisoformat(expiry).strftime("%y%m%d")
    pers = f(personal, 14)
    pcd = check_digit(pers) if personal else "<"
    body = num + check_digit(num) + f(nationality, 3) + b + check_digit(b) + sex[:1].upper() + e + check_digit(e) + pers + pcd
    composite = num + check_digit(num) + b + check_digit(b) + e + check_digit(e) + pers + pcd
    l2 = body + check_digit(composite)
    assert len(l1) == 44 and len(l2) == 44, (len(l1), len(l2))
    return l1, l2


def parse_td3(line1: str, line2: str) -> dict:
    l1, l2 = line1.strip().upper().replace(" ", ""), line2.strip().upper().replace(" ", "")
    if len(l1) != 44 or len(l2) != 44:
        raise ToolError("BAD_MRZ", "TD3 MRZ must be 2 lines of 44 characters", got=[len(l1), len(l2)])
    if not re.fullmatch(r"[A-Z0-9<]{44}", l1 + l2[:0]) or not re.fullmatch(r"[A-Z0-9<]{44}", l2):
        raise ToolError("BAD_MRZ", "MRZ contains invalid characters")
    names = l1[5:].split("<<", 1)
    surname = names[0].replace("<", " ").strip()
    given = names[1].replace("<", " ").strip() if len(names) > 1 else ""
    num, num_cd = l2[0:9], l2[9]
    nat = l2[10:13]
    dob, dob_cd = l2[13:19], l2[19]
    sex = l2[20]
    exp, exp_cd = l2[21:27], l2[27]
    pers, pers_cd = l2[28:42], l2[42]
    comp_cd = l2[43]
    composite = l2[0:10] + l2[13:20] + l2[21:43]
    checks = {
        "document_number": check_digit(num) == num_cd,
        "date_of_birth": check_digit(dob) == dob_cd,
        "expiry_date": check_digit(exp) == exp_cd,
        "personal_number": (pers_cd == "<" and set(pers) <= {"<"}) or check_digit(pers) == pers_cd,
        "composite": check_digit(composite) == comp_cd,
    }
    return {
        "document_type": l1[0:2].replace("<", ""),
        "issuing_country": l1[2:5].replace("<", ""),
        "surname": surname,
        "given_names": given,
        "document_number": num.replace("<", ""),
        "nationality": nat.replace("<", ""),
        "date_of_birth": _yymmdd(dob, future=False),
        "sex": sex.replace("<", "X"),
        "expiry_date": _yymmdd(exp, future=True),
        "personal_number": pers.replace("<", ""),
        "check_digits": checks,
        "valid": all(checks.values()),
        "mrz": [l1, l2],
    }


def _extract_mrz_lines(text: str) -> tuple[str, str]:
    lines = [re.sub(r"\s", "", l).upper() for l in text.splitlines()]
    lines = [l for l in lines if len(l) >= 40 and re.fullmatch(r"[A-Z0-9<]+", l)]
    if len(lines) < 2:
        raise ToolError("MRZ_NOT_FOUND", "Could not find two MRZ lines")
    return lines[-2][:44].ljust(44, "<"), lines[-1][:44].ljust(44, "<")


def mrz_from_image(image_bytes: bytes) -> tuple[str, str, str]:
    """-> (line1, line2, method)"""
    # 1) Gemini multimodal (production path)
    if settings.gcp_project or __import__("os").environ.get("GOOGLE_API_KEY"):
        try:  # pragma: no cover - needs Vertex AI
            from google import genai
            from google.genai import types

            client = genai.Client()
            resp = client.models.generate_content(
                model=settings.gemini_model,
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                    "This is a passport data page. Return ONLY the two machine-readable zone (MRZ) lines, exactly as printed, "
                    "one per line, 44 characters each, using '<' for fillers. No other text.",
                ],
            )
            l1, l2 = _extract_mrz_lines(resp.text or "")
            return l1, l2, f"gemini:{settings.gemini_model}"
        except ToolError:
            raise
        except Exception:
            pass
    # 2) offline fallback for generated SPECIMEN images
    try:
        from PIL import Image

        im = Image.open(io.BytesIO(image_bytes))
        mrz = (getattr(im, "text", {}) or {}).get("mrz") or im.info.get("mrz")
        if mrz:
            l1, l2 = _extract_mrz_lines(mrz)
            return l1, l2, "offline-specimen-metadata (demo fallback, not OCR)"
    except Exception:
        pass
    raise ToolError("OCR_UNAVAILABLE", "Gemini is not configured and the image has no embedded specimen MRZ; pass mrz_text instead")


def parse_passport_image(image_b64: Optional[str] = None, mrz_text: Optional[str] = None, student_id: Optional[str] = None,
                         image_bytes: Optional[bytes] = None) -> dict:
    if mrz_text:
        l1, l2 = _extract_mrz_lines(mrz_text)
        method = "mrz_text"
    else:
        raw = image_bytes
        if raw is None:
            if not image_b64:
                raise ToolError("MISSING_INPUT", "provide image (base64) or mrz_text")
            raw = base64.b64decode(image_b64.split(",")[-1])
        l1, l2, method = mrz_from_image(raw)
    parsed = parse_td3(l1, l2)
    parsed["extraction"] = method
    flags = []
    if not parsed["valid"]:
        bad = [k for k, v in parsed["check_digits"].items() if not v]
        flags.append({"severity": "high", "code": "CHECK_DIGIT_FAILED", "message": f"MRZ check digit(s) failed: {', '.join(bad)} - possible misread or altered document; verify the original"})
    if student_id:
        from .visa import get_student_record

        st = get_student_record(student_id)
        parsed["student_id"] = student_id
        def norm(x):
            return re.sub(r"[^A-Z]", "", (x or "").upper())
        rec_tokens = {norm(x) for x in st["name"].split()} - {""}
        mrz_tokens = {norm(x) for x in (parsed["given_names"] + " " + parsed["surname"]).split()} - {""}
        if rec_tokens and not rec_tokens <= mrz_tokens:
            flags.append({"severity": "medium", "code": "NAME_MISMATCH", "message": f"Name on record '{st['name']}' does not match passport '{parsed['given_names']} {parsed['surname']}'"})
        if st.get("passport_no") and st["passport_no"] != parsed["document_number"]:
            flags.append({"severity": "medium", "code": "NUMBER_MISMATCH", "message": f"Passport number on record {st['passport_no']} != MRZ {parsed['document_number']}"})
        if st.get("dob") and parsed["date_of_birth"] and st["dob"] != parsed["date_of_birth"]:
            flags.append({"severity": "medium", "code": "DOB_MISMATCH", "message": "Date of birth differs from record"})
        exp = parsed["expiry_date"]
        if exp and st.get("pass_expiry") and exp < st["pass_expiry"]:
            flags.append({"severity": "high", "code": "PASSPORT_EXPIRES_BEFORE_PASS", "message": f"Passport expires {exp}, before the student pass ({st['pass_expiry']}) - renew the passport before the pass renewal (R-PASSPORT)"})
        if exp:
            days = (date.fromisoformat(exp) - settings.now().date()).days
            if days < 183:
                flags.append({"severity": "high" if days < 90 else "medium", "code": "PASSPORT_EXPIRING", "message": f"Passport expires in {days} days"})
    parsed["flags"] = flags
    parsed["ok"] = not flags
    return parsed
