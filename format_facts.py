"""
Reads layout facts straight from the uploaded DOCX/PDF so the AI reviewer can verify format rules
(header, page setup, fonts, captions, algorithm box, images) that plain text extraction cannot show.
Only the standard library (and Pillow / PyMuPDF if present) is needed.
"""
import io, re, zipfile
from collections import Counter
import xml.etree.ElementTree as ET

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
RNS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
q = lambda t: "{%s}%s" % (W, t)


def _txt(el):
    return "".join(t.text or "" for t in el.iter(q("t")))


def _mm(tw):
    try:
        return round(int(tw) / 1440 * 25.4, 1)
    except Exception:
        return None


def _inch(tw):
    try:
        return round(int(tw) / 1440, 2)
    except Exception:
        return None


class _Styles:
    def __init__(self, root):
        self.by = {}
        self.def_sz = None
        self.def_font = None
        if root is None:
            return
        dd = root.find(q("docDefaults"))
        if dd is not None:
            rp = dd.find(q("rPrDefault") + "/" + q("rPr"))
            if rp is not None:
                s = rp.find(q("sz")); f = rp.find(q("rFonts"))
                self.def_sz = int(s.get(q("val"))) / 2 if s is not None else None
                self.def_font = f.get(q("ascii")) if f is not None else None
        for st in root.findall(q("style")):
            sid = st.get(q("styleId"))
            rp = st.find(q("rPr")); pp = st.find(q("pPr"))
            d = {"based": (st.find(q("basedOn")).get(q("val")) if st.find(q("basedOn")) is not None else None), "sz": None, "font": None, "b": None, "jc": None}
            if rp is not None:
                s = rp.find(q("sz")); f = rp.find(q("rFonts")); b = rp.find(q("b"))
                d["sz"] = int(s.get(q("val"))) / 2 if s is not None else None
                d["font"] = f.get(q("ascii")) if f is not None else None
                d["b"] = (b is not None and b.get(q("val")) not in ("0", "false"))
            if pp is not None and pp.find(q("jc")) is not None:
                d["jc"] = pp.find(q("jc")).get(q("val"))
            self.by[sid] = d

    def resolve(self, sid, key):
        seen = 0
        while sid and seen < 8:
            d = self.by.get(sid)
            if not d:
                break
            if d.get(key) is not None:
                return d[key]
            sid = d["based"]; seen += 1
        return None


def _run_props(p, styles):
    """(font, size, bold) of the dominant text run of a paragraph."""
    sid = None
    ppr = p.find(q("pPr"))
    if ppr is not None and ppr.find(q("pStyle")) is not None:
        sid = ppr.find(q("pStyle")).get(q("val"))
    best = None
    for r in p.iter(q("r")):
        t = _txt(r)
        if not t.strip():
            continue
        rp = r.find(q("rPr"))
        font = size = bold = None
        if rp is not None:
            f = rp.find(q("rFonts")); s = rp.find(q("sz")); b = rp.find(q("b"))
            font = f.get(q("ascii")) if f is not None else None
            size = int(s.get(q("val"))) / 2 if s is not None else None
            bold = (b is not None and b.get(q("val")) not in ("0", "false")) if b is not None else None
        font = font or styles.resolve(sid, "font") or styles.def_font
        size = size or styles.resolve(sid, "sz") or styles.def_sz
        if bold is None:
            bold = bool(styles.resolve(sid, "b"))
        if best is None or len(t) > best[3]:
            best = (font, size, bold, len(t))
    return best[:3] if best else (None, None, None)


def _jc(p, styles):
    ppr = p.find(q("pPr"))
    if ppr is not None and ppr.find(q("jc")) is not None:
        return ppr.find(q("jc")).get(q("val"))
    sid = ppr.find(q("pStyle")).get(q("val")) if ppr is not None and ppr.find(q("pStyle")) is not None else None
    return styles.resolve(sid, "jc") or "left"


