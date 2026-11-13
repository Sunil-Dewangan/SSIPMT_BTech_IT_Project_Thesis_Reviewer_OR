"""
PDF Report Generator - SSIPMT B.Tech Project Report Reviewer
Uses fpdf2.

Every table and paragraph is word-wrapped and measured before it is drawn, so no text is
cut off or runs past the page edge. The full review report mirrors every section shown on
the web page (issues, priority actions, format checks, front matter, chapters, technical
elements, abstract, references, language, strengths).
"""
from fpdf import FPDF
from datetime import datetime
import io

SSIPMT = "Shri Shankaracharya Institute of Professional Management & Technology, Raipur"

WEIGHT_NAMES = {
    "format": "Format Compliance", "front_matter": "Front Matter", "chapters": "Chapter Content",
    "technical": "Technical Elements", "abstract": "Abstract Quality",
    "references": "References", "language": "Language & Writing",
}

# Same decision bands as the web app (override_recommendation in app.py).
RUBRIC_ROWS = [
    ("APPROVED", ">= 95", "All SSIPMT formatting, structural (14 chapters, front matter, 40-150 pages), technical (DFDs, ER diagram, algorithms, 8 testing types) and IEEE reference standards met exceptionally. Ready for final submission."),
    ("MINOR REVISION", "75 - 94", "Most requirements met with only minor gaps in formatting, captions, abstract word count (300-500 words) or citation details. Student must correct the highlighted issues before final sign-off."),
    ("MAJOR REVISION", "40 - 74", "Multiple thin chapters (< 2 pages), unverifiable or missing technical diagrams (DFD Level 0/1/2, ER, Waterfall, testing tables), reference gaps (< 15 total or < 10 peer-reviewed) or first-person writing. Requires substantial revision and re-review."),
    ("REJECTED", "< 40", "Critical failures throughout: missing mandatory chapters, severe structural non-compliance, placeholder text or lack of technical implementation. Must be rewritten and resubmitted."),
]

NAVY = (30, 58, 138)
LIGHT = (249, 250, 251)
GREEN = (22, 163, 74)
BLUE = (37, 99, 235)
ORANGE = (194, 65, 12)
RED = (220, 38, 38)
GREY = (100, 100, 100)

_R = {
    '—': '-', '–': '-', '‒': '-', '‑': '-', '‐': '-',
    '…': '...', '“': '"', '”': '"', '‘': "'", '’': "'",
    '•': '*', '‣': '*', '●': '*', '→': '->', '←': '<-',
    '≥': '>=', '≤': '<=', '×': 'x', '÷': '/',
    '✓': 'Yes', '✗': 'No', '°': 'deg', '®': '(R)',
    '©': '(C)', '±': '+/-', '≈': '~=', '≠': '!=',
    '∞': 'inf', ' ': ' ', '​': '', '‎': '', '‏': '', '﻿': '',
    '″': '"', '′': "'", 'é': 'e', 'è': 'e', 'ê': 'e',
    'à': 'a', 'â': 'a', 'ä': 'a', 'ö': 'o', 'ü': 'u', 'ß': 'ss',
}


def safe(text):
    if text is None:
        return ""
    if isinstance(text, (list, tuple)):
        text = "; ".join(str(t) for t in text)
    text = str(text)
    for ch, rep in _R.items():
        text = text.replace(ch, rep)
    return text.encode('latin-1', 'replace').decode('latin-1')


def sc(s):
    s = s or 0
    if s >= 85:
        return GREEN
    if s >= 75:
        return BLUE
    if s >= 40:
        return ORANGE
    return RED


def rec_color(rec):
    return {"APPROVED": GREEN, "MINOR_REVISION": BLUE, "MAJOR_REVISION": ORANGE, "REJECTED": RED}.get(rec, GREY)


def rec_bg(rec):
    return {"APPROVED": (220, 252, 231), "MINOR_REVISION": (219, 234, 254),
            "MAJOR_REVISION": (254, 215, 170), "REJECTED": (254, 226, 226)}.get(rec, (243, 244, 246))


def _num(v, default=0):
    try:
        return int(round(float(v)))
    except Exception:
        return default


def _ch_avg(review):
    chs = review.get("chapters", []) or []
    return round(sum(_num(c.get("score", 0)) for c in chs) / len(chs)) if chs else 0


def _as_list(v):
    if v is None or v == "":
        return []
    if isinstance(v, (list, tuple)):
        return [x for x in v if x not in (None, "")]
    return [v]


class BasePDF(FPDF):
    LM = 15
    RM = 15

    def __init__(self, session="2026-27", orientation="P"):
        super().__init__(orientation=orientation, unit="mm", format="A4")
        self.session = session or "2026-27"
        self.set_auto_page_break(auto=False)
        self.set_margins(self.LM, 20, self.RM)
        self.bottom = 16          # keep-clear zone above footer (mm)

    # ---- geometry -------------------------------------------------------
    @property
    def cw(self):
        return self.w - self.l_margin - self.r_margin

    @property
    def y_limit(self):
        return self.h - self.bottom

    def ensure(self, h):
        """Start a new page when fewer than h mm remain."""
        if self.get_y() + h > self.y_limit:
            self.add_page()
            return True
        return False

    # ---- page furniture --------------------------------------------------
    def header(self):
        dept_line = f"Department of Information Technology  |  Session {self.session}"
        self.set_fill_color(*NAVY)
        self.rect(0, 0, self.w, 14, "F")
        self.set_font("Helvetica", "B", 7)
        self.set_text_color(255, 255, 255)
        txt = safe(SSIPMT + "  |  " + dept_line)
        while self.get_string_width(txt) > self.w - 10 and len(txt) > 10:
            txt = txt[:-4] + "..."
        self.set_xy(0, 4)
        self.cell(self.w, 6, txt, align="C")
        self.set_text_color(0, 0, 0)
        self.set_y(19)

    def footer(self):
        self.set_y(-11)
        self.set_x(self.l_margin)
        self.set_font("Helvetica", "I", 7)
        self.set_text_color(150, 150, 150)
        self.cell(self.cw, 5, safe(f"Page {self.page_no()}  |  Generated {datetime.now().strftime('%d %B %Y')}  |  AI-generated review - SSIPMT Dept. of IT"), align="C")
        self.set_text_color(0, 0, 0)

    # ---- text measuring ---------------------------------------------------
    def wrap(self, text, width, style="", size=8):
        """Greedy word wrap that also breaks over-long words. Returns list of lines."""
        self.set_font("Helvetica", style, size)
        text = safe(text)
        out = []
        for raw in text.split("\n"):
            words = raw.split(" ")
            line = ""
            for w in words:
                if w == "":
                    continue
                while self.get_string_width(w) > width and len(w) > 1:
                    # hard-split a word wider than the cell
                    k = len(w)
                    while k > 1 and self.get_string_width(w[:k]) > width:
                        k -= 1
                    if line:
                        out.append(line)
                        line = ""
                    out.append(w[:k])
                    w = w[k:]
                cand = (line + " " + w).strip()
                if self.get_string_width(cand) <= width:
                    line = cand
                else:
                    if line:
                        out.append(line)
                    line = w
            out.append(line)
        return out or [""]

    # ---- building blocks --------------------------------------------------
    def sec(self, text):
        self.ensure(22)
        self.ln(2)
        self.set_x(self.l_margin)
        self.set_fill_color(*NAVY)
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 9)
        self.cell(self.cw, 6.5, safe("  " + text), fill=True)
        self.ln(6.5)
        self.set_text_color(0, 0, 0)
        self.ln(1.5)

    def sub(self, text, color=NAVY):
        self.ensure(12)
        self.set_x(self.l_margin)
        self.set_font("Helvetica", "B", 8.5)
        self.set_text_color(*color)
        self.cell(self.cw, 5, safe(text))
        self.ln(5)
        self.set_text_color(0, 0, 0)

    def para(self, text, size=8.5, style="", color=(40, 40, 40), indent=0, lh=4.3, bullet=None, width=None, gap_after=0.8):
        """Word-wrapped paragraph; breaks across pages line by line."""
        if text is None or str(text).strip() == "":
            return
        avail = (width or self.cw) - indent
        bw = 0
        if bullet:
            self.set_font("Helvetica", "B", size)
            bw = self.get_string_width(bullet + " ") + 1
        lines = self.wrap(text, avail - bw, style, size)
        self.set_text_color(*color)
        for i, ln_ in enumerate(lines):
            self.ensure(lh + 0.5)
            self.set_x(self.l_margin + indent)
            if bullet and i == 0:
                self.set_font("Helvetica", "B", size)
                self.cell(bw, lh, safe(bullet))
            elif bw > 0:
                self.cell(bw, lh, "")
            self.set_font("Helvetica", style, size)
            self.cell(avail - bw, lh, ln_)
            self.ln(lh)
        self.set_text_color(0, 0, 0)
        self.ln(gap_after)

    def bul(self, text, color=(80, 30, 20), indent=3, size=8.5):
        self.para(text, size=size, color=color, indent=indent, bullet="-")

    def boxed(self, text, fill=(239, 246, 255), size=8.5, style="I", lh=4.4):
        lines = self.wrap(text, self.cw - 6, style, size)
        h = len(lines) * lh + 4
        self.ensure(min(h, 40))
        x = self.l_margin
        y = self.get_y()
        # box may span pages: draw per chunk
        i = 0
        while i < len(lines):
            room = int((self.y_limit - self.get_y() - 4) // lh)
            if room < 1:
                self.add_page()
                continue
            chunk = lines[i:i + room]
            hh = len(chunk) * lh + 4
            self.set_fill_color(*fill)
            self.set_draw_color(180, 190, 210)
            self.rect(x, self.get_y(), self.cw, hh, "DF")
            self.set_y(self.get_y() + 2)
            self.set_font("Helvetica", style, size)
            for l in chunk:
                self.set_x(x + 3)
                self.cell(self.cw - 6, lh, l)
                self.ln(lh)
            self.set_y(self.get_y() + 2)
            i += len(chunk)
        self.set_draw_color(0, 0, 0)
        self.ln(1.5)

    def table(self, headers, rows, widths, aligns=None, lh=4.0, size=8, head_size=8, repeat_header=True, zebra=True):
        """
        rows: list of rows; each cell is a str or dict(text, color, style, fill, size).
        widths: relative or absolute mm values (scaled to the content width).
        Rows never overflow the cell: the row height follows the tallest wrapped cell.
        """
        tot = float(sum(widths))
        widths = [w * self.cw / tot for w in widths]
        aligns = aligns or ["L"] * len(widths)
        pad = 1.2

        def draw_head():
            self.ensure(10)
            self.set_x(self.l_margin)
            self.set_font("Helvetica", "B", head_size)
            self.set_fill_color(*NAVY)
            self.set_text_color(255, 255, 255)
            hl = [self.wrap(h, w - 2 * pad, "B", head_size) for h, w in zip(headers, widths)]
            hh = max(len(x) for x in hl) * lh + 2 * pad - 0.4
            x = self.l_margin
            y = self.get_y()
            for h_lines, w, al in zip(hl, widths, aligns):
                self.rect(x, y, w, hh, "DF")
                yy = y + pad - 0.2
                for l in h_lines:
                    self.set_xy(x + pad, yy)
                    self.set_font("Helvetica", "B", head_size)
                    self.cell(w - 2 * pad, lh, l, align="C" if al != "L" else "L")
                    yy += lh
                x += w
            self.set_y(y + hh)
            self.set_text_color(0, 0, 0)

        if headers:
            draw_head()
        for ri, row in enumerate(rows):
            cells = []
            for c, w in zip(row, widths):
                d = c if isinstance(c, dict) else {"text": c}
                st = d.get("style", "")
                sz = d.get("size", size)
                cells.append((d, self.wrap(d.get("text", ""), w - 2 * pad, st, sz)))
            h = max(len(l) for _, l in cells) * lh + 2 * pad
            if self.get_y() + h > self.y_limit:
                self.add_page()
                if headers and repeat_header:
                    draw_head()
            x = self.l_margin
            y = self.get_y()
            for (d, lines_), w, al in zip(cells, widths, aligns):
                fill = d.get("fill") or ((255, 255, 255) if (ri % 2 == 0 or not zebra) else LIGHT)
                self.set_fill_color(*fill)
                self.set_draw_color(190, 190, 190)
                self.rect(x, y, w, h, "DF")
                self.set_text_color(*d.get("color", (30, 30, 30)))
                yy = y + pad
                for l in lines_:
                    self.set_font("Helvetica", d.get("style", ""), d.get("size", size))
                    self.set_xy(x + pad, yy)
                    self.cell(w - 2 * pad, lh, l, align={"L": "L", "C": "C", "R": "R"}[al])
                    yy += lh
                x += w
            self.set_y(y + h)
        self.set_text_color(0, 0, 0)
        self.set_draw_color(0, 0, 0)
        self.ln(2)

    def rubric_table(self):
        rows = []
        for lbl, rng, crit in RUBRIC_ROWS:
            col = rec_color(lbl.replace(" ", "_"))
            rows.append([{"text": lbl, "color": col, "style": "B"}, {"text": rng, "style": "B"}, {"text": crit, "size": 7.5}])
        self.table(["Decision", "Score", "Evaluation Criteria"], rows, [30, 18, 132], ["L", "C", "L"], lh=3.8, size=7.5, head_size=7.5)

    def score_banner(self, score, rec, details):
        """Score box | decision box | details box - all wrapped to their own width."""
        widths = [34, 62, self.cw - 96]
        rb, rc = rec_bg(rec), rec_color(rec)
        dl = self.wrap(details, widths[2] - 6, "", 8)
        h = max(22, len(dl) * 4.2 + 6)
        self.ensure(h + 4)
        x = self.l_margin
        y = self.get_y()
        self.set_draw_color(150, 150, 150)
        self.set_fill_color(*NAVY)
        self.rect(x, y, widths[0], h, "DF")
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 28)
        self.set_xy(x, y + h / 2 - 6)
        self.cell(widths[0], 12, safe(str(score)), align="C")
        self.set_fill_color(*rb)
        self.rect(x + widths[0], y, widths[1], h, "DF")
        self.set_text_color(*rc)
        label = safe(str(rec).replace("_", " "))
        self.set_font("Helvetica", "B", 12)
        self.set_xy(x + widths[0], y + h / 2 - 3)
        self.cell(widths[1], 6, label, align="C")
        self.set_fill_color(248, 250, 252)
        self.rect(x + widths[0] + widths[1], y, widths[2], h, "DF")
        self.set_text_color(60, 60, 60)
        self.set_font("Helvetica", "", 8)
        yy = y + (h - len(dl) * 4.2) / 2
        for l in dl:
            self.set_xy(x + widths[0] + widths[1] + 3, yy)
            self.cell(widths[2] - 6, 4.2, l)
            yy += 4.2
        self.set_text_color(0, 0, 0)
        self.set_draw_color(0, 0, 0)
        self.set_y(y + h + 2)