def _fmt(t):
    f, s, b = t
    return f"{f or '?'} {('%g' % s) if s else '?'}pt {'bold' if b else 'regular'}"


def _mode(vals):
    vals = [v for v in vals if v is not None]
    return Counter(vals).most_common(1)[0] if vals else (None, 0)


def docx_format_facts(raw: bytes) -> str:
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
        doc = ET.fromstring(z.read("word/document.xml"))
    except Exception as e:
        return f"(format facts unavailable: {e})"
    styles = _Styles(ET.fromstring(z.read("word/styles.xml")) if "word/styles.xml" in z.namelist() else None)
    body = doc.find(q("body"))
    out = []

    # ---- sections: page size, margins, border, header / footer
    rels = {}
    if "word/_rels/document.xml.rels" in z.namelist():
        for r in ET.fromstring(z.read("word/_rels/document.xml.rels")):
            rels[r.get("Id")] = r.get("Target")
    sects = list(body.iter(q("sectPr")))
    sizes, margins, borders, hdr_txt, hdr_props, ftr_page = Counter(), Counter(), 0, [], [], 0
    for sp in sects:
        sz = sp.find(q("pgSz")); mg = sp.find(q("pgMar"))
        if sz is not None:
            sizes[(_mm(sz.get(q("w"))), _mm(sz.get(q("h"))))] += 1
        if mg is not None:
            margins[tuple(_inch(mg.get(q(k))) for k in ("top", "bottom", "left", "right"))] += 1
        if sp.find(q("pgBorders")) is not None:
            borders += 1
        hrefs = sp.findall(q("headerReference")); frefs = sp.findall(q("footerReference"))
        txt, props = "", None
        for h in hrefs:
            tgt = rels.get(h.get("{%s}id" % RNS))
            if tgt and ("word/" + tgt) in z.namelist():
                hx = ET.fromstring(z.read("word/" + tgt))
                t = _txt(hx).strip()
                if t:
                    txt = t
                    for p in hx.iter(q("p")):
                        if _txt(p).strip():
                            props = _run_props(p, styles); hj = _jc(p, styles); props = props + (hj,); break
        hdr_txt.append(txt); hdr_props.append(props)
        for f in frefs:
            tgt = rels.get(f.get("{%s}id" % RNS))
            if tgt and ("word/" + tgt) in z.namelist() and "PAGE" in z.read("word/" + tgt).decode("utf8", "ignore"):
                ftr_page += 1; break
    n = len(sects)
    out.append("PAGE SETUP")
    for (w_, h_), c in sizes.items():
        out.append(f"- Paper size {w_} x {h_} mm ({'A4' if abs(w_-210)<1 and abs(h_-297)<1 else 'not A4'}) in {c} of {n} sections")
    for m, c in margins.most_common(3):
        out.append(f"- Margins top/bottom/left/right (inches): {m[0]}/{m[1]}/{m[2]}/{m[3]} in {c} of {n} sections")
    out.append(f"- Page border (box) defined in {borders} of {n} sections")
    with_h = [t for t in hdr_txt if t]
    out.append("INSTITUTE HEADER")
    if with_h:
        p0 = next(p for p in hdr_props if p)
        out.append(f"- Header text present in {len(with_h)} of {n} sections: \"{with_h[0][:110]}\"")
        out.append(f"- Header font: {_fmt(p0[:3])}, alignment {p0[3]}")
        out.append(f"- Sections without header: {n-len(with_h)} (cover page and chapter-separator pages are meant to have none)")
    else:
        out.append("- No header text found in any section")
    out.append(f"- Page-number footer present in {ftr_page} of {n} sections")

    # ---- body paragraphs
    paras = [p for p in body.findall(q("p"))]
    allp = list(body.iter(q("p")))
    long_p = [p for p in paras if len(_txt(p)) > 120]
    fonts = Counter(); sizes_ = Counter(); lines = Counter(); after = Counter(); before = Counter(); jcs = Counter()
    for p in long_p:
        f, s, b = _run_props(p, styles)
        fonts[f] += 1; sizes_[s] += 1; jcs[_jc(p, styles)] += 1
        sp_ = p.find(q("pPr") + "/" + q("spacing"))
        if sp_ is not None:
            ln = sp_.get(q("line")); rule = sp_.get(q("lineRule"))
            if ln:
                lines[(int(ln), rule or "auto")] += 1
            after[int(sp_.get(q("after"), 0)) / 20] += 1
            before[int(sp_.get(q("before"), 0)) / 20] += 1
    out.append("BODY TEXT")
    if long_p:
        fo, fc = _mode(list(fonts.elements())); so, sc_ = _mode(list(sizes_.elements())); jo, jc_ = _mode(list(jcs.elements()))
        out.append(f"- Body paragraphs analysed: {len(long_p)}; dominant font {fo} ({fc} paras), size {so}pt ({sc_} paras), alignment {jo} ({jc_} paras)")
        if lines:
            (lv, lr), lc = lines.most_common(1)[0]
            if lr == "auto":
                out.append(f"- Line spacing: {lv/240:g} lines ('auto') in {lc} paragraphs")
            else:
                sz_ = so or 12
                out.append(f"- Line spacing: exactly {lv/20:g}pt ({lv/20/sz_:g} x font size) in {lc} paragraphs")
        if after:
            out.append(f"- Space after paragraph: {after.most_common(1)[0][0]:g}pt in {after.most_common(1)[0][1]} paragraphs; space before ranges {min(before):g}-{max(before):g}pt (used as paragraph gap)")

    # ---- headings / captions
    def collect(pat, kind="p"):
        res = []
        for p in allp:
            t = _txt(p).strip()
            if re.match(pat, t):
                res.append((t, p))
        return res
    out.append("HEADING AND CAPTION STYLES")
    sep = collect(r"^CHAPTER \d+$")
    if sep:
        f = _run_props(sep[0][1], styles); out.append(f"- Chapter separator pages: {len(sep)} found, e.g. '{sep[0][0]}' in {_fmt(f)}, {_jc(sep[0][1], styles)}-aligned, no header or page number on those pages")
    ch = collect(r"^Chapter \d+$")
    if ch:
        f = _run_props(ch[0][1], styles); out.append(f"- Chapter content headings: {len(ch)} found, e.g. '{ch[0][0]}' in {_fmt(f)}, {_jc(ch[0][1], styles)}-aligned")
    sec = collect(r"^\d+\.\d+\s")
    if sec:
        f = _run_props(sec[0][1], styles); out.append(f"- Section headings (1.1 style): {len(sec)} found, e.g. '{sec[0][0][:40]}' in {_fmt(f)}, {_jc(sec[0][1], styles)}-aligned")
    figs = collect(r"^Fig\. ?\d+\.\d+")
    if figs:
        f = _run_props(figs[0][1], styles); out.append(f"- Figure captions: {len(figs)} found, e.g. '{figs[0][0][:50]}' in {_fmt(f)}, {_jc(figs[0][1], styles)}-aligned, placed below the figure")
    tabs = collect(r"^Table \d+\.\d+")
    above = 0
    kids = list(body)
    for t, p in tabs:
        try:
            i = kids.index(p)
        except ValueError:
            continue
        if i + 1 < len(kids) and kids[i + 1].tag == q("tbl"):
            above += 1
    if tabs:
        f = _run_props(tabs[0][1], styles); out.append(f"- Table captions: {len(tabs)} found, e.g. '{tabs[0][0][:50]}' in {_fmt(f)}, {_jc(tabs[0][1], styles)}-aligned, placed ABOVE the table in {above} of {len(tabs)} cases")

    # ---- algorithm boxes
    algo = []
    for tbl in body.iter(q("tbl")):
        first = _txt(tbl)[:7]
        if first.startswith("Input"):
            ps = [p for p in tbl.iter(q("p")) if _txt(p).strip()]
            fz = Counter(); szs = Counter()
            for p in ps:
                f, s, b = _run_props(p, styles); fz[f] += 1; szs[s] += 1
            bord = tbl.find(".//" + q("tcBorders") + "/" + q("top"))
            algo.append((fz.most_common(1)[0][0], szs.most_common(1)[0][0], bord is not None and bord.get(q("val")) not in (None, "nil", "none"), len(ps)))
    out.append("ALGORITHMS")
    if algo:
        for i, (f, s, bd, np_) in enumerate(algo, 1):
            out.append(f"- Algorithm box {i}: {np_} lines, font {f} {s}pt, bordered box: {'yes' if bd else 'no'}, begins with Input: and Output:")
    else:
        out.append("- No bordered Input/Output algorithm box found")

    # ---- images per chapter + colour
    out.append("IMAGES / SCREENSHOTS")
    cur = 0; per = Counter(); total = 0
    for p in allp:
        t = _txt(p).strip()
        m = re.match(r"^Chapter (\d+)$", t)
        if m:
            cur = int(m.group(1))
        k = len(list(p.iter(q("drawing"))))
        if k:
            per[cur] += k; total += k
    out.append(f"- Embedded pictures in document: {total}; per chapter: " + (", ".join(f"Ch{c}: {n}" for c, n in sorted(per.items())) or "none"))
    media = [n for n in z.namelist() if n.startswith("word/media/")]
    try:
        from PIL import Image
        colour = grey = 0
        for n in media:
            try:
                im = Image.open(io.BytesIO(z.read(n))).convert("RGB").resize((64, 64))
                px = list(im.getdata())
                frac = sum(1 for p_ in px if max(p_) - min(p_) > 30) / len(px)
                if frac > 0.02:
                    colour += 1
                else:
                    grey += 1
            except Exception:
                pass
        out.append(f"- Image files: {len(media)}; in colour: {colour}; black-and-white/greyscale: {grey}")
    except ImportError:
        out.append(f"- Image files: {len(media)} (colour check unavailable)")
    return "\n".join(out)