def _dims(review, weights):
    ch_avg = _ch_avg(review)
    g = lambda k: _num((review.get(k) or {}).get("score", 0))
    return [
        ("Format Compliance", g("format_compliance"), weights.get("format", 15)),
        ("Front Matter", g("front_matter"), weights.get("front_matter", 10)),
        ("Chapter Content", ch_avg, weights.get("chapters", 25)),
        ("Technical Elements", g("technical_elements"), weights.get("technical", 20)),
        ("Abstract Quality", g("abstract"), weights.get("abstract", 5)),
        ("References", g("references"), weights.get("references", 15)),
        ("Language & Writing", g("language_quality"), weights.get("language", 10)),
    ]


def _assess(score, long=False):
    if score >= 80:
        return "Good - meets standard" if long else "Good"
    if score >= 60:
        return "Needs improvement"
    return "Significant revision required" if long else "Significant work required"


def _dimension_table(pdf, review, weights):
    rows = []
    for name, score, wt in _dims(review, weights):
        rows.append([name, {"text": str(score), "color": sc(score), "style": "B"}, {"text": f"{wt}%"}, _assess(score)])
    pdf.table(["Dimension", "Score", "Weight", "Assessment"], rows, [70, 20, 20, 70], ["L", "C", "C", "L"], lh=4.2, size=8.5)


def _students(review):
    s = review.get("student_names") or ["-"]
    return ", ".join(str(x) for x in s) if isinstance(s, (list, tuple)) else str(s)


def _status_cell(status):
    st = str(status or "CANNOT_VERIFY").upper()
    col = {"PASS": GREEN, "FAIL": RED, "WARNING": ORANGE, "CANNOT_VERIFY": GREY}.get(st, GREY)
    return {"text": {"PASS": "PASS", "FAIL": "FAIL", "WARNING": "WARNING", "CANNOT_VERIFY": "UNVERIFIED"}.get(st, st), "color": col, "style": "B", "size": 7.5}


# ======================================================================
#  FULL REVIEW REPORT  (mirrors the web page, every detail)
# ======================================================================
def generate_full_report(review: dict, weights: dict, weighted_score: int, recommendation: str = None, meta: dict = None) -> bytes:
    meta = meta or {}
    session = meta.get("session", "2026-27")
    sub_name = meta.get("sub_name", "-")
    sub_code = meta.get("sub_code", "-")
    sem_lbl = meta.get("semester_label", "-")
    fulfillment = meta.get("fulfillment", "-")
    weights = weights or {}

    pdf = BasePDF(session=session)
    pdf.add_page()
    rec = recommendation or review.get("overall_recommendation", "")
    date_str = datetime.now().strftime("%d %B %Y")

    pdf.ln(1)
    pdf.set_font("Helvetica", "B", 15)
    pdf.set_text_color(*NAVY)
    pdf.cell(pdf.cw, 9, "B.Tech Project Report - AI Review", align="C")
    pdf.ln(9)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*GREY)
    pdf.cell(pdf.cw, 5, safe(f"Academic Session: {session}  |  {sem_lbl}  |  {date_str}"), align="C")
    pdf.ln(6)
    pdf.set_text_color(0, 0, 0)

    # ---- Report information
    pdf.sec("Report Information")
    sem_txt = f"{sem_lbl} ({fulfillment})" if fulfillment and fulfillment != "-" else sem_lbl
    info = [("Project Title", review.get("project_title", "-")), ("Student(s)", _students(review)),
            ("Guide", review.get("guide_name", "-")), ("Academic Session", session), ("Semester", sem_txt),
            ("Subject", f"{sub_name} ({sub_code})"), ("Report Type", review.get("report_type", "B.Tech Project Report"))]
    pdf.table(None, [[{"text": k, "style": "B"}, v] for k, v in info], [40, 140], lh=4.4, size=8.5)

    # ---- Score summary
    pdf.sec("Score Summary")
    pdf.score_banner(weighted_score, rec, f"Weighted score: {weighted_score}/100\nAI raw score: {_num(review.get('overall_score', 0))}/100\nSubject: {sub_name} ({sub_code})")
    if review.get("executive_summary"):
        pdf.boxed(review.get("executive_summary"))
    pdf.set_font("Helvetica", "I", 7)
    pdf.set_text_color(*GREY)
    pdf.para("Thresholds: >=95 APPROVED | 75-94 MINOR REVISION | 40-74 MAJOR REVISION | <40 REJECTED", size=7, style="I", color=GREY)

    # ---- Dimensions
    pdf.sec("Dimension Score Breakdown & Weightage (Total: 100%)")
    _dimension_table(pdf, review, weights)

    # ---- Rubric
    pdf.sec("Decision Rubric & Evaluation Criteria")
    pdf.rubric_table()

    # ---- Issues
    for key, label, col in (("critical_issues", "Critical Issues - Must Fix Before Submission", (127, 29, 29)),
                            ("major_issues", "Major Issues - Significant Corrections Required", (124, 45, 18)),
                            ("minor_issues", "Minor Issues - Recommended Improvements", (113, 63, 18))):
        items = _as_list(review.get(key))
        if items:
            pdf.sec(f"{label} ({len(items)})")
            for it in items:
                pdf.bul(it, color=col)

    # ---- Priority action list
    pal = [a for a in _as_list(review.get("priority_action_list")) if isinstance(a, dict)]
    if pal:
        pdf.sec("Priority Action List")
        rows = []
        for i, a in enumerate(pal):
            sev = str(a.get("severity", "")).upper()
            scol = {"CRITICAL": RED, "MAJOR": (234, 88, 12), "MINOR": BLUE}.get(sev, (0, 0, 0))
            rows.append([{"text": str(a.get("priority", i + 1)), "style": "B"}, a.get("action", ""), a.get("location", ""),
                         {"text": sev, "color": scol, "style": "B", "size": 7.5}])
        pdf.table(["#", "Action Required", "Location", "Severity"], rows, [8, 100, 46, 22], ["C", "L", "L", "C"], lh=4.0, size=8)

    # ---- Format compliance
    fc = review.get("format_compliance") or {}
    if fc.get("checks"):
        pdf.sec(f"Format Compliance - Score: {_num(fc.get('score', 0))}")
        rows = []
        for c in fc["checks"]:
            if not isinstance(c, dict):
                continue
            rows.append([_status_cell(c.get("status")), {"text": c.get("item", c.get("check", c.get("name", "?"))), "style": "B"},
                         c.get("detail", c.get("description", ""))])
        pdf.table(["Status", "Check", "Detail"], rows, [22, 55, 103], ["C", "L", "L"], lh=4.0, size=8)

    # ---- Front matter
    fm = review.get("front_matter") or {}
    if fm.get("sections"):
        pdf.sec(f"Front Matter - Score: {_num(fm.get('score', 0))}")
        rows = []
        for s in fm["sections"]:
            if not isinstance(s, dict):
                continue
            ok = bool(s.get("present", False))
            iss = s.get("issues")
            iss = "-" if (not iss or str(iss).strip().lower() in ("none", "none.")) else iss
            rows.append([s.get("name", s.get("section", "?")), {"text": "PRESENT" if ok else "MISSING", "color": GREEN if ok else RED, "style": "B", "size": 7.5}, iss])
        pdf.table(["Section", "Status", "Issues / Remarks"], rows, [48, 22, 110], ["L", "C", "L"], lh=4.0, size=8)

    # ---- Chapter by chapter
    chs = review.get("chapters") or []
    if chs:
        pdf.sec("Chapter-by-Chapter Review")
        rows = []
        for ch in chs:
            ok = bool(ch.get("present", False))
            warn = "" if ch.get("meets_2page_minimum", True) else "  (under 2-page minimum)"
            s_ = _num(ch.get("score", 0))
            rows.append([{"text": str(ch.get("number", "")), "style": "B"}, str(ch.get("title", "")) + warn,
                         {"text": "Yes" if ok else "MISSING", "color": GREEN if ok else RED, "style": "B"},
                         f"~{ch.get('estimated_pages', 0)}", {"text": str(s_), "color": sc(s_), "style": "B"}])
        pdf.table(["#", "Chapter", "Present", "~Pages", "Score"], rows, [10, 100, 24, 22, 24], ["C", "L", "C", "C", "C"], lh=4.0, size=8)
        for ch in chs:
            s_ = _num(ch.get("score", 0))
            pdf.ensure(30)
            pdf.sub(f"Ch.{ch.get('number', '?')}: {ch.get('title', 'Untitled')}   [Score {s_}  |  ~{ch.get('estimated_pages', 0)} pages  |  {'Present' if ch.get('present') else 'MISSING'}]", color=sc(s_))
            if ch.get("feedback"):
                pdf.para(ch["feedback"], size=8.3, indent=2)
            for i in _as_list(ch.get("issues")):
                pdf.bul(i, color=(127, 29, 29), indent=4, size=8.2)
            for i in _as_list(ch.get("strengths")):
                pdf.bul(i, color=(22, 101, 52), indent=4, size=8.2)
            pdf.ln(1)

    # ---- Technical elements
    te = review.get("technical_elements") or {}
    if te:
        pdf.sec(f"Technical Elements - Score: {_num(te.get('score', 0))}")
        rows = []
        for nm, k in [("DFD Level 0", "dfd_level0"), ("DFD Level 1", "dfd_level1"), ("DFD Level 2", "dfd_level2"),
                      ("ER Diagram", "er_diagram"), ("Database Table Structures", "table_structures"),
                      ("Algorithms", "algorithms"), ("Waterfall Model Diagram", "waterfall_diagram")]:
            el = te.get(k)
            if not isinstance(el, dict):
                continue
            present = bool(el.get("present", False))
            cnt = f" ({el['count']})" if "count" in el else ""
            extra = ""
            if k == "algorithms" and "properly_formatted" in el:
                extra = "Format OK. " if el.get("properly_formatted") else "Format not verified/incorrect. "
            iss = el.get("issues")
            iss = "" if (not iss or str(iss).strip().lower() in ("none", "none.")) else str(iss)
            rows.append([nm, {"text": ("PRESENT" if present else "MISSING") + cnt, "color": GREEN if present else RED, "style": "B", "size": 7.5}, (extra + iss).strip() or "-"])
        pdf.table(["Element", "Status", "Remarks"], rows, [44, 30, 106], ["L", "C", "L"], lh=4.0, size=8)
        tst = te.get("testing_types") or {}
        types = ", ".join(str(t) for t in (tst.get("types_found") or [])) or "None identified"
        pdf.para(f"Testing: {_num(tst.get('count', 0))}/8 types - {types}", size=8.5, style="B")
        if tst.get("issues"):
            pdf.para(str(tst.get("issues")), size=8.2, indent=3)

    # ---- Abstract
    ab = review.get("abstract") or {}
    if ab:
        pdf.sec(f"Abstract - Score: {_num(ab.get('score', 0))}")
        yn = lambda v: {"text": "Yes" if v else "No", "color": GREEN if v else RED, "style": "B"}
        rows = [["Word count (300-500)", f"~{_num(ab.get('estimated_word_count', 0))}", yn(ab.get("within_300_500"))],
                ["Keywords (5-8)", str(_num(ab.get("keyword_count", 0))), yn(ab.get("has_keywords"))],
                ["Covers problem", "", yn(ab.get("covers_problem"))],
                ["Covers solution", "", yn(ab.get("covers_solution"))],
                ["Covers technologies", "", yn(ab.get("covers_technologies"))],
                ["Covers results", "", yn(ab.get("covers_results"))],
                ["Free of citations", "", yn(not ab.get("has_citations"))]]
        pdf.table(["Check", "Value", "Result"], rows, [70, 50, 60], ["L", "C", "C"], lh=4.0, size=8)
        for i in _as_list(ab.get("issues")):
            pdf.bul(i, color=(127, 29, 29))
        if ab.get("feedback"):
            pdf.boxed(ab["feedback"], style="")

    # ---- References
    ref = review.get("references") or {}
    if ref:
        pdf.sec(f"References - Score: {_num(ref.get('score', 0))}")
        yn = lambda v: {"text": "Yes" if v else "No", "color": GREEN if v else RED, "style": "B"}
        rows = [["Total references (minimum 15)", str(_num(ref.get("total_count", 0))), yn(ref.get("meets_minimum_15"))],
                ["Peer-reviewed (minimum 10)", str(_num(ref.get("peer_reviewed_count", 0))), yn(ref.get("meets_10_peer_reviewed"))],
                ["IEEE format", str(ref.get("ieee_format", "?")), ""]]
        pdf.table(["Check", "Value", "Meets requirement"], rows, [80, 40, 60], ["L", "C", "C"], lh=4.0, size=8)
        for i in _as_list(ref.get("issues")):
            pdf.bul(i, color=(127, 29, 29))
        if ref.get("feedback"):
            pdf.boxed(ref["feedback"], style="")

    # ---- Language
    lq = review.get("language_quality") or {}
    if lq:
        pdf.sec(f"Language & Writing - Score: {_num(lq.get('score', 0))}")
        rows = [["Grammar", str(lq.get("grammar_quality", "-"))], ["Technical accuracy", str(lq.get("technical_accuracy", "-"))],
                ["Academic tone", str(lq.get("academic_tone", "-"))],
                ["Placeholder text", {"text": "FOUND - replace before submission", "color": RED, "style": "B"} if lq.get("placeholder_text_found") else {"text": "None found", "color": GREEN, "style": "B"}]]
        pdf.table(["Aspect", "Assessment"], rows, [60, 120], ["L", "L"], lh=4.0, size=8)
        fp = _as_list(lq.get("first_person_violations"))
        if fp:
            pdf.sub("First-person violations", color=ORANGE)
            for v in fp:
                pdf.bul('"' + str(v) + '"', color=(124, 45, 18), size=8.2)
        if lq.get("feedback"):
            pdf.boxed(lq["feedback"], style="")

    # ---- Strengths
    st_ = _as_list(review.get("strengths"))
    if st_:
        pdf.sec("Strengths")
        for s in st_:
            pdf.bul(s, color=(22, 101, 52))

    # ---- Sign-off
    pdf.ensure(48)
    pdf.sec("Reviewer Sign-off")
    pdf.ln(4)
    cw3 = pdf.cw / 3
    pdf.set_font("Helvetica", "", 9)
    for t in ("Reviewed by:", "Designation:", f"Date: {date_str}"):
        pdf.cell(cw3, 5, safe(t))
    pdf.ln(14)
    for t in ("_" * 30, "_" * 26, "_" * 16):
        pdf.cell(cw3, 4, t)
    pdf.ln(5)
    pdf.set_font("Helvetica", "I", 7)
    pdf.set_text_color(*GREY)
    for t in ("Name & Designation", "Department / SSIPMT Raipur", "Signature"):
        pdf.cell(cw3, 4, t)
    pdf.ln(8)
    pdf.para("This report was generated by an AI system. It is a review aid for supervising faculty. Final decisions remain with the Department of IT, SSIPMT Raipur.", size=7, style="I", color=(130, 130, 130))

    buf = io.BytesIO()
    pdf.output(buf)
    return buf.getvalue()