def pdf_format_facts(raw: bytes) -> str:
    try:
        import fitz
    except ImportError:
        return ""
    d = fitz.open(stream=raw, filetype="pdf")
    n = len(d)
    out = ["PAGE SETUP"]
    w, h = d[0].rect.width, d[0].rect.height
    out.append(f"- Page size {w/72*25.4:.0f} x {h/72*25.4:.0f} mm ({'A4' if abs(w/72*25.4-210)<2 else 'not A4'}), {n} pages")
    fonts = Counter(); sizes = Counter(); hdr = 0; imgs = 0; colour = 0; bold_hdr = None
    left = []; right = []
    for pg in d:
        blocks = pg.get_text("dict")["blocks"]
        first = None
        for b in blocks:
            if b["type"] == 0:
                for l in b["lines"]:
                    for s in l["spans"]:
                        if len(s["text"].strip()) > 3:
                            fonts[s["font"]] += len(s["text"]); sizes[round(s["size"])] += len(s["text"])
                            if first is None or s["bbox"][1] < first["bbox"][1]:
                                first = s
                    if l["spans"]:
                        left.append(l["bbox"][0]); right.append(l["bbox"][2])
        if first and "Shankaracharya" in first["text"] and first["bbox"][1] < 60:
            hdr += 1; bold_hdr = (first["font"], round(first["size"]))
        imgs += len(pg.get_images())
    out.append(f"- Dominant body font: {fonts.most_common(1)[0][0]}, size {sizes.most_common(1)[0][0]}pt")
    if left:
        out.append(f"- Typical text margins: left {sorted(left)[len(left)//10]/72:.2f} in, right {(w-sorted(right)[-len(right)//10-1])/72:.2f} in")
    out.append(f"- Institute header text found at top of {hdr} of {n} pages" + (f" in {bold_hdr[0]} {bold_hdr[1]}pt" if bold_hdr else ""))
    out.append(f"- Embedded images: {imgs}")
    return "\n".join(out)