# ======================================================================
#  STUDENT REPORT CARD
# ======================================================================
def generate_report_card(review: dict, weights: dict, weighted_score: int, recommendation: str = None, meta: dict = None) -> bytes:
    meta = meta or {}
    session = meta.get("session", "2026-27")
    sub_name = meta.get("sub_name", "-")
    sub_code = meta.get("sub_code", "-")
    sem_lbl = meta.get("semester_label", "-")
    weights = weights or {}

    pdf = BasePDF(session=session)
    pdf.add_page()
    rec = recommendation or review.get("overall_recommendation", "")
    date_str = datetime.now().strftime("%d %B %Y")

    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(*NAVY)
    pdf.cell(pdf.cw, 8, "STUDENT REVIEW REPORT CARD", align="C")
    pdf.ln(8)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*GREY)
    sub_line = safe(f"Session: {session}  |  {sem_lbl}  |  Subject: {sub_name} ({sub_code})  |  {date_str}")
    for l in pdf.wrap(sub_line, pdf.cw, "", 8):
        pdf.cell(pdf.cw, 4.5, l, align="C")
        pdf.ln(4.5)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(2)

    info = [("Project", review.get("project_title", "-")), ("Student(s)", _students(review)), ("Guide", review.get("guide_name", "-")),
            ("Session / Semester", f"{session}  |  {sem_lbl}"), ("Subject", f"{sub_name} ({sub_code})")]
    pdf.table(None, [[{"text": k, "style": "B", "fill": (239, 246, 255)}, {"text": v, "fill": (255, 255, 255)}] for k, v in info], [36, 144], lh=4.4, size=8.5)

    pdf.score_banner(weighted_score, rec, f"Score: {weighted_score}/100\nAI raw: {_num(review.get('overall_score', 0))}/100\n>=95 Approved | 75-94 Minor\n40-74 Major | <40 Rejected")

    _dimension_table(pdf, review, weights)

    pdf.sub("Evaluation & Decision Rubric")
    pdf.rubric_table()

    pal = [a for a in _as_list(review.get("priority_action_list")) if isinstance(a, dict)]
    ci = _as_list(review.get("critical_issues"))
    mi = _as_list(review.get("major_issues"))
    if not pal:       # the priority table already carries the issues, so keep the card to one page
        pass
    else:
        ci, mi = [], []
    if ci:
        pdf.sub(f"Critical Issues ({len(ci)}) - must fix", color=RED)
        for i in ci:
            pdf.bul(i, color=(127, 29, 29), size=8)
    if mi:
        pdf.sub(f"Major Issues ({len(mi)})", color=ORANGE)
        for i in mi:
            pdf.bul(i, color=(124, 45, 18), size=8)

    if pal:
        pdf.sub("Priority Actions for Student")
        rows = []
        for i, a in enumerate(pal):
            sev = str(a.get("severity", "")).upper()
            scol = {"CRITICAL": RED, "MAJOR": (234, 88, 12), "MINOR": BLUE}.get(sev, (0, 0, 0))
            bg = {"CRITICAL": (254, 242, 242), "MAJOR": (255, 247, 237), "MINOR": (239, 246, 255)}.get(sev, LIGHT)
            rows.append([{"text": str(a.get("priority", i + 1)), "style": "B", "fill": bg},
                         {"text": sev, "color": scol, "style": "B", "size": 7.5, "fill": bg},
                         {"text": a.get("action", ""), "fill": bg}, {"text": a.get("location", ""), "fill": bg}])
        pdf.table(["#", "Severity", "Action", "Location"], rows, [7, 20, 105, 48], ["C", "C", "L", "L"], lh=3.9, size=7.8, zebra=False)

    pdf.ensure(32)
    pdf.ln(3)
    pdf.set_draw_color(180, 180, 180)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(3)
    cw3 = pdf.cw / 3
    pdf.set_font("Helvetica", "", 8.5)
    for t in ("Reviewer:", "Dept. of IT, SSIPMT Raipur", f"Date: {date_str}"):
        pdf.cell(cw3, 5, safe(t))
    pdf.ln(12)
    for t in ("_" * 30, "_" * 26, "_" * 16):
        pdf.cell(cw3, 4, t)
    pdf.ln(5)
    pdf.set_font("Helvetica", "I", 7)
    pdf.set_text_color(*GREY)
    for t in ("Name & Signature", "Department Stamp", "Signature"):
        pdf.cell(cw3, 4, t)

    buf = io.BytesIO()
    pdf.output(buf)
    return buf.getvalue()


# ======================================================================
#  BATCH COMPARISON TABLE  (landscape, wrapped)
# ======================================================================
def _ws(review, weights):
    wt = weights or {}
    total = sum(wt.values()) or 1
    ch_avg = _ch_avg(review)
    g = lambda k: _num((review.get(k) or {}).get("score", 0))
    dim = {"format": g("format_compliance"), "front_matter": g("front_matter"), "chapters": ch_avg,
           "technical": g("technical_elements"), "abstract": g("abstract"), "references": g("references"), "language": g("language_quality")}
    return round(sum(dim.get(k, 0) * (wt.get(k, 0) / total) for k in wt))


def _decision(score):
    return "APPROVED" if score >= 95 else "MINOR_REVISION" if score >= 75 else "MAJOR_REVISION" if score >= 40 else "REJECTED"


def generate_comparison_table(batch_results: list, weights: dict, meta: dict = None) -> bytes:
    meta = meta or {}
    session = meta.get("session", "2026-27")
    sub_name = meta.get("sub_name", "-")
    sub_code = meta.get("sub_code", "-")
    sem_lbl = meta.get("semester_label", "-")
    weights = weights or {}

    pdf = BasePDF(session=session, orientation="L")
    pdf.add_page()
    date_str = datetime.now().strftime("%d %B %Y")
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(*NAVY)
    pdf.cell(pdf.cw, 8, "BATCH REVIEW COMPARISON TABLE", align="C")
    pdf.ln(8)
    done = [r for r in batch_results if not r.get("error")]
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*GREY)
    pdf.cell(pdf.cw, 5, safe(f"Session: {session}  |  {sem_lbl}  |  Subject: {sub_name} ({sub_code})  |  Generated {date_str} ({len(done)} report(s))"), align="C")
    pdf.ln(7)
    pdf.set_text_color(0, 0, 0)
    wt_note = "Weights: " + " | ".join(f"{WEIGHT_NAMES[k]}={v}%" for k, v in weights.items() if k in WEIGHT_NAMES)
    pdf.boxed(wt_note, size=7.5)
    pdf.rubric_table()
    pdf.ln(1)

    rows = []
    for i, r in enumerate(batch_results):
        if r.get("error"):
            rows.append([str(i + 1), r.get("file", ""), {"text": "ERROR: " + str(r.get("error", "")), "color": RED}, "", "", "", "", "", "", "", "", ""])
            continue
        rv = r["review"]
        ws = _ws(rv, weights)
        g = lambda k: _num((rv.get(k) or {}).get("score", 0))
        cell = lambda v: {"text": str(v), "color": sc(v), "style": "B"}
        rec = _decision(ws)
        rows.append([str(i + 1), r.get("file", ""), _students(rv), str(rv.get("project_title", "")), cell(ws),
                     {"text": rec.replace("_", " "), "color": rec_color(rec), "style": "B", "size": 7},
                     cell(g("format_compliance")), cell(g("front_matter")), cell(_ch_avg(rv)), cell(g("technical_elements")),
                     cell(g("abstract")), cell(g("references")), cell(g("language_quality"))])
    pdf.table(["#", "File", "Student(s)", "Title", "Score", "Decision", "Fmt", "FM", "Ch", "Tech", "Abs", "Ref", "Lang"],
              [r + [""] * (13 - len(r)) for r in rows],
              [6, 38, 40, 48, 12, 26, 9, 9, 9, 10, 9, 9, 10],
              ["C", "L", "L", "L", "C", "C", "C", "C", "C", "C", "C", "C", "C"], lh=3.8, size=7.5, head_size=7.5)
    buf = io.BytesIO()
    pdf.output(buf)
    return buf.getvalue()
