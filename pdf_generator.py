import os
import io
import re
import shutil
import tempfile
import subprocess
from io import BytesIO
from typing import List, Dict, Any, Optional, Tuple
from PIL import Image
from pypdf import PdfReader, PdfWriter

from graph_generator import inject_python_graphs
import docx_generator

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, HRFlowable, Image as RLImage, KeepTogether
)
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

def safe_print(*args, **kwargs):
    """Safely prints messages, suppressing broken pipe or Errno 5 EIO in detached Streamlit environments."""
    try:
        print(*args, **kwargs)
    except Exception:
        pass


# Register modern humanist and friendly system fonts for High School Maths Cover Sheets
FONT_MATH_TITLE = 'Helvetica-Bold'
FONT_MATH_BOLD = 'Helvetica-Bold'
FONT_MATH_REG = 'Helvetica'
FONT_MATH_OBL = 'Helvetica-Oblique'

try:
    if os.path.exists('/System/Library/Fonts/Supplemental/Trebuchet MS.ttf'):
        pdfmetrics.registerFont(TTFont('Trebuchet', '/System/Library/Fonts/Supplemental/Trebuchet MS.ttf'))
        pdfmetrics.registerFont(TTFont('Trebuchet-Bold', '/System/Library/Fonts/Supplemental/Trebuchet MS Bold.ttf'))
        pdfmetrics.registerFont(TTFont('Trebuchet-Italic', '/System/Library/Fonts/Supplemental/Trebuchet MS Italic.ttf'))
        FONT_MATH_REG = 'Trebuchet'
        FONT_MATH_BOLD = 'Trebuchet-Bold'
        FONT_MATH_OBL = 'Trebuchet-Italic'
    if os.path.exists('/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf'):
        pdfmetrics.registerFont(TTFont('ArialRounded', '/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf'))
        FONT_MATH_TITLE = 'ArialRounded'
    else:
        FONT_MATH_TITLE = FONT_MATH_BOLD
except Exception:
    FONT_MATH_TITLE = 'Helvetica-Bold'
    FONT_MATH_BOLD = 'Helvetica-Bold'
    FONT_MATH_REG = 'Helvetica'
    FONT_MATH_OBL = 'Helvetica-Oblique'

HAS_UNICODE_FONT = False
REPORT_FONT = 'Helvetica'
REPORT_FONT_BOLD = 'Helvetica-Bold'

for _ufont_path in [
    '/Library/Fonts/Arial Unicode.ttf',
    '/System/Library/Fonts/Supplemental/Arial Unicode.ttf',
    '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
    '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
    'C:\\Windows\\Fonts\\arialuni.ttf',
]:
    if os.path.exists(_ufont_path):
        try:
            pdfmetrics.registerFont(TTFont('DAUnicode', _ufont_path))
            pdfmetrics.registerFontFamily('DAUnicode', normal='DAUnicode', bold='DAUnicode', italic='DAUnicode', boldItalic='DAUnicode')
            REPORT_FONT = 'DAUnicode'
            REPORT_FONT_BOLD = 'DAUnicode'
            HAS_UNICODE_FONT = True
            break
        except Exception:
            pass

LOGO_PATH = os.path.join(os.path.dirname(__file__), "da_logo.png")
LOGO_TRANSPARENT_PATH = os.path.join(os.path.dirname(__file__), "da_logo_transparent.png")
LOGO_BW_PATH = os.path.join(os.path.dirname(__file__), "da_logo_bw.png")
LOGO_SHIELD_PATH = os.path.join(os.path.dirname(__file__), "da_watermark_shield.png")

def ensure_bw_logo() -> str:
    """Ensures a transparent black-and-white version of the logo exists for the subtle watermark."""
    if not os.path.exists(LOGO_BW_PATH):
        if os.path.exists(LOGO_SHIELD_PATH):
            try:
                im = Image.open(LOGO_SHIELD_PATH).convert('L')
                target_size = 1600
                im_up = im.resize((target_size, target_size), Image.Resampling.LANCZOS)
                import numpy as np
                arr = np.array(im_up, dtype=np.float32)
                t_low = 25.0
                t_high = 245.0
                alpha = np.clip(1.0 - (arr - t_low) / (t_high - t_low), 0.0, 1.0)
                alpha = alpha * alpha * (3.0 - 2.0 * alpha)
                alpha_u8 = (alpha * 255.0).astype(np.uint8)
                zeros = np.zeros_like(alpha_u8)
                rgba_arr = np.stack([zeros, zeros, zeros, alpha_u8], axis=-1)
                out_im = Image.fromarray(rgba_arr)
                out_im.save(LOGO_BW_PATH, 'PNG')
            except Exception:
                pass
        if not os.path.exists(LOGO_BW_PATH):
            src = LOGO_TRANSPARENT_PATH if os.path.exists(LOGO_TRANSPARENT_PATH) else LOGO_PATH
            if os.path.exists(src):
                try:
                    im = Image.open(src).convert("RGBA")
                    r, g, b, a = im.split()
                    gray = im.convert("L")
                    bw_img = Image.merge("RGBA", (gray, gray, gray, a))
                    bw_img.save(LOGO_BW_PATH)
                except Exception:
                    pass
    return LOGO_BW_PATH if os.path.exists(LOGO_BW_PATH) else LOGO_TRANSPARENT_PATH

def get_proportional_logo(target_height: float = 50.0, max_width: float = 85.0) -> Optional[RLImage]:
    """Calculates exact aspect ratio from PIL to avoid any image distortion in ReportLab."""
    if not os.path.exists(LOGO_PATH):
        return None
    try:
        with Image.open(LOGO_PATH) as img:
            orig_w, orig_h = img.size
            aspect = orig_w / orig_h
        calc_w = target_height * aspect
        calc_h = target_height
        if calc_w > max_width:
            calc_w = max_width
            calc_h = calc_w / aspect
        return RLImage(LOGO_PATH, width=calc_w, height=calc_h)
    except Exception:
        return None

def find_pdflatex() -> Optional[str]:
    """Finds the pdflatex binary on the host system."""
    candidate_paths = [
        "/Library/TeX/texbin/pdflatex",
        "/usr/local/bin/pdflatex",
        "/opt/homebrew/bin/pdflatex",
        "/usr/bin/pdflatex"
    ]
    for p in candidate_paths:
        if os.path.exists(p) and os.access(p, os.X_OK):
            return p
    return shutil.which("pdflatex")


def is_blank_or_header_only_page(page_text: str, topic: str = "", year_level: str = "") -> bool:
    """
    Checks if an extracted PDF page contains only running headers, footers, or page numbers,
    with no actual learning, problem, solution, or question body content.
    """
    if not page_text or not page_text.strip():
        return True
    lines = [l.strip() for l in page_text.splitlines() if l.strip()]
    if not lines:
        return True
    body_lines = []
    for line in lines:
        # Strip plain page numbers (e.g. "8", "15", "Page 8 of 8")
        if re.match(r"^\d+(?:\s*(?:of|/)\s*\d+)?$", line, re.IGNORECASE):
            continue
        if re.match(r"^page\s+\d+", line, re.IGNORECASE):
            continue
        norm = re.sub(r"\s+", "", line).lower()
        if "datuition" in norm:
            continue
        if any(h in norm for h in ["studentprivate", "teachermaster", "studentclass", "completenotes", "in-classworkbook"]):
            continue
        if topic and re.sub(r"\s+", "", topic).lower() in norm:
            continue
        if year_level and re.sub(r"\s+", "", year_level).lower() in norm:
            continue
        if "maths" in norm or "mathematics" in norm:
            if any(k in norm for k in ["year", "stage", "standard", "advanced", "extension"]):
                continue
        body_lines.append(line)
    return len(body_lines) == 0


def prune_trailing_blank_pages(pdf_bytes: Optional[bytes], topic: str = "", year_level: str = "") -> Optional[bytes]:
    """
    Scans compiled PDF bytes from the end and prunes any trailing pages that are completely blank
    or contain only running headers/footers/page numbers.
    Never prunes if the document has only 1 page.
    """
    if not pdf_bytes:
        return pdf_bytes
    try:
        import io
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        num_pages = len(reader.pages)
        if num_pages <= 1:
            return pdf_bytes

        last_valid_page = num_pages - 1
        while last_valid_page >= 0:
            p_text = reader.pages[last_valid_page].extract_text() or ""
            has_images = len(reader.pages[last_valid_page].images) > 1  # 1 image is background watermark logo
            if has_images:
                break
            if not is_blank_or_header_only_page(p_text, topic=topic, year_level=year_level):
                break
            last_valid_page -= 1

        if last_valid_page == num_pages - 1:
            return pdf_bytes

        keep_count = max(1, last_valid_page + 1)
        writer = pypdf.PdfWriter()
        for idx in range(keep_count):
            writer.add_page(reader.pages[idx])

        out_buf = io.BytesIO()
        writer.write(out_buf)
        return out_buf.getvalue()
    except Exception as e:
        safe_print(f"[prune_trailing_blank_pages error] {e}")
        return pdf_bytes


def get_font_latex_preamble(font_theme: str = "charter") -> List[str]:
    """
    Returns the LaTeX preamble lines for the specified font theme.
    Defaults to Charter (Contemporary Editorial).
    """
    f = str(font_theme or "").strip().lower().replace(" ", "").replace("-", "").replace("_", "")
    if "inter" in f:
        return [
            r"\usepackage[default]{inter}",
            r"\usepackage[italic]{mathastext}"
        ]
    elif "source" in f:
        return [
            r"\usepackage[default]{sourcesanspro}",
            r"\usepackage[italic]{mathastext}"
        ]
    elif "hero" in f or "helvet" in f or "swiss" in f:
        return [
            r"\usepackage{tgheros}",
            r"\renewcommand*\familydefault{\sfdefault}",
            r"\usepackage[italic]{mathastext}"
        ]
    elif "roboto" in f:
        return [
            r"\usepackage[default]{roboto}",
            r"\usepackage[italic]{mathastext}"
        ]
    elif "classic" in f or "computermodern" in f or "cm" in f:
        return []
    else:
        # Default signature font: Charter (Contemporary Editorial)
        return [
            r"\usepackage{charter}",
            r"\usepackage[italic]{mathastext}"
        ]

def markdown_table_to_latex(text: str) -> str:
    """
    Detects markdown pipe tables (e.g. | Col 1 | Col 2 | ...) and converts them
    to standard LaTeX \begin{tabular} environments before sanitization.
    """
    if not text or "|" not in text:
        return text
    lines = str(text).split("\n")
    new_lines = []
    in_table = False
    table_rows = []

    def flush_table(rows):
        if not rows:
            return []
        cleaned_rows = []
        for r in rows:
            cells = [c.strip() for c in r.strip().strip("|").split("|")]
            if all(re.match(r"^:?-+:?$", c) for c in cells if c):
                continue
            cleaned_rows.append(cells)
        if not cleaned_rows:
            return []
        col_count = max(len(r) for r in cleaned_rows)
        for r in cleaned_rows:
            while len(r) < col_count:
                r.append("")

        header = [c.lower() for c in cleaned_rows[0]]
        is_stem_leaf = (len(header) == 2 and "stem" in header[0] and "leaf" in header[1])

        if is_stem_leaf:
            col_spec = "r|l"
            tex = [
                f"\\begin{{tabular}}{{{col_spec}}}",
                f"\\textbf{{{cleaned_rows[0][0]}}} & \\textbf{{{cleaned_rows[0][1]}}} \\\\",
                r"\hline"
            ]
            for r in cleaned_rows[1:]:
                tex.append(f"{r[0]} & {r[1]} \\\\")
            tex.append(r"\end{tabular}")
            return tex
        else:
            col_spec = "|" + "c|" * col_count
            tex = [
                f"\\begin{{tabular}}{{{col_spec}}}",
                r"\hline"
            ]
            for idx, r in enumerate(cleaned_rows):
                if idx == 0:
                    tex.append(" & ".join([f"\\textbf{{{c}}}" if not c.startswith("\\textbf") else c for c in r]) + r" \\ \hline")
                else:
                    tex.append(" & ".join(r) + r" \\ \hline")
            tex.append(r"\end{tabular}")
            return tex

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|") and "|" in stripped[1:-1]:
            table_rows.append(stripped)
            in_table = True
        else:
            if in_table:
                new_lines.extend(flush_table(table_rows))
                table_rows = []
                in_table = False
            new_lines.append(line)
    if in_table:
        new_lines.extend(flush_table(table_rows))
    return "\n".join(new_lines)

def wrap_bare_fractions(text: str) -> str:
    """Wraps bare \\frac{...}{...} outside math mode in \\ensuremath{...}, supporting nested braces."""
    idx = 0
    res = []
    while idx < len(text):
        pos = text.find(r"\frac", idx)
        if pos == -1:
            res.append(text[idx:])
            break
        if pos >= 11 and text[pos-11:pos] == r"\ensuremath{":
            res.append(text[idx:pos+5])
            idx = pos + 5
            continue
        brace1_start = text.find("{", pos + 5)
        if brace1_start == -1 or text[pos+5:brace1_start].strip() != "":
            res.append(text[idx:pos+5])
            idx = pos + 5
            continue
        depth = 1
        curr = brace1_start + 1
        while curr < len(text) and depth > 0:
            if text[curr] == "{": depth += 1
            elif text[curr] == "}": depth -= 1
            curr += 1
        if depth != 0:
            res.append(text[idx:pos+5])
            idx = pos + 5
            continue
        brace1_end = curr
        brace2_start = text.find("{", brace1_end)
        if brace2_start == -1 or text[brace1_end:brace2_start].strip() != "":
            res.append(text[idx:brace1_end])
            idx = brace1_end
            continue
        depth = 1
        curr = brace2_start + 1
        while curr < len(text) and depth > 0:
            if text[curr] == "{": depth += 1
            elif text[curr] == "}": depth -= 1
            curr += 1
        if depth != 0:
            res.append(text[idx:brace1_end])
            idx = brace1_end
            continue
        brace2_end = curr
        res.append(text[idx:pos])
        frac_content = text[pos:brace2_end]
        res.append(f"\\ensuremath{{{frac_content}}}")
        idx = brace2_end
    return "".join(res)


def wrap_bare_sqrts(text: str) -> str:
    """Safely wraps bare \\sqrt{...} or \\sqrt(...) in \\ensuremath{...}, including optional leading \\pm."""
    text = re.sub(r"(?<!\\ensuremath\{)\\sqrt\(([^)]+)\)", r"\\sqrt{\1}", text)
    idx = 0
    res = []
    while idx < len(text):
        pos = text.find(r"\sqrt", idx)
        if pos == -1:
            res.append(text[idx:])
            break
        if pos >= 11 and text[pos-11:pos] == r"\ensuremath{":
            res.append(text[idx:pos+5])
            idx = pos + 5
            continue

        # Check for optional leading \pm
        start_pos = pos
        m_pm = re.search(r"(\\pm\s*)$", text[idx:pos])
        if m_pm:
            pm_start = pos - len(m_pm.group(1))
            if pm_start < 11 or text[pm_start-11:pm_start] != r"\ensuremath{":
                start_pos = pm_start

        curr = pos + 5
        if curr < len(text) and text[curr] == "[":
            opt_end = text.find("]", curr)
            if opt_end != -1:
                curr = opt_end + 1
        brace_start = text.find("{", curr)
        if brace_start == -1 or text[curr:brace_start].strip() != "":
            res.append(text[idx:start_pos])
            sqrt_prefix = text[start_pos:pos]
            res.append(f"\\ensuremath{{{sqrt_prefix}\\sqrt{{}}}}")
            idx = curr
            continue
        depth = 1
        c = brace_start + 1
        while c < len(text) and depth > 0:
            if text[c] == "{": depth += 1
            elif text[c] == "}": depth -= 1
            c += 1
        if depth != 0:
            res.append(text[idx:curr])
            idx = curr
            continue
        brace_end = c
        res.append(text[idx:start_pos])
        sqrt_content = text[start_pos:brace_end]
        res.append(f"\\ensuremath{{{sqrt_content}}}")
        idx = brace_end
    return "".join(res)


def _preserve_case(orig: str, replacement: str) -> str:
    """Preserves uppercase, capitalized, or lowercase casing from original word."""
    if orig.isupper():
        return replacement.upper()
    if orig.istitle():
        return replacement.capitalize()
    return replacement.lower()


AU_SPELLING_PAIRS = [
    # -ize / -ized / -izing / -ization -> -ise / -ised / -ising / -isation
    (r"\b(factor)iz(e[sd]?|ing|ation)\b", r"\1is\2"),
    (r"\b(rational)iz(e[sd]?|ing|ation)\b", r"\1is\2"),
    (r"\b(minim)iz(e[sd]?|ing|ation)\b", r"\1is\2"),
    (r"\b(maxim)iz(e[sd]?|ing|ation)\b", r"\1is\2"),
    (r"\b(summar)iz(e[sd]?|ing|ation)\b", r"\1is\2"),
    (r"\b(recogn)iz(e[sd]?|ing|ation)\b", r"\1is\2"),
    (r"\b(emphas)iz(e[sd]?|ing)\b", r"\1is\2"),
    (r"\b(character)iz(e[sd]?|ing|ation)\b", r"\1is\2"),
    (r"\b(standard)iz(e[sd]?|ing|ation)\b", r"\1is\2"),
    (r"\b(general)iz(e[sd]?|ing|ation)\b", r"\1is\2"),
    (r"\b(hypothes)iz(e[sd]?|ing)\b", r"\1is\2"),
    (r"\b(memor)iz(e[sd]?|ing)\b", r"\1is\2"),
    (r"\b(visual)iz(e[sd]?|ing|ation)\b", r"\1is\2"),
    (r"\b(util)iz(e[sd]?|ing|ation)\b", r"\1is\2"),
    (r"\b(priorit)iz(e[sd]?|ing|ation)\b", r"\1is\2"),
    (r"\b(categor)iz(e[sd]?|ing|ation)\b", r"\1is\2"),
    (r"\b(linear)iz(e[sd]?|ing|ation)\b", r"\1is\2"),
    (r"\b(diagonal)iz(e[sd]?|ing|ation)\b", r"\1is\2"),
    (r"\b(parameter|parametr)iz(e[sd]?|ing|ation)\b", r"\1is\2"),
    (r"\b(normal)iz(e[sd]?|ing|ation)\b", r"\1is\2"),
    (r"\b(organ)iz(e[sd]?|ing|ation)\b", r"\1is\2"),
    (r"\b(synthes)iz(e[sd]?|ing)\b", r"\1is\2"),
    # analyze / paralyze
    (r"\b(analy)z(e[sd]?|ing)\b", r"\1s\2"),
    (r"\b(paraly)z(e[sd]?|ing)\b", r"\1s\2"),
    # -or -> -our
    (r"\b(col)or([s]?|ed|ing|ful)\b", r"\1our\2"),
    (r"\b(behavio)r([s]?)\b", r"\1ur\2"),
    (r"\b(neighbo)r([s]?|hood|ing)\b", r"\1ur\2"),
    (r"\b(flavo)r([s]?|ed|ing)\b", r"\1ur\2"),
    (r"\b(hono)r([s]?|ed|ing|able)\b", r"\1ur\2"),
    (r"\b(labo)r([s]?|ed|ing)\b", r"\1ur\2"),
    # Doubled consonants
    (r"\b(label)ed\b", r"\1led"),
    (r"\b(label)ing\b", r"\1ling"),
    (r"\b(model)ed\b", r"\1led"),
    (r"\b(model)ing\b", r"\1ling"),
    (r"\b(travel)ed\b", r"\1led"),
    (r"\b(travel)ing\b", r"\1ling"),
    (r"\b(cancel)ed\b", r"\1led"),
    (r"\b(cancel)ing\b", r"\1ling"),
    (r"\b(signal)ed\b", r"\1led"),
    (r"\b(signal)ing\b", r"\1ling"),
    # -er -> -re (excluding diameter, perimeter, parameter, thermometer, barometer)
    (r"(?<!\\)(?<!\\begin\{)(?<!\\end\{)(?<!anchor=)\b(cent)er\b", r"\1re"),
    (r"(?<!\\)(?<!anchor=)\b(cent)ered\b", r"\1red"),
    (r"(?<!\\)(?<!anchor=)\b(cent)ers\b", r"\1res"),
    (r"\b(centi|milli|kilo|mega)?(met)er(s)?\b", r"\1\2re\3"),
]


def enforce_australian_english_text(text: str) -> str:
    """Enforces Australian English spelling across text strings, preserving casing and LaTeX commands."""
    if not text:
        return ""
    result = str(text)
    for pat, repl in AU_SPELLING_PAIRS:
        def _replace_match(m):
            matched = m.group(0)
            expanded = m.expand(repl)
            return _preserve_case(matched, expanded)
        result = re.sub(pat, _replace_match, result, flags=re.IGNORECASE)
    return result


def enforce_australian_english_dict(obj: Any) -> Any:
    """Recursively traverses a dict, list, or string and enforces Australian English spelling on all text."""
    if isinstance(obj, str):
        return enforce_australian_english_text(obj)
    elif isinstance(obj, dict):
        return {k: enforce_australian_english_dict(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [enforce_australian_english_dict(item) for item in obj]
    return obj


def get_sketch_solution_fallback_tikz(problem_text: str, solution_text: str = "") -> str:
    """
    Generates a publication-quality, compilable TikZ coordinate plane diagram
    when a question asks to 'sketch', 'plot', or 'graph' a function or relation,
    but no solution diagram was provided.
    """
    combined = (str(problem_text) + " " + str(solution_text)).lower()

    # 1. Sideways parabola: y^2 = 4x, y^2 = ax, or x = y^2
    if re.search(r"y\^2\s*=\s*\d*x|x\s*=\s*y\^2|sideways\s+parabola", combined):
        m = re.search(r"y\^2\s*=\s*(\d+)x", combined)
        coeff = int(m.group(1)) if m else 4
        pt_y_val = coeff ** 0.5
        pt_y_str = f"{int(pt_y_val)}" if pt_y_val.is_integer() else f"{pt_y_val:.1f}"
        return rf"""\begin{{tikzpicture}}[x=1.1cm, y=0.85cm]
\draw[->, thick, danavy] (-0.8, 0) -- (4.8, 0) node[right, font=\footnotesize] {{$x$}};
\draw[->, thick, danavy] (0, -3.2) -- (0, 3.2) node[above, font=\footnotesize] {{$y$}};
\node[below left=2pt, font=\footnotesize] at (0, 0) {{$O$}};
\draw[line width=1.4pt, dablue, domain=0:4.2, samples=100] plot (\x, {{sqrt({coeff}*\x)}});
\draw[line width=1.4pt, dablue, domain=0:4.2, samples=100] plot (\x, {{-sqrt({coeff}*\x)}});
\node[dablue, font=\footnotesize\bfseries, right] at (4.0, 2.7) {{$y^2 = {coeff}x$}};
\fill[danavy] (0, 0) circle (2.2pt) node[below left=1pt, font=\scriptsize\bfseries] {{Vertex $(0,0)$}};
\draw[dashed, thick, dawine] (1, -2.8) -- (1, 2.8) node[above, font=\scriptsize\bfseries, text=dawine, fill=white, fill opacity=0.9, text opacity=1, inner sep=1pt] {{Test line: $x = 1$}};
\fill[dawine] (1, {pt_y_val}) circle (2.5pt) node[above right=1pt, font=\scriptsize\bfseries, text=dawine, fill=white, fill opacity=0.9, text opacity=1, inner sep=1pt] {{$(1, {pt_y_str})$}};
\fill[dawine] (1, -{pt_y_val}) circle (2.5pt) node[below right=1pt, font=\scriptsize\bfseries, text=dawine, fill=white, fill opacity=0.9, text opacity=1, inner sep=1pt] {{$(1, -{pt_y_str})$}};
\draw[->, thick, dagreen!80!black] (2.2, 1.8) to[bend left=15] (2.8, 2.9);
\node[above, font=\scriptsize\bfseries, text=dagreen!80!black, fill=white, fill opacity=0.9, text opacity=1, inner sep=1.5pt] at (3.0, 3.0) {{Restricted branch $y \ge 0 \implies y = \sqrt{{{coeff}x}}$ (Function)}};
\node[align=center, font=\scriptsize, fill=white, fill opacity=0.95, text opacity=1, draw=dawine!40, rounded corners=3pt, inner sep=3pt] at (2.4, -2.5) {{
\textbf{{\color{{dawine}}Vertical Line Test:}} 2 intersection points at $x = 1 \implies$ \textbf{{Not a function}}
}};
\end{{tikzpicture}}"""

    # 2. Circle: x^2 + y^2 = r^2
    if re.search(r"x\^2\s*\+\s*y\^2\s*=\s*(\d+)", combined) or ("circle" in combined and any(k in combined for k in ["x^2", "y^2"])):
        m = re.search(r"x\^2\s*\+\s*y\^2\s*=\s*(\d+)", combined)
        r_sq = int(m.group(1)) if m else 9
        r = int(r_sq ** 0.5) if (r_sq ** 0.5).is_integer() else 3
        return rf"""\begin{{tikzpicture}}[scale=0.9]
\draw[->, thick, danavy] (-{r+0.8}, 0) -- ({r+1.0}, 0) node[right, font=\footnotesize] {{$x$}};
\draw[->, thick, danavy] (0, -{r+0.8}) -- (0, {r+1.0}) node[above, font=\footnotesize] {{$y$}};
\node[below left=2pt, font=\footnotesize] at (0, 0) {{$O$}};
\draw[line width=1.4pt, dablue] (0, 0) circle ({r});
\node[dablue, font=\footnotesize\bfseries, above right] at ({r*0.7:.1f}, {r*0.7:.1f}) {{$x^2 + y^2 = {r_sq}$}};
\fill[danavy] ({r}, 0) circle (2pt) node[below right, font=\scriptsize] {{({r}, 0)}};
\fill[danavy] (-{r}, 0) circle (2pt) node[below left, font=\scriptsize] {{(-{r}, 0)}};
\fill[danavy] (0, {r}) circle (2pt) node[above left, font=\scriptsize] {{(0, {r})}};
\fill[danavy] (0, -{r}) circle (2pt) node[below left, font=\scriptsize] {{(0, -{r})}};
\draw[dashed, thick, dawine] (1, -{r+0.4}) -- (1, {r+0.4}) node[above, font=\scriptsize\bfseries, text=dawine, fill=white, fill opacity=0.9, text opacity=1, inner sep=1pt] {{$x = 1$}};
\node[align=center, font=\scriptsize, fill=white, fill opacity=0.95, text opacity=1, draw=dawine!40, rounded corners=3pt, inner sep=2.5pt] at (0, -{r+1.1}) {{
\textbf{{\color{{dawine}}Vertical Line Test:}} 2 intersection points $\implies$ \textbf{{Not a function}}
}};
\end{{tikzpicture}}"""

    # 3. Semicircle: y = sqrt(r^2 - x^2) or y = -sqrt(...)
    if "sqrt(" in combined and ("- x^2" in combined or "-x^2" in combined):
        m = re.search(r"(\d+)\s*-\s*x\^2", combined)
        r_sq = int(m.group(1)) if m else 9
        r = int(r_sq ** 0.5) if (r_sq ** 0.5).is_integer() else 3
        is_lower = "-" in combined and "y = -" in combined
        sign_mult = -1 if is_lower else 1
        minus_str = "-" if is_lower else ""
        y_max = 0.5 if is_lower else r + 0.8
        y_min = -(r + 0.8) if is_lower else -0.5
        return rf"""\begin{{tikzpicture}}[scale=0.9]
\draw[->, thick, danavy] (-{r+0.8}, 0) -- ({r+1.0}, 0) node[right, font=\footnotesize] {{$x$}};
\draw[->, thick, danavy] (0, {y_min}) -- (0, {y_max}) node[above, font=\footnotesize] {{$y$}};
\node[below left=2pt, font=\footnotesize] at (0, 0) {{$O$}};
\draw[line width=1.4pt, dablue, domain=-{r}:{r}, samples=100] plot (\x, {{{sign_mult}*sqrt({r_sq} - \x*\x)}});
\fill[danavy] ({r}, 0) circle (2pt) node[above right, font=\scriptsize] {{({r}, 0)}};
\fill[danavy] (-{r}, 0) circle (2pt) node[above left, font=\scriptsize] {{(-{r}, 0)}};
\fill[danavy] (0, {sign_mult*r}) circle (2pt) node[right, font=\scriptsize] {{(0, {sign_mult*r})}};
\node[dablue, font=\footnotesize\bfseries, above] at (0, {sign_mult*r + 0.3}) {{$y = {minus_str}\sqrt{{{r_sq} - x^2}}$}};
\draw[dashed, thick, dagreen!80!black] (1, {y_min}) -- (1, {y_max}) node[above, font=\scriptsize\bfseries, text=dagreen!80!black] {{$x = 1$}};
\node[align=center, font=\scriptsize, fill=white, fill opacity=0.95, text opacity=1, draw=dagreen!40, rounded corners=3pt, inner sep=2pt] at (0, {y_min - 0.4}) {{
\textbf{{\color{{dagreen!80!black}}Passes VLT:}} Each vertical line intersects at most once $\implies$ \textbf{{Function}}
}};
\end{{tikzpicture}}"""

    # 4. Upright Parabola: y = x^2, quadratic
    if re.search(r"y\s*=\s*x\^2|parabola|quadratic", combined):
        return r"""\begin{tikzpicture}[x=0.9cm, y=0.55cm]
\draw[->, thick, danavy] (-3.2, 0) -- (3.5, 0) node[right, font=\footnotesize] {$x$};
\draw[->, thick, danavy] (0, -1.0) -- (0, 5.2) node[above, font=\footnotesize] {$y$};
\node[below left=2pt, font=\footnotesize] at (0, 0) {$O$};
\draw[line width=1.4pt, dablue, domain=-2.2:2.2, samples=100] plot (\x, {\x*\x});
\node[dablue, font=\footnotesize\bfseries, right] at (2.2, 4.8) {$y = x^2$};
\fill[danavy] (0, 0) circle (2pt) node[below=2pt, font=\scriptsize\bfseries] {Vertex $(0,0)$};
\draw[dashed, thick, dagreen!80!black] (1.5, -0.5) -- (1.5, 4.8) node[above, font=\scriptsize\bfseries, text=dagreen!80!black] {$x = 1.5$};
\fill[dagreen!80!black] (1.5, 2.25) circle (2.2pt) node[right=2pt, font=\scriptsize\bfseries] {$(1.5, 2.25)$};
\node[align=center, font=\scriptsize, fill=white, fill opacity=0.95, text opacity=1, draw=dagreen!40, rounded corners=3pt, inner sep=2pt] at (0, -0.6) {
\textbf{\color{dagreen!80!black}Passes VLT:} Exactly 1 intersection per $x$-value $\implies$ \textbf{Function}
};
\end{tikzpicture}"""

    # 5. Hyperbola: y = 1/x or y = k/x
    if re.search(r"y\s*=\s*\d*/x|xy\s*=\s*\d+|hyperbola", combined):
        return r"""\begin{tikzpicture}[x=0.9cm, y=0.9cm]
\draw[->, thick, danavy] (-3.2, 0) -- (3.5, 0) node[right, font=\footnotesize] {$x$};
\draw[->, thick, danavy] (0, -3.2) -- (0, 3.5) node[above, font=\footnotesize] {$y$};
\node[below left=2pt, font=\footnotesize] at (0, 0) {$O$};
\draw[line width=1.4pt, dablue, domain=0.35:3.2, samples=100] plot (\x, {1/\x});
\draw[line width=1.4pt, dablue, domain=-3.2:-0.35, samples=100] plot (\x, {1/\x});
\node[dablue, font=\footnotesize\bfseries, right] at (1.5, 2.2) {$y = \frac{1}{x}$};
\node[font=\tiny, text=danavy!70] at (2.0, 0.25) {Asymptote $y=0$};
\node[font=\tiny, text=danavy!70, rotate=90] at (0.25, 2.0) {Asymptote $x=0$};
\draw[dashed, thick, dagreen!80!black] (1.2, -2.5) -- (1.2, 2.8) node[above, font=\scriptsize\bfseries, text=dagreen!80!black] {$x = 1.2$};
\fill[dagreen!80!black] (1.2, 0.833) circle (2pt);
\node[align=center, font=\scriptsize, fill=white, fill opacity=0.95, text opacity=1, draw=dagreen!40, rounded corners=3pt, inner sep=2pt] at (0, -2.7) {
\textbf{\color{dagreen!80!black}Passes VLT:} Intersects at most once $\implies$ \textbf{Function} (Domain: $x \ne 0$)
};
\end{tikzpicture}"""

    # 6. Exponential: y = 2^x or y = a^x or exponential
    if re.search(r"y\s*=\s*\d*\^x|y\s*=\s*e\^x|exponential", combined):
        return r"""\begin{tikzpicture}[x=1.0cm, y=0.8cm]
\draw[->, thick, danavy] (-3.2, 0) -- (3.2, 0) node[right, font=\footnotesize] {$x$};
\draw[->, thick, danavy] (0, -0.6) -- (0, 4.5) node[above, font=\footnotesize] {$y$};
\node[below left=2pt, font=\footnotesize] at (0, 0) {$O$};
\draw[line width=1.4pt, dablue, domain=-2.8:2.1, samples=100] plot (\x, {2^(\x)});
\node[dablue, font=\footnotesize\bfseries, left] at (2.0, 4.2) {$y = 2^x$};
\fill[danavy] (0, 1) circle (2pt) node[above left, font=\scriptsize] {$(0, 1)$};
\draw[dashed, thick, dagreen!80!black] (1.0, -0.4) -- (1.0, 3.8) node[above, font=\scriptsize\bfseries, text=dagreen!80!black] {$x = 1$};
\fill[dagreen!80!black] (1.0, 2) circle (2pt) node[right, font=\scriptsize] {$(1, 2)$};
\node[align=center, font=\scriptsize, fill=white, fill opacity=0.95, text opacity=1, draw=dagreen!40, rounded corners=3pt, inner sep=2pt] at (0, -0.8) {
\textbf{\color{dagreen!80!black}Passes VLT:} Exactly 1 intersection per $x$-value $\implies$ \textbf{Function}
};
\end{tikzpicture}"""

    # 7. Absolute Value: y = |x|
    if re.search(r"y\s*=\s*\|x\||absolute\s+value", combined):
        return r"""\begin{tikzpicture}[x=0.9cm, y=0.9cm]
\draw[->, thick, danavy] (-3.2, 0) -- (3.5, 0) node[right, font=\footnotesize] {$x$};
\draw[->, thick, danavy] (0, -0.6) -- (0, 3.5) node[above, font=\footnotesize] {$y$};
\node[below left=2pt, font=\footnotesize] at (0, 0) {$O$};
\draw[line width=1.4pt, dablue] (-3, 3) -- (0, 0) -- (3, 3);
\node[dablue, font=\footnotesize\bfseries, right] at (2.5, 2.7) {$y = |x|$};
\fill[danavy] (0, 0) circle (2pt) node[below=2pt, font=\scriptsize\bfseries] {Vertex $(0,0)$};
\draw[dashed, thick, dagreen!80!black] (1.5, -0.4) -- (1.5, 3.0) node[above, font=\scriptsize\bfseries, text=dagreen!80!black] {$x = 1.5$};
\fill[dagreen!80!black] (1.5, 1.5) circle (2pt) node[right, font=\scriptsize] {$(1.5, 1.5)$};
\node[align=center, font=\scriptsize, fill=white, fill opacity=0.95, text opacity=1, draw=dagreen!40, rounded corners=3pt, inner sep=2pt] at (0, -0.8) {
\textbf{\color{dagreen!80!black}Passes VLT:} Exactly 1 intersection $\implies$ \textbf{Function}
};
\end{tikzpicture}"""

    # 8. Cubic: y = x^3
    if re.search(r"y\s*=\s*x\^3|cubic", combined):
        return r"""\begin{tikzpicture}[x=1.0cm, y=0.6cm]
\draw[->, thick, danavy] (-2.5, 0) -- (2.8, 0) node[right, font=\footnotesize] {$x$};
\draw[->, thick, danavy] (0, -3.5) -- (0, 3.8) node[above, font=\footnotesize] {$y$};
\node[below left=2pt, font=\footnotesize] at (0, 0) {$O$};
\draw[line width=1.4pt, dablue, domain=-1.5:1.5, samples=100] plot (\x, {\x*\x*\x});
\node[dablue, font=\footnotesize\bfseries, right] at (1.4, 3.0) {$y = x^3$};
\fill[danavy] (0, 0) circle (2pt) node[below right, font=\scriptsize] {Point of Inflection $(0,0)$};
\draw[dashed, thick, dagreen!80!black] (1, -2.5) -- (1, 2.5) node[above, font=\scriptsize\bfseries, text=dagreen!80!black] {$x = 1$};
\fill[dagreen!80!black] (1, 1) circle (2pt) node[right, font=\scriptsize] {$(1, 1)$};
\node[align=center, font=\scriptsize, fill=white, fill opacity=0.95, text opacity=1, draw=dagreen!40, rounded corners=3pt, inner sep=2pt] at (0, -3.8) {
\textbf{\color{dagreen!80!black}Passes VLT:} Exactly 1 intersection per $x$-value $\implies$ \textbf{Function}
};
\end{tikzpicture}"""

    # 9. Linear function: y = mx + b or linear
    if re.search(r"y\s*=\s*[-+]?\d*x|linear", combined):
        return r"""\begin{tikzpicture}[x=0.9cm, y=0.7cm]
\draw[->, thick, danavy] (-3.0, 0) -- (3.5, 0) node[right, font=\footnotesize] {$x$};
\draw[->, thick, danavy] (0, -2.5) -- (0, 3.8) node[above, font=\footnotesize] {$y$};
\node[below left=2pt, font=\footnotesize] at (0, 0) {$O$};
\draw[line width=1.4pt, dablue] (-2.5, -2) -- (2.5, 3);
\node[dablue, font=\footnotesize\bfseries, right] at (2.2, 2.8) {$y = mx + c$};
\fill[danavy] (0, 0.5) circle (2pt) node[left, font=\scriptsize] {$(0, c)$};
\draw[dashed, thick, dagreen!80!black] (1, -1.8) -- (1, 3.0) node[above, font=\scriptsize\bfseries, text=dagreen!80!black] {$x = 1$};
\fill[dagreen!80!black] (1, 1.5) circle (2pt);
\node[align=center, font=\scriptsize, fill=white, fill opacity=0.95, text opacity=1, draw=dagreen!40, rounded corners=3pt, inner sep=2pt] at (0, -2.8) {
\textbf{\color{dagreen!80!black}Passes VLT:} Exactly 1 intersection per $x$-value $\implies$ \textbf{Function}
};
\end{tikzpicture}"""

    # 10. Vertical line: x = c (relation, not a function)
    if re.search(r"x\s*=\s*[-+]?\d+|vertical\s+line", combined) and not re.search(r"vertical\s+line\s+test", combined):
        return r"""\begin{tikzpicture}[x=0.9cm, y=0.7cm]
\draw[->, thick, danavy] (-2.0, 0) -- (4.0, 0) node[right, font=\footnotesize] {$x$};
\draw[->, thick, danavy] (0, -2.5) -- (0, 3.5) node[above, font=\footnotesize] {$y$};
\node[below left=2pt, font=\footnotesize] at (0, 0) {$O$};
\draw[line width=1.5pt, dawine] (2, -2.2) -- (2, 3.2);
\node[dawine, font=\footnotesize\bfseries, right] at (2, 2.8) {$x = 2$};
\fill[dawine] (2, 0) circle (2pt) node[below right, font=\scriptsize] {$(2, 0)$};
\node[align=center, font=\scriptsize, fill=white, fill opacity=0.95, text opacity=1, draw=dawine!40, rounded corners=3pt, inner sep=2pt] at (1.0, -2.8) {
\textbf{\color{dawine}Fails VLT:} Infinitely many intersections at $x = 2 \implies$ \textbf{Not a function}
};
\end{tikzpicture}"""

    return ""


def _build_custom_network_tikz(vertices: List[str], edges: List[Any]) -> str:
    n = len(vertices)
    coords = {}
    if n == 4:
        coords = {
            vertices[0]: (0.0, 1.4),
            vertices[1]: (2.5, 2.5),
            vertices[2]: (2.5, 0.3),
            vertices[3]: (5.0, 1.4)
        }
    elif n == 3:
        coords = {
            vertices[0]: (0.0, 0.0),
            vertices[1]: (2.2, 2.2),
            vertices[2]: (4.4, 0.0)
        }
    elif n == 5:
        coords = {
            vertices[0]: (0.0, 1.4),
            vertices[1]: (2.2, 2.5),
            vertices[2]: (2.2, 0.3),
            vertices[3]: (4.6, 2.5),
            vertices[4]: (4.6, 0.3)
        }
    else:
        radius = max(2.0, 0.48 * n)
        for i, v in enumerate(vertices):
            angle = 90 - (360.0 / n) * i
            rad = math.radians(angle)
            coords[v] = (round(radius * math.cos(rad), 2), round(radius * math.sin(rad), 2))

    tikz_lines = [
        r'\begin{center}',
        r'\begin{adjustbox}{max width=0.85\linewidth, max totalheight=3.4cm, keepaspectratio, center}',
        r'\begin{tikzpicture}[',
        r'    scale=0.95,',
        r'    vertex/.style={circle, draw=danavy, fill=dablue!15, thick, inner sep=0pt, minimum size=7.0mm, font=\small\bfseries\color{danavy}},',
        r'    edge/.style={draw=danavy, thick}',
        r']'
    ]
    for v in vertices:
        x, y = coords.get(v, (0, 0))
        tikz_lines.append(f'\\node[vertex] ({v}) at ({x}, {y}) {{{v}}};')

    for u, v, w in edges:
        xu, yu = coords.get(u, (0, 0))
        xv, yv = coords.get(v, (0, 0))
        dx = xv - xu
        dy = yv - yu
        if abs(dx) < 0.2:
            pos = 'left=2pt' if (xu <= 2.5) else 'right=2pt'
        elif abs(dy) < 0.2:
            pos = 'above=2pt' if (yu >= 1.4) else 'below=2pt'
        elif dy > 0:
            pos = 'above left=1pt' if dx > 0 else 'above right=1pt'
        else:
            pos = 'below right=1pt' if dx > 0 else 'below left=1pt'

        weight_label = f' node[midway, {pos}, font=\\scriptsize\\bfseries, fill=white, fill opacity=0.92, text opacity=1, inner sep=1.5pt] {{{w}}}' if w else ''
        tikz_lines.append(f'\\draw[edge] ({u}) -- ({v}){weight_label};')

    tikz_lines.append(r'\end{tikzpicture}')
    tikz_lines.append(r'\end{adjustbox}')
    tikz_lines.append(r'\end{center}')
    return '\n'.join(tikz_lines)


def _build_planar_graph_tikz() -> str:
    return rf"""\begin{{center}}
\begin{{adjustbox}}{{max width=0.85\linewidth, max totalheight=3.4cm, keepaspectratio, center}}
\begin{{tikzpicture}}[
    scale=0.95,
    vertex/.style={{circle, draw=danavy, fill=dablue!15, thick, inner sep=0pt, minimum size=7.0mm, font=\small\bfseries\color{{danavy}}}},
    edge/.style={{draw=danavy, thick}}
]
\node[vertex] (A) at (0.0, 1.4) {{A}};
\node[vertex] (B) at (2.2, 2.6) {{B}};
\node[vertex] (C) at (2.2, 0.2) {{C}};
\node[vertex] (D) at (4.4, 2.6) {{D}};
\node[vertex] (E) at (4.4, 0.2) {{E}};
\draw[edge] (A) -- (B);
\draw[edge] (A) -- (C);
\draw[edge] (B) -- (C);
\draw[edge] (B) -- (D);
\draw[edge] (C) -- (E);
\draw[edge] (D) -- (E);
\draw[edge] (B) -- (E);
\draw[edge] (A) to[bend left=38] (D);
\end{{tikzpicture}}
\end{{adjustbox}}
\end{{center}}"""


def _build_shortest_path_network_tikz() -> str:
    return rf"""\begin{{center}}
\begin{{adjustbox}}{{max width=0.85\linewidth, max totalheight=3.4cm, keepaspectratio, center}}
\begin{{tikzpicture}}[
    scale=0.95,
    vertex/.style={{circle, draw=danavy, fill=dablue!15, thick, inner sep=0pt, minimum size=7.0mm, font=\small\bfseries\color{{danavy}}}},
    edge/.style={{draw=danavy, thick}}
]
\node[vertex] (A) at (0.0, 1.4) {{A}};
\node[vertex] (B) at (2.2, 2.6) {{B}};
\node[vertex] (C) at (2.2, 0.2) {{C}};
\node[vertex] (D) at (4.5, 1.4) {{D}};
\node[vertex] (Z) at (6.6, 1.4) {{Z}};
\draw[edge] (A) -- (B) node[midway, above left=1pt, font=\scriptsize\bfseries, fill=white, fill opacity=0.92, inner sep=1.2pt] {{4}};
\draw[edge] (A) -- (C) node[midway, below left=1pt, font=\scriptsize\bfseries, fill=white, fill opacity=0.92, inner sep=1.2pt] {{3}};
\draw[edge] (B) -- (C) node[midway, right=1pt, font=\scriptsize\bfseries, fill=white, fill opacity=0.92, inner sep=1.2pt] {{2}};
\draw[edge] (B) -- (D) node[midway, above right=1pt, font=\scriptsize\bfseries, fill=white, fill opacity=0.92, inner sep=1.2pt] {{5}};
\draw[edge] (C) -- (D) node[midway, below right=1pt, font=\scriptsize\bfseries, fill=white, fill opacity=0.92, inner sep=1.2pt] {{4}};
\draw[edge] (D) -- (Z) node[midway, above=1pt, font=\scriptsize\bfseries, fill=white, fill opacity=0.92, inner sep=1.2pt] {{3}};
\draw[edge] (B) to[bend left=30] node[midway, above=1pt, font=\scriptsize\bfseries, fill=white, fill opacity=0.92, inner sep=1.2pt] {{7}} (Z);
\end{{tikzpicture}}
\end{{adjustbox}}
\end{{center}}"""


def _build_general_network_tikz() -> str:
    return rf"""\begin{{center}}
\begin{{adjustbox}}{{max width=0.85\linewidth, max totalheight=3.4cm, keepaspectratio, center}}
\begin{{tikzpicture}}[
    scale=0.95,
    vertex/.style={{circle, draw=danavy, fill=dablue!15, thick, inner sep=0pt, minimum size=7.0mm, font=\small\bfseries\color{{danavy}}}},
    edge/.style={{draw=danavy, thick}}
]
\node[vertex] (A) at (0.0, 1.4) {{A}};
\node[vertex] (B) at (2.2, 2.6) {{B}};
\node[vertex] (C) at (2.2, 0.2) {{C}};
\node[vertex] (D) at (4.4, 2.6) {{D}};
\node[vertex] (E) at (4.4, 0.2) {{E}};
\draw[edge] (A) -- (B);
\draw[edge] (A) -- (C);
\draw[edge] (B) -- (C);
\draw[edge] (B) -- (D);
\draw[edge] (C) -- (E);
\draw[edge] (D) -- (E);
\end{{tikzpicture}}
\end{{adjustbox}}
\end{{center}}"""


def _build_directed_network_tikz() -> str:
    return rf"""\begin{{center}}
\begin{{adjustbox}}{{max width=0.85\linewidth, max totalheight=3.4cm, keepaspectratio, center}}
\begin{{tikzpicture}}[
    scale=0.95,
    vertex/.style={{circle, draw=danavy, fill=dablue!15, thick, inner sep=0pt, minimum size=7.0mm, font=\small\bfseries\color{{danavy}}}},
    edge/.style={{draw=danavy, thick, ->, >=Stealth}}
]
\node[vertex] (A) at (0.0, 1.8) {{A}};
\node[vertex] (B) at (3.2, 1.8) {{B}};
\node[vertex] (C) at (0.8, 0.0) {{C}};
\node[vertex] (D) at (4.0, 0.0) {{D}};
\draw[edge] (A) -- (B);
\draw[edge] (B) -- (C);
\draw[edge] (A) -- (C);
\draw[edge] (C) -- (D);
\draw[edge] (B) -- (D);
\draw[edge] (D) to[bend right=25] (B);
\end{{tikzpicture}}
\end{{adjustbox}}
\end{{center}}"""


def _build_mst_network_tikz() -> str:
    return rf"""\begin{{center}}
\begin{{adjustbox}}{{max width=0.85\linewidth, max totalheight=3.4cm, keepaspectratio, center}}
\begin{{tikzpicture}}[
    scale=0.95,
    vertex/.style={{circle, draw=danavy, fill=dablue!15, thick, inner sep=0pt, minimum size=7.0mm, font=\small\bfseries\color{{danavy}}}},
    edge/.style={{draw=danavy, thick}}
]
\node[vertex] (A) at (0.0, 1.4) {{A}};
\node[vertex] (B) at (2.2, 2.5) {{B}};
\node[vertex] (C) at (2.2, 0.3) {{C}};
\node[vertex] (D) at (4.5, 2.5) {{D}};
\node[vertex] (E) at (4.5, 0.3) {{E}};
\draw[edge] (A) -- (B) node[midway, above left=1pt, font=\scriptsize\bfseries, fill=white, fill opacity=0.92, inner sep=1.2pt] {{3}};
\draw[edge] (A) -- (C) node[midway, below left=1pt, font=\scriptsize\bfseries, fill=white, fill opacity=0.92, inner sep=1.2pt] {{5}};
\draw[edge] (B) -- (C) node[midway, left=1pt, font=\scriptsize\bfseries, fill=white, fill opacity=0.92, inner sep=1.2pt] {{2}};
\draw[edge] (B) -- (D) node[midway, above=1pt, font=\scriptsize\bfseries, fill=white, fill opacity=0.92, inner sep=1.2pt] {{6}};
\draw[edge] (C) -- (E) node[midway, below=1pt, font=\scriptsize\bfseries, fill=white, fill opacity=0.92, inner sep=1.2pt] {{4}};
\draw[edge] (D) -- (E) node[midway, right=1pt, font=\scriptsize\bfseries, fill=white, fill opacity=0.92, inner sep=1.2pt] {{3}};
\draw[edge] (C) -- (D) node[midway, above right=1pt, font=\scriptsize\bfseries, fill=white, fill opacity=0.92, inner sep=1.2pt] {{5}};
\end{{tikzpicture}}
\end{{adjustbox}}
\end{{center}}"""


def _build_traversable_network_tikz() -> str:
    return rf"""\begin{{center}}
\begin{{adjustbox}}{{max width=0.85\linewidth, max totalheight=3.4cm, keepaspectratio, center}}
\begin{{tikzpicture}}[
    scale=0.95,
    vertex/.style={{circle, draw=danavy, fill=dablue!15, thick, inner sep=0pt, minimum size=7.0mm, font=\small\bfseries\color{{danavy}}}},
    edge/.style={{draw=danavy, thick}}
]
\node[vertex] (A) at (0.0, 0.0) {{A}};
\node[vertex] (B) at (2.2, 2.0) {{B}};
\node[vertex] (C) at (4.4, 0.0) {{C}};
\node[vertex] (D) at (2.2, 0.0) {{D}};
\draw[edge] (A) -- (B);
\draw[edge] (B) -- (C);
\draw[edge] (C) -- (D);
\draw[edge] (D) -- (A);
\draw[edge] (B) -- (D);
\draw[edge] (A) to[bend left=30] (C);
\end{{tikzpicture}}
\end{{adjustbox}}
\end{{center}}"""


def _build_degree_loop_network_tikz() -> str:
    return rf"""\begin{{center}}
\begin{{adjustbox}}{{max width=0.85\linewidth, max totalheight=3.4cm, keepaspectratio, center}}
\begin{{tikzpicture}}[
    scale=0.95,
    vertex/.style={{circle, draw=danavy, fill=dablue!15, thick, inner sep=0pt, minimum size=7.0mm, font=\small\bfseries\color{{danavy}}}},
    edge/.style={{draw=danavy, thick}},
    multiedge/.style={{draw=dablue, thick}},
    loopedge/.style={{draw=dawine, thick}},
    every loop/.style={{min distance=10mm, looseness=7}}
]
\node[vertex] (P) at (0.0, 1.4) {{P}};
\node[vertex] (Q) at (2.4, 1.4) {{Q}};
\node[vertex] (R) at (4.8, 1.4) {{R}};
\node[vertex] (S) at (2.4, -0.4) {{S}};
\draw[multiedge] (P) to[bend left=22] (Q);
\draw[multiedge] (P) to[bend right=22] (Q);
\draw[edge] (Q) -- (R);
\draw[edge] (P) -- (S);
\draw[edge] (Q) -- (S);
\draw[loopedge] (R) edge[loop right] (R);
\end{{tikzpicture}}
\end{{adjustbox}}
\end{{center}}"""


def synthesize_concept_diagram(concept_name: str, topic: str = "", q_text: str = "") -> Optional[str]:
    """
    Synthesizes an authentic, compilable LaTeX TikZ diagram matching the mathematical concept.
    Used to guarantee question variety for visual topics when questions lack individual diagrams.
    """
    c_lower = str(concept_name or "").lower()
    t_lower = str(topic or "").lower()
    q_lower = str(q_text or "").lower()
    comb = f"{c_lower} {t_lower} {q_lower}"

    if any(k in comb for k in ["directed", "digraph", "adjacency matrix", "adjacency matrices"]):
        return _build_directed_network_tikz()
    elif any(k in comb for k in ["tree", "spanning tree", "minimum spanning", "kruskal", "prim"]):
        return _build_mst_network_tikz()
    elif any(k in comb for k in ["shortest path", "dijkstra"]):
        return _build_shortest_path_network_tikz()
    elif any(k in comb for k in ["planar", "euler", "faces", "regions"]):
        return _build_planar_graph_tikz()
    elif any(k in comb for k in ["traversable", "eulerian", "hamiltonian", "trail", "circuit"]):
        return _build_traversable_network_tikz()
    elif any(k in comb for k in ["loop", "multiple edge", "handshaking", "degree of each vertex"]):
        return _build_degree_loop_network_tikz()
    elif any(k in comb for k in ["network", "graph theory", "vertex", "vertices", "edge"]):
        return _build_general_network_tikz()
    elif any(k in comb for k in ["right-angled", "triangle", "hypotenuse", "pythagoras", "trigonometry", "sin", "cos", "tan"]):
        return _build_right_triangle_tikz(q_text)
    elif any(k in comb for k in ["parallel", "transversal", "co-interior", "alternate angle", "corresponding angle"]):
        return _build_parallel_lines_transversal_tikz(q_text)
    return None


def ensure_concept_practice_question_variety(
    practice_questions: List[Dict[str, Any]],
    concept_name: str,
    topic: str
) -> List[Dict[str, Any]]:
    """
    Guarantees authentic pedagogical variety across practice questions:
    approximately 35% to 50% of questions receive clear visual diagrams,
    while remaining questions remain non-diagram calculation or algebraic drills.
    """
    if not practice_questions or len(practice_questions) < 2:
        return practice_questions

    c_name_lower = str(concept_name or "").lower()
    topic_lower = str(topic or "").lower()
    comb = f"{c_name_lower} {topic_lower}"

    is_visual = any(k in comb for k in [
        "network", "graph theory", "planar", "euler", "vertex", "vertices", "edge",
        "shortest path", "spanning tree", "dijkstra", "prim", "kruskal", "digraph", "directed",
        "geometry", "angle", "triangle", "parallel", "transversal", "pythagoras", "trigonometry",
        "bearing", "elevation", "depression", "circle geometry", "quadrilateral", "polygon"
    ])
    if not is_visual:
        return practice_questions

    # Count how many practice questions already have diagrams
    existing_diag_indices = set()
    for idx, pq in enumerate(practice_questions):
        diag = pq.get("diagram_tikz") or pq.get("tikz_diagram") or pq.get("diagram")
        if diag and str(diag).strip():
            existing_diag_indices.add(idx)
        else:
            q_t = pq.get("text") or pq.get("question_text") or pq.get("question") or ""
            if synthesize_network_diagram_from_text(q_t, topic=topic, concept_name=concept_name):
                existing_diag_indices.add(idx)

    # If already has adequate variety (at least 1 diagram for <=3 questions, or at least 2 for >3 questions), keep as is
    n = len(practice_questions)
    target_count = 1 if n <= 3 else (2 if n <= 5 else 3)
    if len(existing_diag_indices) >= target_count:
        return practice_questions

    # Choose alternating candidate indices (Q2, Q4, Q6 -> indices 1, 3, 5)
    candidates = [i for i in [1, 3, 5] if i < n and i not in existing_diag_indices]
    need = target_count - len(existing_diag_indices)
    to_assign = candidates[:need]

    for idx in to_assign:
        pq = practice_questions[idx]
        q_t = pq.get("text") or pq.get("question_text") or pq.get("question") or ""
        diag = synthesize_concept_diagram(concept_name, topic, q_t)
        if diag:
            pq["diagram_tikz"] = diag
            # If the question text does not refer to the diagram, prepend a clean visual reference
            if not re.search(r'\b(shown below|in the diagram|in the network shown|in the figure shown|for the network shown|refer to the diagram)\b', q_t, re.IGNORECASE):
                if "planar" in comb:
                    prefix = "In the planar graph shown below, "
                elif any(k in comb for k in ["directed", "digraph"]):
                    prefix = "For the directed network shown below: "
                elif any(k in comb for k in ["triangle", "pythagoras", "trigonometry"]):
                    prefix = "In the right-angled triangle shown below, "
                elif any(k in comb for k in ["parallel"]):
                    prefix = "In the figure shown below with parallel lines, "
                else:
                    prefix = "For the network shown below: "

                if re.match(r'^(?:A|The)\s+(?:connected\s+)?planar\s+graph\b', q_t, re.IGNORECASE):
                    q_t_adj = re.sub(r'^(?:A|The)\s+(?:connected\s+)?planar\s+graph\b', 'The planar graph shown below', q_t, count=1, flags=re.IGNORECASE)
                elif re.match(r'^(?:A|The)\s+network\b', q_t, re.IGNORECASE):
                    q_t_adj = re.sub(r'^(?:A|The)\s+network\b', 'The network shown below', q_t, count=1, flags=re.IGNORECASE)
                else:
                    q_t_adj = prefix + (q_t[0].lower() + q_t[1:] if q_t else "")

                if "text" in pq:
                    pq["text"] = q_t_adj
                if "question_text" in pq:
                    pq["question_text"] = q_t_adj
                if "question" in pq:
                    pq["question"] = q_t_adj

    return practice_questions


def _build_right_triangle_tikz(t_clean: str) -> str:
    angle_m = re.search(r'\b([1-8]\d)\s*(?:\^?\\circ|degrees?)\b', t_clean, re.IGNORECASE)
    has_theta = bool(re.search(r'\btheta\b|\b\\theta\b|angle\s+[A-Za-z]', t_clean, re.IGNORECASE))
    unit = r"\,\text{cm}" if "cm" in t_clean.lower() else (r"\,\text{m}" if " m" in t_clean.lower() or "metres" in t_clean.lower() else "")

    nums = [int(n) for n in re.findall(r'\b(\d+)\b', t_clean) if 1 <= int(n) <= 500 and (not angle_m or int(n) != int(angle_m.group(1)))]

    if len(nums) >= 2:
        s_nums = sorted(nums, reverse=True)
        hyp_val = f"${s_nums[0]}{unit}$"
        base_val = f"${s_nums[1]}{unit}$"
        height_val = "$x$"
    elif len(nums) == 1:
        base_val = f"${nums[0]}{unit}$"
        hyp_val = "$x$"
        height_val = "$h$" if not angle_m else ""
    else:
        base_val = "$b$"
        height_val = "$a$"
        hyp_val = "$c$"

    angle_code = ""
    if angle_m:
        ang_val = f"{angle_m.group(1)}^\\circ"
        angle_code = rf"""\draw[thick, dablue] (0.8, 0) arc (0:32:0.8);
\node[right, font=\footnotesize\bfseries\color{{dablue}}] at (0.85, 0.25) {{${ang_val}$}};"""
    elif has_theta:
        angle_code = rf"""\draw[thick, dablue] (0.8, 0) arc (0:32:0.8);
\node[right, font=\footnotesize\bfseries\color{{dablue}}] at (0.85, 0.25) {{$\theta$}};"""

    return rf"""\begin{{center}}
\begin{{adjustbox}}{{max width=0.85\linewidth, max totalheight=3.4cm, keepaspectratio, center}}
\begin{{tikzpicture}}[scale=0.9]
\coordinate (A) at (0, 0);
\coordinate (B) at (4.0, 0);
\coordinate (C) at (4.0, 2.5);
\draw[line width=1.2pt, danavy] (A) -- (B) -- (C) -- cycle;
\draw[thick, danavy] (3.6, 0) -- (3.6, 0.4) -- (4.0, 0.4);
\node[below, font=\small\bfseries\color{{danavy}}] at (2.0, -0.05) {{{base_val}}};
\node[right, font=\small\bfseries\color{{danavy}}] at (4.05, 1.25) {{{height_val}}};
\node[above left, font=\small\bfseries\color{{danavy}}] at (2.0, 1.3) {{{hyp_val}}};
{angle_code}
\end{{tikzpicture}}
\end{{adjustbox}}
\end{{center}}"""


def _build_parallel_lines_transversal_tikz(t_clean: str) -> str:
    angle_m = re.search(r'\b([1-8]\d)\s*(?:\^?\\circ|degrees?)\b', t_clean, re.IGNORECASE)
    angle_val = f"{angle_m.group(1)}^\\circ" if angle_m else "65^\\circ"
    return rf"""\begin{{center}}
\begin{{adjustbox}}{{max width=0.85\linewidth, max totalheight=3.4cm, keepaspectratio, center}}
\begin{{tikzpicture}}[scale=0.9]
\draw[line width=1.1pt, danavy] (-0.5, 2.0) -- (4.8, 2.0);
\draw[line width=1.1pt, danavy] (-0.5, 0.0) -- (4.8, 0.0);
\draw[line width=1.2pt, danavy, ->] (2.0, 2.0) -- (2.3, 2.0);
\draw[line width=1.2pt, danavy, ->] (2.0, 0.0) -- (2.3, 0.0);
\draw[line width=1.1pt, dawine] (0.4, -0.5) -- (3.8, 2.5);
\draw[thick, dablue] (1.05, 0) arc (0:41:0.5);
\node[above right, font=\footnotesize\bfseries\color{{dablue}}] at (1.05, 0.05) {{$x$}};
\draw[thick, dablue] (3.25, 2.0) arc (0:41:0.5);
\node[above right, font=\footnotesize\bfseries\color{{dablue}}] at (3.25, 2.05) {{${angle_val}$}};
\end{{tikzpicture}}
\end{{adjustbox}}
\end{{center}}"""


def synthesize_question_diagram(q_text: str, topic: str = "", concept_name: str = "") -> Optional[str]:
    """
    Synthesizes an authentic, compilable LaTeX TikZ diagram when a question references
    a visual figure (networks, planar graphs, right-angled triangles, geometry, parallel lines)
    or specifies network edges in text, but diagram_tikz is empty.

    Purely formula-based or algebraic questions without diagram references return None,
    preserving natural pedagogical question variety between diagram and non-diagram questions.
    """
    if not q_text:
        return None
    raw_text = str(q_text)
    t_clean = re.sub(r'[\$\*\_]', '', raw_text)
    combined_ctx = (t_clean + " " + str(topic) + " " + str(concept_name)).lower()

    # 1. Match explicit weighted or unweighted edge lists in text
    edge_pat1 = re.compile(r'\b([A-Z])([A-Z])\s*[:=]\s*(\d+(?:\.\d+)?)\b')
    weighted_edges = edge_pat1.findall(t_clean)
    if not weighted_edges:
        edge_pat2 = re.compile(r'\(([A-Z])\s*,\s*([A-Z])\)\s*[:=]\s*(\d+(?:\.\d+)?)\b')
        weighted_edges = edge_pat2.findall(t_clean)
    if not weighted_edges:
        edge_pat3 = re.compile(r'\b([A-Z])\s*[-–—]\s*([A-Z])\s*[:=]\s*(\d+(?:\.\d+)?)\b')
        weighted_edges = edge_pat3.findall(t_clean)
    if not weighted_edges:
        edge_pat4 = re.compile(r'\b([A-Z])([A-Z])\s*\(\s*(\d+(?:\.\d+)?)\s*\)')
        weighted_edges = edge_pat4.findall(t_clean)

    unweighted_edges = []
    if not weighted_edges:
        unw_m = re.search(r'\bedges\s*(?:are)?\s*[:\-–—]?\s*([A-Z,\s]+)', t_clean, re.IGNORECASE)
        if unw_m:
            pairs = re.findall(r'\b([A-Z])([A-Z])\b', unw_m.group(1))
            unweighted_edges = [(u, v, '') for u, v in pairs]

    edges = weighted_edges if weighted_edges else unweighted_edges

    v_match = re.search(r'\bvertices\s*(?:are|include)?\s*[:\-–—]?\s*([A-Za-z\s,]+?)(?:\.|\bEdges\b|\bwith\b|\n)', t_clean, re.IGNORECASE)
    vertices = []
    if v_match:
        vertices = [v.upper() for v in re.findall(r'\b[A-Za-z]\b', v_match.group(1))]

    if not vertices and edges:
        v_set = []
        for u, v, w in edges:
            if u not in v_set:
                v_set.append(u)
            if v not in v_set:
                v_set.append(v)
        vertices = sorted(v_set)

    # Deduplicate vertices
    seen = set()
    dedup_v = []
    for v in vertices:
        if v not in seen:
            seen.add(v)
            dedup_v.append(v)
    vertices = dedup_v

    # If explicit edges exist, build custom network
    if len(vertices) >= 3 and edges:
        return _build_custom_network_tikz(vertices, edges)

    # 2. Check for explicit diagram references in question text
    has_diagram_ref = bool(re.search(
        r'\b(shown below|in the diagram|in the network shown|in the figure shown|for the network shown|'
        r'planar graph shown|in the graph shown|refer to the diagram|from the diagram|in the following network|'
        r'given network|the network below|network given below|diagram shows|figure shows|shown in the diagram|'
        r'in the triangle below|in the right-angled triangle|in the diagram alongside)\b',
        t_clean, re.IGNORECASE
    ))

    # If the question does NOT refer to a diagram and has no explicit edges, keep it as a non-diagram drill
    if not has_diagram_ref:
        return None

    # 3. Diagram synthesis based on topic / content
    # First: Check specific geometry / network features in the question text itself:
    t_lower = t_clean.lower()

    # A. Right-Angled Triangle / Trigonometry / Pythagoras
    if any(k in t_lower for k in ['right-angled', 'triangle', 'hypotenuse', 'pythagoras', 'trigonometry', 'sin', 'cos', 'tan', 'angle of elevation', 'angle of depression']):
        return _build_right_triangle_tikz(t_clean)

    # B. Parallel Lines with Transversal
    if any(k in t_lower for k in ['parallel', 'transversal', 'co-interior', 'alternate angle', 'corresponding angle']):
        return _build_parallel_lines_transversal_tikz(t_clean)

    # C. Planar Graphs (Euler's formula: V - E + F = 2, faces, regions)
    if any(k in t_lower for k in ['planar', 'euler', 'faces', 'face', 'regions']):
        return _build_planar_graph_tikz()

    # D. Shortest Path / Dijkstra / Minimum Spanning Tree / Weighted Network
    if any(k in t_lower for k in ['shortest path', 'dijkstra', 'minimum spanning', 'kruskal', 'prim']):
        return _build_shortest_path_network_tikz()

    # E. General Network / Vertex Degrees / Walks / Trails / Eulerian / Hamiltonian
    if any(k in t_lower for k in ['network', 'vertices', 'vertex', 'edges', 'degree', 'eulerian', 'hamiltonian', 'bridge', 'trail', 'walk']):
        return _build_general_network_tikz()

    # Second: If question text only had generic wording ("in the diagram shown below..."), check topic & concept context:
    if any(k in combined_ctx for k in ['planar', 'euler', 'faces', 'face', 'regions']):
        return _build_planar_graph_tikz()

    if any(k in combined_ctx for k in ['shortest path', 'dijkstra', 'minimum spanning', 'kruskal', 'prim']):
        return _build_shortest_path_network_tikz()

    if any(k in combined_ctx for k in ['network', 'vertices', 'vertex', 'edges', 'degree', 'eulerian', 'hamiltonian', 'bridge', 'trail', 'walk']):
        return _build_general_network_tikz()

    if any(k in combined_ctx for k in ['right-angled', 'triangle', 'hypotenuse', 'trigonometry', 'pythagoras', 'sin', 'cos', 'tan']):
        return _build_right_triangle_tikz(t_clean)

    if any(k in combined_ctx for k in ['parallel', 'transversal', 'co-interior', 'alternate angle', 'corresponding angle']):
        return _build_parallel_lines_transversal_tikz(t_clean)

    return None


def synthesize_network_diagram_from_text(q_text: str, topic: str = "", concept_name: str = "") -> Optional[str]:
    """
    Backwards-compatible wrapper delegating to synthesize_question_diagram.
    """
    return synthesize_question_diagram(q_text, topic=topic, concept_name=concept_name)


def clean_sigma_and_advanced_symbols(text: str) -> str:
    """
    Translates capital sigma summation notation (\\sum, \\Sigma, ∑, Σ) and obscure advanced symbols
    into friendly plain English and standard secondary school notation for NSW Year 10 (Stage 5) students.
    Year 10 students have not learned sigma summation notation.
    """
    if not text or not isinstance(text, str):
        return text
    s = text

    # 1. Degree sum / Handshaking Lemma equations:
    # e.g. \sum \deg(v) = 2e, ∑ deg(v) = 2e, \sum_{v \in V} \deg(v) = 2e, \sum \deg = 2e
    s = re.sub(
        r'(?:\\sum|\\Sigma|[∑Σ])\s*(?:_\{[^}]*\}|_v)?\s*\\?(?:deg|text\{deg\}|mathrm\{deg\})\s*(?:\(\s*v(?:_i)?\s*\))?\s*=\s*2\s*([eE])\b',
        r'\\text{Sum of degrees} = 2\1',
        s
    )
    s = re.sub(
        r'(?:\\sum|\\Sigma|[∑Σ])\s*(?:_\{[^}]*\}|_v)?\s*\\?(?:deg|text\{deg\}|mathrm\{deg\})\s*(?:\(\s*v(?:_i)?\s*\))?',
        r'\\text{Sum of degrees}',
        s
    )
    s = re.sub(
        r'(?:\\sum|\\Sigma|[∑Σ])\s*deg\s*(?:\(\s*v\s*\))?',
        r'\\text{Sum of degrees}',
        s
    )

    # 2. Handshaking Lemma phrasing in text mode:
    s = re.sub(
        r'Handshaking\s+Lemma\s*:\s*(?:\\sum|\\Sigma|[∑Σ])\s*\\?deg\s*(?:\(\s*v\s*\))?\s*=\s*2\s*([eE])',
        r'Handshaking Lemma: \\text{Sum of degrees} = 2\1',
        s,
        flags=re.IGNORECASE
    )
    s = re.sub(
        r'Handshaking\s+Lemma\s*:\s*(?:\\sum|\\Sigma|[∑Σ])',
        r'Handshaking Lemma: \\text{Sum of degrees}',
        s,
        flags=re.IGNORECASE
    )

    # 3. Statistics summation:
    # \sum x_i or \sum x or \sum X -> Sum of scores / Sum of x
    s = re.sub(r'(?:\\sum|\\Sigma|[∑Σ])\s*(?:_\{[^}]*\}\^?\{?[^}]*\}?)?\s*([xX])(?:_i)?\b', r'\\text{Sum of }\1', s)
    # \sum fx or \sum f_i x_i -> Sum of (f × x)
    s = re.sub(r'(?:\\sum|\\Sigma|[∑Σ])\s*(?:_\{[^}]*\}\^?\{?[^}]*\}?)?\s*f(?:_i)?\s*([xX])(?:_i)?\b', r'\\text{Sum of }(f \\times \1)', s)
    # \sum f or \sum f_i -> Total frequency n
    s = re.sub(r'(?:\\sum|\\Sigma|[∑Σ])\s*(?:_\{[^}]*\}\^?\{?[^}]*\}?)?\s*f(?:_i)?\b', r'\\text{Total frequency } n', s)

    # 4. General summation with indices: \sum_{i=1}^n -> Sum of
    s = re.sub(r'(?:\\sum|\\Sigma|[∑Σ])\s*_\{[^}]*\}\s*(?:\^\{[^}]*\})?', r'\\text{Sum of }', s)
    s = re.sub(r'(?:\\sum|\\Sigma|[∑Σ])\s*_[a-zA-Z0-9]\s*(?:\^[a-zA-Z0-9])?', r'\\text{Sum of }', s)

    # 5. Standalone \sum, \Sigma, ∑, Σ in math or text
    s = re.sub(r'\\sum\b', r'\\text{Sum}', s)
    s = re.sub(r'\\Sigma\b', r'\\text{Sum}', s)
    s = re.sub(r'[∑Σ]', 'Sum', s)

    # 6. Product notation (\prod or ∏)
    s = re.sub(r'\\prod\b', r'\\text{Product}', s)
    s = re.sub(r'∏', 'Product', s)

    # 7. Lowercase sigma (\sigma or σ) in stats
    s = re.sub(r'\\sigma\^2', r'\\text{variance}', s)
    s = re.sub(r'\\sigma\b', r'\\text{SD}', s)
    s = re.sub(r'σ\^2', r'variance', s)
    s = re.sub(r'σ', r'SD', s)

    return s


def sanitize_for_latex(text: str) -> str:
    r"""
    Safely escapes text for LaTeX while preserving:
    1. TikZ diagrams (\begin{tikzpicture}...\end{tikzpicture})
    2. LaTeX tables (\begin{tabular}...\end{tabular}) including stem-and-leaf plots and frequency tables
    3. Mathematical expressions ($$...$$, $...$, \[...\])
    4. Converts bare geometric symbols and markdown formatting safely in text mode.
    """
    if not text:
        return ""

    # Convert any markdown pipe tables to LaTeX tabular before splitting
    text_clean = markdown_table_to_latex(str(text))
    text_clean = clean_sigma_and_advanced_symbols(text_clean)

    # Clean up percentage math wrappers ($5.4\%$ or $5.4%$ or $5%) to pure text mode percentages (5.4\%)
    text_clean = re.sub(r"(?<!\\)\$(\s*\d+(?:\.\d+)?\s*)\\?%\$", r"\1\\%", text_clean)
    # Strip accidental lone dollar sign placed directly before a percentage ($5.4% or $5.4\% -> 5.4%)
    text_clean = re.sub(r"(?<!\\)\$(?=\s*\d+(?:\.\d+)?\s*\\?%)", "", text_clean)

    # Pre-convert currency dollars ($7500, $7 500, $ 50, $7,500.50, $100 000) to \$ so they are never misparsed as math mode
    # Must NOT match percentages, closing dollars, decimal points, math operators, or comma-separated lists of math numbers like ($1, 2, 3, 4$)
    curr_pat = re.compile(
        r"(?<!\\)\$"
        r"(?="
        r"\s*\d+(?:[,\s]\d{3})*(?:\.\d+)?"
        r"(?![0-9]|\.[0-9])"                 # Must not leave digits or decimal behind!
        r"(?!\s*!)"                          # A factorial such as $6!$ is mathematical notation
        r"(?!\s*\$)"                         # Must not be followed immediately by closing $ (e.g. $0.4$, $0.006$)
        r"(?![^$\n]*\\[a-zA-Z])"             # If there is a LaTeX command like \mid or \times before the closing $, it is math!
        r"(?!\s*[+\-*/=^<>|](?:\s*\d|\s*[a-zA-Z]|\s*\\))"
        r"(?!\s*,\s*(?:\d|\b[a-zA-Z]\b|\\))"
        r"(?:"
          r"\s*%"
          r"|\s+[a-zA-Z]+"
          r"|/[a-zA-Z]+"
          r"|[.,;:?!)\]\}\s]"
          r"|$"
        r")"
        r")"
    )
    text_clean = curr_pat.sub(r"\\$", text_clean)

    # Strip accidental stray dollar sign inside parenthesized number lists like ($1, 2, 3, 4) -> (1, 2, 3, 4)
    text_clean = re.sub(r"\(\$(\d+(?:\s*,\s*\d+)*)\)", r"(\1)", text_clean)

    # Pre-wrap bare piecewise cases, matrices, aligned, and array environments that lack outer $ or \[
    text_clean = re.sub(
        r"(?<!\$)(?<!\\\[)(\\begin\{(?:cases|matrix|pmatrix|bmatrix|aligned|array)\}[\s\S]*?\\end\{(?:cases|matrix|pmatrix|bmatrix|aligned|array)\})(?!\$)(?!\\\])",
        r"$\1$",
        text_clean
    )

    # Normalize paired $$...$$ into \[...\] for standard LaTeX display math
    text_clean = re.sub(r"\$\$(.*?)\$\$", r"\\[\1\\]", text_clean, flags=re.DOTALL)
    # Convert any remaining lone $$ into $ to avoid unclosed display math delimiters
    text_clean = text_clean.replace("$$", "$")

    pattern = (
        r"((?:\\begin\{center\}\s*)?\\begin\{tikzpicture\}[\s\S]*?\\end\{tikzpicture\}(?:\s*\\end\{center\})?|"
        r"(?:\\begin\{center\}\s*)?(?:\\renewcommand\{\\arraystretch\}\{[^\}]*\}\s*)?\\begin\{tabular\*?\}[\s\S]*?\\end\{tabular\*?\}(?:\s*(?:\\\\\[[^\]]*\]|\\\\)?\s*(?:\\textbf\{)?Key:[^\n]*)?(?:\s*\\end\{center\})?|"
        r"(?<!\\)\$(?:\\\$|[^\$])+?(?<!\\)\$|\\\[[\s\S]*?\\\])"
    )
    parts = re.split(pattern, text_clean)
    res = []
    for p in parts:
        if r"\begin{tikzpicture}" in p and r"\end{tikzpicture}" in p:
            # Preserve TikZ code, ensuring adjustbox wrapping to prevent bounding box overflow and large vertical spires
            if "adjustbox" not in p:
                res.append(f"\\begin{{adjustbox}}{{max width=0.88\\linewidth, max totalheight=5.5cm, keepaspectratio, center}}\n{p}\n\\end{{adjustbox}}")
            else:
                res.append(p)
        elif r"\begin{tabular" in p:
            # Preserve LaTeX tables (stem-and-leaf, frequency tables, matrices)
            tab_block = p.strip()
            key_match = re.search(r"(?:\\\\(?:\[[^\]]*\])?)?\s*(\\textbf\{Key:\}[^\n]*|Key:[^\n]*)", tab_block, flags=re.IGNORECASE)
            key_formatted = ""
            if key_match:
                key_raw = key_match.group(1).strip()
                key_val = re.sub(r"^(?:\\textbf\{)?Key:(?:\})?\s*", "", key_raw, flags=re.IGNORECASE).strip().rstrip(".")
                if "|" in key_val and "$" not in key_val:
                    key_val = re.sub(r"(\d+)\s*\|\s*(\d+)\s*=\s*(\d+)", r"$\1 \\mid \2 = \3$", key_val)
                key_formatted = f"\n\\\\[0.15cm]\n\\textbf{{Key:}} {key_val}"
                tab_block = tab_block[:key_match.start(0)] + tab_block[key_match.end(0):]

            # Strip all outer center and arraystretch wrappers
            tab_block = re.sub(r"^\s*\\begin\{center\}\s*", "", tab_block, flags=re.IGNORECASE).strip()
            tab_block = re.sub(r"\\end\{center\}\s*$", "", tab_block, flags=re.IGNORECASE).strip()
            tab_block = re.sub(r"^\s*\\renewcommand\{\\arraystretch\}\{[^\}]*\}\s*", "", tab_block, flags=re.IGNORECASE).strip()
            tab_block = re.sub(r"\\end\{center\}\s*$", "", tab_block, flags=re.IGNORECASE).strip()

            is_stem_leaf = bool(re.search(r"\bStem\b", tab_block, flags=re.IGNORECASE) and re.search(r"\bLeaf\b", tab_block, flags=re.IGNORECASE))
            if is_stem_leaf:
                tab_block = re.sub(r"(?<!\\textbf\{)Stem\b", r"\\textbf{Stem}", tab_block)
                tab_block = re.sub(r"(?<!\\textbf\{)Leaf\b", r"\\textbf{Leaf}", tab_block)

            res.append(f"\n\\begin{{center}}\n\\renewcommand{{\\arraystretch}}{{1.2}}\n{tab_block}{key_formatted}\n\\end{{center}}\n")
        elif (p.startswith("$") and p.endswith("$")) or (p.startswith(r"\[") and p.endswith(r"\]")):
            # Check for runaway English prose accidentally trapped inside inline math delimiters
            is_runaway = False
            if p.startswith("$") and p.endswith("$") and not p.startswith("$$") and len(p) > 2:
                inner = p[1:-1]
                stripped_inner = re.sub(r"\\(?:text|mathrm|mathbf|mathit|operatorname)\{[^}]*\}", "", inner)
                if re.search(r"[a-zA-Z]{2,}\s+[a-zA-Z]{2,}\s+[a-zA-Z]{2,}", stripped_inner):
                    is_runaway = True

            if not is_runaway:
                # Math mode: standardize math symbols
                m = p
                m = m.replace("—", "-").replace("–", "-").replace("±", "\\pm ")
                m = m.replace("×", "\\times ").replace("÷", "\\div ")
                m = m.replace("°", "^\\circ ").replace("π", "\\pi ")
                m = m.replace("≤", "\\le ").replace("≥", "\\ge ").replace("≠", "\\ne ")
                m = m.replace("≈", "\\approx ").replace("∩", "\\cap ").replace("∪", "\\cup ")
                m = m.replace("⇒", "\\implies ").replace("→", "\\to ")
                # Escape bare & inside \text{...} or non-matrix math environments
                if "&" in m:
                    m = re.sub(r"(\\text\{[^\}]*?)&(.*?})", r"\1\\&\2", m)
                    if not any(env in m for env in ["matrix", "cases", "aligned", "array"]):
                        m = re.sub(r"(?<!\\)&", r"\\&", m)
                # Escape unescaped percent signs in math mode (% -> \%) so LaTeX never comments out closing $ or rest of line
                m = re.sub(r"\\{2,}%", r"\\%", m)
                m = re.sub(r"(?<!\\)%", r"\\%", m)
                res.append(m)
            else:
                # Runaway prose unwrapped to text mode
                s = enforce_australian_english_text(inner)
                res.append(s)
        else:
            # Text mode: enforce Australian English spelling
            s = enforce_australian_english_text(p)
            s = re.sub(r"(\\angle\s+[A-Za-z0-9]+)", lambda m: f"${m.group(1)}$", s)
            s = re.sub(r"(\\angle\b)(?!\s*[A-Za-z0-9])", lambda m: f"${m.group(1)}$", s)
            s = re.sub(r"(\\triangle\s+[A-Za-z]+)", lambda m: f"${m.group(1)}$", s)
            s = re.sub(r"(\\triangle\b)(?!\s*[A-Za-z])", lambda m: f"${m.group(1)}$", s)
            s = re.sub(r"(\\therefore\b)", lambda m: f"${m.group(1)}$", s)
            s = re.sub(r"(\\parallel\b)", lambda m: f"${m.group(1)}$", s)
            s = re.sub(r"(\\perp\b)", lambda m: f"${m.group(1)}$", s)
            s = re.sub(r"(\\sim\b)", lambda m: f"${m.group(1)}$", s)
            s = re.sub(r"(\\equiv\b)", lambda m: f"${m.group(1)}$", s)
            s = re.sub(r"(\\cong\b)", lambda m: f"${m.group(1)}$", s)
            s = re.sub(r"(\d+)\s*\^\\circ\b", lambda m: f"${m.group(1)}^\\circ$", s)
            s = re.sub(r"\\pm\s*\.\.\.", r"\\ensuremath{\\pm\\dots}", s)
            s = re.sub(r"(?<!\\ensuremath\{)\\mathbb\{([^}]+)\}", lambda m: f"\\ensuremath{{\\mathbb{{{m.group(1)}}}}}", s)
            s = re.sub(r"(?<!\\ensuremath\{)\\mathbf\{([^}]+)\}", lambda m: f"\\ensuremath{{\\mathbf{{{m.group(1)}}}}}", s)

            # Auto-wrap fractions and sqrts safely handling nested braces
            s = wrap_bare_sqrts(s)
            s = wrap_bare_fractions(s)

            # Auto-wrap bare algebraic equations (e.g. x - 2y - 1 = 0, y = mx + b, ax + by + c = 0, y - y_1 = m(x - x_1)) in math mode
            eq_pat = re.compile(
                r"(?<![\$\w\\])(?:(?<=\s)|(?<=^)|(?<=\())"
                r"([a-zA-Z0-9_\(\)]+(?:\s*[+\-*/]\s*[a-zA-Z0-9_\(\)]+)*\s*=\s*[+-]?\s*[a-zA-Z0-9_\(\)]+(?:\s*[+\-*/]\s*[a-zA-Z0-9_\(\)]+)*)"
                r"(?=[\s\.,;\?\)]|$)"
            )
            def _wrap_eq_match(m):
                eq = m.group(1).strip()
                if "=" in eq and any(c.isalpha() for c in eq):
                    return f"\\ensuremath{{{eq}}}"
                return m.group(0)

            s = eq_pat.sub(_wrap_eq_match, s)

            # Inverse trig functions: \tan^{-1}, \sin^{-1}, \cos^{-1}
            s = re.sub(r"(?<!\\ensuremath\{)\\(?:tan|sin|cos|cot|sec|csc)\^\{?-1\}?", r"\\ensuremath{\\g<0>}", s)

            # Extrema: A\max -> \ensuremath{A_{\text{max}}}, \max -> \ensuremath{\max}
            s = re.sub(r"(?<![a-zA-Z\\])([a-zA-Z]+)\\(max|min)\b", r"\\ensuremath{\1_{\\text{\2}}}", s)
            s = re.sub(r"(?<!\\ensuremath\{)\\(max|min|lim|sup|inf)\b", r"\\ensuremath{\\g<0>}", s)

            # Subscripts in text mode: m_\perp, y_1, m_{AB}, m_{tan}, m_{norm}
            s = re.sub(r"\b([a-zA-Z])_\\([a-zA-Z]+)\b", r"\\ensuremath{\1_{\\\2}}", s)
            s = re.sub(r"\b([a-zA-Z])_(\{[^\}]+\}|[a-zA-Z0-9]+)", r"\\ensuremath{\1_{\2}}", s)

            bare_math_names = [
                "in", "notin", "subset", "subseteq", "cup", "cap",
                "pm", "mp", "implies", "iff", "to", "le", "ge", "ne", "neq",
                "approx", "times", "div", "infty", "forall", "exists",
                "tan", "sin", "cos", "sec", "csc", "cot", "log", "ln", "exp",
                "Delta", "theta", "alpha", "beta", "gamma", "lambda", "pi",
                "phi", "sigma", "mu", "omega", "Omega",
                "cdot", "dots", "cdots", "vdots", "ddots",
                "setminus", "mid", "parallel", "perp", "triangle", "angle",
                "therefore", "because", "sim", "cong", "equiv"
            ]
            for cmd in bare_math_names:
                s = re.sub(
                    rf"(?<!\\ensuremath\{{)\\{cmd}(?![a-zA-Z])",
                    lambda m, c=cmd: f"\\ensuremath{{\\{c}}}",
                    s
                )

            # Auto-wrap bare algebraic powers (x^2, (1-h)^3, 1^-, 0^+, etc.) safely
            s = re.sub(r"(?<!\\ensuremath\{)(?<!\$)(\([^\(\)\$]+\)\^[\-a-zA-Z0-9\{\}\+\-]+)", r"\\ensuremath{\1}", s)
            s = re.sub(r"(?<!\\ensuremath\{)(?<!\$)(\b[a-zA-Z0-9]+\^[\-a-zA-Z0-9\{\}\+\-]+)", r"\\ensuremath{\1}", s)

            # Protect \ensuremath{...} blocks from text-mode escaping (e.g. converting '_' to '\_')
            ens_blocks = []
            pos = 0
            while True:
                idx = s.find(r"\ensuremath{", pos)
                if idx == -1:
                    break
                start = idx + len(r"\ensuremath{")
                depth = 1
                cur = start
                while cur < len(s) and depth > 0:
                    if s[cur] == '{':
                        depth += 1
                    elif s[cur] == '}':
                        depth -= 1
                    cur += 1
                if depth == 0:
                    full_chunk = s[idx:cur]
                    placeholder = f"XXENSBLK{len(ens_blocks)}XX"
                    ens_blocks.append(full_chunk)
                    s = s[:idx] + placeholder + s[cur:]
                    pos = idx + len(placeholder)
                else:
                    pos = idx + 11

            # Convert markdown bold and italics into LaTeX formatting
            s = re.sub(r"\*\*(.+?)\*\*", lambda m: f"\\textbf{{{m.group(1)}}}", s)
            s = re.sub(r"(?<!\*)\*([^\*\n]+?)\*(?!\*)", lambda m: f"\\textit{{{m.group(1)}}}", s)

            # Escape special LaTeX characters in text mode
            # Clean up over-escaped percent signs (\\% -> \%) and escape unescaped %
            s = re.sub(r"\\{2,}%", r"\\%", s)
            s = re.sub(r"(?<!\\)%", r"\\%", s)
            s = s.replace("_", "\\_")
            s = s.replace("&", "\\&")
            s = s.replace("#", "\\#")
            s = s.replace("—", "---").replace("–", "--")
            s = s.replace("“", "``").replace("”", "''").replace("’", "'").replace("‘", "'")

            # Restore \ensuremath blocks
            for i, block in enumerate(ens_blocks):
                s = s.replace(f"XXENSBLK{i}XX", block)

            res.append(s)
    return "".join(res)

def clean_subtopic_title(subtopic: str) -> str:
    """
    Strips textbook chapter references from a subtopic title.
    e.g. '8A Theoretical probability and sample space' -> 'Theoretical probability & sample space'
    '1.1 Index laws and negative/fractional indices' -> 'Index laws & negative/fractional indices'
    'Chapter 3B: Trigonometry' -> 'Trigonometry'
    'Part 1: 8A Something' -> 'Something'
    """
    s = str(subtopic or "").strip()
    s = re.sub(r'^(?:Part\s+[A-Za-z0-9]+[\:\-\–\—\.]\s*)', '', s, flags=re.IGNORECASE).strip()
    s = re.sub(r'^(?:Set\s+[A-Za-z0-9]+[\:\-\–\—\.]\s*)', '', s, flags=re.IGNORECASE).strip()
    s = re.sub(r'^(?:Chapter|Unit|Topic)\s*\d+[A-Za-z]?[\:\-\–\—\.]\s*', '', s, flags=re.IGNORECASE).strip()
    s = re.sub(r'^\d+\.\d+[\.\:\-\–\—\s]\s*', '', s, flags=re.IGNORECASE).strip()
    s = re.sub(r'^\d+[\.\:\-\–\—]\s*', '', s, flags=re.IGNORECASE).strip()
    if not re.match(r'^[23]D\b', s, flags=re.IGNORECASE):
        s = re.sub(r'^\d+[A-Za-z][\.\:\-\–\—\s]\s*', '', s, flags=re.IGNORECASE).strip()
    s = re.sub(r'\s+and\s+', ' & ', s, flags=re.IGNORECASE).strip()
    return s

def clean_ex_title(title: str) -> str:
    """Strips duplicate 'Example 1:', 'Example 2 -', etc. from example titles, preserving 'Exam Style'."""
    if not title:
        return ""
    t = re.sub(r'^(?:Example|Ex(?!am\b)|E\.g\.?)\s*\d*\s*[:\-–—]?\s*', '', str(title).strip(), flags=re.IGNORECASE)
    t = re.sub(r'^\d+[\.\:\-\–\—\s]\s*', '', t).strip()
    return t.strip() or str(title).strip()

def format_teacher_example_heading(ex_num: int, raw_title: str, year_level: str = "") -> str:
    """
    Formats Teacher Demonstration Example heading according to pedagogical tiers:
    e.g. 'Example 1: Practice (Maximising Enclosed Area with Fixed Perimeter)'
    e.g. 'Example 2: Further Practice (Open-Topped Box Construction)'
    Followed by Application, Thinking Creatively, and Exam Questions.
    """
    clean_t = clean_ex_title(raw_title)
    tier_name = ""

    yl = str(year_level).lower()
    is_senior = ("11" in yl or "12" in yl or "hsc" in yl or "prelim" in yl)

    tier_definitions = [
        ("Thinking Creatively", ["thinking creatively", "challenging", "extension", "level 4", "tier 4"]),
        ("Further Practice", ["further practice", "deeper understanding", "intermediate", "level 2", "tier 2"]),
        ("Exam Questions", ["exam questions", "exam question", "exam style", "past papers", "past paper", "nsw hsc / trial style question", "nsw hsc / trial style", "nsw hsc", "trial style", "hsc style", "level 5", "tier 5"]),
        ("Application", ["application", "advanced", "applying", "level 3", "tier 3"]),
        ("Practice", ["practice", "drilling", "foundation", "level 1", "tier 1"]),
    ]

    for t_name, keywords in tier_definitions:
        kw_pat = "|".join(re.escape(k) for k in keywords)
        m = re.match(rf"^(?:{kw_pat})\s*(?:[:\-–—]|\()\s*(.*?)(?:\))?$", clean_t, flags=re.IGNORECASE)
        if m:
            tier_name = t_name
            clean_t = m.group(1).strip()
            break
        elif re.match(rf"^(?:{kw_pat})$", clean_t, flags=re.IGNORECASE):
            tier_name = t_name
            clean_t = ""
            break

    # Strip any leading/trailing punctuation or parens
    clean_t = re.sub(r"^[\s(:\-–—]+|[\s):\-\—]+$", "", clean_t).strip()

    if not is_senior:
        clean_t = re.sub(r"\b(?:NSW\s+)?HSC\s*/\s*Trial\s*Style\s*Questions?\b", "", clean_t, flags=re.IGNORECASE)
        clean_t = re.sub(r"\b(?:NSW\s+)?HSC\s*/\s*Trial(?:\s+Questions?)?\b", "", clean_t, flags=re.IGNORECASE)
        clean_t = re.sub(r"\b(?:NSW\s+)?HSC(?:\s+Style)?(?:\s+Questions?)?\b", "", clean_t, flags=re.IGNORECASE)
        clean_t = re.sub(r"\bTrial\s*Style\s*Questions?\b", "", clean_t, flags=re.IGNORECASE)
        clean_t = re.sub(r"^[/:,\-\s()]+|[/:,\-\s()]+$", "", clean_t).strip()

    if not tier_name:
        tier_map = {
            1: "Practice",
            2: "Further Practice",
            3: "Application",
            4: "Thinking Creatively",
            5: "Exam Questions"
        }
        tier_name = tier_map.get(ex_num, "Practice")
    else:
        # In classroom theory booklets, Example 1 is always Practice and Example 2 is Further Practice
        if ex_num == 1 and tier_name != "Practice":
            tier_name = "Practice"
        elif ex_num == 2 and tier_name != "Further Practice":
            tier_name = "Further Practice"

    # If clean_t is just the tier name or generic example title, avoid repeating
    if clean_t.lower() in [tier_name.lower(), f"example {ex_num}".lower(), "example"]:
        clean_t = ""

    # Strip any remaining surrounding parentheses or brackets from clean_t
    while (clean_t.startswith("(") and clean_t.endswith(")")) or (clean_t.startswith("[") and clean_t.endswith("]")):
        clean_t = clean_t[1:-1].strip()

    if clean_t:
        return f"Example {ex_num}: {tier_name} ({sanitize_for_latex(clean_t)})"
    else:
        return f"Example {ex_num}: {tier_name}"


def clean_set_notation(text: str) -> str:
    r"""
    Translates advanced / university set theory notation and set builder symbols
    into plain English and standard high school inequalities or intervals for NSW Stage 6 students.
    Eliminates: \in, \notin, \forall, \exists, \mathbb{R}, set-builder braces {x : ...}, cardinality |{...}|, etc.
    """
    if not text or not isinstance(text, str):
        return text
    s = clean_sigma_and_advanced_symbols(text)

    # Specific VLT pattern (Screenshot 1: |{y : (c, y) \in f}| \le 1 \quad \forall c \in \mathbb{R})
    s = re.sub(
        r'\|?\{\s*y\s*:\s*\(?\s*c\s*,\s*y\s*\)?\s*(?:\\in|in)\s*f\s*\}?\|?\s*(?:\\le|<=)\s*1\s*(?:\\quad)?\s*(?:\\forall|for\s+all)?\s*c\s*(?:\\in|in)\s*(?:\\mathbb\{R\}|\b[Rr]\b)',
        r'Any vertical line $x = c$ intersects the graph at most once',
        s,
        flags=re.IGNORECASE
    )
    # Function condition pattern (Screenshot 1: If (x, y_1) \in f and (x, y_2) \in f, then y_1 = y_2)
    s = re.sub(
        r'(?:If\s*)?\$?\(\s*x\s*,\s*y_1\s*\)\s*\\in\s*f\$?\s+and\s+\$?\(\s*x\s*,\s*y_2\s*\)\s*\\in\s*f\$?,?\s*then\s+\$?y_1\s*=\s*y_2\$?',
        r'Each $x$-value has at most one $y$-value (if $x_1 = x_2$, then $y_1 = y_2$)',
        s,
        flags=re.IGNORECASE
    )

    # For all x in R -> for all real x
    s = re.sub(
        r'\b([Ff]or\s+all|[Ff]or\s+any|[Ff]or\s+each)\s*\$?([a-zA-Z])\s*\\in\s*(?:\\mathbb\{R\}|\bR\b)\$?',
        r'\1 real $\2$',
        s,
        flags=re.IGNORECASE
    )

    # Domain/Range set builder: Domain: {x \in \mathbb{R} : x \ne a} -> Domain: all real x \ne a
    s = re.sub(
        r'([Dd]omain|[Rr]ange)\s*:\s*\{\s*([xy])\s*(?:\\in\s*\\mathbb\{R\})?\s*[:\|]\s*([^}]+)\s*\}',
        r'\1: $\3$',
        s
    )
    s = re.sub(
        r'([Dd]omain|[Rr]ange)\s*:\s*\{\s*([xy])\s*\\in\s*\\mathbb\{R\}\s*\}',
        r'\1: all real $\2$',
        s
    )

    # General set builder: {x : condition} or {y : condition} -> condition
    s = re.sub(r'\{\s*([a-zA-Z])\s*[:\|]\s*([^}]+)\s*\}', r'\2', s)

    # Generic \forall and \exists
    s = re.sub(r'\\forall\s*([a-zA-Z])\s*\\in\s*(?:\\mathbb\{R\}|\bR\b)', r'\\text{for all real } \1', s)
    s = re.sub(r'\\forall\s*([a-zA-Z])\b', r'\\text{for all } \1', s)
    s = re.sub(r'\\forall\b', 'for all', s)
    s = re.sub(r'\\exists\s*([a-zA-Z])\b', r'\\text{there exists } \1', s)
    s = re.sub(r'\\exists\b', 'there exists', s)

    # x \in \mathbb{R} -> x is real
    s = re.sub(r'([a-zA-Z])\s*\\in\s*\\mathbb\{R\}', r'\1 \\in \\text{real numbers}', s)
    s = re.sub(r'\\in\s*\\mathbb\{R\}', r'\\text{ is real}', s)
    s = re.sub(r'\\mathbb\{R\}', r'\\text{real numbers}', s)
    s = re.sub(r'\\mathbb\{Z\}', r'\\text{integers}', s)
    s = re.sub(r'\\mathbb\{Q\}', r'\\text{rational numbers}', s)
    s = re.sub(r'\\mathbb\{N\}', r'\\text{natural numbers}', s)

    # Interval in set: x \in [a, b] -> a \le x \le b
    s = re.sub(r'([a-zA-Z])\s*\\in\s*\[\s*([^,\]]+)\s*,\s*([^,\]]+)\s*\]', r'\2 \\le \1 \\le \3', s)
    s = re.sub(r'([a-zA-Z])\s*\\in\s*\(\s*([^,\)]+)\s*,\s*([^,\)]+)\s*\)', r'\2 < \1 < \3', s)
    s = re.sub(r'([a-zA-Z])\s*\\in\s*\[\s*([^,\]]+)\s*,\s*([^,\)]+)\s*\)', r'\2 \\le \1 < \3', s)
    s = re.sub(r'([a-zA-Z])\s*\\in\s*\(\s*([^,\)]+)\s*,\s*([^,\]]+)\s*\]', r'\2 < \1 \\le \3', s)

    # (x, y) \in f or (c, y) \in f
    s = re.sub(r'\(\s*([a-zA-Z0-9_]+)\s*,\s*([a-zA-Z0-9_]+)\s*\)\s*\\in\s*f\b', r'(\1, \2) \\text{ lies on the graph}', s)
    s = re.sub(r'\s*\\in\s*f\b', r' \\text{ lies on the curve}', s)

    # Financial math simplifications for Year 10 / Stage 5:
    # 1. P = A(1 + r)^{-n} -> P = \frac{A}{(1+r)^n} (no negative exponents for present value)
    s = re.sub(r'([PAV])\s*=\s*([PAV])\s*\(\s*1\s*([+-])\s*([rn])\s*\)\^\{\s*-\s*([n1-9])\s*\}', r'\1 = \\frac{\2}{(1 \3 \4)^{\5}}', s)
    s = re.sub(r'([PAV])\s*\(\s*1\s*([+-])\s*([rn])\s*\)\^\{\s*-\s*([n1-9])\s*\}', r'\\frac{\1}{(1 \2 \3)^{\4}}', s)
    s = re.sub(r'([PAV])\s*=\s*([PAV])\s*\(\s*1\s*([+-])\s*([rn])\s*\)\^-\s*([n1-9])\b', r'\1 = \\frac{\2}{(1 \3 \4)^{\5}}', s)
    # 2. Obscure compound interest formula I = P[(1+r)^n - 1] -> I = A - P
    s = re.sub(r'I\s*=\s*P\s*\[\s*\(\s*1\s*\+\s*r\s*\)\^n\s*-\s*1\s*\]', r'I = A - P', s)

    return s


def is_prose_line(line: str) -> bool:
    """
    Returns True if the line contains explanatory English prose, instructions,
    or sentences rather than a pure mathematical equation step.
    """
    s = line.strip()
    if not s:
        return False
    # Strip subpart markers like (a), (b), (i), Step 1:, etc.
    s_clean = re.sub(r'^(?:\([a-hA-H0-9ivx]+\)|\b(?:Step|Case|Condition|Method|Part)\s*\d+[\:\.\-]?)\s*', '', s, flags=re.IGNORECASE).strip()
    # Strip all LaTeX math commands like \frac, \sqrt, \pm, \implies, \alpha, etc.
    s_no_cmds = re.sub(r'\\[a-zA-Z]+', ' ', s_clean)
    # Strip math blocks $...$ or \[...\]
    s_no_math = re.sub(r'\$[^\$]+\$', ' ', s_no_cmds)
    s_no_math = re.sub(r'\\\[[^\\]+\\\]', ' ', s_no_math)
    # Find all words of 2 or more letters
    words = re.findall(r'\b[a-zA-Z]{2,}\b', s_no_math)

    # Common math function / operator words that can appear in pure equations
    MATH_IDENTIFIERS = {
        'sin', 'cos', 'tan', 'sec', 'csc', 'cot', 'arcsin', 'arccos', 'arctan',
        'log', 'ln', 'exp', 'lim', 'max', 'min', 'inf', 'sup', 'det', 'dim',
        'ker', 'deg', 'gcd', 'lcm', 'mod', 'arg', 'dx', 'dy', 'dt', 'du', 'dv'
    }

    english_words = [w for w in words if w.lower() not in MATH_IDENTIFIERS]

    # Known mathematical instruction / heading words
    PROSE_KEYWORDS = {
        'factorize', 'factorise', 'factoring', 'factor', 'expand', 'expanding',
        'rearrange', 'rearranging', 'substitute', 'substituting', 'subbing',
        'solve', 'solving', 'solves', 'differentiate', 'differentiating',
        'integrate', 'integrating', 'evaluate', 'evaluating', 'simplify', 'simplifying',
        'find', 'finding', 'state', 'stating', 'show', 'showing', 'prove', 'proving',
        'check', 'checking', 'verify', 'verifying', 'test', 'testing', 'inspect',
        'condition', 'conditions', 'case', 'cases', 'step', 'steps', 'note', 'notes',
        'notice', 'recall', 'remember', 'let', 'since', 'because', 'therefore',
        'hence', 'thus', 'so', 'then', 'when', 'if', 'for', 'each', 'every', 'all',
        'any', 'both', 'either', 'neither', 'with', 'without', 'where', 'which',
        'from', 'into', 'onto', 'between', 'under', 'over', 'above', 'below',
        'area', 'triangle', 'circle', 'parabola', 'curve', 'line', 'tangent',
        'normal', 'intercept', 'intercepts', 'vertex', 'roots', 'root', 'domain',
        'range', 'asymptote', 'asymptotes', 'maximum', 'minimum', 'extrema',
        'inflexion', 'gradient', 'slope', 'equation', 'equations', 'value', 'values',
        'point', 'points', 'coordinate', 'coordinates', 'ordered', 'pairs',
        'relation', 'relations', 'function', 'functions', 'formula', 'expression',
        'quantity', 'denominator', 'numerator', 'fraction', 'surd', 'radicand',
        'positive', 'negative', 'definite', 'indefinite', 'real', 'numbers',
        'zero', 'distinct', 'equal', 'repeated', 'extraneous', 'gives', 'yields',
        'produces', 'equals', 'satisfies', 'meets', 'intersects', 'crosses',
        'touches', 'cuts', 'opens', 'spans', 'ranges', 'takes', 'holds', 'applies',
        'requires', 'require', 'leads', 'leading', 'is', 'are', 'was', 'were',
        'fails', 'fail', 'passes', 'pass', 'vlt',
        'be', 'been', 'being', 'have', 'has', 'had', 'and', 'or', 'but', 'not',
        'no', 'only', 'also', 'as', 'at', 'by', 'to'
    }

    if any(w.lower() in PROSE_KEYWORDS for w in english_words):
        return True
    return len(english_words) >= 2


def split_implication_chain(raw_line: str, indent: str = r"\hspace*{0.4cm}", mark: str = "") -> List[str]:
    r"""
    Safely splits a mathematical line with implications (\implies, \Rightarrow, \iff)
    into vertically separated steps without corrupting math mode delimiters ($...$)
    or leaving unclosed math blocks.
    """
    line = str(raw_line).strip()
    line = line.replace("⇒", r"\implies ").replace("→", r"\to ")

    # Check if there is a colon separating leading label / text from equation
    # e.g. "y-intercept (set x = 0): y = 4/(0-2) + 1 = -1 \implies (0, -1)."
    colon_m = re.match(r'^([^:]+[:])\s*(.*)$', line)
    leading_label = ""
    if colon_m and not colon_m.group(1).startswith("$") and not colon_m.group(1).startswith(r"\("):
        leading_label = colon_m.group(1).strip()
        line = colon_m.group(2).strip()

    # Check for leading prose words before math
    # e.g. "Set $2 + k = 3 \implies k = 1.$"
    # "Domain requires $49 - x^2 \ge 0 \implies ...$"
    m_prose = re.match(r'^([A-Za-z\s,\(\)\d]+[:\s])\s*\$?([^\$]+.*)$', line)
    leading_prose = ""
    if m_prose:
        cand = m_prose.group(1).strip()
        if any(w.lower() in [
            "set", "let", "domain", "range", "from", "substitute", "sub", "condition",
            "case", "step", "expand", "rearrange", "method", "hence", "therefore",
            "subtract", "divide", "multiply", "add", "equate", "factorise", "factorize"
        ] for w in re.findall(r"\b[a-zA-Z]{2,}\b", cand)):
            leading_prose = cand
            line = m_prose.group(2).strip()

    # Strip any outer and inner stray dollar signs from the math equation body
    clean_math = line.replace("$", "").strip().rstrip(".")

    imp_parts = re.split(r'(\\(?:implies|Rightarrow|iff)\b)', clean_math)
    steps = []

    if leading_label:
        steps.append(f"\\noindent{indent}\\textbf{{{sanitize_for_latex(leading_label)}}}")
    if leading_prose:
        steps.append(f"\\noindent{indent}\\textit{{{sanitize_for_latex(leading_prose)}}}")

    curr = imp_parts[0].strip()
    if curr:
        if is_prose_line(curr):
            curr_math = curr
        else:
            curr_math = f"$\\displaystyle {curr}$"
        steps.append(f"\\noindent{indent}{sanitize_for_latex(curr_math)}")

    j = 1
    while j < len(imp_parts):
        sym = imp_parts[j].strip()
        nxt = imp_parts[j+1].strip() if j+1 < len(imp_parts) else ""
        j += 2
        if nxt:
            trail_prose = ""
            # Detect trailing explanatory sentence after a period: e.g. "y = \pm 4. Since a single input..."
            trail_m = re.search(r'(?<=[.!?])\s+([A-Z][a-zA-Z\s,\$\(\)\-\d]+(?:fails|is|are|yields|domain|range|not|therefore|hence|since|for|in|gives|produces|note|which|because).*)', nxt, flags=re.IGNORECASE)
            if trail_m:
                trail_prose = nxt[trail_m.start():].strip()
                nxt = nxt[:trail_m.start()].strip()

            if is_prose_line(nxt) or re.search(r'\b(?:Function|Relation|Undefined|Parallel|Perpendicular)\b', nxt, flags=re.IGNORECASE):
                step_math = f"$\\displaystyle {sym}$ {nxt}"
            else:
                step_math = f"$\\displaystyle {sym} {nxt}$"
            step_str = f"\\noindent{indent}{sanitize_for_latex(step_math)}"
            if j >= len(imp_parts) and mark and not trail_prose:
                step_str += f" \\hfill{{\\small\\color{{dagreen}}\\textbf{{{sanitize_for_latex(mark)}}}}}"
                mark = ""
            steps.append(step_str)
            if trail_prose:
                steps.append(f"\\noindent{indent}{sanitize_for_latex(trail_prose)}")

    return steps


def format_latex_solution_steps(raw_sol: str) -> str:
    """
    Formats mathematical solutions vertically down, one step per line,
    just like whiteboard mathematical working. Explanations remain as sentences,
    while mathematical equations are displayed on separate vertical lines.
    """
    if not raw_sol:
        return ""
    text_clean = str(raw_sol).strip()
    text_clean = clean_set_notation(text_clean)
    # Preserve LaTeX commands starting with \n (e.g. \ne, \neq, \notin, \node, \noindent, \newline, etc.)
    text_clean = re.sub(
        r'\\n(?!(?:e|eq|otin|abla|u|eg|ot|atural|i|ode|oindent|ew[a-zA-Z]*|ormalsize|opagebreak|eedspace|warrow|earrow|subseteq|supseteq|parallel|mid|exists|ull)\b)',
        '\n',
        text_clean
    )
    # Remove conversational self-correction scratchpad artifacts from LLM
    text_clean = re.sub(r'(?i)\b(?:Wait,?\s*(?:notice this|let\'?s check|let\'?s solve carefully|let\'?s fix|if the condition)|Let\'?s (?:re-verify|solve carefully|verify))\b.*', '', text_clean)

    # Ensure distinct equation steps on the same line start on a new line:
    # 1. Adjacent math blocks separated by whitespace, quad, semicolon, or linebreak: $eq1$ $eq2$ -> $eq1$\n$eq2$
    text_clean = re.sub(r"\$[ \t]*(?:\\quad|\\qquad|;|\\\\)?[ \t]+(?=\$)", "$\n", text_clean)
    # 2. Convert explicit LaTeX linebreaks outside math/environments into newlines
    text_clean = re.sub(r"(?<!\\)\\\\\s*(?!\s*(?:\[|begin|end))", "\n", text_clean)

    lines = text_clean.split("\n")
    formatted_steps = []
    first_item = True

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line in (":", ".", "-", "!"):
            continue

        # Extract mark criteria if present, e.g. [1 mark for ...]
        mark_match = re.search(r'(\[(?:\d+\s*marks?|[A-Za-z0-9\s,]+mark[s]?)[^\]]*\])', line, flags=re.IGNORECASE)
        mark_str = ""
        if mark_match:
            mark_raw = mark_match.group(1)
            mark_str = f"\\hfill{{\\small\\color{{dagreen}}\\textbf{{{sanitize_for_latex(mark_raw)}}}}}"
            line = line[:mark_match.start(1)] + line[mark_match.end(1):]
            line = line.strip().rstrip(".").rstrip(",")
            if not line or line in (":", ".", "-", "!"):
                if mark_str:
                    formatted_steps.append(f"{mark_str}\\par\\vspace{{0.08cm}}")
                continue

        # Check for subpart markers: (a), (b), (c), (d), (i), (ii)
        sub_m = re.match(r'^(?:\*{1,2})?\(([a-hA-H0-9ivx]+)\)(?:\*{1,2})?\s*(.*)$', line)
        if sub_m:
            sub_lbl = sub_m.group(1).lower()
            rest = sub_m.group(2).strip()
            vsep = "" if first_item else "\\par\\vspace{0.14cm}\n"
            first_item = False

            if not rest:
                formatted_steps.append(f"{vsep}\\noindent\\textbf{{\\color{{danavy}}({sub_lbl})}}")
                continue

            # If rest contains implications \implies, separate prose from equation safely
            if r"\implies" in rest or r"\Rightarrow" in rest or r"\iff" in rest or "⇒" in rest:
                formatted_steps.append(f"{vsep}\\noindent\\textbf{{\\color{{danavy}}({sub_lbl})}}")
                imp_steps = split_implication_chain(rest, indent=r"\hspace*{0.4cm}", mark=mark_str)
                mark_str = ""
                for s in imp_steps:
                    formatted_steps.append(f"{s}\\par\\vspace{{0.06cm}}")
                continue
            elif is_prose_line(rest):
                colon_m = re.match(r'^([^:]+[:])\s*(.*)$', rest)
                if colon_m and colon_m.group(2).strip():
                    heading = colon_m.group(1).strip()
                    math_tail = colon_m.group(2).strip()
                    formatted_steps.append(f"{vsep}\\noindent\\textbf{{\\color{{danavy}}({sub_lbl}) {sanitize_for_latex(heading)}}}\\par\\vspace{{0.04cm}}")
                    if math_tail:
                        if not math_tail.startswith("$") and not is_prose_line(math_tail):
                            if "$" not in math_tail:
                                math_tail = f"$\\displaystyle {math_tail}$"
                        step_tex = sanitize_for_latex(math_tail)
                        if mark_str:
                            step_tex += f" {mark_str}"
                            mark_str = ""
                        formatted_steps.append(f"\\noindent\\hspace*{{0.4cm}}{step_tex}\\par\\vspace{{0.06cm}}")
                else:
                    line_tex = f"\\noindent\\textbf{{\\color{{danavy}}({sub_lbl})}}\\enspace {sanitize_for_latex(rest)}"
                    if mark_str:
                        line_tex += f" {mark_str}"
                        mark_str = ""
                    formatted_steps.append(f"{vsep}{line_tex}\\par\\vspace{{0.06cm}}")
                continue
            else:
                s_rest = rest if (rest.startswith("$") or "$" in rest) else f"$\\displaystyle {rest}$"
                step_tex = sanitize_for_latex(s_rest)
                if mark_str:
                    step_tex += f" {mark_str}"
                    mark_str = ""
                formatted_steps.append(f"{vsep}\\noindent\\textbf{{\\color{{danavy}}({sub_lbl})}}\\enspace\\quad {step_tex}\\par\\vspace{{0.06cm}}")
                continue

        first_item = False

        # Check if line is a general prose line or heading
        if is_prose_line(line):
            step_m = re.match(r'^(Step\s*\d+[\:\.\-]?|Condition\s*\d+[\:\.\-]?|Case\s*\d+[\:\.\-]?|Note[\:\.\-]?|Recall[\:\.\-]?)\s*(.*)$', line, flags=re.IGNORECASE)
            if step_m:
                lbl = step_m.group(1).strip()
                bdy = step_m.group(2).strip()
                s_bdy = f" {sanitize_for_latex(bdy)}" if bdy else ""
                sanitized_line = f"\\noindent\\textbf{{\\color{{danavy}}{sanitize_for_latex(lbl)}}}{s_bdy}"
            elif line.endswith(":") or re.match(r'^[^:]+:\s*$', line):
                sanitized_line = f"\\noindent\\textbf{{{sanitize_for_latex(line)}}}"
            else:
                sanitized_line = f"\\noindent {sanitize_for_latex(line)}"

            if mark_str:
                sanitized_line += f" {mark_str}"
            formatted_steps.append(f"{sanitized_line}\\par\\vspace{{0.06cm}}")
            continue

        # If line contains chained implications:
        if r"\implies" in line or r"\Rightarrow" in line or r"\iff" in line or "⇒" in line:
            imp_steps = split_implication_chain(line, indent=r"\hspace*{0.4cm}", mark=mark_str)
            mark_str = ""
            for s in imp_steps:
                formatted_steps.append(f"{s}\\par\\vspace{{0.06cm}}")
            continue

        # Pure equation step:
        fa_match = re.match(r'^(?:Final Answer|Answer)[\:\s]+(.*)$', line, flags=re.IGNORECASE)
        prefix = ""
        s_line = line
        if fa_match:
            prefix = r"\textbf{\color{dagreen}Final Answer:}\quad "
            s_line = fa_match.group(1).strip()

        if s_line.startswith("$") and s_line.endswith("$") and s_line.count("$") == 2:
            inner = s_line[1:-1].strip()
            if not inner.startswith(r"\displaystyle"):
                inner = r"\displaystyle " + inner
            step_tex = f"{prefix}${inner}$"
        elif s_line.startswith(r"\[") and s_line.endswith(r"\]"):
            step_tex = f"{prefix}{s_line}"
        else:
            if "$" in s_line:
                step_tex = f"{prefix}{s_line}"
            else:
                step_tex = f"{prefix}$\\displaystyle {s_line}$"

        step_tex = sanitize_for_latex(step_tex)
        if mark_str:
            step_tex += f" {mark_str}"
        formatted_steps.append(f"\\noindent\\hspace*{{0.4cm}}{step_tex}\\par\\vspace{{0.06cm}}")

    return "\n".join(formatted_steps)


def format_latex_practice_solution(raw_sol: str) -> str:
    """
    Formats practice question worked solutions line-by-line vertically down,
    ensuring each subpart (a), (b), (c) starts on a fresh line, each equation step
    starts on its own indented line, chained implications are separated vertically,
    mark badges [1 mark] do not glue to subsequent words, and trailing mark allocation
    blocks (e.g. [1 mark for part (a), 2 marks for part (b)...]) are cleanly formatted
    without breaking into fragmented lines or empty orphan boxes.
    """
    if not raw_sol:
        return ""
    text = str(raw_sol).strip()
    text = clean_set_notation(text)
    # Preserve LaTeX commands starting with \n
    text = re.sub(
        r'\\n(?!(?:e|eq|otin|abla|u|eg|ot|atural|i|ode|oindent|ew[a-zA-Z]*|ormalsize|opagebreak|eedspace|warrow|earrow|subseteq|supseteq|parallel|mid|exists|ull)\b)',
        '\n',
        text
    )
    # Fix glued marks like [1 mark].yields or [1 mark].m_{BC} -> [1 mark]. yields
    text = re.sub(r'(\[[^\]]*mark[s]?\])\.([a-zA-Z\$\\])', r'\1. \2', text, flags=re.IGNORECASE)

    # 1. Extract trailing or standalone mark allocation block e.g. [1 mark for part (a), 2 marks for part (b)...]
    mark_alloc_match = re.search(
        r'(\[\s*(?:(?:\d+\s*marks?\s+(?:for|each))|Marking|Total:\s*\d+\s*marks?)[^\]]*\])\s*$',
        text,
        flags=re.IGNORECASE
    )
    mark_alloc_str = ""
    part_marks = {}
    if mark_alloc_match:
        mark_alloc_str = mark_alloc_match.group(1).strip()
        text = text[:mark_alloc_match.start(1)].strip()
        # Parse individual subpart allocations
        for m in re.finditer(r'(\d+\s*marks?)\s+for\s+(?:part\s+)?\(?([a-h]|i{1,3}|iv|v|vi)\)?', mark_alloc_str, flags=re.IGNORECASE):
            part_marks[m.group(2).lower()] = f"[{m.group(1).strip()}]"
        for m in re.finditer(r'(?:part\s+)?\(?([a-h]|i{1,3}|iv|v|vi)\)?\s*:\s*(\d+\s*marks?)', mark_alloc_str, flags=re.IGNORECASE):
            part_marks[m.group(1).lower()] = f"[{m.group(2).strip()}]"

    # Ensure distinct equation steps on the same line start on a new line:
    # Adjacent math blocks separated by whitespace, quad, semicolon, or linebreak: $eq1$ $eq2$ -> $eq1$\n$eq2$
    text = re.sub(r"\$[ \t]*(?:\\quad|\\qquad|;|\\\\)?[ \t]+(?=\$)", "$\n", text)
    # Convert explicit LaTeX linebreaks outside math/environments into newlines
    text = re.sub(r"(?<!\\)\\\\\s*(?!\s*(?:\[|begin|end))", "\n", text)

    # Check for subpart markers: (a), (b), (c), etc.
    # Filter out references ("part (a)", "from (b)", "using (a)"), bracketed text, and non-canonical sequences
    subpart_pat = r'(?:(?<=\A)|(?<=[\n.,;!?\s]))(?:\*{1,2})?\(([a-h]|i{1,3}|iv|v|vi)\)(?:\*{1,2})?\s*'
    candidates = list(re.finditer(subpart_pat, text, flags=re.IGNORECASE))

    skip_words = {"part", "subpart", "in", "from", "for", "to", "of", "see", "using", "and", "or", "by", "with", "into", "substitute", "step"}
    valid_matches = []
    expected_alpha = ["a", "b", "c", "d", "e", "f", "g", "h"]
    expected_roman = ["i", "ii", "iii", "iv", "v", "vi"]
    seq_type = None
    next_idx = 0

    for m in candidates:
        lbl = m.group(1).lower()
        pre_text = text[:m.start()].rstrip()
        last_word = pre_text.split()[-1].lower() if pre_text.split() else ""
        last_word = re.sub(r"[^a-z]", "", last_word)
        if last_word in skip_words:
            continue
        open_brackets = text[:m.start()].count("[") - text[:m.start()].count("]")
        if open_brackets > 0:
            continue

        if seq_type is None:
            if lbl in expected_alpha:
                seq_type = "alpha"
                valid_matches.append(m)
                next_idx = expected_alpha.index(lbl) + 1
            elif lbl in expected_roman:
                seq_type = "roman"
                valid_matches.append(m)
                next_idx = expected_roman.index(lbl) + 1
        elif seq_type == "alpha" and next_idx < len(expected_alpha) and lbl == expected_alpha[next_idx]:
            valid_matches.append(m)
            next_idx += 1
        elif seq_type == "roman" and next_idx < len(expected_roman) and lbl == expected_roman[next_idx]:
            valid_matches.append(m)
            next_idx += 1

    parts = []
    if valid_matches and len(valid_matches) >= 2:
        for idx, m in enumerate(valid_matches):
            start = m.end()
            end = valid_matches[idx + 1].start() if idx + 1 < len(valid_matches) else len(text)
            lbl = m.group(1).lower()
            p_text = text[start:end].strip()
            parts.append((f"({lbl})", p_text))
    elif valid_matches and len(valid_matches) == 1 and valid_matches[0].start() < 15:
        lbl = valid_matches[0].group(1).lower()
        p_text = text[valid_matches[0].end():].strip()
        parts.append((f"({lbl})", p_text))
    else:
        if text.strip():
            parts.append(("", text))

    out_blocks = []
    for lbl, p_text in parts:
        block_lines = []
        if lbl:
            block_lines.append(f"\\noindent\\textbf{{\\color{{danavy}}{lbl}}}")

        raw_steps = []
        for line in p_text.split("\n"):
            line = line.strip()
            if not line or re.match(r"^[,;:.!\-\]\[\s]+$", line):
                continue
            # Split sentences that end with [X mark(s)].
            sub_chunks = re.split(r'(\[[^\]]*mark[s]?\]\.?)\s*', line, flags=re.IGNORECASE)
            i = 0
            while i < len(sub_chunks):
                chunk = sub_chunks[i].strip()
                mark = ""
                if i + 1 < len(sub_chunks) and re.match(r'^\[[^\]]*mark[s]?\]\.?$', sub_chunks[i + 1].strip(), flags=re.IGNORECASE):
                    mark = sub_chunks[i + 1].strip().rstrip('.')
                    i += 2
                else:
                    i += 1
                if chunk or mark:
                    raw_steps.append((chunk, mark))

        # Check if this part has a mark allocated from part_marks
        lbl_key = lbl.strip("()") if lbl else ""
        if lbl_key in part_marks and raw_steps:
            has_existing_mark = any(m for _, m in raw_steps)
            if not has_existing_mark:
                last_c, _ = raw_steps[-1]
                raw_steps[-1] = (last_c, part_marks[lbl_key])

        for chunk, mark in raw_steps:
            # Clean leading/trailing punctuation and stray brackets
            chunk = re.sub(r"^[,;:\s\]\[]+", "", chunk).strip()
            chunk = re.sub(r"[,;:\s\]\[]+$", "", chunk).strip()
            if not chunk and mark:
                block_lines.append(f"\\hspace*{{0.25cm}}{{\\footnotesize\\color{{dagreen}}\\textbf{{{mark}}}}}")
                continue

            if not chunk or re.match(r"^[,;:.!\-\]\[\s]+$", chunk):
                continue

            # Check if chunk contains chained implications
            if r"\implies" in chunk or r"\Rightarrow" in chunk or r"\iff" in chunk or "⇒" in chunk:
                imp_steps = split_implication_chain(chunk, indent=r"\hspace*{0.25cm}", mark=mark)
                for s in imp_steps:
                    block_lines.append(s)
                continue

            # Check if chunk has a colon separating explanation and equation
            colon_m = re.match(r'^([^:]+[:])\s*(.+)$', chunk)
            if colon_m and not colon_m.group(1).startswith("$") and not colon_m.group(1).startswith(r"\("):
                exp_part = colon_m.group(1).strip()
                math_part = colon_m.group(2).strip()
                block_lines.append(f"\\noindent\\hspace*{{0.15cm}}\\textit{{{sanitize_for_latex(exp_part)}}}")
                chunk = math_part

            # Check for numbering labels like 1) or Step 1:
            num_m = re.match(r'^((?:\d+\)|[a-zA-Z]\)|\([a-zA-Z0-9]+\)|Step\s*\d+:?|Case\s*\d+:?|Condition\s*\d+:?)\s*)(.*)$', chunk, flags=re.IGNORECASE)
            if num_m and num_m.group(2).strip():
                num_lbl = num_m.group(1).strip()
                rest_chunk = num_m.group(2).strip()
                block_lines.append(f"\\noindent\\hspace*{{0.25cm}}\\textbf{{{sanitize_for_latex(num_lbl)}}}\\enspace")
                chunk = rest_chunk

            clean_c = chunk.strip()
            if not is_prose_line(clean_c) and not clean_c.startswith("$") and not clean_c.startswith(r"\(") and not clean_c.startswith(r"\["):
                if "$" not in clean_c:
                    chunk_formatted = f"$\\displaystyle {clean_c}$"
                else:
                    chunk_formatted = clean_c
            else:
                chunk_formatted = clean_c

            s_chunk = sanitize_for_latex(chunk_formatted)
            if mark:
                s_chunk += f" \\hfill{{\\footnotesize\\color{{dagreen}}\\textbf{{{mark}}}}}"
            block_lines.append(f"\\noindent\\hspace*{{0.25cm}}{s_chunk}")

        if block_lines:
            out_blocks.append("\n\\par\\vspace{0.03cm}\n".join(block_lines))

    # If there was a mark_alloc_str and parts did not consume it or there were no subparts:
    if mark_alloc_str and (not parts or not any(out_blocks)):
        clean_alloc = mark_alloc_str.strip("[]").strip()
        out_blocks.append(f"\\noindent{{\\footnotesize\\color{{dagreen}}\\textbf{{Mark Allocation:}}\\enspace {sanitize_for_latex(clean_alloc)}}}")

    return "\n\\par\\vspace{0.08cm}\n".join(out_blocks)



def sanitize_out_of_syllabus_abs_y(booklet_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Scans and sanitizes/replaces any questions, examples, or notes containing absolute value of y (|y|),
    which is strictly out of scope for NSW Stage 6 Mathematics Advanced.
    """
    if not isinstance(booklet_data, dict):
        return booklet_data

    abs_y_pattern = re.compile(r'\|(?:\s*y\s*|\s*y\s*[\+\-][^|]*)\||\babs\s*\(\s*y\s*\)|\\lvert\s*y\s*\\rvert|\\vert\s*y\s*\\vert', re.IGNORECASE)

    for concept in booklet_data.get("concepts", []):
        if not isinstance(concept, dict):
            continue

        # Sanitize practice questions
        for q in concept.get("practice_questions", []) + concept.get("review_questions", []):
            q_text = q.get("text") or q.get("question_text") or q.get("question") or ""
            q_sol = q.get("worked_solution") or q.get("solution") or ""
            if abs_y_pattern.search(q_text) or abs_y_pattern.search(q_sol):
                replacement_text = "A relation is defined by the equation $x^2 + y^2 = 25$. (a) Determine whether the relation is a function, justifying your answer using the vertical line test. (b) State the domain and range of the relation."
                replacement_ans = "(a) Not a function (fails VLT); (b) Domain: $[-5, 5]$, Range: $[-5, 5]$"
                replacement_sol = "(a) A vertical line such as $x = 0$ intersects the circle at $(0, 5)$ and $(0, -5)$. Because one input produces two outputs, it fails the vertical line test and is not a function [1 mark]. (b) Since $x^2 \\le 25$ and $y^2 \\le 25$, the domain is $-5 \\le x \\le 5$ and the range is $-5 \\le y \\le 5$ [1 mark]."
                q_text = replacement_text
                q_ans = replacement_ans
                q_sol = replacement_sol
            else:
                q_ans = q.get("final_answer") or q.get("answer") or ""

            # Clean set notation from questions and solutions
            q_text = clean_set_notation(q_text)
            q_ans = clean_set_notation(q_ans)
            q_sol = clean_set_notation(q_sol)
            if q.get("diagram_tikz"):
                q["diagram_tikz"] = clean_sigma_and_advanced_symbols(q["diagram_tikz"])
            if q.get("solution_diagram_tikz"):
                q["solution_diagram_tikz"] = clean_sigma_and_advanced_symbols(q["solution_diagram_tikz"])

            q["text"] = q_text
            if "question_text" in q:
                q["question_text"] = q_text
            if "question" in q:
                q["question"] = q_text
            q["final_answer"] = q_ans
            if "answer" in q:
                q["answer"] = q_ans
            q["worked_solution"] = q_sol
            if "solution" in q:
                q["solution"] = q_sol

        # Sanitize teacher demonstration & worked past paper examples
        examples_list = concept.get("teacher_examples", []) or concept.get("worked_past_paper_examples", []) or concept.get("demonstration_examples", [])
        for ex in examples_list:
            p_text = ex.get("problem_text") or ex.get("text") or ex.get("question") or ""
            ex_sol = ex.get("worked_solution") or ex.get("solution") or ""
            if abs_y_pattern.search(p_text) or abs_y_pattern.search(ex_sol):
                replacement_prob = "Consider the relation defined by $x = y^2 - 4$. State whether the relation is a function, and justify your answer algebraically or using a sketch."
                replacement_sol = "Rearranging gives $y^2 = x + 4 \\implies y = \\pm\\sqrt{x+4}$. For $x = 0$, $y = \\pm 2$. Since a single $x$-value yields two distinct $y$-values, the relation fails the vertical line test and is not a function."
                p_text = replacement_prob
                ex_sol = replacement_sol
                ex["title"] = "Vertical Line Test Justification"

            p_text = clean_set_notation(p_text)
            ex_sol = clean_set_notation(ex_sol)
            if ex.get("diagram_tikz"):
                ex["diagram_tikz"] = clean_sigma_and_advanced_symbols(ex["diagram_tikz"])
            if ex.get("solution_diagram_tikz"):
                ex["solution_diagram_tikz"] = clean_sigma_and_advanced_symbols(ex["solution_diagram_tikz"])
            ex["problem_text"] = p_text
            if "text" in ex:
                ex["text"] = p_text
            ex["worked_solution"] = ex_sol
            if "solution" in ex:
                ex["solution"] = ex_sol
            if "teaching_notes" in ex:
                ex["teaching_notes"] = clean_set_notation(ex["teaching_notes"])

        # Sanitize study notes and exam hacks
        s_notes = concept.get("study_notes")
        if isinstance(s_notes, dict):
            pts = s_notes.get("summary_points", [])
            for idx, pt in enumerate(pts):
                pt = re.sub(r'\s*or\s*\$?\s*\|(?:\s*y\s*|\s*y\s*[\+\-][^|]*)\|\s*(?:=\s*[a-zA-Z0-9]+)?\$?', '', pt)
                pt = re.sub(r'\$?\s*\|(?:\s*y\s*|\s*y\s*[\+\-][^|]*)\|\s*\$?', '', pt)
                pts[idx] = clean_set_notation(pt)

        th_content = concept.get("theory_content", "")
        if th_content:
            th_content = re.sub(r'\s*or\s*\$?\s*\|(?:\s*y\s*|\s*y\s*[\+\-][^|]*)\|\s*(?:=\s*[a-zA-Z0-9]+)?\$?', '', th_content)
            th_content = re.sub(r'\$?\s*\|(?:\s*y\s*|\s*y\s*[\+\-][^|]*)\|\s*\$?', '', th_content)
            concept["theory_content"] = clean_set_notation(th_content)

        if "tutor_tips" in concept:
            concept["tutor_tips"] = clean_set_notation(concept["tutor_tips"])

        if "key_formulas" in concept and isinstance(concept["key_formulas"], list):
            concept["key_formulas"] = [clean_set_notation(str(kf)) for kf in concept["key_formulas"]]
        if "key_rules" in concept and isinstance(concept["key_rules"], list):
            concept["key_rules"] = [clean_set_notation(str(kr)) for kr in concept["key_rules"]]

        if concept.get("tikz_diagram"):
            concept["tikz_diagram"] = clean_sigma_and_advanced_symbols(concept["tikz_diagram"])

        for hack in concept.get("exam_hacks", []):
            h_content = hack.get("hack_content", "")
            if h_content:
                h_content = re.sub(r'\s*or\s*\$?\s*\|(?:\s*y\s*|\s*y\s*[\+\-][^|]*)\|\s*(?:=\s*[a-zA-Z0-9]+)?\$?', '', h_content)
                h_content = re.sub(r'\$?\s*\|(?:\s*y\s*|\s*y\s*[\+\-][^|]*)\|\s*\$?', '', h_content)
                hack["hack_content"] = clean_set_notation(h_content)

    return booklet_data


def split_question_subparts(text: str) -> tuple:
    """
    Parses question text into an introductory stem and ordered subparts (e.g. (a), (b), ... or (i), (ii), ...).
    Safeguards against math expressions such as h(x), f(x), (x+1), (x - 2), f(a), etc.
    Returns (stem, [(label, content), ...]). If no valid subparts exist, returns (text, []).
    """
    text = str(text or "").strip()
    if not text:
        return "", []

    # If text is purely a mark allocation block like "[1 mark for part (a)...]", do not split into subparts
    if re.match(r"^\[\s*(?:\d+\s*marks?|Marking|Total)[^\]]+\]$", text, flags=re.IGNORECASE):
        return text, []

    # Allowed subpart markers:
    # 1. Parenthesized lowercase letter (a-h) or roman numerals (i, ii, iii, iv, v, vi), optional markdown bold
    # 2. Or lowercase letter followed by closing parenthesis, period, or colon: a) or a. or a:
    # Must be preceded by start of text or whitespace/punctuation (never a letter/digit/backslash/underscore)
    pattern = re.compile(
        r'(?:(?<=\A)|(?<=[\s.,;:?!\n]))(?:\*{1,2})?(?:\(([a-h]|i{1,3}|iv|v|vi)\)|([a-h])[\)\.\:])(?:\*{1,2})?\s*',
        re.IGNORECASE
    )
    matches = list(pattern.finditer(text))

    skip_words = {"part", "subpart", "in", "from", "for", "to", "of", "see", "using", "and", "or", "by", "with", "into", "substitute", "step"}
    valid_candidates = []
    for m in matches:
        pre_text = text[:m.start()].rstrip()
        last_word = pre_text.split()[-1].lower() if pre_text.split() else ""
        last_word = re.sub(r"[^a-z]", "", last_word)
        if last_word in skip_words:
            continue
        open_brackets = text[:m.start()].count("[") - text[:m.start()].count("]")
        if open_brackets > 0:
            continue
        valid_candidates.append(m)

    labels = [(m.group(1) or m.group(2)).lower() for m in valid_candidates]
    alpha_seq = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h']
    roman_seq = ['i', 'ii', 'iii', 'iv', 'v', 'vi']

    valid_matches = []
    if labels and labels[0] == 'a':
        expected_idx = 0
        for m, lbl in zip(valid_candidates, labels):
            if expected_idx < len(alpha_seq) and lbl == alpha_seq[expected_idx]:
                valid_matches.append(m)
                expected_idx += 1
    elif labels and labels[0] == 'i':
        expected_idx = 0
        for m, lbl in zip(valid_candidates, labels):
            if expected_idx < len(roman_seq) and lbl == roman_seq[expected_idx]:
                valid_matches.append(m)
                expected_idx += 1

    # A single match in the middle of text (not starting at 0) without a following subpart is not a subpart sequence
    if valid_matches and not (len(valid_matches) < 2 and valid_matches[0].start() > 0):
        stem = text[:valid_matches[0].start()].strip()
        stem = re.sub(r'\*+$', '', stem).strip()
        subparts = []
        for i in range(len(valid_matches)):
            m = valid_matches[i]
            lbl = (m.group(1) or m.group(2)).lower()
            start = m.end()
            end = valid_matches[i+1].start() if i + 1 < len(valid_matches) else len(text)
            part_content = text[start:end].strip()
            part_content = re.sub(r'^[:.]\s*', '', part_content)
            part_content = re.sub(r'[\s;,]+$', '', part_content)
            subparts.append((lbl, part_content))
        return stem, subparts

    # Fallback: Multi-line questions where separate lines are separate subpart questions
    # (e.g. Stem: Flowchart... Line 1: Write... Line 2: In your expression from part (a)... Line 3: If the flowchart...)
    raw_lines = [l.strip() for l in text.splitlines() if l.strip()]
    if len(raw_lines) >= 3:
        action_verb_pat = re.compile(
            r"^(?:(?:For\s+part\s+\([a-h]\)|In\s+(?:your\s+)?(?:part\s+\([a-h]\)|expression|answer|working|result))[,:\s]+)?"
            r"(?:Write|State|Find|Determine|Calculate|Evaluate|Simplify|Solve|Identify|Explain|Show|Hence|If|Consider|Describe|Draw|Sketch|Compare|Express|Name|Give|List|Factorise|Expand)\b",
            re.IGNORECASE
        )
        has_part_ref = any(re.search(r"\bpart\s*\([a-h]\)", l, re.IGNORECASE) for l in raw_lines[1:])
        has_verbs = sum(1 for l in raw_lines[1:] if action_verb_pat.search(l))
        if has_part_ref or has_verbs >= len(raw_lines[1:]) - 1:
            stem = raw_lines[0]
            subparts = []
            for idx, ql in enumerate(raw_lines[1:]):
                lbl = alpha_seq[idx] if idx < len(alpha_seq) else str(idx + 1)
                clean_ql = re.sub(r"^(?:\([a-hA-H0-9]+\)|[a-hA-H0-9]+[\.\:\)])\s*", "", ql).strip()
                subparts.append((lbl, clean_ql))
            return stem, subparts

    return text, []


def split_stem_bullet_items(text: str) -> tuple:
    """
    Detects comparative bullet items or sub-options inside a question stem, e.g.:
    'Chloe has $12 000... - Account 1: ... - Account 2: ... Calculate total interest...'
    or '... returns of 7.5% p.a. - Fund A charges ... - Fund B charges ... Calculate the final balance...'
    Returns (intro_text, list_of_bullet_strings, trailing_question_text).
    """
    if not text or not isinstance(text, str):
        return text, [], ""

    keywords = (
        "Fund|Account|Option|Bank|Plan|Investment|Package|Deal|Scheme|Worker|Job|Car|Store|Offer|"
        "Method|Person|Case|Company|Strategy|Policy|Bond|Super|Superannuation|Machine|Contract|Supplier|Loan|Card|Tier"
    )

    # 1. Keyword-based option matching (colon optional if preceded by dash/bullet or newline/boundary):
    item_pat = (
        rf"(?:(?<=\A)|(?<=[\n\s:.]))(?:"
        rf"(?:\s*[-*•]\s*)(?:(?:{keywords})\s+(?:[1-9]|[A-Z])(?:\s*:|\b))|"
        rf"(?:\s*)(?:(?:{keywords})\s+(?:[1-9]|[A-Z])\s*:\s*)|"
        rf"(?:(?<=[\n:;])|(?<=\.\s))\s*(?:(?:{keywords})\s+(?:[1-9]|[A-Z])(?:\s*:|\s+(?:offers|charges|pays|gives|features|has|provides|earns|costs|invests)\b))"
        rf")"
    )
    matches = list(re.finditer(item_pat, text, flags=re.IGNORECASE))

    # 2. Generic bullet items: e.g. '- Option A: ... - Option B: ...' or '- First item ... - Second item ...'
    if len(matches) < 2:
        generic_bullet_pat = r"(?:(?<=\A)|(?<=[\n\s:.]))\s*[-*•]\s+[A-Za-z0-9\s]{2,25}(?::|\s+[a-z])"
        matches = list(re.finditer(generic_bullet_pat, text, flags=re.IGNORECASE))

    if len(matches) < 2:
        return text, [], ""

    intro = text[:matches[0].start()].strip()
    last_m = matches[-1]
    last_text = text[last_m.start():]

    # Detect trailing question prompt
    q_match = re.search(
        r"(?:[.?!\n]|\b(?:p\.a\.|etc\.)\s+)\s*("
        r"(?:Calculate|Find|Determine|Evaluate|Which|What|How|Compare|State|Hence|Show|Verify|Identify|Explain|Write|Compute|Solve|Estimate)\b[\s\S]*)$",
        last_text,
        flags=re.IGNORECASE
    )

    trailing_q = ""
    if q_match:
        trailing_q = q_match.group(1).strip()
        last_bullet_content = last_text[:q_match.start(1)].strip()
        last_bullet_content = re.sub(r"[.\s]+$", "", last_bullet_content).strip()
        if not last_bullet_content.endswith(".") and "p.a" in last_bullet_content:
            last_bullet_content += "."
        elif not last_bullet_content.endswith((".", "!", "?")):
            last_bullet_content += "."
    else:
        last_bullet_content = last_text.strip()

    bullets = []
    for idx, bm in enumerate(matches[:-1]):
        start = bm.start()
        end = matches[idx+1].start()
        item = text[start:end].strip()
        item = re.sub(r"^[-*•]\s*", "", item).strip()
        bullets.append(item)

    last_item = re.sub(r"^[-*•]\s*", "", last_bullet_content).strip()
    bullets.append(last_item)

    return intro, bullets, trailing_q


def format_stem_with_bullet_items(stem_text: str, as_item: bool = True) -> list:
    """
    Formats a question stem that contains comparative items / bullet options
    so that each option starts on a clean new indented line, followed by the concluding prompt.
    """
    intro, bullets, trailing_q = split_stem_bullet_items(stem_text)
    if not bullets:
        prefix = r"\item " if as_item else ""
        return [f"{prefix}{sanitize_for_latex(stem_text)}"]

    keywords = (
        "Fund|Account|Option|Bank|Plan|Investment|Package|Deal|Scheme|Worker|Job|Car|Store|Offer|"
        "Method|Person|Case|Company|Strategy|Policy|Bond|Super|Superannuation|Machine|Contract|Supplier|Loan|Card|Tier"
    )

    lines = []
    prefix = r"\item " if as_item else ""
    if intro:
        lines.append(f"{prefix}{sanitize_for_latex(intro)}")
    for idx, b in enumerate(bullets):
        b_clean = sanitize_for_latex(b)
        colon_m = re.match(r"^([^:]+:)\s*(.*)$", b_clean)
        if colon_m:
            b_tex = f"\\textbf{{{colon_m.group(1)}}}~{colon_m.group(2)}"
        else:
            kw_m = re.match(rf"^((?:{keywords})\s+(?:[1-9]|[A-Z]))\b\s*(.*)$", b_clean, flags=re.IGNORECASE)
            if kw_m:
                b_tex = f"\\textbf{{{kw_m.group(1)}}}~{kw_m.group(2)}"
            else:
                b_tex = b_clean
        lines.append(f"\\par\\nopagebreak\\vspace{{0.06cm}}\\hspace*{{0.35cm}}\\textbullet\\enspace {b_tex}")
    if trailing_q:
        lines.append(f"\\par\\nopagebreak\\vspace{{0.08cm}}\\noindent {sanitize_for_latex(trailing_q)}")
    return lines


def format_latex_question_with_subparts(text: str, as_item: bool = True) -> list:
    """
    Formats a question with subparts so that each subpart (a), (b), etc. starts on a fresh line
    with hanging indentation (wrapped lines align underneath the text after the label, not the label itself).
    Also formats bullet items (- Account 1: ... - Account 2: ...) onto separate lines.
    If as_item is True, prefixes the first line with \\item.
    """
    text = clean_set_notation(text)
    stem, subparts = split_question_subparts(text)
    if not subparts:
        return format_stem_with_bullet_items(text, as_item=as_item)

    first_label = subparts[0][0]
    list_label = r"\textbf{(\roman*)}" if first_label in ["i", "ii", "iii"] else r"\textbf{(\alph*)}"

    lines = []
    if stem:
        stem_lines = format_stem_with_bullet_items(stem, as_item=as_item)
        lines.extend(stem_lines)
    elif as_item:
        lines.append(r"\item \leavevmode")

    lines.append(f"\\begin{{enumerate}}[label={list_label}, leftmargin=1.8em, itemsep=0.2em, topsep=0.15em]")
    for lbl, part in subparts:
        sub_stem, roman_subs = split_question_subparts(part)
        if roman_subs and roman_subs[0][0] in ["i", "ii", "iii"]:
            if sub_stem:
                lines.append(f"\\item {sanitize_for_latex(sub_stem)}")
            else:
                lines.append(r"\item \leavevmode")
            lines.append(r"\begin{enumerate}[label=\textbf{(\roman*)}, leftmargin=1.8em, itemsep=0.15em, topsep=0.1em]")
            for r_lbl, r_part in roman_subs:
                lines.append(f"\\item {sanitize_for_latex(r_part)}")
            lines.append(r"\end{enumerate}")
        else:
            lines.append(f"\\item {sanitize_for_latex(part)}")
    lines.append(r"\end{enumerate}")

    return lines


def condense_theory_notes_for_in_class(content: str) -> str:
    """
    Condenses theory notes for in-class teaching booklets:
    - Extracts Core Definition (1-2 crisp mathematical sentences, stripping fluff/analogies).
    - Extracts Key Rules & Properties.
    - Extracts DA Quick-Method (2-3 procedural steps with numbers on new lines).
    - Strips fluff, self-study analogies (e.g. vending machines, rulers), and redundant triggers/traps.
    """
    if not content:
        return ""

    text = str(content).strip()
    bullet_pat = re.compile(r'(?:^|\n)[\-\*\•]\s+(?:\*\*(.+?)\*\*|__([^_]+)__)?\s*[:\-–—]?\s*([\s\S]*?)(?=(?:\n[\-\*\•]\s+)|\Z)')
    matches = list(bullet_pat.finditer(text))

    if not matches:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return "\n".join(lines[:3])

    sections = {}
    for m in matches:
        header = (m.group(1) or m.group(2) or "").strip().lower()
        body = (m.group(3) or "").strip()
        sections[header] = body

    out_bullets = []

    # 1. Core Definition
    def_body = ""
    for k in ["what it is (from scratch)", "what it is", "core definition", "definition", "core concept", "concept"]:
        if k in sections:
            def_body = sections[k]
            break

    if def_body:
        sentences = re.split(r'(?<=[.!?])\s+', def_body)
        clean_sentences = []
        for s in sentences:
            s_clean = s.strip()
            if not s_clean:
                continue
            if re.match(r'^(?:think of|picture|imagine|for example|analogy|as an analogy)\b', s_clean, re.IGNORECASE):
                continue
            clean_sentences.append(s_clean)
        def_text = " ".join(clean_sentences[:2]).strip()
        if def_text:
            out_bullets.append(f"- **Core Definition**: {def_text}")

    # 2. Key Rules & Properties
    rule_body = ""
    for k in ["rule", "rules", "key rules", "key rules & properties", "key rules and properties", "the golden rule", "properties"]:
        if k in sections:
            rule_body = sections[k]
            break

    if rule_body:
        sentences = re.split(r'(?<=[.!?])\s+', rule_body)
        clean_rule_sentences = []
        for s in sentences:
            s_clean = s.strip()
            if not s_clean:
                continue
            if re.match(r'^(?:think of|picture|imagine)\b', s_clean, re.IGNORECASE):
                continue
            clean_rule_sentences.append(s_clean)
        rule_text = " ".join(clean_rule_sentences[:2]).strip()
        if rule_text:
            out_bullets.append(f"- **Key Rules**: {rule_text}")

    # 3. DA Quick-Method / Step-by-Step Method
    method_body = ""
    for k in ["da quick-method", "quick-method", "step-by-step method", "step-by-step", "method", "steps"]:
        if k in sections:
            method_body = sections[k]
            break

    if method_body:
        step_items = []
        step_pat = re.compile(r'(?:^|\n|\s+)(?:(\d+)[\.\)]\s+)([\s\S]*?)(?=(?:\n|\s+)\d+[\.\)]|\Z)')
        m_steps = list(step_pat.finditer(method_body))
        if m_steps:
            for sm in m_steps[:3]:
                step_text = sm.group(2).strip()
                step_text = " ".join(step_text.split())
                step_items.append(step_text)
        else:
            for line in method_body.splitlines()[:3]:
                line = line.strip()
                line = re.sub(r'^\d+[\.\)]\s*', '', line).strip()
                if line:
                    step_items.append(line)

        if step_items:
            method_lines = ["**DA Quick-Method:**"]
            for s_idx, st in enumerate(step_items, 1):
                method_lines.append(f"{s_idx}. {st}")
            out_bullets.append("\n".join(method_lines))

    if not out_bullets:
        for m in matches[:3]:
            h = (m.group(1) or m.group(2) or "").strip()
            b = (m.group(3) or "").strip()
            b_sents = re.split(r'(?<=[.!?])\s+', b)
            b_trimmed = " ".join(b_sents[:2]).strip()
            if h:
                out_bullets.append(f"- **{h}**: {b_trimmed}")
            else:
                out_bullets.append(f"- {b_trimmed}")

    return "\n".join(out_bullets)


def format_practice_difficulty(diff: str) -> str:
    """
    Converts difficulty levels into modern pedagogical labels:
    - Section 1 - Practice
    - Section 2 - Further Practice
    - Section 3 - Application
    - Section 4 - Challenging
    - Exam Style
    """
    d = str(diff or "").strip()
    d_lower = d.lower()
    if "further" in d_lower or "deeper" in d_lower or "understanding" in d_lower or "medium" in d_lower or "level 2" in d_lower or "section 2" in d_lower:
        return "Section 2 - Further Practice"
    elif "drilling" in d_lower or "practice" in d_lower or "easy" in d_lower or "refresher" in d_lower or "level 1" in d_lower or "section 1" in d_lower:
        return "Section 1 - Practice"
    elif "extremely" in d_lower or "challenging" in d_lower or "distinction" in d_lower or "level 4" in d_lower or "section 4" in d_lower:
        return "Section 4 - Challenging"
    elif "hard" in d_lower or "application" in d_lower or "level 3" in d_lower or "applying" in d_lower or "section 3" in d_lower:
        return "Section 3 - Application"
    elif "exam" in d_lower or "past" in d_lower or "hsc" in d_lower:
        return "Exam Style"
    res = d if d else "Section 1 - Practice"
    return re.sub(r"\bLevel\b", "Section", res, flags=re.IGNORECASE)


def format_hsc_solution_latex(sol: str) -> str:
    """
    Formats mathematical worked solutions into spaced-out, line-by-line official HSC Marking Guideline style:
    1. Detects and separates 'Step 1:', 'Step 2:', 'Method 1:', 'Case 1:', 'Condition 1:', etc. into distinct spaced paragraphs.
    2. Leaves a clear blank line before Step 2, Step 3, etc. for visual separation.
    3. Strips raw markdown bold asterisks around Step headers (**Step 1: ...**).
    4. Unwraps display math if it wraps plain English prose, avoiding centered text blocks and dangling commas.
    5. Formats bulleted deductions ('- Turning Point:', '- Axis of Symmetry:').
    6. Ensures mathematical deductions are spaced out and never clumped into a run-on block.
    """
    if not sol:
        return ""

    text = str(sol).strip()

    # 1. Strip markdown bold asterisks around Step headers
    text = re.sub(r'^\s*\*{1,2}\s*(Step\s+\d+|Method\s+\d+|Case\s+\d+|Condition\s+\d+|Part\s+[A-Za-z0-9]+)\s*[:\-]?\s*(.*?)\s*\*{0,2}\s*$', r'\1: \2', text, flags=re.MULTILINE | re.IGNORECASE)
    text = re.sub(r'\*{1,2}\s*(Step\s+\d+|Method\s+\d+|Case\s+\d+|Condition\s+\d+|Part\s+[A-Za-z0-9]+)\s*[:\-]?\s*\*{1,2}', r'\1:', text, flags=re.IGNORECASE)

    # 2. Normalize step headers so they always start on a fresh newline
    step_pat = r"(?<=\S)\s+(?=(?:Step\s+\d+|Method\s+\d+|Case\s+\d+|Condition\s+\d+|Part\s+[A-Za-z0-9]+)\s*[:\-])"
    text = re.sub(step_pat, "\n\n", text, flags=re.IGNORECASE)

    # 3. Unwrap display math \[ ... \] if it contains predominantly English sentences / prose
    def _unwrap_text_display_math(m):
        inner = m.group(1).strip()
        if inner.startswith(r"\text{") or re.search(r'[A-Za-z]{3,}\s+[A-Za-z]{3,}', inner):
            unwrapped = re.sub(r'\\text\{([^}]*)\}', r'\1', inner)
            return f"\n{unwrapped}\n"
        return m.group(0)

    text = re.sub(r'\\\[([\s\S]*?)\\\]', _unwrap_text_display_math, text)

    # 4. Fix run-on sentences where period is followed immediately by letter without space
    text = re.sub(r'(?<=[a-zA-Z0-9\$\)\}])\.(?=[a-zA-Z])', '. ', text)
    text = re.sub(r'\.\s*:\s*', '.\n\n', text)

    # 5. Fix dangling comma or period on new line (e.g. ".\n, the relation fails..." -> ". Therefore, the relation fails...")
    text = re.sub(r'\.\s*\n\s*,\s*', '. Therefore, ', text)
    text = re.sub(r'\.\s*,\s*', '. Therefore, ', text)
    text = re.sub(r'\n\s*,\s*', ', ', text)
    text = re.sub(r'\n\s*\.\s*', '. ', text)

    # 6. Normalize inline bullet points like " - Turning Point:"
    text = re.sub(r"(?<=\S)\s+[-•]\s+(?=[A-Za-z][A-Za-z0-9\s\-_/]{1,35}:)", "\n- ", text)

    lines = [l.strip() for l in text.split("\n") if l.strip()]
    formatted_blocks = []
    step_count = 0

    for line in lines:
        # Clean dangling comma at start of line
        if line.startswith(","):
            line = line.lstrip(", ").strip()
            if line.startswith("Domain:") or line.startswith("Range:"):
                pass
            elif line:
                line = "Therefore, " + line[0].lower() + line[1:]

        # Check if line is a Step / Method / Case header
        m_step = re.match(r"^(?:\*\*)?\s*(Step\s+\d+|Method\s+\d+|Case\s+\d+|Condition\s+\d+|Part\s+[A-Za-z0-9]+)\s*[:\-]?\s*(.*?)(?:\*\*)?$", line, flags=re.IGNORECASE)
        if m_step:
            step_tag = m_step.group(1).strip()
            rest = m_step.group(2).strip().rstrip("*").strip()
            
            # Leave a clear blank line before step 2, step 3, etc.
            if step_count > 0:
                spacing = r"\par\vspace{0.38cm}"
            else:
                spacing = r"\par\noindent"

            if rest:
                formatted_blocks.append(f"{spacing}\\textbf{{\\color{{dawine}}{sanitize_for_latex(step_tag)}:}} {sanitize_for_latex(rest)}\\\\[0.10cm]")
            else:
                formatted_blocks.append(f"{spacing}\\textbf{{\\color{{dawine}}{sanitize_for_latex(step_tag)}:}}\\\\[0.10cm]")
            step_count += 1
            continue

        # Check if line is a bullet item
        if line.startswith("- ") or line.startswith("* "):
            bullet_text = line[2:].strip()
            formatted_blocks.append(f"\\par\\noindent\\hspace*{{1.2em}}\\ensuremath{{\\bullet}}~{sanitize_for_latex(bullet_text)}\\\\[0.05cm]")
            continue

        # Check if line is a standalone display math or equation
        if line.startswith(r"\[") or line.startswith(r"$$") or line.startswith(r"\begin{aligned}"):
            formatted_blocks.append(sanitize_for_latex(line))
            continue

        # Regular line of working
        formatted_blocks.append(f"\\par\\noindent {sanitize_for_latex(line)}\\\\[0.08cm]")

    return "\n".join(formatted_blocks)


def format_theory_summary_point_latex(clean_pt: str) -> str:
    """
    Formats an individual theory summary bullet point:
    1. Replaces 'The High-Yield Rule' with 'Rule:'.
    2. Detects 'Step-by-Step Self-Study Guide:' and splits individual steps onto their own numbered lines.
    3. Increases vertical spacing between bullet points to 0.28cm for optimal readability.
    """
    clean_pt = str(clean_pt).strip()
    if clean_pt.startswith("- "):
        clean_pt = clean_pt[2:].strip()
    clean_pt = re.sub(r'(\*\*|\b)(?:The\s+)?High-Yield\s+Rule:?(\*\*|\b)?', r'**Rule:**', clean_pt, flags=re.IGNORECASE)

    # Check if this point is a Step-by-Step Guide or contains numbered steps 1. ... 2. ...
    guide_match = re.match(r'^(?:\*\*)?(Step-by-Step(?:[\s\-]+Self-Study)?[\s\-]+Guide:?)(?:\*\*)?\s*(.*)$', clean_pt, flags=re.IGNORECASE | re.DOTALL)
    if guide_match:
        guide_header = guide_match.group(1).strip().rstrip(":")
        steps_body = guide_match.group(2).strip()

        # Split steps: 1. ..., 2. ..., 3. ... or Step 1: ..., Step 2: ...
        raw_steps = re.split(r'(?:^|\s+)(?:Step\s+)?\d+[\.:\)]\s+', steps_body)
        steps = [s.strip() for s in raw_steps if s.strip()]

        if len(steps) >= 2:
            lines = [
                f"\\noindent $\\blacktriangleright$~\\textbf{{{guide_header}:}}\\\\[0.10cm]",
                "\\begin{enumerate}[leftmargin=2.2em, itemsep=0.18em, topsep=0.08cm, parsep=0pt, label=\\textbf{\\arabic*.}]"
            ]
            for step in steps:
                step_clean = step.strip().rstrip("*").strip()
                lines.append(f"\\item {sanitize_for_latex(step_clean)}")
            lines.append("\\end{enumerate}")
            lines.append("\\vspace{0.25cm}")
            return "\n".join(lines)

    # Default bullet point with enlarged spacing (0.28cm)
    return f"\\noindent $\\blacktriangleright$~{sanitize_for_latex(clean_pt)}\\\\[0.28cm]"



def format_question_parts_latex(q_text: str) -> str:
    r"""
    Ensures that question sub-parts like (i), (ii), (iii), (iv), (v) or (a), (b), (c)
    each start on their own brand-new line with proper vertical spacing and no indent,
    while carefully preserving LaTeX math environments ($...$, $$...$$, \[...\]).
    """
    if not q_text:
        return ""

    tokens = re.split(r"(\$\$.*?\$\$|\$.*?\$|\\\[.*?\\\])", q_text, flags=re.DOTALL)

    part_pattern = re.compile(
        r"(?:^|(?<=\s)|(?<=[\.\?!:;\n]))\(([a-e]|i{1,3}|iv|v|vi{0,3}|ix|x)\)(?=\s+)",
        re.IGNORECASE
    )

    formatted_tokens = []
    first_part_seen = False

    for i, token in enumerate(tokens):
        if i % 2 == 0:
            def replace_part(match):
                nonlocal first_part_seen
                part_tag = f"({match.group(1)})"
                if not first_part_seen and match.start() == 0 and i == 0:
                    first_part_seen = True
                    return f"\\noindent\\textbf{{{part_tag}}}"
                first_part_seen = True
                return f"\\par\\vspace{{0.12cm}}\\noindent\\textbf{{{part_tag}}}"

            token = part_pattern.sub(replace_part, token)
            formatted_tokens.append(token)
        else:
            formatted_tokens.append(token)

    return "".join(formatted_tokens)


def format_answer_parts_latex(ans_text: str) -> str:
    """
    Formats an answer string for the Quick Verification Answers sheet so that sub-parts
    (i), (ii), (iii), (iv), (v) or (a), (b), (c) each start on their own brand-new line (\\[0.1cm])
    with bold part tags, stripping unnecessary separators like semicolons or commas before the tag.
    """
    if not ans_text:
        return ""

    tokens = re.split(r"(\$\$.*?\$\$|\$.*?\$|\\\[.*?\\\])", str(ans_text), flags=re.DOTALL)
    part_pat = re.compile(
        r"(?:;\s*|,\s*|\.\s*|\s+|^)\(([a-e]|i{1,3}|iv|v|vi{0,3}|ix|x)\)(?=\s+)",
        re.IGNORECASE
    )

    formatted_tokens = []
    first_part = True
    for i, tok in enumerate(tokens):
        if i % 2 == 0:
            def repl(m):
                nonlocal first_part
                tag = f"({m.group(1)})"
                if first_part and m.start() == 0:
                    first_part = False
                    return f"\\textbf{{{tag}}} "
                first_part = False
                return f"\\\\[0.1cm]\\textbf{{{tag}}} "

            tok = part_pat.sub(repl, tok)
            formatted_tokens.append(tok)
        else:
            formatted_tokens.append(tok)

    return "".join(formatted_tokens).strip()


def estimate_exam_question_content_height_cm(q: Dict[str, Any]) -> float:
    """Estimates the vertical height in cm consumed by question header, text, subparts, and diagram."""
    h = 0.85
    text = q.get("text", "")
    subparts = re.findall(r"(?:^|(?<=\s)|(?<=[\.\?!:;\n]))\(([a-e]|i{1,3}|iv|v|vi{0,3}|ix|x)\)(?=\s+)", text, re.IGNORECASE)
    num_parts = len(subparts)
    char_count = len(text)
    base_lines = max(1, char_count // 75 + 1)
    h += base_lines * 0.48
    if num_parts > 0:
        h += num_parts * 0.38
    diag = q.get("diagram_tikz") or q.get("tikz_diagram")
    if not diag or not str(diag).strip():
        fallback_diag = synthesize_network_diagram_from_text(text)
        if fallback_diag:
            diag = fallback_diag
    if diag and str(diag).strip():
        h += 5.0
    h += 0.35
    return round(h, 2)


def paginate_exam_practice_questions(questions: List[Dict[str, Any]], is_first_concept: bool) -> List[Dict[str, Any]]:
    """
    Partitions exam practice questions into pages and calculates enlarged working box heights
    so that no page has wasted space, spreading boxes all the way down until just above the page number.
    """
    if not questions:
        return []

    pages = []
    current_page = []

    def get_pack_avail_h(p_num: int) -> float:
        if is_first_concept and p_num == 0:
            return 15.8
        elif not is_first_concept and p_num == 0:
            return 22.8
        else:
            return 24.6

    def get_expand_avail_h(p_num: int) -> float:
        if is_first_concept and p_num == 0:
            return 17.6
        elif not is_first_concept and p_num == 0:
            return 22.2
        else:
            return 24.2

    def get_min_box_h(marks: Any) -> float:
        try:
            m = float(marks)
        except Exception:
            m = 2.0
        if m <= 1:
            return 3.5
        elif m <= 2:
            return 4.0
        elif m <= 3:
            return 4.5
        else:
            return 5.0

    p_idx = 0
    cur_content_h = 0.0
    cur_min_box_h = 0.0

    for q in questions:
        c_h = estimate_exam_question_content_height_cm(q)
        m_b = get_min_box_h(q.get("marks", 2))
        avail = get_pack_avail_h(p_idx)

        if current_page and (cur_content_h + cur_min_box_h + c_h + m_b > avail):
            pages.append(current_page)
            p_idx += 1
            current_page = [q]
            cur_content_h = c_h
            cur_min_box_h = m_b
        else:
            current_page.append(q)
            cur_content_h += c_h
            cur_min_box_h += m_b

    if current_page:
        pages.append(current_page)

    pages_plan = []
    for p_num, page_qs in enumerate(pages):
        avail_h = get_expand_avail_h(p_num)
        c_heights = [estimate_exam_question_content_height_cm(q) for q in page_qs]
        tot_c = sum(c_heights)
        inter_space = (len(page_qs) - 1) * 0.25
        rem_box = max(len(page_qs) * 3.5, avail_h - tot_c - inter_space)

        max_single = 21.0 if (not is_first_concept or p_num > 0) else 15.6
        weights = [max(float(q.get("marks", 2)), 1.5) for q in page_qs]
        tot_w = sum(weights)

        box_heights = []
        for w in weights:
            bh = rem_box * (w / tot_w)
            bh = max(3.5, min(max_single, bh))
            box_heights.append(round(bh, 1))

        diff = round(rem_box - sum(box_heights), 1)
        if box_heights and (box_heights[-1] + diff) <= max_single:
            box_heights[-1] = round(max(3.5, box_heights[-1] + diff), 1)

        pages_plan.append({
            "questions": page_qs,
            "box_heights": box_heights
        })

    return pages_plan


BOOKLET_PART_TIERS: List[Tuple[str, List[str]]] = [
    ("Part 1: Commit to Memory", ["commit to memory", "commit", "memory", "drilling", "easy", "refresher", "level 1", "part 1"]),
    ("Part 2: Further Practice", ["further practice", "further", "deeper", "understanding", "medium", "level 2", "part 2"]),
    ("Part 3: Application", ["application", "hard", "level 3", "applying", "part 3"]),
    ("Part 4: Thinking Creatively", ["thinking creatively", "creativ", "thinking", "challeng", "extreme", "distinction", "level 4", "part 4"]),
    ("Part 5: Exam Questions", ["exam questions", "exam", "past", "hsc", "level 5", "part 5", "exam style"])
]

def get_booklet_part_tier(diff: str) -> str:
    """Maps a difficulty string to one of the 5 standardized booklet pedagogical parts."""
    d = str(diff or "").strip().lower()
    for part_title, keywords in BOOKLET_PART_TIERS:
        if any(kw in d for kw in keywords):
            return part_title
    return "Part 1: Commit to Memory"

def group_booklet_questions_by_part(questions: List[Dict[str, Any]]) -> List[Tuple[str, List[Dict[str, Any]]]]:
    """
    Groups questions for a concept into ordered pedagogical parts:
    Part 1: Drilling -> Part 2: Further Practice -> Part 3: Application -> Part 4: Thinking Creatively -> Part 5: Exam Questions.
    Returns only non-empty parts in strict sequence.
    """
    buckets = {part_title: [] for part_title, _ in BOOKLET_PART_TIERS}
    for q in questions:
        diff = q.get("difficulty", "")
        tier = get_booklet_part_tier(diff)
        buckets[tier].append(q)

    result = []
    for part_title, _ in BOOKLET_PART_TIERS:
        if buckets[part_title]:
            result.append((part_title, buckets[part_title]))
    if not result and questions:
        result.append(("Part 1: Commit to Memory", list(questions)))
    return result

def strip_mc_options_from_text(text: str) -> str:
    """If question text contains embedded options like (A) ... (B) ... (C) ... (D) ..., strips them."""
    lines = str(text or "").split("\n")
    clean_lines = []
    for line in lines:
        stripped_line = line.strip()
        if re.match(r'^\(?[A-Da-d][\)\.\:\-]\s+', stripped_line):
            continue
        clean_lines.append(line)
    return "\n".join(clean_lines).strip()

def _replace_crowded_combinatorics_diagram(diag: str) -> Optional[str]:
    """Use measured layouts for recurring generated diagrams with colliding labels."""
    if ("5!" in diag and "120" in diag
            and re.search(r"n\s*!", diag)
            and re.search(r"n\s*[-−]\s*2", diag)):
        return r"""\begin{tikzpicture}[>=Stealth]
\node[draw=blue!65, fill=blue!8, rounded corners=3pt, minimum width=1.9cm, minimum height=1.0cm, font=\large] (five) at (0,1.05) {$5!$};
\node[draw=green!60!black, fill=green!8, rounded corners=3pt, minimum width=1.9cm, minimum height=1.0cm, font=\large] (ratio) at (0,-1.05) {$\dfrac{n!}{(n-2)!}$};
\draw[->, thick, blue!75] (five.east) -- (2.45,1.05);
\draw[->, thick, green!60!black] (ratio.east) -- (2.45,-1.05);
\node[anchor=west, font=\large] at (2.65,1.05) {$5\times4\times3\times2\times1=120$};
\node[anchor=west, font=\normalsize] at (2.65,-1.05) {$\dfrac{n(n-1)(n-2)!}{(n-2)!}=n(n-1)$};
\end{tikzpicture}"""

    if (re.search(r"\bPeel\b", diag, re.IGNORECASE)
            and re.search(r"n\s*!", diag)
            and re.search(r"n\s*[-−]\s*2", diag)):
        return r"""\begin{tikzpicture}[>=Stealth]
\node[draw=blue!60!black, fill=blue!9, rounded corners=3pt, minimum width=1.4cm, minimum height=1.1cm, font=\large] (start) at (0,0) {$n!$};
\node[draw=green!50!black, fill=green!9, rounded corners=3pt, minimum width=3.5cm, minimum height=1.1cm, font=\large] (first) at (4.0,0) {$n\times(n-1)!$};
\node[draw=orange!70!black, fill=orange!10, rounded corners=3pt, minimum width=4.1cm, minimum height=1.1cm, font=\large] (second) at (10.0,0) {$n(n-1)(n-2)!$};
\draw[->, thick] (start.east) -- (first.west);
\draw[->, thick] (first.east) -- (second.west);
\node[font=\footnotesize, anchor=south] at (2.0,0.72) {Unroll $n$};
\node[font=\footnotesize, anchor=south] at (7.0,0.72) {Unroll $(n-1)$};
\end{tikzpicture}"""

    if re.search(r"\bUnordered\b", diag, re.IGNORECASE) and re.search(r"\bOrdered\b", diag, re.IGNORECASE):
        return r"""\begin{tikzpicture}[>=Stealth]
\node[draw=green!50!black, fill=green!9, rounded corners=3pt, minimum width=3.5cm, minimum height=1.55cm, align=center, inner sep=5pt] (ordered) at (0,0) {\textbf{Ordered} $({}^nP_r)$\\[2pt]$(A,B)\neq(B,A)$};
\node[draw=blue!60!black, fill=blue!9, rounded corners=3pt, minimum width=3.5cm, minimum height=1.55cm, align=center, inner sep=5pt] (unordered) at (6.1,0) {\textbf{Unordered} $({}^nC_r)$\\[2pt]$\{A,B\}=\{B,A\}$};
\draw[->, very thick, blue!75!black] (ordered.east) -- node[above=4pt, font=\small] {$\div r!$} (unordered.west);
\end{tikzpicture}"""

    if re.search(r"Peel\s+off", diag, re.IGNORECASE) and re.search(r"Remaining\s+countdown", diag, re.IGNORECASE):
        return r"""\begin{tikzpicture}[>=Stealth]
\node[draw=blue!60!black, fill=blue!9, rounded corners=3pt, minimum width=1.7cm, minimum height=1.1cm] (factorial) at (0,0) {$n!$};
\node[draw=green!50!black, fill=green!9, rounded corners=3pt, minimum width=1.5cm, minimum height=1.1cm] (first) at (3.1,0) {$n$};
\node[font=\large] at (4.55,0) {$\times$};
\node[draw=orange!70!black, fill=orange!10, rounded corners=3pt, minimum width=2.3cm, minimum height=1.1cm] (rest) at (6.6,0) {$(n-1)!$};
\draw[->, thick] (factorial.east) -- (first.west);
\node[font=\scriptsize, align=center, text width=2.8cm] at (3.1,-0.95) {Unroll the first factor};
\node[font=\scriptsize, align=center, text width=2.9cm] at (6.6,-0.95) {Remaining countdown};
\end{tikzpicture}"""

    if re.search(r"\bAnchor\b", diag, re.IGNORECASE) and re.search(r"\bChair\s*[2-5]\b", diag, re.IGNORECASE):
        return r"""\begin{tikzpicture}
\draw[thick] (0,0) circle (1.15cm);
\fill[red] (0,1.15) circle (2.2pt);
\fill[blue] (1.09,0.36) circle (2.2pt);
\fill[blue] (0.67,-0.93) circle (2.2pt);
\fill[blue] (-0.67,-0.93) circle (2.2pt);
\fill[blue] (-1.09,0.36) circle (2.2pt);
\node[font=\small\bfseries, text=red, anchor=south] at (0,1.48) {Anchor (1 way)};
\node[font=\small, text=blue, anchor=west] at (1.4,0.36) {Chair 2};
\node[font=\small, text=blue, anchor=north west] at (0.86,-1.13) {Chair 3};
\node[font=\small, text=blue, anchor=north east] at (-0.86,-1.13) {Chair 4};
\node[font=\small, text=blue, anchor=east] at (-1.4,0.36) {Chair 5};
\node[font=\large] at (0,0) {$(5-1)!=24$};
\end{tikzpicture}"""

    if re.search(r"Sample\s+Space", diag, re.IGNORECASE) and re.search(r"\bEvent\b", diag, re.IGNORECASE):
        return r"""\begin{tikzpicture}
\draw[thick] (-2.7,-1.35) rectangle (2.7,1.35);
\node[font=\small\bfseries, anchor=north] at (0,1.17) {Sample Space $S$};
\filldraw[fill=blue!18, draw=black, thick] (0,-0.38) circle (0.73cm);
\node[font=\small\bfseries] at (0,-0.38) {Event $E$};
\end{tikzpicture}"""
    return None


def sanitize_tikz_diagram(diag: str) -> str:
    """Sanitizes TikZ diagram code to fix common LLM formatting errors, prevent overflowing, auto-scale coordinates, and fix quadrant collisions."""
    if not diag:
        return ""
    s = str(diag).strip()
    s = _replace_crowded_combinatorics_diagram(s) or s
    # Australian English spelling
    s = re.sub(r'\bSynthesizer\b', 'Synthesiser', s, flags=re.IGNORECASE)

    # Replace variable=\t with variable=\x to avoid collision with LaTeX \t text accent (only when explicitly used as plot variable)
    if "variable=\\t" in s or "variable = \\t" in s or "variable =\\t" in s or "variable= \\t" in s:
        s = re.sub(r"variable\s*=\s*\\t\b", "variable=\\x", s)
        s = re.sub(r"\\t\b", "\\x", s)
        s = s.replace("{\\t}", "{\\x}")

    # Fix Cartesian plane quadrant label collisions:
    # Stack the quadrant name and sign tuple vertically, add a semi-opaque background badge, and position away from axes and coordinate points
    quad_nodes = {
        1: r"\node[align=center, font=\footnotesize, fill=white, fill opacity=0.85, text opacity=1, inner sep=1.5pt] at (1.8, 3.1) {\textbf{Quadrant 1}\\$(+,+)$};",
        2: r"\node[align=center, font=\footnotesize, fill=white, fill opacity=0.85, text opacity=1, inner sep=1.5pt] at (-2.0, 1.4) {\textbf{Quadrant 2}\\$(-,+)$};",
        3: r"\node[align=center, font=\footnotesize, fill=white, fill opacity=0.85, text opacity=1, inner sep=1.5pt] at (-2.0, -2.6) {\textbf{Quadrant 3}\\$(-,-)$};",
        4: r"\node[align=center, font=\footnotesize, fill=white, fill opacity=0.85, text opacity=1, inner sep=1.5pt] at (2.0, -1.4) {\textbf{Quadrant 4}\\$(+,-)$};"
    }
    q_roman = {1: r"(?:1|I\b)", 2: r"(?:2|II\b)", 3: r"(?:3|III\b)", 4: r"(?:4|IV\b)"}
    for q_num, node_repl in quad_nodes.items():
        q_pat = rf"\\node\s*(?:\[[^\]]*\])?\s*at\s*\([^\)]*\)\s*\{{.*?\bQuadrant\s*{q_roman[q_num]}.*?\}};"
        s = re.sub(q_pat, lambda m, nr=node_repl: nr, s, flags=re.IGNORECASE)

    # Prevent coordinate labels near axes/curves from colliding or being obscured:
    # Ensure coordinate labels like (3, 7) or (0, -11) have white halos if not already styled
    def _halo_node(m):
        prefix = m.group(1)
        opts = m.group(2)
        suffix = m.group(3)
        if "fill=" not in opts:
            opts = f"{opts}, fill=white, fill opacity=0.85, text opacity=1, inner sep=1pt" if opts else "fill=white, fill opacity=0.85, text opacity=1, inner sep=1pt"
        return f"{prefix}{opts}{suffix}"
    s = re.sub(r'((?:\\node|node)\s*\[)([^\]]*?)(\]\s*(?:at\s*\([^\)]*\)\s*)?\{(?:\$)?\([^\)]*\)(?:\$)?\};?)', _halo_node, s)

    # Protect text labels near axes (e.g. Single intersection, test lines, etc.) so axis line never cuts through them:
    def _halo_text_node(m):
        prefix = m.group(1)
        opts = m.group(2)
        content = m.group(3)
        stripped = content.strip()
        # Preserve plain axis labels {$x$}, {$y$}, {$O$}
        if re.match(r'^\{\s*\$?[xyO]\$?\s*\}$', stripped):
            return m.group(0)
        # If node only has right/left without above/below, elevate it above the horizontal axis line
        if "above" not in opts and "below" not in opts:
            opts = re.sub(r'\bright(?:\s*=\s*[^,\]]+)?\b', 'above right=3pt', opts)
            opts = re.sub(r'\bleft(?:\s*=\s*[^,\]]+)?\b', 'above left=3pt', opts)
        if "fill=" not in opts:
            opts = f"{opts}, fill=white, fill opacity=0.92, text opacity=1, inner sep=1.5pt" if opts else "fill=white, fill opacity=0.92, text opacity=1, inner sep=1.5pt"
        return f"{prefix}[{opts}]{content}"

    s = re.sub(r'((?:\\node|node)\s*)\[([^\]]*?)\](\s*\{[^\}]+\})', _halo_text_node, s)

    # Give edge labels their own white halo as well. Without this, a label such
    # as a weight, angle, or table name can be drawn directly over an edge or
    # shape and become unreadable in the compiled booklet.
    def _halo_edge_label(m):
        prefix, opts, suffix = m.group(1), m.group(2), m.group(3)
        if "fill=" not in opts:
            opts = f"{opts}, fill=white, fill opacity=0.92, text opacity=1, inner sep=1.2pt"
        return f"{prefix}{opts}{suffix}"

    s = re.sub(
        r'(node\s*\[)([^\]]*(?:midway|near|above|below|left|right)[^\]]*)(\]\s*\{[^{}]*\})',
        _halo_edge_label,
        s,
        flags=re.IGNORECASE,
    )

    # Fix vertical line test at x = 0 colliding with y-axis arrow:
    def _fix_vlt_node(m):
        prefix = m.group(1)
        opts = m.group(2)
        content = m.group(3)
        opts_clean = re.sub(r'\babove\s*(?:left)?\b', '', opts).strip(', ')
        opts_clean = f'{opts_clean}, above right=4pt, fill=white, fill opacity=0.92, text opacity=1, inner sep=1.5pt' if opts_clean else 'above right=4pt, fill=white, fill opacity=0.92, text opacity=1, inner sep=1.5pt'
        return f'{prefix}{opts_clean}{content}'

    s = re.sub(r'((?:\\node|node)\s*\[)([^\]]*?)(\]\s*(?:at\s*\(\s*0(?:\.0+)?\s*,[^\)]*\)\s*)?\{(?:\$)?x\s*=\s*0(?:\$)?\}(?:;|\s))', _fix_vlt_node, s, flags=re.IGNORECASE)

    if re.search(r'x\s*=\s*0', s):
        s = re.sub(r'(node\s*\[)([^\]]*?\babove\b[^\]]*?)(\]\s*\{(?:\$)?y(?:\$)?\})', r'\1above left\3', s, flags=re.IGNORECASE)

    # Auto-scale TikZ coordinates if large coordinate ranges are detected without explicit unit scaling
    coords = re.findall(r'\(\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\)', s)
    if len(coords) >= 2:
        try:
            xs = [float(x) for x, y in coords]
            ys = [float(y) for x, y in coords]
            dx = max(xs) - min(xs)
            dy = max(ys) - min(ys)
            if dy > 7.0 and not re.search(r'\by\s*=', s) and not re.search(r'\byscale\s*=', s):
                scale_x = round(min(1.1, max(0.45, 6.8 / dx)), 2) if dx > 0 else 1.0
                scale_y = round(min(1.0, max(0.12, 4.8 / dy)), 2) if dy > 0 else 1.0
                # Prepend x and y scale into \begin{tikzpicture}[...]
                if re.search(r'\\begin\{tikzpicture\}\s*\[', s):
                    s = re.sub(r'(\\begin\{tikzpicture\}\s*\[)', rf'\1x={scale_x}cm, y={scale_y}cm, ', s, count=1)
                else:
                    s = re.sub(r'\\begin\{tikzpicture\}', rf'\\begin{{tikzpicture}}[x={scale_x}cm, y={scale_y}cm]', s, count=1)
        except Exception:
            pass

    # Detect broken linear function diagrams where x-intercept or theta is detached:
    if ("mx + c" in s or "mx+c" in s) and ("c/m" in s or r"\frac{c}{m}" in s):
        if re.search(r'\\node.*?[-\\]frac\{c\}\{m\}.*?;', s) and not re.search(r'\\fill\[red!80!black\]\s*\(-2(?:\.0+)?,\s*0\)', s):
            s = get_concept_fallback_tikz("linear functions")

    # Detect colliding credit card timeline diagrams:
    if re.search(r'billing\s+cycle', s, re.IGNORECASE) and re.search(r'payment\s+window|grace\s+period', s, re.IGNORECASE):
        if "raise=24pt" not in s and "raise=20pt" not in s:
            s = get_concept_fallback_tikz("credit card interest, repayments and personal loans")

    # Detect abstract / unreadable superannuation risk-return diagrams:
    if re.search(r'superannuation|super\s+fund', s, re.IGNORECASE) and re.search(r'risk', s, re.IGNORECASE):
        if "Life-Stage Strategy" not in s and "Cash" not in s:
            s = get_concept_fallback_tikz("comparing superannuation growth and investment options")

    # Ensure adjustbox wrapping so diagrams never overflow page boundaries or box borders
    if "begin{tikzpicture}" in s and "adjustbox" not in s:
        if s.startswith(r"\begin{center}") and s.endswith(r"\end{center}"):
            inner = s[14:-12].strip()
            s = f"\\begin{{center}}\n\\begin{{adjustbox}}{{max width=0.88\\linewidth, max totalheight=5.5cm, keepaspectratio, center}}\n{inner}\n\\end{{adjustbox}}\n\\end{{center}}"
        else:
            s = f"\\begin{{adjustbox}}{{max width=0.88\\linewidth, max totalheight=5.5cm, keepaspectratio, center}}\n{s}\n\\end{{adjustbox}}"
    return s


def get_concept_fallback_tikz(concept_name: str, topic: str = "") -> str:
    """
    Generates a pedagogically rich, perfectly scaled, compilable LaTeX TikZ diagram
    for standard NSW Mathematics concepts when no custom diagram was provided by the AI.
    """
    c_lower = str(concept_name or "").lower()
    t_lower = str(topic or "").lower()
    combined = f"{c_lower} {t_lower}"

    # 0. Networks and Graph Theory (NSW Stage 5 / Stage 6 Standard & Advanced)
    if any(k in combined for k in ["network", "graph theory", "vertex", "vertices", "edges", "loops", "degree", "planar", "euler", "matrix", "matrices", "traversable"]):
        if any(k in combined for k in ["tree", "spanning tree", "minimum spanning", "kruskal", "prim"]):
            return r'''\begin{center}
\begin{tikzpicture}[
    scale=0.92,
    vertex/.style={circle, draw=danavy, fill=dablue!20, thick, inner sep=0pt, minimum size=6.5mm, font=\small\bfseries\color{danavy}},
    tree_edge/.style={draw=dablue, line width=1.6pt},
    non_tree_edge/.style={draw=gray!50, thick, dashed}
]
\node[vertex] (A) at (0, 1.8) {A};
\node[vertex] (B) at (3.0, 2.2) {B};
\node[vertex] (C) at (1.2, 0) {C};
\node[vertex] (D) at (4.5, 0.4) {D};
\node[vertex] (E) at (2.6, -1.2) {E};

\draw[tree_edge] (A) -- (C) node[midway, left, font=\scriptsize\bfseries, text=dablue] {2};
\draw[tree_edge] (C) -- (E) node[midway, below left, font=\scriptsize\bfseries, text=dablue] {3};
\draw[tree_edge] (C) -- (B) node[midway, left=2pt, font=\scriptsize\bfseries, text=dablue] {4};
\draw[tree_edge] (B) -- (D) node[midway, above right, font=\scriptsize\bfseries, text=dablue] {5};

\draw[non_tree_edge] (A) -- (B) node[midway, above, font=\scriptsize] {7};
\draw[non_tree_edge] (D) -- (E) node[midway, right, font=\scriptsize] {8};
\draw[non_tree_edge] (C) -- (D) node[midway, below, font=\scriptsize] {6};

\node[align=center, font=\scriptsize, fill=white, fill opacity=0.95, text opacity=1, draw=dablue!40, rounded corners=3pt, inner sep=3.5pt] at (2.4, -2.0) {
\textbf{Minimum Spanning Tree (MST):} $V = 5 \implies E = V-1 = 4$ edges (bold blue)\\
\textbf{No Cycles} \quad$\vert$\quad \textbf{Minimum Total Weight:} $2 + 3 + 4 + 5 = 14$
};
\end{tikzpicture}
\end{center}'''
        elif any(k in combined for k in ["directed", "digraph", "adjacency matrix", "adjacency matrices"]):
            return r'''\begin{center}
\begin{tikzpicture}[
    scale=0.92,
    vertex/.style={circle, draw=danavy, fill=dablue!20, thick, inner sep=0pt, minimum size=6.5mm, font=\small\bfseries\color{danavy}},
    edge/.style={draw=danavy, thick, ->, >=Stealth}
]
\node[vertex] (A) at (0, 1.8) {A};
\node[vertex] (B) at (3.2, 1.8) {B};
\node[vertex] (C) at (0.8, 0) {C};
\node[vertex] (D) at (4.0, 0) {D};

\draw[edge] (A) -- (B);
\draw[edge] (B) -- (C);
\draw[edge] (A) -- (C);
\draw[edge] (C) -- (D);
\draw[edge] (B) -- (D);
\draw[edge] (D) to[bend right=25] (B);

\node[align=center, font=\scriptsize, fill=white, fill opacity=0.95, text opacity=1, draw=danavy!30, rounded corners=3pt, inner sep=3.5pt] at (2.0, -0.95) {
\textbf{Directed Network (Digraph):} Arrows define one-way flow ($i \to j$)\\
\textbf{Row Sum:} Out-degree of $i$ \quad$\vert$\quad \textbf{Column Sum:} In-degree of $j$ \quad$\vert$\quad $M^2$: Two-step paths
};
\end{tikzpicture}
\end{center}'''
        elif any(k in combined for k in ["planar", "euler", "faces", "regions"]):
            return r'''\begin{center}
\begin{tikzpicture}[
    scale=0.92,
    vertex/.style={circle, draw=danavy, fill=dablue!20, thick, inner sep=0pt, minimum size=6.5mm, font=\small\bfseries\color{danavy}},
    edge/.style={draw=danavy, thick}
]
\node[vertex] (A) at (0, 1.5) {A};
\node[vertex] (B) at (2.2, 2.5) {B};
\node[vertex] (C) at (2.2, 0.4) {C};
\node[vertex] (D) at (4.4, 1.5) {D};

\draw[edge] (A) -- (B);
\draw[edge] (A) -- (C);
\draw[edge] (B) -- (C);
\draw[edge] (B) -- (D);
\draw[edge] (C) -- (D);
\draw[edge] (A) to[bend left=38] (D);

\node[font=\footnotesize\bfseries\color{dablue}] at (1.4, 1.45) {$F_1$};
\node[font=\footnotesize\bfseries\color{dablue}] at (3.0, 1.45) {$F_2$};
\node[font=\footnotesize\bfseries\color{dablue}] at (2.2, 2.05) {$F_3$};
\node[font=\footnotesize\bfseries\color{dablue}] at (2.2, -0.2) {$F_4$ (Exterior)};

\node[align=center, font=\scriptsize, fill=white, fill opacity=0.95, text opacity=1, draw=danavy!30, rounded corners=3pt, inner sep=3.5pt] at (2.2, -0.95) {
\textbf{Planar Graph \& Euler's Formula:} $v - e + f = 2$\\
$v = 4 \text{ vertices}, \quad e = 6 \text{ edges} \implies f = 2 - 4 + 6 = 4 \text{ faces (always include exterior region!)}$
};
\end{tikzpicture}
\end{center}'''
        elif any(k in combined for k in ["traversable", "eulerian", "hamiltonian", "walk", "trail", "circuit", "konigsberg"]):
            return r'''\begin{center}
\begin{tikzpicture}[
    scale=0.92,
    vertex/.style={circle, draw=danavy, fill=dablue!20, thick, inner sep=0pt, minimum size=6.5mm, font=\small\bfseries\color{danavy}},
    edge/.style={draw=danavy, thick}
]
\node[vertex] (A) at (0, 0) {A};
\node[vertex] (B) at (2.2, 2.0) {B};
\node[vertex] (C) at (4.4, 0) {C};
\node[vertex] (D) at (2.2, 0) {D};

\draw[edge] (A) -- (B);
\draw[edge] (B) -- (C);
\draw[edge] (C) -- (D);
\draw[edge] (D) -- (A);
\draw[edge] (B) -- (D);
\draw[edge] (A) to[bend left=30] (C);

\node[above left=1pt, font=\scriptsize\bfseries\color{danavy}] at (A) {$\deg(A)=3$};
\node[above=1pt, font=\scriptsize\bfseries\color{danavy}] at (B) {$\deg(B)=3$};
\node[above right=1pt, font=\scriptsize\bfseries\color{danavy}] at (C) {$\deg(C)=3$};
\node[below=1pt, font=\scriptsize\bfseries\color{danavy}] at (D) {$\deg(D)=3$};

\node[align=center, font=\scriptsize, fill=white, fill opacity=0.95, text opacity=1, draw=danavy!30, rounded corners=3pt, inner sep=3.5pt] at (2.2, -0.95) {
\textbf{Eulerian Trail:} Exactly $2$ odd vertices (starts at one odd, ends at other)\\
\textbf{Eulerian Circuit:} All vertices even ($\deg \equiv 0 \pmod 2$) \quad$\vert$\quad \textbf{Hamiltonian:} Visits every vertex once
};
\end{tikzpicture}
\end{center}'''
        elif any(k in combined for k in ["shortest path", "dijkstra", "weighted network"]):
            return r'''\begin{center}
\begin{tikzpicture}[
    scale=0.92,
    vertex/.style={circle, draw=danavy, fill=dablue!20, thick, inner sep=0pt, minimum size=6.5mm, font=\small\bfseries\color{danavy}},
    edge/.style={draw=danavy, thick}
]
\node[vertex] (A) at (0, 1.4) {A};
\node[vertex] (B) at (2.2, 2.4) {B};
\node[vertex] (C) at (2.2, 0.4) {C};
\node[vertex] (D) at (4.4, 1.4) {D};

\draw[edge] (A) -- (B) node[midway, above left, font=\scriptsize\bfseries\color{dablue}] {5};
\draw[edge] (A) -- (C) node[midway, below left, font=\scriptsize\bfseries\color{dablue}] {2};
\draw[edge] (C) -- (B) node[midway, right=1pt, font=\scriptsize\bfseries\color{dablue}] {1};
\draw[edge] (B) -- (D) node[midway, above right, font=\scriptsize\bfseries\color{dablue}] {4};
\draw[edge] (C) -- (D) node[midway, below right, font=\scriptsize\bfseries\color{dablue}] {7};

\node[align=center, font=\scriptsize, fill=white, fill opacity=0.95, text opacity=1, draw=danavy!30, rounded corners=3pt, inner sep=3.5pt] at (2.2, -0.95) {
\textbf{Shortest Path Algorithm:} Compare candidate paths from Start to Finish\\
Path $A \to B \to D = 5 + 4 = 9$ \quad vs \quad Path $A \to C \to B \to D = 2 + 1 + 4 = 7$ (\textbf{Optimal: 7})
};
\end{tikzpicture}
\end{center}'''
        else:
            return r'''\begin{center}
\begin{tikzpicture}[
    scale=0.92,
    vertex/.style={circle, draw=danavy, fill=dablue!20, thick, inner sep=0pt, minimum size=6.5mm, font=\small\bfseries\color{danavy}},
    edge/.style={draw=danavy, thick},
    multiedge/.style={draw=dablue, thick},
    loopedge/.style={draw=dawine, thick},
    every loop/.style={min distance=12mm, looseness=8}
]
\node[vertex] (A) at (0, 1.8) {A};
\node[vertex] (B) at (3.5, 1.8) {B};
\node[vertex] (C) at (1.0, 0) {C};
\node[vertex] (D) at (4.5, 0) {D};

\draw[multiedge] (A) to[bend left=24] node[midway, above, font=\scriptsize, text=dablue] {Multiple Edge} (B);
\draw[multiedge] (A) to[bend right=24] (B);
\draw[edge] (A) -- (C) node[midway, left=2pt, font=\scriptsize] {Edge};
\draw[edge] (B) -- (C);
\draw[edge] (C) -- (D);
\draw[loopedge] (D) edge[loop right] node[right=2pt, font=\scriptsize\bfseries, text=dawine] {Loop (+2 deg)} (D);

\node[above left=1pt, font=\scriptsize\bfseries, text=danavy, fill=white, fill opacity=0.85, text opacity=1, inner sep=1pt] at (A) {$\deg(A)=3$};
\node[above right=1pt, font=\scriptsize\bfseries, text=danavy, fill=white, fill opacity=0.85, text opacity=1, inner sep=1pt] at (B) {$\deg(B)=3$};
\node[below left=1pt, font=\scriptsize\bfseries, text=danavy, fill=white, fill opacity=0.85, text opacity=1, inner sep=1pt] at (C) {$\deg(C)=3$};
\node[below right=1pt, font=\scriptsize\bfseries, text=dawine, fill=white, fill opacity=0.85, text opacity=1, inner sep=1pt] at (D) {$\deg(D)=3$};

\node[align=center, font=\scriptsize, fill=white, fill opacity=0.95, text opacity=1, draw=danavy!30, rounded corners=3pt, inner sep=3.5pt] at (2.4, -0.95) {
\textbf{Handshaking Lemma:} $\text{Sum of degrees} = 2 \times E = 2 \times 6 = 12$ \quad$\vert$\quad \textbf{Key Rule:} Each loop adds $+2$ to vertex degree!
};
\end{tikzpicture}
\end{center}'''

    # 0.5. Pythagoras and Right-Angled Trigonometry
    elif any(k in combined for k in ["pythagoras", "pythagorean", "right-angled", "right angled", "soh cah toa", "trigonometric ratio"]):
        return r'''\begin{center}
\begin{tikzpicture}[scale=0.85]
\draw[line width=1.2pt, danavy] (0, 0) -- (4, 0) -- (4, 2.5) -- cycle;
\draw[thick, danavy] (3.6, 0) -- (3.6, 0.4) -- (4, 0.4);
\node[below, font=\footnotesize] at (2, 0) {Adjacent side $a$};
\node[right, font=\footnotesize] at (4, 1.25) {Opposite side $b$};
\node[above left, font=\footnotesize] at (2, 1.35) {Hypotenuse $c$};
\draw[dawine, thick] (0.8, 0) arc (0:32:0.8);
\node[dawine, font=\small\bfseries] at (1.1, 0.25) {$\theta$};
\node[align=center, font=\scriptsize, fill=white, fill opacity=0.95, text opacity=1, draw=danavy!30, rounded corners=3pt, inner sep=3pt] at (2.0, -0.9) {
\textbf{Pythagoras:} $c^2 = a^2 + b^2$ \quad$\vert$\quad
$\sin\theta = \frac{\text{Opp}}{\text{Hyp}}$, \quad
$\cos\theta = \frac{\text{Adj}}{\text{Hyp}}$, \quad
$\tan\theta = \frac{\text{Opp}}{\text{Adj}}$ (\textbf{SOH CAH TOA})
};
\end{tikzpicture}
\end{center}'''

    # 1. Financial Mathematics (NSW Stage 5 / Stage 6)
    elif any(k in c_lower for k in ["fractional", "compounding period", "compounding frequency", "fractional period", "quarterly", "monthly"]):
        return r'''\begin{center}
\begin{tikzpicture}[x=1.15cm, y=1cm]
% Main 1-year axis divided into 4 quarters
\draw[line width=1.4pt, danavy] (0, 0) -- (8.8, 0);
\foreach \x/\lbl/\sublbl in {0/{Start (Jan 1)}/{$t=0$}, 2.2/{End Q1 (Mar 31)}/{$n=1$}, 4.4/{End Q2 (Jun 30)}/{$n=2$}, 6.6/{End Q3 (Sep 30)}/{$n=3$}, 8.8/{End Q4 (Dec 31)}/{$n=4$}} {
    \draw[thick, danavy] (\x, 0.18) -- (\x, -0.18);
    \fill[danavy] (\x, 0) circle (2pt);
    \node[below=4pt, align=center, font=\scriptsize] at (\x, 0) {\textbf{\lbl}\\\sublbl};
}
% Interval brackets with interest added
\foreach \x in {1.1, 3.3, 5.5, 7.7} {
    \draw[->, thick, dagold!90!black] (\x-0.7, 0.45) to[bend left=25] (\x+0.7, 0.45);
    \node[above, font=\scriptsize\bfseries, text=dagold!90!black] at (\x, 0.72) {+Interest};
}
% Golden rule badge below
\node[align=center, font=\footnotesize\bfseries, fill=blue!5, draw=danavy!40, rounded corners=3pt, inner sep=4pt] at (4.4, -1.35) {
Compounding Quarterly ($4\times$ per year) $\implies$ 
Rate per period: $r = \frac{\text{Annual Rate}}{4}$ \quad$\vert$\quad Total periods: $n = \text{Years} \times 4$
};
\end{tikzpicture}
\end{center}'''

    elif any(k in c_lower for k in ["compound interest", "future value", "present value"]) or (re.search(r"\bcompound\b", c_lower) and "period" not in c_lower):
        return r'''\begin{center}
\begin{tikzpicture}[x=0.9cm, y=0.75cm]
\draw[->, thick] (-0.5, 0) -- (8.5, 0) node[right, font=\footnotesize] {Time $n$ (years)};
\draw[->, thick] (0, -0.5) -- (0, 5.5) node[above, font=\footnotesize] {Value (\$)};
\node[below left=2pt] at (0, 0) {$O$};
% Simple interest straight line
\draw[thick, gray!80!black, dashed] (0, 1.2) -- (7.5, 3.2);
\node[gray!80!black, right, font=\scriptsize] at (7.5, 3.2) {Simple: $I = Prt$};
% Compound interest exponential curve
\draw[line width=1.5pt, blue!85!black] plot[domain=0:7.2, samples=60] (\x, {1.2*exp(0.19*\x)});
\node[blue!85!black, above right, font=\footnotesize\bfseries] at (6.8, 4.8) {$A = P(1+r)^n$};
% Shading between compound and simple
\fill[green!50!black, opacity=0.12] plot[domain=0:7.2] (\x, {1.2*exp(0.19*\x)}) -- (7.2, {1.2 + (2.0/7.5)*7.2}) -- (0, 1.2) -- cycle;
% Principal P marker
\fill[red!80!black] (0, 1.2) circle (2.2pt) node[above left=3pt, font=\footnotesize\bfseries, text=red!80!black] {Principal $P$};
% Annotation callout
\node[align=center, font=\scriptsize\bfseries, text=green!50!black, fill=white, fill opacity=0.95, text opacity=1, draw=green!60!black, rounded corners=2pt, inner sep=2.5pt] at (3.5, 3.8) {Snowball Effect:\\Extra interest on interest!};
\end{tikzpicture}
\end{center}'''

    elif any(k in c_lower for k in ["depreciation", "declining-balance", "declining balance", "salvage", "asset value"]) or ("straight" in c_lower and "depreciation" in (c_lower + " " + str(topic).lower())):
        return r'''\begin{center}
\begin{tikzpicture}[x=0.95cm, y=0.75cm]
\draw[->, thick] (-0.5, 0) -- (8.2, 0) node[right, font=\footnotesize] {Time $n$ (years)};
\draw[->, thick] (0, -0.5) -- (0, 5.5) node[above, font=\footnotesize] {Book Value $S$ (\$)};
\node[below left=2pt] at (0, 0) {$O$};
% Initial purchase price V_0
\fill[red!80!black] (0, 4.8) circle (2.2pt) node[left=2pt, font=\footnotesize\bfseries, text=red!80!black] {Cost $V_0$};
% Straight-line depreciation (linear drop)
\draw[line width=1.3pt, blue!85!black] (0, 4.8) -- (7.2, 1.2) node[above right, font=\scriptsize\bfseries] {Straight-Line: $S = V_0 - Dn$};
% Declining-balance depreciation (exponential decay)
\draw[line width=1.3pt, purple!80!black] plot[domain=0:7.2, samples=60] (\x, {4.8*exp(-0.28*\x)});
\node[purple!80!black, below right, font=\scriptsize\bfseries] at (6.8, 0.9) {Declining-Balance: $S = V_0(1-r)^n$};
% Salvage value line
\draw[gray, dashed] (0, 1.2) -- (7.2, 1.2);
\node[gray!80!black, left, font=\scriptsize] at (0, 1.2) {Salvage};
% Badge comparing both
\node[align=left, font=\scriptsize, fill=white, fill opacity=0.92, text opacity=1, draw=danavy!30, rounded corners=2pt, inner sep=3pt] at (4.0, 3.8) {
\textbf{Straight-Line:} Constant \$ loss each year ($D = \frac{V_0 - S}{n}$)\\
\textbf{Declining-Balance:} Drops fastest initially, then slows
};
\end{tikzpicture}
\end{center}'''

    elif any(k in c_lower for k in ["credit card", "billing cycle", "payment window", "grace period", "interest-free", "personal loan"]):
        return r'''\begin{center}
\begin{tikzpicture}[x=0.22cm, y=1cm]
% Timeline axis: 0 to 58 days
\draw[line width=1.2pt, -{Latex[length=2.5mm]}] (0,0) -- (58,0) node[right, font=\footnotesize\bfseries] {Days};
\foreach \d in {1, 30, 55} {
    \draw[thick] (\d, 0.15) -- (\d, -0.15);
}
% Date markers below line
\node[below=3pt, font=\scriptsize\bfseries] at (1, 0) {Day 1};
\node[below=3pt, font=\scriptsize, align=center] at (30, 0) {\textbf{Day 30}\\\textbf{Statement Date}};
\node[below=3pt, font=\scriptsize, align=center, text=purple!80!black] at (55, 0) {\textbf{Day 55}\\\textbf{Due Date}};

% Purchase marker on Day 13 with pointer arrow
\fill[purple!80!black] (13, 0) circle (3pt);
\draw[<-, thick, purple!80!black] (13, 0.2) -- (13, 0.9);
\node[above, font=\scriptsize\bfseries, text=purple!80!black] at (13, 0.9) {Purchase Made (Day 13)};

% Tier 1: Billing Cycle (Days 1 to 30)
\draw[thick, blue!85!black] (1, 1.6) -- (30, 1.6);
\draw[thick, blue!85!black] (1, 1.4) -- (1, 1.8);
\draw[thick, blue!85!black] (30, 1.4) -- (30, 1.8);
\node[above, font=\footnotesize\bfseries, text=blue!85!black] at (15.5, 1.6) {Billing Cycle (30 Days)};

% Tier 1: Payment Window (Days 30 to 55)
\draw[thick, teal!80!black] (30, 1.6) -- (55, 1.6);
\draw[thick, teal!80!black] (55, 1.4) -- (55, 1.8);
\node[above, font=\footnotesize\bfseries, text=teal!80!black] at (42.5, 1.6) {Payment Window (25 Days)};

% Tier 2: Up to 55 Days Interest-Free
\draw[thick, gray!80!black] (1, 2.5) -- (55, 2.5);
\draw[thick, gray!80!black] (1, 2.3) -- (1, 2.7);
\draw[thick, gray!80!black] (55, 2.3) -- (55, 2.7);
\node[above, font=\footnotesize\bfseries, text=danavy] at (28, 2.5) {Up to 55 Days Interest-Free};

% Horizontal callout box positioned with plenty of breathing room at y = -2.0
\node[align=center, font=\scriptsize, fill=yellow!10, draw=orange!60!black, rounded corners=3pt, inner sep=3.5pt] at (28, -2.0) {
\textbf{Pay in full by Day 55:} \textbf{\$0 Interest!} \quad$\vert$\quad \textbf{Unpaid balance:} Interest charged from transaction date (Day 13) at daily rate $r = \frac{r_{\text{annual}}}{365}$
};
\end{tikzpicture}
\end{center}'''

    elif any(k in c_lower for k in ["superannuation", "super", "risk vs return", "risk and return", "investment option", "investment growth", "portfolio"]):
        return r'''\begin{center}
\begin{tikzpicture}[x=0.85cm, y=0.75cm]
\draw[->, thick] (-0.5, 0) -- (9.5, 0) node[right, font=\footnotesize] {Risk (Volatility)};
\draw[->, thick] (0, -0.5) -- (0, 5.5) node[above, font=\footnotesize] {Expected Return};
\node[below left=2pt] at (0, 0) {$O$};
% Risk-return upward trendline
\draw[line width=1.5pt, danavy, -{Latex[length=2.5mm]}] (0.8, 0.8) -- (8.5, 4.8);
% Asset categories along the line
\fill[blue!70!black] (1.2, 1.05) circle (2.5pt) node[above left=2pt, align=center, font=\scriptsize\bfseries] {Cash\\(Guaranteed)};
\fill[teal!80!black] (3.2, 2.1) circle (2.5pt) node[above left=2pt, align=center, font=\scriptsize\bfseries] {Conservative\\(Bonds/Fixed)};
\fill[orange!85!black] (5.5, 3.3) circle (2.5pt) node[above left=2pt, align=center, font=\scriptsize\bfseries] {Balanced\\(Growth + Defensive)};
\fill[red!80!black] (7.8, 4.45) circle (2.5pt) node[above left=2pt, align=center, font=\scriptsize\bfseries] {High Growth\\(Shares/Property)};
% Life stage advice box
\node[align=left, font=\scriptsize, fill=danavy!5, draw=danavy!40, rounded corners=3pt, inner sep=3.5pt] at (4.5, -1.2) {
\textbf{Life-Stage Strategy for Superannuation:}\\
$\bullet$ \textbf{Younger workers (20s--40s):} High Growth / Balanced (long investment horizon rides out dips)\\
$\bullet$ \textbf{Approaching retirement (55+):} Conservative / Cash (protect accumulated nest egg)
};
\end{tikzpicture}
\end{center}'''

    if any(k in c_lower for k in ["vertical line", "concept of a function", "function vs", "relations and functions"]):
        return r'''\begin{center}
\begin{tikzpicture}[x=0.75cm, y=0.75cm]
\draw[->, thick] (-4.2, 0) -- (4.2, 0) node[right] {$x$};
\draw[->, thick] (0, -2.8) -- (0, 3.2) node[above left] {$y$};
\node[below left=2pt] at (0, 0) {$O$};
\draw[thick, blue!85!black, domain=-2.3:2.3, samples=80] plot ({\x*\x - 3}, \x);
\node[blue!85!black, left] at (-3, 0.4) {$x = y^2 - 3$};
\draw[red!80!black, dashed, thick] (1, -2.6) -- (1, 2.8);
\fill[red!80!black] (1, 2) circle (2.2pt) node[above right, font=\footnotesize, fill=white, fill opacity=0.9, text opacity=1, inner sep=1pt] {$(1, 2)$};
\fill[red!80!black] (1, -2) circle (2.2pt) node[below right, font=\footnotesize, fill=white, fill opacity=0.9, text opacity=1, inner sep=1pt] {$(1, -2)$};
\node[align=center, font=\scriptsize\bfseries, text=red!80!black, fill=white, fill opacity=0.95, text opacity=1, inner sep=2pt] at (1, 3.2) {Vertical Line $x = 1$\\(Fails VLT $\implies$ Relation)};
\end{tikzpicture}
\end{center}'''

    elif any(k in c_lower for k in ["domain", "range", "notation"]):
        return r'''\begin{center}
\begin{tikzpicture}[x=0.75cm, y=0.75cm]
\draw[->, thick] (-3.5, 0) -- (4.5, 0) node[right] {$x$};
\draw[->, thick] (0, -1.2) -- (0, 3.8) node[above left] {$y$};
\node[below left=2pt] at (0, 0) {$O$};
\draw[thick, blue!85!black, domain=-2:4, samples=80] plot (\x, {sqrt(\x + 2) + 0.5});
\fill[blue!85!black] (-2, 0.5) circle (2.2pt) node[above left=1pt, font=\footnotesize, fill=white, inner sep=1pt] {$(-2, 0.5)$};
\node[blue!85!black, above right, font=\footnotesize] at (2, 2.5) {$y = \sqrt{x+2} + 0.5$};
\draw[line width=2.5pt, green!60!black, opacity=0.75] (-2, 0) -- (4.2, 0);
\node[above, font=\scriptsize\bfseries, text=green!60!black, fill=white, inner sep=1pt] at (1.2, 0.15) {$\text{Domain: } x \ge -2$};
\draw[line width=2.5pt, purple!70!black, opacity=0.75] (0, 0.5) -- (0, 3.4);
\node[right, font=\scriptsize\bfseries, text=purple!70!black, fill=white, inner sep=1pt] at (0.15, 2.0) {$\text{Range: } y \ge 0.5$};
\end{tikzpicture}
\end{center}'''

    elif any(k in c_lower for k in ["linear", "straight line", "gradient"]):
        return r'''\begin{center}
\begin{tikzpicture}[x=0.8cm, y=0.8cm]
\draw[->, thick] (-3.8, 0) -- (4.2, 0) node[right] {$x$};
\draw[->, thick] (0, -1.8) -- (0, 4.2) node[above] {$y$};
\node[below left=2pt] at (0, 0) {$O$};
% Line y = 0.8x + 1.6 from x = -3.5 to x = 3.0
\draw[thick, blue!85!black] (-3.5, -1.2) -- (3.0, 4.0) node[right, font=\footnotesize\bfseries] {$y = mx + c$};
% y-intercept at (0, 1.6)
\fill[red!80!black] (0, 1.6) circle (2.2pt) node[above left, font=\footnotesize\bfseries, text=red!80!black, fill=white, fill opacity=0.9, text opacity=1, inner sep=1pt] {$(0, c)$};
% x-intercept at (-2, 0)
\fill[red!80!black] (-2.0, 0) circle (2.2pt) node[below left=2pt, font=\footnotesize\bfseries, text=red!80!black, fill=white, fill opacity=0.9, text opacity=1, inner sep=1pt] {$\left(-\frac{c}{m}, 0\right)$};
% Angle of inclination theta at x-intercept (-2, 0): arctan(0.8) = 38.66 deg
\draw[thick, red!75!black] (-2.0, 0) ++(0:0.75cm) arc (0:38.66:0.75cm);
\node[red!75!black, font=\footnotesize\bfseries] at (-1.35, 0.22) {$\theta$};
% High-yield formula badge
\node[align=left, font=\scriptsize, fill=white, fill opacity=0.92, text opacity=1, draw=danavy!30, rounded corners=2pt, inner sep=2.5pt] at (2.2, 1.1) {$m = \tan\theta$\\[1.5pt]$\text{y-int}: (0, c)$\\[1.5pt]$\text{x-int}: \left(-\frac{c}{m}, 0\right)$};
\end{tikzpicture}
\end{center}'''

    elif any(k in c_lower for k in ["quadratic", "parabola"]):
        return r'''\begin{center}
\begin{tikzpicture}[x=0.75cm, y=0.55cm]
\draw[->, thick] (-3, 0) -- (5, 0) node[right] {$x$};
\draw[->, thick] (0, -5) -- (0, 4.2) node[above] {$y$};
\node[below left=2pt] at (0, 0) {$O$};
\draw[thick, blue!85!black, domain=-1.5:3.5, samples=80] plot (\x, {\x*\x - 2*\x - 3});
\draw[red!80!black, dashed, thick] (1, -4.8) -- (1, 3.5) node[above, font=\scriptsize\bfseries, fill=white, inner sep=1pt] {Axis of Sym: $x = 1$};
\fill[red!80!black] (1, -4) circle (2.2pt) node[below=2pt, font=\footnotesize, fill=white, inner sep=1pt] {Vertex $(1, -4)$};
\fill[blue!85!black] (-1, 0) circle (2pt) node[above left, font=\footnotesize, fill=white, inner sep=1pt] {$(-1, 0)$};
\fill[blue!85!black] (3, 0) circle (2pt) node[above right, font=\footnotesize, fill=white, inner sep=1pt] {$(3, 0)$};
\fill[blue!85!black] (0, -3) circle (2pt) node[left, font=\footnotesize, fill=white, inner sep=1pt] {$(0, -3)$};
\end{tikzpicture}
\end{center}'''

    elif any(k in c_lower for k in ["cubic", "polynomial"]):
        return r'''\begin{center}
\begin{tikzpicture}[x=0.8cm, y=0.8cm]
\draw[->, thick] (-3, 0) -- (3, 0) node[right] {$x$};
\draw[->, thick] (0, -3) -- (0, 3) node[above] {$y$};
\node[below left=2pt] at (0, 0) {$O$};
\draw[thick, blue!85!black, domain=-2.1:2.1, samples=80] plot (\x, {0.5*(\x*\x*\x - 3*\x)});
\fill[red!80!black] (-1, 1) circle (2pt) node[above left, font=\scriptsize, fill=white, inner sep=1pt] {Max $(-1, 1)$};
\fill[red!80!black] (1, -1) circle (2pt) node[below right, font=\scriptsize, fill=white, inner sep=1pt] {Min $(1, -1)$};
\fill[blue!85!black] (0, 0) circle (2pt) node[above right=2pt, font=\scriptsize, fill=white, inner sep=1pt] {Inflection $(0,0)$};
\node[blue!85!black, right, font=\footnotesize] at (1.6, 2.2) {$y = x^3 - 3x$};
\end{tikzpicture}
\end{center}'''

    elif any(k in c_lower for k in ["hyperbola", "rational", "asymptote"]):
        return r'''\begin{center}
\begin{tikzpicture}[x=0.75cm, y=0.75cm]
\draw[->, thick] (-3, 0) -- (5, 0) node[right] {$x$};
\draw[->, thick] (0, -3) -- (0, 5) node[above] {$y$};
\node[below left=2pt] at (0, 0) {$O$};
\draw[red!80!black, dashed, thick] (1, -2.8) -- (1, 4.5) node[above, font=\scriptsize\bfseries, fill=white, inner sep=1pt] {$x = 1$};
\draw[red!80!black, dashed, thick] (-2.8, 1) -- (4.8, 1) node[right, font=\scriptsize\bfseries, fill=white, inner sep=1pt] {$y = 1$};
\draw[thick, blue!85!black] plot[domain=1.25:4.5, samples=60] (\x, {1/(\x - 1) + 1});
\draw[thick, blue!85!black] plot[domain=-2.5:0.75, samples=60] (\x, {1/(\x - 1) + 1});
\fill[red!80!black] (1, 1) circle (2pt) node[above right=1pt, font=\scriptsize, fill=white, inner sep=1pt] {Center $(1, 1)$};
\node[blue!85!black, font=\footnotesize, fill=white, inner sep=1pt] at (3.5, 3.2) {$y = \frac{1}{x-1} + 1$};
\end{tikzpicture}
\end{center}'''

    elif any(k in c_lower for k in ["circle", "semicircle"]):
        return r'''\begin{center}
\begin{tikzpicture}[x=0.75cm, y=0.75cm]
\draw[->, thick] (-3.5, 0) -- (3.5, 0) node[right] {$x$};
\draw[->, thick] (0, -3.5) -- (0, 3.5) node[above] {$y$};
\node[below left=2pt] at (0, 0) {$O$};
\draw[thick, blue!85!black] (0, 0) circle (2.2cm);
\draw[->, thick, red!80!black] (0, 0) -- (1.555, 1.555) node[midway, above left, font=\footnotesize, fill=white, inner sep=1pt] {$r$};
\node[font=\footnotesize, fill=white, inner sep=1pt] at (0, -2.7) {$x^2 + y^2 = r^2$};
\end{tikzpicture}
\end{center}'''

    elif any(k in c_lower for k in ["exponential", "logarithm", "indices", "power"]):
        return r'''\begin{center}
\begin{tikzpicture}[x=0.8cm, y=0.8cm]
\draw[->, thick] (-3, 0) -- (3.5, 0) node[right] {$x$};
\draw[->, thick] (0, -1) -- (0, 4.5) node[above] {$y$};
\node[below left=2pt] at (0, 0) {$O$};
\draw[thick, blue!85!black, domain=-2.5:2, samples=60] plot (\x, {2^(\x)});
\draw[red!80!black, dashed, thick] (-2.8, 0) -- (3.2, 0);
\fill[red!80!black] (0, 1) circle (2pt) node[above left, font=\footnotesize, fill=white, inner sep=1pt] {$(0, 1)$};
\fill[blue!85!black] (1, 2) circle (2pt) node[right, font=\footnotesize, fill=white, inner sep=1pt] {$(1, 2)$};
\node[blue!85!black, right, font=\footnotesize] at (1.5, 3.8) {$y = 2^x$};
\node[below, font=\scriptsize\bfseries, text=red!80!black] at (-1.5, -0.1) {Asymptote $y = 0$};
\end{tikzpicture}
\end{center}'''

    elif any(k in c_lower for k in ["absolute value", "modulus"]):
        return r'''\begin{center}
\begin{tikzpicture}[x=0.8cm, y=0.8cm]
\draw[->, thick] (-1.5, 0) -- (5.0, 0) node[right] {$x$};
\draw[->, thick] (0, -1) -- (0, 4.5) node[above] {$y$};
\node[below left=2pt] at (0, 0) {$O$};
\draw[thick, blue!85!black] (-1, 4) -- (2, 1) -- (4.5, 3.5) node[right, font=\footnotesize] {$y = |x - 2| + 1$};
\fill[red!80!black] (2, 1) circle (2.2pt) node[below=2pt, font=\footnotesize, fill=white, inner sep=1pt] {Vertex $(2, 1)$};
\draw[red!80!black, dashed] (2, 0) -- (2, 1);
\draw[dashed, gray] (2, 1) -- (0, 1);
\end{tikzpicture}
\end{center}'''

    elif any(k in c_lower for k in ["trig", "sine", "cosine", "tangent"]):
        return r'''\begin{center}
\begin{tikzpicture}[x=0.75cm, y=0.8cm]
\draw[->, thick] (-0.5, 0) -- (7.0, 0) node[right] {$x$};
\draw[->, thick] (0, -2.5) -- (0, 2.5) node[above] {$y$};
\node[below left=2pt] at (0, 0) {$O$};
\draw[thick, blue!85!black, domain=0:6.28, samples=80] plot (\x, {1.8*sin(\x r)});
\draw[dashed, gray] (0, 1.8) -- (6.28, 1.8);
\draw[dashed, gray] (0, -1.8) -- (6.28, -1.8);
\node[left, font=\scriptsize] at (0, 1.8) {$A$};
\node[left, font=\scriptsize] at (0, -1.8) {$-A$};
\node[below, font=\scriptsize] at (3.14, 0) {$\pi$};
\node[below, font=\scriptsize] at (6.28, 0) {$2\pi$};
\node[blue!85!black, above, font=\footnotesize] at (4.5, 1.9) {$y = A\sin(x)$};
\end{tikzpicture}
\end{center}'''

    elif any(k in c_lower for k in ["vector"]):
        return r'''\begin{center}
\begin{tikzpicture}[x=0.8cm, y=0.8cm]
\draw[->, thick] (-1, 0) -- (4.5, 0) node[right] {$x$};
\draw[->, thick] (0, -1) -- (0, 3.5) node[above] {$y$};
\node[below left=2pt] at (0, 0) {$O$};
\draw[->, line width=1.5pt, blue!85!black] (0, 0) -- (3, 2) node[above right, font=\footnotesize] {$\mathbf{v} = 3\mathbf{i} + 2\mathbf{j}$};
\draw[->, thick, red!80!black] (0, 0) -- (3, 0) node[midway, below, font=\scriptsize] {$3\mathbf{i}$};
\draw[->, thick, green!60!black] (3, 0) -- (3, 2) node[midway, right, font=\scriptsize] {$2\mathbf{j}$};
\draw[dashed, gray] (0, 2) -- (3, 2);
\end{tikzpicture}
\end{center}'''

    # Financial Mathematics Fallbacks
    elif any(k in combined for k in ["earning", "income", "wage", "salary", "overtime", "commission", "piecework"]):
        return r'''\begin{center}
\begin{tikzpicture}[x=1cm, y=0.7cm]
\draw[draw=danavy, fill=danavy!10, rounded corners=3pt, thick] (0, 0) rectangle (3.8, 1.2);
\node[font=\footnotesize\bfseries\color{danavy}] at (1.9, 0.6) {Normal Hours ($1.0\times$)};
\draw[draw=dablue, fill=dablue!20, rounded corners=3pt, thick] (4.1, 0) rectangle (7.5, 1.2);
\node[font=\footnotesize\bfseries\color{dablue}] at (5.8, 0.6) {Overtime ($1.5\times / 2.0\times$)};
\draw[draw=dagreen!80!black, fill=dagreen!15, rounded corners=3pt, thick] (7.8, 0) rectangle (10.2, 1.2);
\node[font=\footnotesize\bfseries\color{dagreen!80!black}] at (9.0, 0.6) {Bonuses};
\draw[->, thick, danavy] (5.1, -0.2) -- (5.1, -0.7);
\node[draw=danavy, fill=white, rounded corners=4pt, line width=1.1pt, font=\small\bfseries\color{danavy}, inner sep=4pt] at (5.1, -1.2) {Total Gross Pay = Base Pay + Overtime + Allowances};
\end{tikzpicture}
\end{center}'''

    elif any(k in combined for k in ["tax", "deduction", "taxable income", "medicare", "payg"]):
        return r'''\begin{center}
\begin{tikzpicture}[x=0.95cm, y=0.65cm]
\node[draw=danavy, fill=danavy!10, rounded corners=3pt, font=\footnotesize\bfseries] (G) at (0, 1) {Gross Income};
\node[draw=dawine, fill=dawine!10, rounded corners=3pt, font=\footnotesize\bfseries] (D) at (3.5, 1) {Deductions};
\node[draw=dablue, fill=dablue!15, rounded corners=3pt, font=\footnotesize\bfseries] (T) at (7.2, 1) {Taxable Income};
\draw[->, thick] (G) -- node[above, font=\tiny] {minus} (D);
\draw[->, thick] (D) -- node[above, font=\tiny] {equals} (T);
\draw[->, thick] (T) |- (4, -0.4);
\node[draw=dagreen!80!black, fill=dagreen!10, rounded corners=4pt, font=\footnotesize\bfseries, align=center] at (4, -1.1) {Apply ATO Tax Brackets + 2\% Medicare Levy $\implies$ Net Tax Payable};
\end{tikzpicture}
\end{center}'''

    elif any(k in combined for k in ["compound", "simple interest", "principal", "interest rate", "balance"]):
        return r'''\begin{center}
\begin{tikzpicture}[x=1.2cm, y=0.75cm]
\draw[->, thick] (0, 0) -- (5.2, 0) node[right, font=\tiny] {Time ($t$)};
\draw[->, thick] (0, 0) -- (0, 3.2) node[above, font=\tiny] {Balance (\$)};
\node[left, font=\tiny] at (0, 0.6) {$P$};
\draw[thick, blue!85!black] (0, 0.6) -- (4.5, 1.9) node[right, font=\tiny] {Simple: $A = P + Prt$};
\draw[line width=1.2pt, red!80!black] (0, 0.6) to[out=10, in=235] (4.5, 3.0) node[right, font=\tiny] {Compound: $A = P(1+r)^t$};
\node[font=\tiny\itshape\color{gray!70!black}, fill=white, inner sep=1pt] at (2.2, 0.9) {Linear growth};
\node[font=\tiny\itshape\color{red!70!black}, fill=white, inner sep=1pt] at (2.2, 2.2) {Snowball growth};
\end{tikzpicture}
\end{center}'''

    elif any(k in combined for k in ["depreciation", "salvage", "declining"]):
        return r'''\begin{center}
\begin{tikzpicture}[x=1.2cm, y=0.75cm]
\draw[->, thick] (0, 0) -- (5.0, 0) node[right, font=\tiny] {Years ($n$)};
\draw[->, thick] (0, 0) -- (0, 3.2) node[above, font=\tiny] {Value (\$)};
\node[left, font=\tiny] at (0, 2.8) {$V_0$ (Cost)};
\draw[thick, red!80!black] (0, 2.8) to[out=-60, in=170] (4.5, 0.4) node[right, font=\tiny] {$S = V_0(1-r)^n$};
\node[font=\tiny\itshape\color{red!80!black}, fill=white, inner sep=1pt] at (2.2, 1.4) {Declining balance (never reaches \$0)};
\end{tikzpicture}
\end{center}'''

    elif any(k in combined for k in ["financial", "consumer arithmetic"]):
        return r'''\begin{center}
\begin{tikzpicture}[x=1.2cm, y=0.7cm]
\node[draw=danavy, fill=danavy!10, rounded corners=3pt, font=\footnotesize\bfseries] at (1, 1) {Earning \& Tax};
\node[draw=dablue, fill=dablue!10, rounded corners=3pt, font=\footnotesize\bfseries] at (4, 1) {Interest \& Growth};
\node[draw=dagreen!80!black, fill=dagreen!10, rounded corners=3pt, font=\footnotesize\bfseries] at (7, 1) {Loans \& Salvage};
\draw[->, thick, danavy] (1, 0.4) -- (1, -0.2);
\draw[->, thick, dablue] (4, 0.4) -- (4, -0.2);
\draw[->, thick, dagreen!80!black] (7, 0.4) -- (7, -0.2);
\node[draw=danavy!80!black, fill=slatebg, rounded corners=4pt, font=\scriptsize\bfseries, align=center] at (4, -0.8) {Golden Rule: Match Rate and Compounding Period ($r_{\text{period}} = \frac{r}{k},\; n_{\text{periods}} = \text{years} \times k$)};
\end{tikzpicture}
\end{center}'''

    return ""


def format_theory_formula(kf: str) -> str:
    """Ensures a theory formula item is properly formatted with prose labels in text mode and math formulas in math mode."""
    kf = str(kf).strip()
    if not kf:
        return ""
    kf = clean_set_notation(kf)
    if "&" in kf and not any(env in kf for env in ["matrix", "cases", "aligned", "array"]):
        kf = re.sub(r"(?<!\\)&", r"\\&", kf)

    if ":" in kf:
        label, _, formula = kf.partition(":")
        label = label.strip()
        formula = formula.strip()
        if "$" in formula or r"\[" in formula or r"\begin{" in formula:
            return f"\\textbf{{{sanitize_for_latex(label)}:}} {sanitize_for_latex(formula)}"
        words = [w for w in re.findall(r"[a-zA-Z]{2,}", formula) if w.lower() not in ["sin", "cos", "tan", "sec", "csc", "cot", "log", "ln", "exp", "lim", "max", "min"]]
        if len(words) >= 3:
            return f"\\textbf{{{sanitize_for_latex(label)}:}} {sanitize_for_latex(formula)}"
        return f"\\textbf{{{sanitize_for_latex(label)}:}} ${formula}$"

    if "$" in kf or r"\[" in kf or r"\begin{" in kf:
        return sanitize_for_latex(kf)
    words = [w for w in re.findall(r"[a-zA-Z]{2,}", kf) if w.lower() not in ["sin", "cos", "tan", "sec", "csc", "cot", "log", "ln", "exp", "lim", "max", "min"]]
    if len(words) >= 3:
        return sanitize_for_latex(kf)
    return sanitize_for_latex(f"${kf}$")

def group_questions_by_subtopic(questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Groups questions into Sets (Set A, Set B, Set C, ...) based on subtopic.
    Returns a list of dicts:
    [
        {
            "set_letter": "A",
            "set_label": "Set A",
            "subtopic": "Vector Definitions, Magnitude and Direction",
            "set_title": "Set A — Vector Definitions, Magnitude and Direction",
            "questions": [...]
        },
        ...
    ]
    """
    groups = []
    subtopic_to_group = {}
    
    for idx, q in enumerate(questions, start=1):
        raw_sub = (q.get('subtopic') or '').strip() or 'Core Exercises'
        sub = clean_subtopic_title(raw_sub)
        if sub not in subtopic_to_group:
            group_idx = len(groups)
            letter = chr(ord('A') + group_idx) if group_idx < 26 else f"{group_idx + 1}"
            group_obj = {
                "set_letter": letter,
                "set_label": f"Set {letter}",
                "subtopic": sub,
                "set_title": f"Set {letter} — {sub}",
                "questions": []
            }
            groups.append(group_obj)
            subtopic_to_group[sub] = group_obj
        
        subtopic_to_group[sub]["questions"].append(q)
        
    return groups

DIFF_TIER_CONFIG = [
    ("Easy", "Commit to Memory"),
    ("Medium", "Further Practice"),
    ("Hard", "Application"),
    ("Extremely Hard", "Thinking Creatively"),
    ("Past Exam", "Exam Questions")
]

def clean_worksheet_topic_title(topic: str) -> str:
    """
    Cleans a syllabus topic title by:
    1. Removing leading year level prefixes (e.g. 'Year 12 (Advanced) Mathematics - ').
    2. Removing leading chapter/unit numbers (e.g. '1. ', '14. ', '6: ', '10A. ', 'Chapter 1 - ') without stripping '2D' or '3D'.
    3. Removing trailing labels like 'Theory Booklet', 'Worksheet', 'Homework', etc.
    4. Normalizing ' and ' or isolated 'and' to ' & '.
    5. Replacing underscores with clean spaces and normalizing whitespace.
    Runs iteratively until all prefixes and trailing tags are eliminated.
    """
    cleaned = str(topic or "").strip()
    changed = True
    while changed:
        prev = cleaned
        # Strip Year prefixes: e.g. 'Year 12 (Advanced) Mathematics - ', 'Year 11 Maths: '
        cleaned = re.sub(r'^Year\s+\d+\s*(?:\([^\)]+\))?\s*(?:Mathematics|Maths)?\s*[\-\–\—\:\.]\s*', '', cleaned, flags=re.IGNORECASE).strip()
        # Strip Chapter/Unit/Topic/Part/Number prefixes: e.g. '1. ', '14. ', '6: ', '10A. ', '8A ', 'Chapter 1 - ', 'Unit 2: '
        if not re.match(r'^[23]D\b', cleaned, flags=re.IGNORECASE):
            cleaned = re.sub(r'^(?:(?:Chapter|Unit|Topic|Part)\s*)?(?:\d+[\.\:\-]\s*|\d+[A-Za-z][\.\:\-\–\—\s]\s*|\d+\s+)', '', cleaned, flags=re.IGNORECASE).strip()
        # Strip trailing labels: e.g. ' - Homework', ' - Theory Booklet', ' — Worksheet'
        cleaned = re.sub(r'\s*[\-\–\—\:]?\s*(Theory & Practice Booklet|Theory & Notes|Theory Booklet|Practice Booklet|Booklet|Worksheet|Homework|Revision & Exam Review|Review Booklet|Review)\s*$', '', cleaned, flags=re.IGNORECASE).strip()
        # Strip leading & trailing punctuation
        cleaned = re.sub(r'^[\-\–\—\:\.\,\s]+', '', cleaned).strip()
        cleaned = re.sub(r'[\-\–\—\:\,\s]+$', '', cleaned).strip()
        changed = (cleaned != prev)

    # Normalize ' and ' to ' & '
    cleaned = re.sub(r'\band\b', '&', cleaned)
    cleaned = cleaned.replace("_", " ")
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned or "Mathematics"

def get_tiered_sections_for_questions(questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Groups questions for a subtopic into dynamically numbered sections based on difficulty:
    - Easy -> Commit to Memory
    - Medium -> Further Practice
    - Hard -> Application
    - Extremely Hard -> Thinking Creatively
    - Past Exam -> Exam Questions
    Only active tiers are included, numbered sequentially: Section 1, Section 2, ...
    If a tier is skipped (e.g. Thinking Creatively is not selected), following tiers are consecutively renumbered.
    """
    def norm_diff(d: str) -> str:
        s = str(d or "").strip().lower()
        if any(k in s for k in ["exam questions", "exam style", "past exam", "past", "exam", "trial", "thsc", "level 5", "section 5", "part 5"]):
            return "Past Exam"
        if any(k in s for k in ["thinking creatively", "creativ", "thinking", "extreme", "eh", "challenge", "challenging", "distinction", "level 4", "section 4", "part 4"]):
            return "Extremely Hard"
        if any(k in s for k in ["application", "hard", "applied", "level 3", "section 3", "part 3"]):
            return "Hard"
        if any(k in s for k in ["further practice", "further", "deeper understanding", "deeper", "medium", "level 2", "section 2", "part 2"]):
            return "Medium"
        if any(k in s for k in ["commit to memory", "commit", "memory", "easy", "applying", "apply", "drilling", "drill", "refresher", "level 1", "section 1", "part 1"]):
            return "Easy"
        if s == "m" or "med" in s:
            return "Medium"
        if s == "h":
            return "Hard"
        if s == "e":
            return "Easy"
        return "Medium"

    tier_buckets = {tier_key: [] for tier_key, _ in DIFF_TIER_CONFIG}
    for q in questions:
        key = norm_diff(q.get("difficulty", "Medium"))
        tier_buckets[key].append(q)

    sections = []
    sec_num = 1
    for tier_key, tier_name in DIFF_TIER_CONFIG:
        q_list = tier_buckets[tier_key]
        if q_list:
            sections.append({
                "section_num": sec_num,
                "section_name": tier_name,
                "section_title": f"Section {sec_num}: {tier_name}",
                "difficulty": tier_key,
                "questions": q_list
            })
            sec_num += 1

    if not sections and questions:
        sections.append({
            "section_num": 1,
            "section_name": "Questions",
            "section_title": "Section 1: Questions",
            "difficulty": "Medium",
            "questions": questions
        })

    return sections

def order_and_renumber_worksheet_questions(questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Orders questions strictly by their subtopic Sets (Set A, Set B, ...) 
    and difficulty Sections (Section 1: Easy, Section 2: Medium, ...)
    and assigns clean consecutive item_labels: 1, 2, 3, 4, 5...
    This ensures the physical worksheet, the answers section, the worked solutions,
    and the student answer sheets are 100% synchronized and numbered in reading order.
    """
    if not questions:
        return []
    
    groups = group_questions_by_subtopic(questions)
    ordered = []
    q_counter = 1
    for grp in groups:
        sections = get_tiered_sections_for_questions(grp["questions"])
        for sec in sections:
            for q in sec["questions"]:
                q_copy = dict(q)
                q_copy["item_label"] = str(q_counter)
                q_copy["num"] = q_counter
                ordered.append(q_copy)
                q_counter += 1
    return ordered

def format_latex_theory_notes(content: str) -> str:
    """Formats theory notes into spaced paragraphs, headings, and bullet lists with LaTeX math intact."""
    if not content:
        return ""
    content_str = str(content)
    content_str = clean_set_notation(content_str)
    if "\n" not in content_str and "\\n" in content_str:
        content_str = re.sub(r'\\n(?!(?:e|eq|otin|abla|u|eg|ot|atural|i|ode|oindent|ew[a-zA-Z]*|ormalsize|opagebreak|eedspace|warrow|earrow|subseteq|supseteq|parallel|mid|exists|ull)\b)', '\n', content_str)
    lines = content_str.split("\n")
    out = []
    in_list = None  # 'itemize' or 'enumerate'

    def close_list():
        nonlocal in_list
        if in_list:
            out.append(f"\\end{{{in_list}}}")
            in_list = None

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            # Peek ahead across blank lines to preserve active list continuity
            next_continues = False
            if in_list:
                for j in range(i + 1, len(lines)):
                    next_line = lines[j].strip()
                    if not next_line:
                        continue
                    if in_list == "itemize" and re.match(r"^[\-\*\•]\s+(.*)$", next_line):
                        next_continues = True
                    elif in_list == "enumerate" and re.match(r"^\d+[\.\)]\s+(.*)$", next_line):
                        next_continues = True
                    break
            if not next_continues:
                close_list()
            i += 1
            continue

        # Markdown headings: ### 1. Heading or ## Heading
        m_head = re.match(r"^#{1,4}\s+(.*)$", line)
        if m_head:
            close_list()
            h_text = m_head.group(1).strip()
            out.append(f"\\noindent\\textbf{{{sanitize_for_latex(h_text)}}}\\\\[0.08cm]")
            i += 1
            continue

        # Bullet list item: - item or * item
        m_bullet = re.match(r"^[\-\*\•]\s+(.*)$", line)
        if m_bullet:
            if in_list == "enumerate":
                close_list()
            item_text = m_bullet.group(1).strip()
            # Handle inline numbered steps inside bullet item (e.g. - **DA Quick-Method:** 1. ... 2. ...)
            m_inline_bullet_steps = re.match(
                r'^(\*\*[^*]+:\*\*|__[^_]+:__)\s+(1[\.\)]\s+.+)$',
                item_text
            )
            if m_inline_bullet_steps:
                close_list()
                label_md = m_inline_bullet_steps.group(1)
                steps_raw = m_inline_bullet_steps.group(2)
                label_tex = sanitize_for_latex(re.sub(r'^\*\*(.+)\*\*$', r'\1', label_md).strip())
                out.append(f"\\noindent\\textbf{{{label_tex}}}\\par\\vspace{{0.04cm}}")
                step_parts = re.split(r'\s+(?=\d+[\.\)]\s)', steps_raw)
                out.append(r"\begin{enumerate}[leftmargin=1.5em, itemsep=0.15em, topsep=0.06em]")
                for sp in step_parts:
                    sp = sp.strip()
                    m_sp = re.match(r'^\d+[\.\)]\s+(.+)$', sp)
                    if m_sp:
                        out.append(f"\\item {sanitize_for_latex(m_sp.group(1).strip())}")
                out.append(r"\end{enumerate}")
                i += 1
                continue

            if not in_list:
                out.append(r"\begin{itemize}[leftmargin=1.5em, itemsep=0.25em, topsep=0.12em, label={\color{dagold}$\blacktriangleright$}]")
                in_list = "itemize"
            out.append(f"\\item {sanitize_for_latex(item_text)}")
            i += 1
            continue

        # Numbered list item: 1. item
        m_num = re.match(r"^\d+[\.\)]\s+(.*)$", line)
        if m_num:
            if in_list == "itemize":
                close_list()
            if not in_list:
                out.append(r"\begin{enumerate}[leftmargin=1.5em, itemsep=0.2em, topsep=0.1em]")
                in_list = "enumerate"
            item_text = m_num.group(1).strip()
            out.append(f"\\item {sanitize_for_latex(item_text)}")
            i += 1
            continue

        # Normal text line / paragraph
        close_list()
        s_line = line.strip()
        if s_line.startswith(r"\[") or s_line.endswith(r"\]") or s_line.startswith("$$") or s_line.endswith("$$"):
            out.append(f"{sanitize_for_latex(line)}\\par")
        else:
            # Detect bold-label with inline numbered steps: **DA Quick-Method:** 1. ... 2. ...
            m_inline_steps = re.match(
                r'^(\*\*[^*]+:\*\*|__[^_]+:__)\s+(1[\.\)]\s+.+)$',
                s_line
            )
            if m_inline_steps:
                label_md = m_inline_steps.group(1)
                steps_raw = m_inline_steps.group(2)
                label_tex = sanitize_for_latex(re.sub(r'^\*\*(.+)\*\*$', r'\1', label_md).strip())
                out.append(f"\\noindent\\textbf{{{label_tex}}}\\par\\vspace{{0.04cm}}")
                # Split inline numbered steps: "1. A 2. B 3. C"
                step_parts = re.split(r'\s+(?=\d+[\.\)]\s)', steps_raw)
                out.append(r"\begin{enumerate}[leftmargin=1.5em, itemsep=0.15em, topsep=0.06em]")
                for sp in step_parts:
                    sp = sp.strip()
                    m_sp = re.match(r'^\d+[\.\)]\s+(.+)$', sp)
                    if m_sp:
                        out.append(f"\\item {sanitize_for_latex(m_sp.group(1).strip())}")
                out.append(r"\end{enumerate}")
            else:
                out.append(f"{sanitize_for_latex(line)}\\par\\vspace{{0.12cm}}")
        i += 1

    close_list()
    return "\n".join(out)


def get_angle_rule_mini_tikz(formula_text: str) -> Optional[str]:
    """
    Returns a compact compilable mini TikZ diagram for geometry angle relationships
    (alternate, corresponding, co-interior, vertically opposite, angle sum of triangle,
    exterior angle, straight line, revolution, complementary).
    Returns None if the formula is not an angle relationship rule.
    """
    txt = formula_text.lower()

    # 1. Alternate angles (Z-shape)
    if ("alternate" in txt and "angle" in txt) or ("'z' shape" in txt) or ("z-shape" in txt) or ("alternate angles" in txt):
        return (
            r"\begin{tikzpicture}[scale=0.52, line width=0.7pt, >=Stealth, baseline=-0.3ex]"
            r"\draw[danavy] (-1.1, 0.45) -- (1.1, 0.45);"
            r"\draw[danavy] (-1.1, -0.45) -- (1.1, -0.45);"
            r"\draw[->, danavy] (-0.3, 0.45) -- (0.0, 0.45);"
            r"\draw[->, danavy] (-0.3, -0.45) -- (0.0, -0.45);"
            r"\draw[dablue, line width=0.85pt] (0.45, 0.75) -- (-0.45, -0.75);"
            r"\draw[dawine, line width=0.9pt] (0.05, 0.45) arc (180:239:0.35);"
            r"\draw[dawine, line width=0.9pt] (-0.05, -0.45) arc (0:59:0.35);"
            r"\node[scale=0.6, dawine] at (-0.08, 0.28) {$\alpha$};"
            r"\node[scale=0.6, dawine] at (0.08, -0.28) {$\alpha$};"
            r"\end{tikzpicture}"
        )

    # 2. Corresponding angles (F-shape)
    if ("corresponding" in txt and "angle" in txt) or ("'f' shape" in txt) or ("f-shape" in txt) or ("corresponding angles" in txt):
        return (
            r"\begin{tikzpicture}[scale=0.52, line width=0.7pt, >=Stealth, baseline=-0.3ex]"
            r"\draw[danavy] (-1.1, 0.45) -- (1.1, 0.45);"
            r"\draw[danavy] (-1.1, -0.45) -- (1.1, -0.45);"
            r"\draw[->, danavy] (-0.3, 0.45) -- (0.0, 0.45);"
            r"\draw[->, danavy] (-0.3, -0.45) -- (0.0, -0.45);"
            r"\draw[dablue, line width=0.85pt] (-0.45, -0.75) -- (0.45, 0.75);"
            r"\draw[dawine, line width=0.9pt] (0.55, 0.45) arc (0:59:0.35);"
            r"\draw[dawine, line width=0.9pt] (0.05, -0.45) arc (0:59:0.35);"
            r"\node[scale=0.6, dawine] at (0.45, 0.7) {$\alpha$};"
            r"\node[scale=0.6, dawine] at (-0.05, -0.2) {$\alpha$};"
            r"\end{tikzpicture}"
        )

    # 3. Co-interior / allied angles (C-shape)
    if ("co-interior" in txt or "cointerior" in txt or "allied" in txt) and ("angle" in txt or "180" in txt or "c' shape" in txt or "c-shape" in txt):
        return (
            r"\begin{tikzpicture}[scale=0.52, line width=0.7pt, >=Stealth, baseline=-0.3ex]"
            r"\draw[danavy] (-1.1, 0.45) -- (1.1, 0.45);"
            r"\draw[danavy] (-1.1, -0.45) -- (1.1, -0.45);"
            r"\draw[->, danavy] (-0.3, 0.45) -- (0.0, 0.45);"
            r"\draw[->, danavy] (-0.3, -0.45) -- (0.0, -0.45);"
            r"\draw[dablue, line width=0.85pt] (0.45, 0.75) -- (-0.45, -0.75);"
            r"\draw[dawine, line width=0.9pt] (0.45, 0.45) arc (0:-121:0.35);"
            r"\draw[dagold!90!black, line width=0.9pt] (-0.05, -0.45) arc (0:59:0.35);"
            r"\node[scale=0.6, dawine] at (0.35, 0.22) {$\alpha$};"
            r"\node[scale=0.6, dagold!90!black] at (0.08, -0.25) {$\beta$};"
            r"\end{tikzpicture}"
        )

    # 4. Exterior angle of a triangle (check before opposite angles to avoid matching 'interior opposite')
    if ("exterior angle" in txt and "triangle" in txt) or ("exterior angle of \\triangle" in txt) or ("exterior angle" in txt):
        return (
            r"\begin{tikzpicture}[scale=0.52, line width=0.7pt, baseline=-0.3ex]"
            r"\coordinate (A) at (-1.0, -0.45);"
            r"\coordinate (B) at (0.35, -0.45);"
            r"\coordinate (C) at (-0.2, 0.6);"
            r"\coordinate (D) at (1.1, -0.45);"
            r"\draw[danavy] (A) -- (B) -- (C) -- cycle;"
            r"\draw[danavy, dashed] (B) -- (D);"
            r"\draw[dawine, line width=0.8pt] (-0.72, -0.45) arc (0:52:0.28);"
            r"\draw[dablue, line width=0.8pt] (-0.34, 0.40) arc (-125:-62:0.25);"
            r"\draw[dagold!90!black, line width=0.9pt] (0.63, -0.45) arc (0:118:0.28);"
            r"\node[scale=0.55, dawine] at (-0.6, -0.32) {$A$};"
            r"\node[scale=0.55, dablue] at (-0.2, 0.22) {$B$};"
            r"\node[scale=0.55, dagold!90!black] at (0.75, -0.22) {$d$};"
            r"\end{tikzpicture}"
        )

    # 5. Vertically opposite angles (X-shape)
    if ("vertically opposite" in txt) or ("vert. opp" in txt) or ("'x' shape" in txt) or ("x-shape" in txt) or ("vertically" in txt and "opposite" in txt):
        return (
            r"\begin{tikzpicture}[scale=0.52, line width=0.7pt, baseline=-0.3ex]"
            r"\draw[danavy] (-1.0, -0.45) -- (1.0, 0.45);"
            r"\draw[dablue] (-1.0, 0.45) -- (1.0, -0.45);"
            r"\draw[dawine, line width=0.9pt] (-0.32, 0.14) arc (156:204:0.35);"
            r"\draw[dawine, line width=0.9pt] (0.32, -0.14) arc (-24:24:0.35);"
            r"\node[scale=0.6, dawine] at (-0.52, 0) {$\alpha$};"
            r"\node[scale=0.6, dawine] at (0.52, 0) {$\alpha$};"
            r"\end{tikzpicture}"
        )

    # 6. Angle sum of a triangle
    if ("angle sum" in txt and "triangle" in txt) or ("angles of a triangle" in txt) or ("interior angles of a triangle" in txt) or ("triangle" in txt and "180" in txt) or ("\\triangle" in txt and "180" in txt):
        return (
            r"\begin{tikzpicture}[scale=0.52, line width=0.7pt, baseline=-0.3ex]"
            r"\coordinate (A) at (-0.9, -0.5);"
            r"\coordinate (B) at (0.9, -0.5);"
            r"\coordinate (C) at (0.0, 0.65);"
            r"\draw[danavy] (A) -- (B) -- (C) -- cycle;"
            r"\draw[dawine, line width=0.8pt] (-0.62, -0.5) arc (0:52:0.28);"
            r"\draw[dablue, line width=0.8pt] (0.62, -0.5) arc (180:128:0.28);"
            r"\draw[dagold!90!black, line width=0.8pt] (-0.17, 0.43) arc (-128:-52:0.28);"
            r"\node[scale=0.55, dawine] at (-0.52, -0.36) {$A$};"
            r"\node[scale=0.55, dablue] at (0.52, -0.36) {$B$};"
            r"\node[scale=0.55, dagold!90!black] at (0.0, 0.3) {$C$};"
            r"\end{tikzpicture}"
        )

    # 7. Angles on a straight line / supplementary
    if ("straight line" in txt and "angle" in txt) or ("angles on a line" in txt) or ("supplementary" in txt and "180" in txt):
        return (
            r"\begin{tikzpicture}[scale=0.52, line width=0.7pt, baseline=-0.3ex]"
            r"\draw[danavy] (-1.1, -0.25) -- (1.1, -0.25);"
            r"\draw[dablue, line width=0.85pt] (0, -0.25) -- (0.35, 0.55);"
            r"\draw[dawine, line width=0.8pt] (0.28, -0.25) arc (0:66:0.28);"
            r"\draw[dagold!90!black, line width=0.8pt] (-0.28, -0.25) arc (180:66:0.28);"
            r"\node[scale=0.6, dawine] at (0.28, 0.05) {$\alpha$};"
            r"\node[scale=0.6, dagold!90!black] at (-0.22, 0.08) {$\beta$};"
            r"\end{tikzpicture}"
        )

    # 8. Angles at a point / revolution
    if ("revolution" in txt) or ("at a point" in txt and "angle" in txt) or ("around a point" in txt):
        return (
            r"\begin{tikzpicture}[scale=0.52, line width=0.7pt, >=Stealth, baseline=-0.3ex]"
            r"\coordinate (O) at (0, 0);"
            r"\draw[danavy] (O) -- (0.9, 0);"
            r"\draw[dablue] (O) -- (-0.4, 0.8);"
            r"\draw[dagold!90!black] (O) -- (-0.5, -0.7);"
            r"\draw[dawine, line width=0.8pt] (0.3, 0) arc (0:116:0.3);"
            r"\draw[dablue, line width=0.8pt] (-0.13, 0.27) arc (116:234:0.3);"
            r"\draw[dagold!90!black, line width=0.8pt] (-0.18, -0.24) arc (234:360:0.3);"
            r"\node[scale=0.5, dawine] at (0.22, 0.22) {$\alpha$};"
            r"\node[scale=0.5, dablue] at (-0.28, 0.05) {$\beta$};"
            r"\node[scale=0.5, dagold!90!black] at (0.05, -0.25) {$\gamma$};"
            r"\end{tikzpicture}"
        )

    # 9. Complementary angles
    if ("complementary" in txt and "angle" in txt) or ("right angle" in txt and "90" in txt):
        return (
            r"\begin{tikzpicture}[scale=0.52, line width=0.7pt, baseline=-0.3ex]"
            r"\coordinate (O) at (-0.6, -0.5);"
            r"\draw[danavy] (O) -- (0.8, -0.5);"
            r"\draw[danavy] (O) -- (-0.6, 0.8);"
            r"\draw[dablue, line width=0.85pt] (O) -- (0.4, 0.5);"
            r"\draw[danavy] (-0.6, -0.3) -- (-0.4, -0.3) -- (-0.4, -0.5);"
            r"\draw[dawine, line width=0.8pt] (-0.25, -0.5) arc (0:40:0.35);"
            r"\draw[dagold!90!black, line width=0.8pt] (-0.33, -0.18) arc (40:90:0.35);"
            r"\node[scale=0.55, dawine] at (-0.15, -0.38) {$\alpha$};"
            r"\node[scale=0.55, dagold!90!black] at (-0.4, 0.02) {$\beta$};"
            r"\end{tikzpicture}"
        )

    return None


def split_method_steps(text: str) -> List[str]:
    """
    Splits method text into individual step strings.
    Handles multi-line input, bracketed step tags ([Step 1...]), unbracketed Step X,
    or numbered lists (1. ... 2. ...).
    """
    text = text.strip()
    if not text:
        return []

    # Check if text already has multiple distinct lines
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if len(lines) >= 2:
        return lines[:4]

    # If single line, try splitting by bracketed step tokens: [Step 1...] [Step 2...]
    bracket_pattern = r'(?=\[\s*Step\s*\d+[^\]]*\])'
    parts = [p.strip() for p in re.split(bracket_pattern, text, flags=re.IGNORECASE) if p.strip()]
    if len(parts) >= 2:
        return parts[:4]

    # Try splitting by unbracketed Step X: or Step X -
    step_word_pattern = r'(?=(?:^|\s+)Step\s*\d+\s*[:\-–—])'
    parts = [p.strip() for p in re.split(step_word_pattern, text, flags=re.IGNORECASE) if p.strip()]
    if len(parts) >= 2:
        return parts[:4]

    # Try splitting by numbered items 1. or 1)
    num_pattern = r'(?=(?:^|\s+)\d+[\.\)]\s+)'
    parts = [p.strip() for p in re.split(num_pattern, text) if p.strip()]
    if len(parts) >= 2:
        return parts[:4]

    return [text]


def get_concept_self_check(
    concept_name: str = "",
    topic: str = "",
    tutor_tips: str = "",
    trap_text: str = ""
) -> str:
    """
    Returns an actionable, topic-specific DA Self-Check rule for any mathematics concept.
    Guarantees every theory booklet unconditionally includes the '✓ DA Self-Check:' section.
    """
    c_lower = str(concept_name).lower()
    t_lower = str(topic).lower()

    # 1. Financial Mathematics checks
    if any(k in c_lower or k in t_lower for k in ["compound", "future value", "present value"]):
        return r"Always circle the frequency word (e.g. \textit{quarterly}) in the exam prompt and immediately write $\div 4$ and $\times 4$ above it."
    if any(k in c_lower or k in t_lower for k in ["depreciation", "salvage", "declining"]):
        return r"Check that salvage value $S$ is strictly less than original purchase price $V_0$. If higher, you used $(1+r)$ instead of $(1-r)$!"
    if any(k in c_lower or k in t_lower for k in ["credit", "card", "interest-free"]):
        return r"Check if balance was paid in full; if not, interest applies retroactively to the full amount from the purchase date."
    if any(k in c_lower or k in t_lower for k in ["superannuation", "super"]):
        return r"Super is employer-funded (11.5\%); verify it is added on top of salary, not deducted from your take-home pay."
    if any(k in c_lower or k in t_lower for k in ["simple interest", "flat rate"]):
        return r"Always check time units: if time is in months, divide by 12; if in weeks, divide by 52, before multiplying into $I = Prn$."
    if any(k in c_lower or k in t_lower for k in ["tax", "taxable income", "medicare", "deduction"]):
        return r"Always subtract allowable deductions before looking up tax brackets: $\text{Taxable Income} = \text{Gross} - \text{Deductions}$."
    if any(k in c_lower or k in t_lower for k in ["earning", "wage", "salary", "overtime"]):
        return r"Remember that 1 year = 52 weeks = 26 fortnights = 12 months. Never multiply weekly wage by 4 to get monthly salary!"
    if any(k in c_lower or k in t_lower for k in ["financial", "consumer arithmetic"]):
        return r"Round currency to 2 decimal places (cents) at the very end; keep unrounded values in calculator memory during intermediate steps."

    # 2. Coordinate Geometry checks
    if any(k in c_lower or k in t_lower for k in ["perpendicular", "gradient", "slope"]):
        return r"For perpendicular lines, test $m_1 \times m_2 = -1$. For parallel lines, test $m_1 = m_2$. Sketch a quick line to confirm positive vs negative slope."
    if any(k in c_lower or k in t_lower for k in ["distance", "midpoint", "length"]):
        return r"Watch out for negative coordinates: $(x_2 - (-x_1))$ becomes $(x_2 + x_1)$. Always verify the midpoint lies visually between the two points."
    if any(k in c_lower or k in t_lower for k in ["collinear"]):
        return r"Check that gradients between all pairs match: $m_{AB} = m_{BC}$. A common point $B$ proves they lie on the exact same line."
    if any(k in c_lower or k in t_lower for k in ["general form"]):
        return r"In $Ax + By + C = 0$, verify that $A \ge 0$ is a positive integer and there are no fractional coefficients."
    if any(k in c_lower or k in t_lower for k in ["coordinate geometry", "linear"]):
        return r"Always sketch a quick Cartesian plane to confirm the quadrant, intercept locations, and direction of slope."

    # 3. Trigonometry checks
    if any(k in c_lower or k in t_lower for k in ["trigonometry", "trig", "bearing", "sine", "cosine", "tangent"]):
        return r"Verify calculator mode first: ensure it is in DEGREE mode ($D$) for geometry or RADIAN mode ($R$) for calculus."

    # 4. Calculus checks
    if any(k in c_lower or k in t_lower for k in ["derivative", "differentiation", "tangent line", "calculus", "integral"]):
        return r"Check power rule $\frac{d}{dx}[x^n] = n x^{n-1}$. For composite functions, always multiply by the inner derivative (chain rule)."

    # 5. Algebra & Equations checks
    if any(k in c_lower or k in t_lower for k in ["quadratic", "factoris", "algebra", "indices", "fraction"]):
        return r"Substitute your solution back into the original equation to verify that LHS = RHS before moving to the next problem."

    # 6. Probability & Statistics checks
    if any(k in c_lower or k in t_lower for k in ["probability", "tree diagram", "venn"]):
        return r"Sanity check: all probabilities must be between 0 and 1, and the sum of all branch probabilities must equal 1."
    if any(k in c_lower or k in t_lower for k in ["statistic", "iqr", "quartile", "box plot", "outlier"]):
        return r"Ensure data is sorted in ascending order before finding the median, $Q_1$, and $Q_3$. Outlier threshold: $Q_3 + 1.5 \times \text{IQR}$."

    # 7. Fallback from tutor tips if available
    if tutor_tips and len(str(tutor_tips).strip()) > 10:
        clean_tip = re.sub(r'^(?:Tip|Note|DA Tip|Check)[:\-–—]?\s*', '', str(tutor_tips).strip(), flags=re.IGNORECASE)
        first_sent = clean_tip.split('.')[0].strip()
        if len(first_sent) > 15:
            return sanitize_for_latex(first_sent + ".")

    # 8. Universal robust fallback
    return r"Reread the question stem, check given units, and verify that the final answer is physically and logically reasonable."


def build_masterclass_theory_box_content(
    theory_content: str,
    key_formulas: List[Any],
    tutor_tips: str,
    concept_name: str = "",
    topic: str = "",
    year_level: str = "",
    tikz_diagram: str = "",
    is_student_scaffold: bool = False
) -> str:
    """
    Renders an elite, high-impact Masterclass Theory Card with zero fluff,
    intuitive mental models, step-by-step master methods, clean formula blueprints,
    and examiner mark-protection traps.
    """
    c_lower = str(concept_name).lower()
    t_lower = str(topic).lower()
    is_factorial_concept = "factorial" in c_lower

    is_fin = any(k in t_lower or k in c_lower for k in [
        "consumer arithmetic", "financial", "interest", "depreciation", "credit", "superannuation", "earning", "tax"
    ])

    curated = None
    is_combinatorics = any(k in t_lower or k in c_lower for k in [
        "combinatorics", "permutation", "combination", "factorial", "counting principle"
    ])
    if is_combinatorics:
        curated = {
            "intuition": r"A factorial is a countdown multiplication: $5! = 5\times4\times3\times2\times1 = 120$. In general, $n! = n(n-1)(n-2)\cdots3\times2\times1$, and $0! = 1$. Factorials are the building blocks for counting arrangements and selections.",
            "formulas": [
                r"n! = n(n-1)(n-2)\cdots 3\times2\times1,\qquad 0! = 1",
                r"n! = n\times(n-1)! \qquad\text{and}\qquad \frac{n!}{(n-r)!} = n(n-1)\cdots(n-r+1)",
            ],
            "variable_defs": r"$n$ is a non-negative integer; $n!$ counts the ways to arrange $n$ distinct objects in a line.",
            "method_title": r"DA MASTER METHOD (FACTORIAL COUNTDOWN)",
            "steps": [
                r"\textbf{\color{dablue}[Step 1] Identify the count:} Decide whether the question asks for an arrangement, selection, or repeated objects.",
                r"\textbf{\color{dablue}[Step 2] Write the factorial:} Expand only as far as needed, for example $10! = 10\times9\times8\times7!$.",
                r"\textbf{\color{dablue}[Step 3] Cancel before calculating:} Cancel common factorial factors first, then simplify the small remaining product.",
            ],
            "pitfall": r"Do not treat $n!$ as $n\times n$; it is the product of every positive integer from $n$ down to $1$.",
            "self_check": r"Check the endpoint: every factorial expansion must finish at $\times2\times1$, while $0!$ is defined as $1$.",
        }
    elif is_fin:
        if any(k in c_lower for k in ["compound", "future value", "present value", "principal", "interest calculation"]):
            curated = {
                "intuition": r"Compound interest is the \textbf{Snowball Effect}---interest is earned on your initial deposit PLUS on all accumulated interest. In exams: $A$ is the final growing snowball, $P$ is the starting snowball. Money compounds forward in time.",
                "formulas": [
                    r"A = P\left(1 + \dfrac{r}{k}\right)^{nk} \qquad\qquad I = A - P",
                ],
                "variable_defs": r"$A = \text{Future Value (Total \$)}$, $P = \text{Starting Principal (\$)}$, $r = \text{Annual Rate (decimal)}$, $k = \text{Compounding periods/yr}$, $n = \text{Years}$.",
                "method_title": r"DA MASTER METHOD (THE 2-SECOND FREQUENCY RULE)",
                "steps": [
                    r"\textbf{\color{dablue}[Step 1] Adjust for Frequency First:} Convert rate and periods \textit{before} touching the calculator:\\ \quad $\bullet$ \textbf{Annually:} $r$, $n$ \qquad $\bullet$ \textbf{Quarterly:} $r \div 4$, $n \times 4$ \qquad $\bullet$ \textbf{Monthly:} $r \div 12$, $n \times 12$",
                    r"\textbf{\color{dablue}[Step 2] Execute Formula:} Substitute adjusted values into $A = P(1+r)^n$.",
                    r"\textbf{\color{dablue}[Step 3] Interest Check:} If the question asks for \textit{interest earned}, always subtract starting money: $I = A - P$."
                ],
                "pitfall": r"70\% of students leave the annual rate $r$ unchanged when compounding monthly or quarterly, losing 2 easy marks!",
                "self_check": r"Always circle the frequency word (e.g. \textit{quarterly}) in the exam prompt and immediately write $\div 4$ and $\times 4$ above it."
            }
        elif any(k in c_lower for k in ["frequency", "compounding period", "quarterly", "monthly"]):
            curated = {
                "intuition": r"More compounding periods per year means \textbf{interest gets calculated more often}, creating a larger final amount $A$. Golden Rule: \textbf{Divide rate, Multiply time}.",
                "formulas": [
                    r"r_{\text{period}} = \dfrac{r_{\text{annual}}}{k} \qquad\qquad n_{\text{periods}} = \text{Years} \times k",
                ],
                "variable_defs": r"$k = \text{compounding frequency per year (Quarterly: 4, Monthly: 12, Fortnightly: 26, Weekly: 52, Daily: 365)}$.",
                "method_title": r"DA MASTER METHOD (PERIOD CONVERSION FAST-TRACK)",
                "steps": [
                    r"\textbf{\color{dablue}[Step 1] Scan Frequency Keyword:} Look for quarterly ($k=4$), monthly ($k=12$), or weekly ($k=52$).",
                    r"\textbf{\color{dablue}[Step 2] Convert Pair:} Calculate $r_{\text{period}} = \frac{r}{k}$ and $n = \text{years} \times k$.",
                    r"\textbf{\color{dablue}[Step 3] Substitute Once:} Enter $A = P(1 + r_{\text{period}})^n$ in one continuous calculator string."
                ],
                "pitfall": r"Entering $n$ as years (e.g. $n=3$) instead of total compounding periods (e.g. $3 \times 12 = 36$).",
                "self_check": r"Check: does compounding more frequently make $A$ slightly bigger? Yes! If not, check your rate conversion."
            }
        elif any(k in c_lower for k in ["depreciation", "salvage", "declining"]):
            curated = {
                "intuition": r"Declining-Balance Depreciation is the \textbf{Reverse Snowball}---assets (cars, phones) lose massive dollar value in Year 1, then the drop slows down every year. It never hits zero, unlike straight-line depreciation which drops by a fixed dollar amount each year.",
                "formulas": [
                    r"S = V_0(1 - r)^n \qquad\qquad \text{Total Loss } = V_0 - S",
                ],
                "variable_defs": r"$S = \text{Salvage Value (Future Value)}$, $V_0 = \text{Purchase Price (Starting Value)}$, $r = \text{Annual Depreciation Rate (decimal)}$, $n = \text{Years}$.",
                "method_title": r"DA MASTER METHOD (THE 3-STEP SALVAGE RECIPE)",
                "steps": [
                    r"\textbf{\color{dablue}[Step 1] Identify Method:} Check for \textit{declining-balance} (percentage $r$) vs \textit{straight-line} (fixed \$ amount $D$).",
                    r"\textbf{\color{dablue}[Step 2] Apply Minus Sign:} Substitute into $S = V_0(1-r)^n$. Notice the minus sign: value ALWAYS decreases!",
                    r"\textbf{\color{dablue}[Step 3] Reality Check:} Salvage value $S$ must ALWAYS be strictly less than $V_0$."
                ],
                "pitfall": r"Accidentally using $(1+r)^n$ instead of $(1-r)^n$, causing a depreciating car or computer to miraculously double in price!",
                "self_check": r"If your final salvage answer is higher than the original purchase price, you made a sign error!"
            }
        elif any(k in c_lower for k in ["credit", "card", "interest-free", "billing"]):
            curated = {
                "intuition": r"The \textbf{Zero-Dollar Principle}---credit cards offer up to 55 days interest-free (30-day billing cycle + 25-day payment window). If you pay 100\% of the closing balance by the due date, you pay \$0 interest.",
                "formulas": [
                    r"\text{Daily Rate} = \dfrac{r_{\text{annual}}}{365} \qquad\qquad I = P \times \left(\dfrac{r_{\text{annual}}}{365}\right) \times d",
                ],
                "variable_defs": r"$P = \text{Original purchase amount (\$)}$, $r = \text{Annual interest rate}$, $d = \text{Exact days from purchase to payment date}$.",
                "method_title": r"DA MASTER METHOD (INTEREST CALCULATION)",
                "steps": [
                    r"\textbf{\color{dablue}[Step 1] Check Full Payment:} If Closing Balance is paid in full by Due Date $\implies \text{Interest} = \$0.00$.",
                    r"\textbf{\color{dablue}[Step 2] Backdated Penalty:} If unpaid or partially paid, interest applies to the \textbf{entire original purchase amount} from the \textbf{date of purchase}, not just the unpaid residue!",
                    r"\textbf{\color{dablue}[Step 3] Count Exact Days:} Count every single day from purchase date up to payment date inclusive."
                ],
                "pitfall": r"Calculating interest only on the unpaid balance, or only for the 25 payment window days.",
                "self_check": r"Missing full payment wipes out the entire 55-day grace period retroactively all the way back to Day 1!"
            }
        elif any(k in c_lower for k in ["superannuation", "super", "investment", "risk", "return"]):
            curated = {
                "intuition": r"Superannuation is a \textbf{Compulsory Wealth Engine}---employers contribute 11.5\% of your ordinary earnings into an investment fund for retirement, taxed at a concessional rate of 15\%.",
                "formulas": [
                    r"\text{Gross Contribution} = \text{Gross Wage} \times 11.5\% \qquad\qquad \text{Net Added} = \text{Gross Contribution} \times (1 - 0.15)",
                ],
                "variable_defs": r"Current Super Guarantee (SG) = 11.5\%, Contributions Tax = 15\%.",
                "method_title": r"DA MASTER METHOD (RISK VS RETURN & NET EARNINGS)",
                "steps": [
                    r"\textbf{\color{dablue}[Step 1] Employer Contribution:} Calculate $\text{Salary} \times 0.115$. (Paid by employer ON TOP of salary, not deducted from it).",
                    r"\textbf{\color{dablue}[Step 2] Contributions Tax:} Deduct 15\% tax: $\text{Net Contribution} = \text{Contribution} \times 0.85$.",
                    r"\textbf{\color{dablue}[Step 3] Net Fund Growth:} $\text{Net Growth} = \text{Investment Earnings (\%)} - \text{Total Fees (\$) - Taxes}."
                ],
                "pitfall": r"Confusing employer super contributions with money deducted from student/employee pay packets.",
                "self_check": r"Super is employer-funded savings for retirement; it sits in a protected account until age 60+."
            }
        elif any(k in c_lower for k in ["earning", "income", "wage", "salary", "overtime", "commission", "piecework", "allowance", "bonus"]):
            curated = {
                "intuition": r"Gross Income is your \textbf{Total Raw Earnings} before any deductions or tax. Understanding pay cycles and overtime rates is crucial: a year has 52 weeks, 26 fortnights, and 12 months. Overtime compensates extra hours at time-and-a-half ($\times 1.5$) or double-time ($\times 2.0$).",
                "formulas": [
                    r"\text{Gross Pay} = \text{Base Pay} + \text{Overtime Pay} + \text{Bonuses/Commissions}",
                    r"\text{Time-and-a-half} = \text{Rate} \times 1.5 \times \text{Hours} \qquad\qquad \text{Double-time} = \text{Rate} \times 2.0 \times \text{Hours}",
                ],
                "variable_defs": r"1 year = 52 weeks = 26 fortnights = 12 months. Note: $\text{Monthly Pay} = \text{Annual} \div 12 \ne \text{Weekly} \times 4$.",
                "method_title": r"DA MASTER METHOD (THE 3-TIER PAYROLL CALCULATOR)",
                "steps": [
                    r"\textbf{\color{dablue}[Step 1] Separate Normal vs Overtime Hours:} Multiply regular hours by the base hourly rate; calculate overtime tiers separately ($1.5\times$ or $2\times$).",
                    r"\textbf{\color{dablue}[Step 2] Add Commissions or Piecework:} For commission, compute $\text{Sales} \times \text{Commission \%}$; for piecework, compute $\text{Units} \times \text{Rate per Unit}$.",
                    r"\textbf{\color{dablue}[Step 3] Sum to Gross Pay:} Combine all components: $\text{Gross Pay} = \text{Base} + \text{Overtime} + \text{Commissions} + \text{Allowances}$."
                ],
                "pitfall": r"Assuming 1 month = 4 weeks (giving only 48 weeks/year). To convert weekly to monthly: calculate $\text{Annual} = \text{Weekly} \times 52$, then $\text{Monthly} = \text{Annual} \div 12$.",
                "self_check": r"Remember that 1 year = 52 weeks = 26 fortnights = 12 months. Never multiply weekly wage by 4 to get monthly salary!"
            }
        elif any(k in c_lower for k in ["tax", "deduction", "taxable income", "medicare", "payg", "refund"]):
            curated = {
                "intuition": r"Taxable Income is the \textbf{Only Portion the Government Taxes}---you subtract allowable work deductions from your gross income first. Medicare levy is an additional 2\% charge on taxable income to fund public healthcare.",
                "formulas": [
                    r"\text{Taxable Income} = \text{Gross Income} - \text{Allowable Deductions}",
                    r"\text{Gross Tax} = \text{Base Tax} + (\text{Marginal Rate} \times \text{Excess over Threshold})",
                    r"\text{Net Tax Payable} = \text{Gross Tax} + \text{Medicare Levy (2\%)} - \text{Tax Offsets}",
                ],
                "variable_defs": r"$\text{Tax Refund} = \text{PAYG Tax Withheld} - \text{Net Tax Payable}$ (positive $\implies$ refund; negative $\implies$ debt owing).",
                "method_title": r"DA MASTER METHOD (ATO TAX BRACKET NAVIGATION)",
                "steps": [
                    r"\textbf{\color{dablue}[Step 1] Determine Taxable Income:} Compute $\text{Taxable Income} = \text{Gross Income} - \text{Allowable Deductions}$.",
                    r"\textbf{\color{dablue}[Step 2] Locate Tax Bracket \& Apply Formula:} Find which bracket taxable income falls in; add base tax to marginal rate $\times$ amount \textit{above} threshold.",
                    r"\textbf{\color{dablue}[Step 3] Medicare Levy \& Refund Check:} Add 2\% Medicare levy ($\text{Taxable} \times 0.02$). Compare with PAYG tax paid to find refund or debt."
                ],
                "pitfall": r"Applying the marginal tax rate to the ENTIRE taxable income instead of only the excess dollars above the bracket threshold!",
                "self_check": r"Always subtract allowable deductions before looking up tax brackets: $\text{Taxable Income} = \text{Gross} - \text{Deductions}$."
            }
        elif any(k in c_lower for k in ["simple interest", "flat rate"]):
            curated = {
                "intuition": r"Simple Interest is the \textbf{Fixed-Dollar Engine}---interest is calculated ONLY on the original starting principal $P$ once, and that same fixed dollar amount is added each period. The investment balance grows linearly.",
                "formulas": [
                    r"I = P \times r \times n \qquad\qquad A = P + I",
                    r"P = \dfrac{I}{r \times n} \qquad\qquad r = \dfrac{I}{P \times n} \qquad\qquad n = \dfrac{I}{P \times r}",
                ],
                "variable_defs": r"$I = \text{Interest (\$)}, P = \text{Principal (\$)}, r = \text{Annual Rate (decimal)}, n = \text{Years}, A = \text{Total Balance (\$)}$.",
                "method_title": r"DA MASTER METHOD (THE SIMPLE INTEREST TRIANGLE)",
                "steps": [
                    r"\textbf{\color{dablue}[Step 1] Convert Rate \& Time to Years:} Write rate $r$ as a decimal and convert time $n$ to years (months $\div 12$, days $\div 365$).",
                    r"\textbf{\color{dablue}[Step 2] Calculate Interest ($I = Prn$):} Multiply $P \times r \times n$ directly in one calculator step.",
                    r"\textbf{\color{dablue}[Step 3] Total Repayment or Balance:} If asked for total balance or loan repayments, calculate $A = P + I$."
                ],
                "pitfall": r"Entering time $n$ in months without dividing by 12, inflating interest by a factor of 12!",
                "self_check": r"Always check time units: if time is in months, divide by 12; if in weeks, divide by 52, before multiplying into $I = Prn$."
            }
        else:
            curated = {
                "intuition": r"Financial mathematics models how \textbf{money changes over time} through earnings, deductions, interest growth, and asset depreciation. Precision in percentage conversions and compounding timeframes protects every mark.",
                "formulas": [
                    r"\text{Earnings: } \text{Gross} = \text{Base} + \text{Overtime} \qquad\qquad \text{Interest: } I = Prn \text{ (Simple)} \text{ vs } A = P(1+r)^n \text{ (Compound)}",
                    r"\text{Tax: } \text{Taxable} = \text{Gross} - \text{Deductions} \qquad\qquad \text{Depreciation: } S = V_0(1-r)^n",
                ],
                "variable_defs": r"$P, V_0 = \text{Initial amount (\$)}$, $A, S = \text{Final amount (\$)}$, $r = \text{Rate (decimal)}$, $n = \text{Time (periods)}$.",
                "method_title": r"DA MASTER METHOD (FINANCIAL CALCULATION STRATEGY)",
                "steps": [
                    r"\textbf{\color{dablue}[Step 1] Identify Category:} Determine whether the problem involves income/wages, tax calculation, simple/compound interest, or depreciation/loans.",
                    r"\textbf{\color{dablue}[Step 2] Normalize Time \& Rate Units:} Ensure all rates and time periods are aligned (annual vs monthly vs quarterly). Convert percentages to decimals.",
                    r"\textbf{\color{dablue}[Step 3] Compute \& Round Appropriately:} Execute the core formula in one continuous step. Round financial currency answers to 2 decimal places (cents) unless exact whole dollars are requested."
                ],
                "pitfall": r"Rounding intermediate calculations on the calculator, which compounds rounding errors into the final dollar cents answer.",
                "self_check": r"Round currency to 2 decimal places (cents) at the very end; keep unrounded values in calculator memory during intermediate steps."
            }

    # Student In-Class Scaffold Mode: generate matched-dimension scaffold cards with generous ruled note spaces
    if is_student_scaffold:
        scaffold_cards = []
        # Card 1: The Big Idea (How to Think About It)
        # 3 clean full-width ruled lines with generous spacing for student handwriting (0.38cm)
        scaffold_cards.append(
            r"\noindent\colorbox{slatebg}{\parbox{\dimexpr\linewidth-2\fboxsep\relax}{"
            r"\textbf{\color{dablue}\sffamily\footnotesize \dalightning\ THE BIG IDEA (HOW TO THINK ABOUT IT)}\par\vspace{0.10cm}"
            r"\rule{\linewidth}{0.4pt}\\[0.38cm]"
            r"\rule{\linewidth}{0.4pt}\\[0.38cm]"
            r"\rule{\linewidth}{0.4pt}\\[0.06cm]"
            r"}}"
        )
        # Card 2: Essential Formulae & Rules
        # 4 clean full-width ruled lines for writing laws, equations, definitions (0.38cm gaps)
        scaffold_cards.append(
            r"\noindent\colorbox{goldbg}{\parbox{\dimexpr\linewidth-2\fboxsep\relax}{"
            r"\textbf{\color{danavy}\sffamily\footnotesize \dalightning\ ESSENTIAL FORMULAE \& RULES}\par\vspace{0.10cm}"
            r"\rule{\linewidth}{0.4pt}\\[0.38cm]"
            r"\rule{\linewidth}{0.4pt}\\[0.38cm]"
            r"\rule{\linewidth}{0.4pt}\\[0.38cm]"
            r"\rule{\linewidth}{0.4pt}\\[0.06cm]"
            r"}}"
        )
        # Card 2.5: Visual Model & Key Diagram (Flush left heading, clean drawing space)
        scaffold_cards.append(
            r"\noindent\colorbox{slatebg}{\parbox{\dimexpr\linewidth-2\fboxsep\relax}{%" + "\n"
            r"\textbf{\color{danavy}\sffamily\footnotesize \ensuremath{\blacktriangleright}\ VISUAL MODEL \& KEY DIAGRAM}\par\vspace{0.06cm}" + "\n"
            r"{\centering" + "\n"
            r"\begin{tikzpicture}" + "\n"
            r"\draw[dashed, color=danavy!40, thick, rounded corners=4pt] (0,0) rectangle (0.94\linewidth, 2.5);" + "\n"
            r"\end{tikzpicture}" + "\n"
            r"\par}\vspace{0.04cm}" + "\n"
            r"}}"
        )
        # Card 3: DA Master Method (Ninja Recipe)
        m_title = (curated["method_title"] if curated else "DA MASTER METHOD (NINJA RECIPE)")
        scaffold_cards.append(
            r"\noindent\colorbox{slatebg}{\parbox{\dimexpr\linewidth-2\fboxsep\relax}{"
            r"\textbf{\color{danavy}\sffamily\footnotesize \ensuremath{\blacktriangleright}\ " + m_title + r"}\par\vspace{0.10cm}"
            r"\small"
            r"\textbf{\color{dablue}[Step 1]} \rule{0.84\linewidth}{0.4pt}\\[0.36cm]"
            r"\textbf{\color{dablue}[Step 2]} \rule{0.84\linewidth}{0.4pt}\\[0.36cm]"
            r"\textbf{\color{dablue}[Step 3]} \rule{0.84\linewidth}{0.4pt}\\[0.06cm]"
            r"}}"
        )
        # Card 4: Examiner's Trap
        scaffold_cards.append(
            r"\noindent\colorbox{pinkbg}{\parbox{\dimexpr\linewidth-2\fboxsep\relax}{"
            r"\textbf{\color{dawine}\sffamily\footnotesize \datrap\ THE EXAMINER'S TRAP (MARK PROTECTOR)}\par\vspace{0.10cm}"
            r"\small \textbf{\color{dawine}Common Pitfall:} \rule{0.73\linewidth}{0.4pt}\\[0.36cm]"
            r"\textbf{\color{dagreen!80!black}\ensuremath{\checkmark} DA Self-Check:} \rule{0.71\linewidth}{0.4pt}\\[0.06cm]"
            r"}}"
        )
        return "\n\n\\par\\vspace{0.08cm}\\noindent\n\n".join(scaffold_cards)

    # Dynamic parser for arbitrary topics (supports bullets - **Header**: and markdown ### Header)
    text = str(theory_content).strip()
    bullet_pat = re.compile(r'(?:^|\n)(?:[\-\*\•]\s+(?:\*\*(.+?)\*\*|__([^_]+)__)\s*[:\-–—]?|#{1,4}\s+([^\n]+))\s*([\s\S]*?)(?=(?:\n(?:[\-\*\•]\s+(?:\*\*|__)|#{1,4}\s+))|\Z)')
    matches = list(bullet_pat.finditer(text))

    sections = {}
    for m in matches:
        hdr = (m.group(1) or m.group(2) or m.group(3) or "").strip().lower()
        bdy = (m.group(4) or "").strip()
        sections[hdr] = bdy

    # Extract Intuition / Definition
    intuition_text = ""
    for sec_hdr, sec_body in sections.items():
        if any(k in sec_hdr for k in ["big idea", "intuition", "mental model", "definition", "concept", "what it is", "aha", "how to think"]):
            intuition_text = sec_body
            break
    if not intuition_text and matches:
        intuition_text = (matches[0].group(3) or "").strip()

    # Extract Method
    method_text = ""
    for sec_hdr, sec_body in sections.items():
        if any(k in sec_hdr for k in ["method", "ninja", "recipe", "step", "procedure", "how to solve", "how to calculate"]):
            method_text = sec_body
            break

    # Handle raw text without bullet formatting
    if not matches and text:
        if re.match(r'^\s*\d+[\.\)]', text):
            method_text = text
        else:
            intuition_text = text

    # Extract Trap
    trap_text = ""
    for sec_hdr, sec_body in sections.items():
        if any(k in sec_hdr for k in ["trap", "pitfall", "ambush", "warning", "mistake", "protector"]):
            trap_text = sec_body
            break
    if not trap_text and tutor_tips:
        trap_text = tutor_tips

    # Enrich from curated if empty
    if not intuition_text and curated:
        intuition_text = curated["intuition"]
    if not method_text and curated:
        method_text = "\n".join(curated["steps"])
    if not trap_text and curated:
        trap_text = curated["pitfall"]

    cards = []

    # Card 1: The Big Idea (How to Think About It)
    if intuition_text:
        sentences = re.split(r'(?<=[.!?])\s+', intuition_text)
        clean_s = [s.strip() for s in sentences if s.strip()]
        c_body = " ".join(clean_s[:3]).strip()
        if curated and len(c_body) < 180:
            c_body = f"{c_body} " + curated["intuition"]
        if is_factorial_concept and not re.search(r"\b6!\s*=", c_body):
            c_body += r" For example, $6! = 6\times5\times4\times3\times2\times1 = 720$; by definition, $0! = 1$."
        cards.append(
            r"\noindent\colorbox{slatebg}{\parbox{\dimexpr\linewidth-2\fboxsep\relax}{"
            r"\textbf{\color{dablue}\sffamily\footnotesize \dalightning\ THE BIG IDEA (HOW TO THINK ABOUT IT)}\\[0.05cm]"
            r"\small " + sanitize_for_latex(c_body) + r"}}"
        )

    # Card 2: Formulas (Each law/formula on its own distinct line)
    f_list = list(key_formulas) if key_formulas else (curated["formulas"] if curated else [])
    if curated and key_formulas and is_combinatorics and not any("!" in str(item) for item in f_list):
        f_list.extend(curated["formulas"])
    if f_list:
        f_items = []
        for kf in f_list:
            kf_clean = format_theory_formula(kf)
            clean_item = f"${kf_clean}$" if not ("$" in kf_clean or r"\[" in kf_clean or r"\textbf{" in kf_clean) else kf_clean
            f_items.append(clean_item)

        form_lines = []
        for fi in f_items[:5]:
            fi_clean = re.sub(r'^(?:[\-\*\•]|\\bullet)\s*', '', fi.strip()).strip()
            if fi_clean:
                bullet_prefix = r"\ensuremath{\bullet}\ " if len(f_items) > 1 else ""
                diag = get_angle_rule_mini_tikz(fi_clean)
                if diag:
                    form_lines.append(
                        r"\noindent\parbox[c]{0.70\linewidth}{\raggedright " + bullet_prefix + fi_clean + r"}"
                        r"\hfill\parbox[c]{0.26\linewidth}{\centering " + diag + r"}"
                    )
                else:
                    form_lines.append(bullet_prefix + fi_clean)
        form_str = r"\\[0.09cm]".join(form_lines)

        var_line = ""
        if curated and curated.get("variable_defs"):
            var_line = r"\\[0.09cm]\raggedright\footnotesize \textbf{Where:} " + curated["variable_defs"]

        cards.append(
            r"\noindent\colorbox{goldbg}{\parbox{\dimexpr\linewidth-2\fboxsep\relax}{"
            r"\textbf{\color{danavy}\sffamily\footnotesize \dalightning\ ESSENTIAL FORMULAE}\\[0.05cm]"
            r"\raggedright\small " + form_str + var_line + r"}}"
        )

    # Card 2.5: Visual Model & Key Diagram (Embedded directly inside Theory Box)
    concept_diag = sanitize_tikz_diagram(tikz_diagram) if tikz_diagram else ""
    if not concept_diag and not is_combinatorics and (concept_name or topic):
        concept_diag = sanitize_tikz_diagram(get_concept_fallback_tikz(concept_name, topic))

    if concept_diag:
        diag_clean = concept_diag.strip()
        # Strip outer center wrappers
        while diag_clean.startswith(r"\begin{center}") and diag_clean.endswith(r"\end{center}"):
            diag_clean = diag_clean[14:-12].strip()

        # Strip any existing adjustbox wrapper so we can apply a pristine, guaranteed-matching one
        m_adj = re.match(r"^\\begin\{adjustbox\}\{[^}]*\}\s*([\s\S]*?)\s*\\end\{adjustbox\}$", diag_clean)
        if m_adj:
            diag_clean = m_adj.group(1).strip()

        # Fix any \label variable in foreach loops (reserved LaTeX core macro)
        diag_clean = re.sub(r'\\foreach\s*\\x/\\label/', r'\\foreach \\x/\\lbl/', diag_clean)
        diag_clean = diag_clean.replace(r'\textbf{\label}', r'\textbf{\lbl}')

        # Fix double option syntax errors (e.g. above left=3pt=2pt -> above left=3pt)
        diag_clean = re.sub(r'([a-zA-Z\s\-]+=[0-9\.]+(?:pt|cm|mm))=[0-9\.]+(?:pt|cm|mm)', r'\1', diag_clean)

        # Strict integrity checks:
        has_begin_tikz = r"\begin{tikzpicture}" in diag_clean
        has_end_tikz = r"\end{tikzpicture}" in diag_clean
        braces_balanced = (diag_clean.count('{') == diag_clean.count('}'))
        brackets_balanced = (diag_clean.count('[') == diag_clean.count(']'))

        # If any integrity check fails, omit diagram cleanly to guarantee Cards 1, 2, 3, 4 ALWAYS render
        if (not has_begin_tikz) or (not has_end_tikz) or (not braces_balanced) or (not brackets_balanced):
            diag_clean = ""

        if diag_clean:
            # Give the factorial unrolling model enough room for labels above
            # both arrows; other diagrams retain the compact theory-card size.
            unroll_model = "Unroll $(n-1)$" in diag_clean
            max_width = "0.94" if unroll_model else "0.88"
            max_height = "3.3" if unroll_model else "2.8"
            diag_clean = f"\\begin{{adjustbox}}{{max width={max_width}\\linewidth, max totalheight={max_height}cm, keepaspectratio, center}}\n{diag_clean}\n\\end{{adjustbox}}"
            cards.append(
                "\\noindent\\colorbox{slatebg}{\\parbox{\\dimexpr\\linewidth-2\\fboxsep\\relax}{%\n"
                "\\textbf{\\color{danavy}\\sffamily\\footnotesize \\ensuremath{\\blacktriangleright}\\ VISUAL MODEL \\& KEY DIAGRAM}\\par\\vspace{0.06cm}\n"
                "{\\centering\n" + diag_clean + "\n\\par}\n"
                "}}"
            )

    # Card 3: Method (Clean steps with no duplicate Step numbers or hyphens)
    if method_text:
        step_items = []
        raw_step_lines = split_method_steps(method_text)

        for s_idx, raw_line in enumerate(raw_step_lines[:4], 1):
            line = raw_line.strip()
            if line.startswith(r"\textbf{\color{dablue}[Step"):
                step_items.append(line)
                continue

            # Strip leading list / bullet markers (-, *, •, 1., etc.)
            line = re.sub(r'^(?:[\-\*\•]|\d+[\.\)])\s*', '', line).strip()

            # Handle duplicate [Step 1] - [Step 1: Title]
            m_nested = re.match(r'^\[\s*Step\s*\d*\s*\]\s*[:\-–—]?\s*\[\s*Step\s*\d*\s*[:\-–—]\s*([^\]]+)\]\s*[:\-–—]?\s*(.*)$', line, re.IGNORECASE)
            # Handle [Step 1: Title] or [Step 1 - Title]
            m_bracket_tag = re.match(r'^\[\s*Step\s*\d*\s*[:\-–—]\s*([^\]]+)\]\s*[:\-–—]?\s*(.*)$', line, re.IGNORECASE)
            # Handle [Step 1] or [Step 1]:
            m_bracket_simple = re.match(r'^\[\s*Step\s*\d*\s*\]\s*[:\-–—]?\s*(.*)$', line, re.IGNORECASE)
            # Handle Step 1: Title - Body or Step 1: Body
            m_plain_step = re.match(r'^Step\s*\d*\s*[:\-–—]\s*(.*)$', line, re.IGNORECASE)

            if m_nested:
                tag = m_nested.group(1).strip()
                body = m_nested.group(2).strip()
                step_items.append(f"\\textbf{{\\color{{dablue}}[Step {s_idx}: {sanitize_for_latex(tag)}]}} {sanitize_for_latex(body)}")
            elif m_bracket_tag:
                tag = m_bracket_tag.group(1).strip()
                body = m_bracket_tag.group(2).strip()
                step_items.append(f"\\textbf{{\\color{{dablue}}[Step {s_idx}: {sanitize_for_latex(tag)}]}} {sanitize_for_latex(body)}")
            elif m_bracket_simple:
                body = m_bracket_simple.group(1).strip()
                m_subtag = re.match(r'^([A-Za-z0-9\s]{3,30})\s*[:\-–—]\s*(.*)$', body)
                if m_subtag:
                    tag = m_subtag.group(1).strip()
                    subbody = m_subtag.group(2).strip()
                    step_items.append(f"\\textbf{{\\color{{dablue}}[Step {s_idx}: {sanitize_for_latex(tag)}]}} {sanitize_for_latex(subbody)}")
                else:
                    step_items.append(f"\\textbf{{\\color{{dablue}}[Step {s_idx}]}} {sanitize_for_latex(body)}")
            elif m_plain_step:
                rest = m_plain_step.group(1).strip()
                m_subtag = re.match(r'^([A-Za-z0-9\s]{3,30})\s*[:\-–—]\s*(.*)$', rest)
                if m_subtag:
                    tag = m_subtag.group(1).strip()
                    subbody = m_subtag.group(2).strip()
                    step_items.append(f"\\textbf{{\\color{{dablue}}[Step {s_idx}: {sanitize_for_latex(tag)}]}} {sanitize_for_latex(subbody)}")
                else:
                    step_items.append(f"\\textbf{{\\color{{dablue}}[Step {s_idx}]}} {sanitize_for_latex(rest)}")
            else:
                step_items.append(f"\\textbf{{\\color{{dablue}}[Step {s_idx}]}} {sanitize_for_latex(line)}")

        if step_items:
            m_title = (curated["method_title"] if curated else "DA MASTER METHOD (NINJA RECIPE)")
            cards.append(
                r"\noindent\colorbox{slatebg}{\parbox{\dimexpr\linewidth-2\fboxsep\relax}{"
                r"\textbf{\color{danavy}\sffamily\footnotesize \ensuremath{\blacktriangleright}\ " + m_title + r"}\\[0.06cm]"
                r"\small " + r"\par\vspace{0.08cm}".join(step_items) + r"}}"
            )

    # Card 4: Trap (Unconditionally include DA Self-Check in all theory booklets)
    self_check_rule = (curated.get("self_check") if curated else "") or get_concept_self_check(concept_name, topic, tutor_tips, trap_text)
    if not trap_text:
        if curated and curated.get("pitfall"):
            trap_text = curated["pitfall"]
        elif any(k in t_lower or k in c_lower for k in ["financial", "arithmetic", "interest"]):
            trap_text = "Prematurely rounding values or forgetting to convert compounding time units before substituting."
        elif any(k in t_lower or k in c_lower for k in ["coordinate", "linear", "geometry"]):
            trap_text = "Making sign errors when subtracting negative coordinates in gradient and distance formulas."
        else:
            trap_text = "Rushing calculations without verifying that the result matches the initial question requirements."

    cards.append(
        r"\noindent\colorbox{pinkbg}{\parbox{\dimexpr\linewidth-2\fboxsep\relax}{"
        r"\textbf{\color{dawine}\sffamily\footnotesize \datrap\ THE EXAMINER'S TRAP (MARK PROTECTOR)}\\[0.05cm]"
        r"\small \textbf{\color{dawine}Common Pitfall:} " + sanitize_for_latex(trap_text) +
        r"\\[0.04cm]\textbf{\color{dagreen!80!black}\ensuremath{\checkmark} DA Self-Check:} " + self_check_rule +
        r"}}"
    )

    if not cards:
        return sanitize_for_latex(text)

    return "\n\n\\par\\vspace{0.12cm}\\noindent\n\n".join(cards)


def build_latex_worksheet_source(
    title: str,
    year_level: str,
    topic: str,
    questions: List[Dict[str, Any]],
    include_solutions: bool = True,
    term: Optional[int] = None,
    week: Optional[int] = None,
    sheet_type: str = "Homework",
    set_number: Optional[int] = 1,
    has_logo: bool = True,
    font_theme: str = "charter"
) -> str:
    """Builds the complete LaTeX source string for an authentic Australian exam worksheet."""
    subject_clean = f"{year_level} Maths"
    questions = order_and_renumber_worksheet_questions(questions)
    groups = group_questions_by_subtopic(questions)
    clean_topic = clean_worksheet_topic_title(topic)

    if str(sheet_type).strip().lower() == "homework":
        set_str = f" Set {set_number if set_number else 1}"
        title_line = f"{clean_topic} --- Homework{set_str}"
        sheet_type_label = f"Homework{set_str}"
    else:
        set_str = f" Set {set_number}" if (set_number and set_number > 1) else ""
        title_line = f"{clean_topic} --- {sheet_type}{set_str}"
        sheet_type_label = f"{sheet_type}{set_str}"

    tex_lines = [
        r"\documentclass[12pt,a4paper]{article}",
        r"\usepackage[top=2.0cm, bottom=2.0cm, left=1.5cm, right=1.5cm, headsep=7mm, footskip=8mm]{geometry}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage{amsmath,amssymb,amsfonts}",
        *get_font_latex_preamble(font_theme),
        r"\usepackage{fancyhdr}",
        r"\usepackage{graphicx}",
        r"\usepackage{adjustbox}",
        r"\usepackage{needspace}",
        r"\usepackage{enumitem}",
        r"\usepackage{tikz}",
        r"\usetikzlibrary{arrows.meta,calc,angles,quotes,shapes.geometric,patterns,decorations.pathreplacing}",
        r"\hyphenpenalty=10000",
        r"\exhyphenpenalty=10000",
        r"\binoppenalty=10000",
        r"\relpenalty=10000",
        r"\tolerance=9999",
        r"\emergencystretch=2.5em",
        "",
        r"\pagestyle{fancy}",
        r"\fancyhf{}",
        f"\\fancyhead[L]{{\\parbox[b]{{0.55\\textwidth}}{{\\raggedright\\footnotesize\\bfseries {subject_clean}}}}}",
        f"\\fancyhead[R]{{\\parbox[b]{{0.42\\textwidth}}{{\\raggedleft\\footnotesize\\bfseries {sheet_type_label} --- DA TUITION}}}}",
        r"\fancyfoot[C]{\thepage}",
        r"\renewcommand{\headrulewidth}{0.4pt}",
        "",
        r"\newcommand{\qmark}[1]{\unskip\hfill\penalty-50\null\hfill\mbox{\textbf{(#1~mark\ifnum#1>1s\fi)}}}",
        "",
        r"\begin{document}",
        r"\thispagestyle{plain}",
        ""
    ]

    header_lines = [
        r"\noindent",
        r"\begin{minipage}[t]{0.72\textwidth}",
        r"\vspace{0pt}",
        f"{{\\LARGE \\textbf{{{subject_clean}}}}}\\\\[0.2cm]",
    ]
    if term and week:
        header_lines.append(f"{{\\large \\textbf{{Term {term} \\quad Week {week}}}}}\\\\[0.15cm]")
    elif term:
        header_lines.append(f"{{\\large \\textbf{{Term {term}}}}}\\\\[0.15cm]")
    elif week:
        header_lines.append(f"{{\\large \\textbf{{Week {week}}}}}\\\\[0.15cm]")
    header_lines.extend([
        f"{{\\Large \\textbf{{{sanitize_for_latex(clean_topic)}}}}}\\\\[0.12cm]",
        f"{{\\large \\textbf{{{sanitize_for_latex(sheet_type_label)}}}}}\\\\[0.2cm]",
        r"\end{minipage}%",
        r"\hfill",
        r"\begin{minipage}[t]{0.26\textwidth}",
        r"\vspace{0pt}",
        r"\raggedleft"
    ])
    tex_lines.extend(header_lines)

    if has_logo:
        tex_lines.append(r"\includegraphics[height=3.0cm,keepaspectratio]{da_logo.png}")
    else:
        tex_lines.append(r"{\LARGE \textbf{DA TUITION}}")

    tex_lines.extend([
        r"\end{minipage}",
        r"\vspace{0.35cm}",
        r"\noindent",
        r"\textbf{Student Name:} \underline{\hspace{7.5cm}} \hfill \textbf{Class:} \underline{\hspace{4.5cm}}\\[0.25cm]",
        r"\hrule",
        r"\vspace{0.4cm}",
        ""
    ])

    # 1. QUESTIONS SECTION
    for grp in groups:
        tex_lines.append(r"\needspace{4.5cm}")
        tex_lines.append(f"\\subsection*{{{sanitize_for_latex(grp['set_title'])}}}")
        tex_lines.append(r"\nopagebreak")
        sections = get_tiered_sections_for_questions(grp["questions"])
        for sec in sections:
            tex_lines.append(r"\needspace{4.0cm}")
            tex_lines.append(f"\\noindent{{\\textbf{{\\large {sanitize_for_latex(sec['section_title'])}}}}}\\\\[0.15cm]")
            tex_lines.append(r"\nopagebreak")
            tex_lines.append(r"\begin{enumerate}[leftmargin=2.2em, itemsep=1.2em]")

            for q in sec["questions"]:
                item_label = q.get('item_label', str(q.get('num', '')))
                raw_text = q.get('text', '')
                options = q.get("options")
                if options and isinstance(options, dict):
                    raw_text = strip_mc_options_from_text(raw_text)
                marks = int(q.get('marks', 1))

                stem, subparts = split_question_subparts(raw_text)
                q_diag = q.get("diagram_tikz") or q.get("tikz_diagram") or q.get("diagram")
                if not q_diag or not str(q_diag).strip():
                    fallback_diag = synthesize_network_diagram_from_text(raw_text, topic=clean_topic, concept_name=q.get("subtopic", ""))
                    if fallback_diag:
                        q_diag = fallback_diag

                if subparts:
                    first_label = subparts[0][0]
                    list_label = r"\textbf{(\roman*)}" if first_label in ["i", "ii", "iii"] else r"\textbf{(\alph*)}"

                    if stem:
                        stem_lines = format_stem_with_bullet_items(stem, as_item=False)
                        stem_body = "\n".join(stem_lines)
                        tex_lines.append(f"\\item[\\textbf{{{item_label}.}}] {{\\raggedright {stem_body}\\par}}")
                    else:
                        tex_lines.append(f"\\item[\\textbf{{{item_label}.}}] \\leavevmode")

                    if q_diag and str(q_diag).strip():
                        tex_lines.append(r"\vspace{0.15cm}")
                        tex_lines.append(sanitize_tikz_diagram(str(q_diag).strip()))
                        tex_lines.append(r"\vspace{0.15cm}")
                        q_diag_rendered = True
                    else:
                        q_diag_rendered = False

                    tex_lines.append(f"\\begin{{enumerate}}[label={list_label}, leftmargin=1.8em, itemsep=0.35em, topsep=0.25em]")
                    for idx, (lbl, part_content) in enumerate(subparts):
                        part_mark_match = re.search(r'(?:\[|\()\s*(\d+)\s*marks?\s*(?:\]|\))\s*$', part_content, re.IGNORECASE)
                        if part_mark_match:
                            p_marks = int(part_mark_match.group(1))
                            p_text = part_content[:part_mark_match.start()].strip()
                            parent_mark_str = f" \\qmark{{{p_marks}}}"
                        elif idx == len(subparts) - 1:
                            p_text = part_content
                            parent_mark_str = f" \\qmark{{{marks}}}"
                        else:
                            p_text = part_content
                            parent_mark_str = ""

                        # Detect nested roman numerals (e.g. (i), (ii)) inside this subpart
                        sub_stem, roman_subs = split_question_subparts(p_text)
                        if roman_subs and roman_subs[0][0] in ["i", "ii", "iii"]:
                            if sub_stem:
                                sub_stem_lines = format_stem_with_bullet_items(sub_stem, as_item=False)
                                tex_lines.append(f"\\item {' '.join(sub_stem_lines)}")
                            else:
                                tex_lines.append(r"\item \leavevmode")
                            tex_lines.append(r"\begin{enumerate}[label=\textbf{(\roman*)}, leftmargin=1.8em, itemsep=0.25em, topsep=0.15em]")
                            for r_idx, (r_lbl, r_content) in enumerate(roman_subs):
                                r_mark_match = re.search(r'(?:\[|\()\s*(\d+)\s*marks?\s*(?:\]|\))\s*$', r_content, re.IGNORECASE)
                                if r_mark_match:
                                    r_m = int(r_mark_match.group(1))
                                    r_body = r_content[:r_mark_match.start()].strip()
                                    tex_lines.append(f"\\item {sanitize_for_latex(r_body)} \\qmark{{{r_m}}}")
                                elif r_idx == len(roman_subs) - 1 and parent_mark_str:
                                    tex_lines.append(f"\\item {sanitize_for_latex(r_content)}{parent_mark_str}")
                                else:
                                    tex_lines.append(f"\\item {sanitize_for_latex(r_content)}")
                            tex_lines.append(r"\end{enumerate}")
                        else:
                            p_lines = format_stem_with_bullet_items(p_text, as_item=False)
                            tex_lines.append(f"\\item {' '.join(p_lines)}{parent_mark_str}")
                    tex_lines.append(r"\end{enumerate}")

                    if q_diag and not q_diag_rendered and str(q_diag).strip():
                        tex_lines.append(r"\vspace{0.15cm}")
                        tex_lines.append(sanitize_tikz_diagram(str(q_diag).strip()))
                        tex_lines.append(r"\vspace{0.15cm}")
                else:
                    stem_lines = format_stem_with_bullet_items(raw_text, as_item=False)
                    q_body = "\n".join(stem_lines)
                    tex_lines.append(f"\\item[\\textbf{{{item_label}.}}] {{\\raggedright {q_body} \\qmark{{{marks}}}\\par}}")
                    if q_diag and str(q_diag).strip():
                        tex_lines.append(r"\vspace{0.15cm}")
                        tex_lines.append(sanitize_tikz_diagram(str(q_diag).strip()))
                        tex_lines.append(r"\vspace{0.15cm}")

                if options and isinstance(options, dict):
                    tex_lines.append(r"\begin{enumerate}[label=(\Alph*), itemsep=0.3em, topsep=0.2em]")
                    for opt_letter in ["A", "B", "C", "D"]:
                        if opt_letter in options:
                            opt_val = sanitize_for_latex(str(options[opt_letter]))
                            tex_lines.append(f"\\item {opt_val}")
                    tex_lines.append(r"\end{enumerate}")

            tex_lines.append(r"\end{enumerate}")
            tex_lines.append(r"\vspace{0.25cm}")

    if include_solutions:
        # 2. ANSWERS SECTION
        tex_lines.extend([
            "",
            r"\newpage",
            r"\begin{center}",
            r"{\Large \textbf{ANSWERS}}\\[0.15cm]",
            f"{{\\large \\textbf{{{subject_clean} \\quad $\\bullet$ \\quad {sanitize_for_latex(clean_topic)} ({sheet_type_label})}}}}\\\\",
            r"\end{center}",
            r"\vspace{0.2cm}",
            r"\hrule",
            r"\vspace{0.4cm}"
        ])

        for grp in groups:
            tex_lines.append(r"\needspace{4.0cm}")
            tex_lines.append(f"\\subsection*{{{sanitize_for_latex(grp['set_title'])}}}")
            tex_lines.append(r"\nopagebreak")
            sections = get_tiered_sections_for_questions(grp["questions"])
            for sec in sections:
                tex_lines.append(r"\needspace{3.5cm}")
                tex_lines.append(f"\\noindent{{\\textbf{{\\large {sanitize_for_latex(sec['section_title'])}}}}}\\\\[0.15cm]")
                tex_lines.append(r"\nopagebreak")
                tex_lines.append(r"\begin{enumerate}[leftmargin=2.2em, itemsep=0.45em]")

                for q in sec["questions"]:
                    item_label = q.get('item_label', str(q.get('num', '')))
                    ans = format_answer_parts_latex(sanitize_for_latex(q.get('correct_answer', '')))
                    tex_lines.append(f"\\item[\\textbf{{{item_label}.}}] {ans}")

                tex_lines.append(r"\end{enumerate}")
                tex_lines.append(r"\vspace{0.2cm}")

        # 3. FULLY WORKED SOLUTIONS
        tex_lines.extend([
            "",
            r"\newpage",
            r"\begin{center}",
            r"{\Large \textbf{DA TUITION --- FULLY WORKED SOLUTIONS \& MARKING KEY}}\\[0.15cm]",
            f"{{\\large \\textbf{{{subject_clean} \\quad $\\bullet$ \\quad {sanitize_for_latex(clean_topic)} ({sheet_type_label})}}}}\\\\",
            r"\end{center}",
            r"\vspace{0.2cm}",
            r"\hrule",
            r"\vspace{0.4cm}"
        ])

        for grp in groups:
            tex_lines.append(r"\needspace{4.0cm}")
            tex_lines.append(f"\\subsection*{{{sanitize_for_latex(grp['set_title'])}}}")
            tex_lines.append(r"\nopagebreak")
            sections = get_tiered_sections_for_questions(grp["questions"])
            for sec in sections:
                tex_lines.append(r"\needspace{3.5cm}")
                tex_lines.append(f"\\noindent{{\\textbf{{\\large {sanitize_for_latex(sec['section_title'])}}}}}\\\\[0.15cm]")
                tex_lines.append(r"\nopagebreak")
                tex_lines.append(r"\begin{enumerate}[leftmargin=2.2em, itemsep=1.2em]")

                for q in sec["questions"]:
                    item_label = q.get('item_label', str(q.get('num', '')))
                    ans = format_answer_parts_latex(sanitize_for_latex(q.get('correct_answer', '')))
                    working = format_latex_practice_solution(q.get('solution_steps', ''))

                    tex_lines.append(f"\\item[\\textbf{{{item_label}.}}] \\textbf{{Final Answer:}} {ans}\\\\")
                    if working:
                        tex_lines.append(f"\\textit{{Working Steps:}}\\par\\vspace{{0.03cm}}\n{working}")
                    q_sol_diag = q.get("solution_diagram_tikz") or q.get("solution_tikz") or q.get("solution_diagram")
                    if not q_sol_diag or not str(q_sol_diag).strip():
                        q_text = str(q.get("text", "")) + " " + str(q.get("question_text", ""))
                        if any(k in (q_text + " " + (working or "")).lower() for k in ["sketch", "plot the", "draw the graph", "draw the curve", "graph of", "graph the"]):
                            fallback_tikz = get_sketch_solution_fallback_tikz(q_text, working or "")
                            if fallback_tikz:
                                q_sol_diag = fallback_tikz
                    if q_sol_diag and str(q_sol_diag).strip():
                        tex_lines.append(r"\par\vspace{0.15cm}")
                        tex_lines.append(sanitize_tikz_diagram(str(q_sol_diag).strip()))
                        tex_lines.append(r"\vspace{0.15cm}")

                tex_lines.append(r"\end{enumerate}")
                tex_lines.append(r"\vspace{0.25cm}")

    tex_lines.append(r"\end{document}")
    return "\n".join(tex_lines)

def generate_latex_worksheet_pdf(
    title: str,
    year_level: str,
    topic: str,
    questions: List[Dict[str, Any]],
    include_solutions: bool = True,
    term: Optional[int] = None,
    week: Optional[int] = None,
    sheet_type: str = "Homework",
    set_number: Optional[int] = 1,
    font_theme: str = "charter"
) -> Optional[bytes]:
    """Compiles an authentic Australian exam-style PDF booklet with LaTeX, TikZ, and Matplotlib graphs."""
    pdflatex_bin = find_pdflatex()
    if not pdflatex_bin:
        return None

    tmp_dir = tempfile.mkdtemp()
    try:
        has_logo = False
        if os.path.exists(LOGO_PATH):
            shutil.copy(LOGO_PATH, os.path.join(tmp_dir, "da_logo.png"))
            has_logo = True

        full_tex = build_latex_worksheet_source(
            title=title,
            year_level=year_level,
            topic=topic,
            questions=questions,
            include_solutions=include_solutions,
            term=term,
            week=week,
            sheet_type=sheet_type,
            set_number=set_number,
            has_logo=has_logo,
            font_theme=font_theme
        )

        full_tex = inject_python_graphs(full_tex, tmp_dir)
        tex_path = os.path.join(tmp_dir, "worksheet.tex")
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(full_tex)

        for _ in range(2):
            subprocess.run(
                [pdflatex_bin, "-interaction=nonstopmode", "worksheet.tex"],
                cwd=tmp_dir,
                capture_output=True,
                check=False
            )

        pdf_path = os.path.join(tmp_dir, "worksheet.pdf")
        if os.path.exists(pdf_path):
            with open(pdf_path, "rb") as f:
                raw_bytes = f.read()
            return prune_trailing_blank_pages(raw_bytes, topic=topic, year_level=year_level)

    except Exception:
        pass
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return None

# --- REPORTLAB FALLBACK ENGINE ---
def format_math_for_reportlab(text: str) -> str:
    """Converts LaTeX and math expressions into clean ReportLab XML markup."""
    if not text:
        return ""
    
    s = str(text)
    # Strip any TikZ environments for ReportLab fallback
    s = re.sub(r"\\begin\{tikzpicture\}[\s\S]*?\\end\{tikzpicture\}", "[Diagram]", s)
    
    # Strip \left and \right sizing modifiers first so they do not conflict with \le
    s = re.sub(r"\\left\b\s*", "", s)
    s = re.sub(r"\\right\b\s*", "", s)
    
    latex_map = [
        (r"\\pm\b", "±"), (r"\\times\b", "×"), (r"\\div\b", "÷"),
        (r"\\degree\b", "°"), (r"\^\\circ\b", "°"), (r"\\circ\b", "°"),
        (r"\\pi\b", "π"), (r"\\le\b", "≤"), (r"\\ge\b", "≥"), (r"\\ne\b", "≠"),
        (r"\\approx\b", "≈"), (r"\\cap\b", "∩"), (r"\\cup\b", "∪"),
        (r"\\Rightarrow\b", "⇒"), (r"\\rightarrow\b", "→"), (r"\\implies\b", "⇒"),
        (r"\\iff\b", "⇔"), (r"\\to\b", "→"), (r"\\infty\b", "∞"),
        (r"\\cdot\b", "·"), (r"\\theta\b", "θ"), (r"\\alpha\b", "α"),
        (r"\\beta\b", "β"), (r"\\Delta\b", "Δ"),
    ]
    for pattern, rep in latex_map:
        s = re.sub(pattern, rep, s)

    s = re.sub(r"\\dot\{([^{}]+)\}", r"\1'", s)
    s = re.sub(r"\\ddot\{([^{}]+)\}", r"\1''", s)
    s = re.sub(r"\\text\{([^{}]+)\}", r"\1", s)
    s = re.sub(r"\\mathrm\{([^{}]+)\}", r"\1", s)
    s = re.sub(r"\\mathbf\{([^{}]+)\}", r"<b>\1</b>", s)
    s = re.sub(r"\\frac\{([^{}]+)\}\{([^{}]+)\}", r"(\1 / \2)", s)
    s = re.sub(r"\\dfrac\{([^{}]+)\}\{([^{}]+)\}", r"(\1 / \2)", s)
    s = re.sub(r"\\sqrt\{([^{}]+)\}", r"√(\1)", s)
    s = re.sub(r"\\sqrt\b", "√", s)
    s = re.sub(r"\^\{([^{}]+)\}", r"<sup>\1</sup>", s)
    s = re.sub(r"\^([a-zA-Z0-9]+)", r"<sup>\1</sup>", s)
    s = re.sub(r"_\{([^{}]+)\}", r"<sub>\1</sub>", s)
    s = re.sub(r"_([a-zA-Z0-9]+)", r"<sub>\1</sub>", s)

    # Convert markdown formatting to ReportLab tags
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(?<!\*)\*([^\*\n]+?)\*(?!\*)", r"<i>\1</i>", s)

    # Clean up raw LaTeX layout commands
    s = re.sub(r"\\begin\{cases\}([\s\S]*?)\\end\{cases\}", lambda m: m.group(1).replace(r"\\", "<br/>&nbsp;&nbsp;"), s)
    s = re.sub(r"\\(?:displaystyle|noindent|par|vspace\{[^}]*\}|hspace\*?\{[^}]*\}|needspace\{[^}]*\}|nopagebreak)\b", "", s)
    s = s.replace(r"\quad", " &nbsp; ").replace(r"\qquad", " &nbsp;&nbsp; ").replace(r"\enspace", " ")

    # Preserve and format linebreaks
    s = s.replace(r"\n", "\n")
    s = s.replace("\n\n", "<br/><br/>").replace("\n", "<br/>")

    s = s.replace("$$", "").replace("$", "")
    s = s.replace("&", "&amp;")
    s = s.replace("&amp;lt;", "<").replace("&amp;gt;", ">")
    s = re.sub(r"&amp;([a-zA-Z]+);", r"&\1;", s)
    # Ensure ReportLab tags like <b> and <i> don't stay escaped as &lt;b&gt;
    s = s.replace("&amp;lt;b&amp;gt;", "<b>").replace("&amp;lt;/b&amp;gt;", "</b>")
    s = s.replace("&amp;lt;i&amp;gt;", "<i>").replace("&amp;lt;/i&amp;gt;", "</i>")
    s = s.replace("&amp;lt;br/&amp;gt;", "<br/>")
    s = s.replace("&amp;lt;sup&amp;gt;", "<sup>").replace("&amp;lt;/sup&amp;gt;", "</sup>")
    s = s.replace("&amp;lt;sub&amp;gt;", "<sub>").replace("&amp;lt;/sub&amp;gt;", "</sub>")
    return s

class ExamCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pages = []
        self.year_level = "Year 10 Maths"
        self.school_name = "DA Tuition"

    def showPage(self):
        self.pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        page_count = len(self.pages)
        for page in self.pages:
            self.__dict__.update(page)
            self.draw_header_footer(page_count)
            super().showPage()
        super().save()

    def draw_header_footer(self, page_count):
        self.saveState()
        self.setFont("Times-Roman", 9)
        self.setFillColor(colors.HexColor("#333333"))

        if self._pageNumber > 1:
            self.drawString(42.5, 841.89 - 30, self.year_level)
            self.drawRightString(595.28 - 42.5, 841.89 - 30, self.school_name)
            self.setStrokeColor(colors.HexColor("#CCCCCC"))
            self.setLineWidth(0.5)
            self.line(42.5, 841.89 - 34, 595.28 - 42.5, 841.89 - 34)

        page_str = f"{self._pageNumber}"
        self.drawCentredString(595.28 / 2.0, 24, page_str)
        self.restoreState()

def generate_reportlab_worksheet_pdf(
    title: str,
    year_level: str,
    topic: str,
    questions: List[Dict[str, Any]],
    include_solutions: bool = True,
    term: Optional[int] = None,
    week: Optional[int] = None,
    sheet_type: str = "Homework",
    set_number: Optional[int] = 1
) -> bytes:
    """ReportLab fallback generator using serif font (Times-Roman) with exact Bonnyrigg margins, Subtopic Sets, and Answers section."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=42.5,
        leftMargin=42.5,
        topMargin=54,
        bottomMargin=54
    )

    styles = getSampleStyleSheet()
    story = []

    subject_clean = f"{year_level} Maths"
    clean_topic = clean_worksheet_topic_title(topic)
    groups = group_questions_by_subtopic(questions)

    if str(sheet_type).strip().lower() == "homework":
        set_str = f" Set {set_number if set_number else 1}"
        title_line = f"{clean_topic} — Homework{set_str}"
        sheet_type_label = f"Homework{set_str}"
    else:
        set_str = f" Set {set_number}" if (set_number and set_number > 1) else ""
        title_line = f"{clean_topic} — {sheet_type}{set_str}"
        sheet_type_label = f"{sheet_type}{set_str}"

    row1_style = ParagraphStyle(
        'BHeaderRow1',
        parent=styles['Normal'],
        fontName='Times-Bold',
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#000000")
    )

    row2_style = ParagraphStyle(
        'BHeaderRow2',
        parent=styles['Normal'],
        fontName='Times-Bold',
        fontSize=13,
        leading=16,
        textColor=colors.HexColor("#000000")
    )

    row3_style = ParagraphStyle(
        'BHeaderRow3',
        parent=styles['Normal'],
        fontName='Times-Bold',
        fontSize=14,
        leading=17,
        textColor=colors.HexColor("#000000")
    )

    meta_style = ParagraphStyle(
        'BMetaStyle',
        parent=styles['Normal'],
        fontName='Times-Roman',
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#333333")
    )

    section_hdr_style = ParagraphStyle(
        'BSectionHdr',
        parent=styles['Normal'],
        fontName='Times-Bold',
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#000000"),
        spaceBefore=10,
        spaceAfter=3
    )

    sol_hdr_style = ParagraphStyle(
        'BSolHdr',
        parent=styles['Normal'],
        fontName='Times-Bold',
        fontSize=13,
        leading=16,
        alignment=1,
        textColor=colors.HexColor("#000000")
    )

    q_text_style = ParagraphStyle(
        'BQText',
        parent=styles['Normal'],
        fontName='Times-Roman',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#000000")
    )

    ans_text_style = ParagraphStyle(
        'BAnsText',
        parent=styles['Normal'],
        fontName='Times-Roman',
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#000000")
    )

    step_text_style = ParagraphStyle(
        'BStepText',
        parent=styles['Normal'],
        fontName='Times-Italic',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#444444")
    )

    left_cell = [
        Paragraph(f"<b>{subject_clean}</b>", row1_style),
        Spacer(1, 4),
    ]
    if term and week:
        left_cell.extend([
            Paragraph(f"<b>Term {term} &nbsp;&nbsp; Week {week}</b>", row2_style),
            Spacer(1, 3),
        ])
    elif term:
        left_cell.extend([
            Paragraph(f"<b>Term {term}</b>", row2_style),
            Spacer(1, 3),
        ])
    elif week:
        left_cell.extend([
            Paragraph(f"<b>Week {week}</b>", row2_style),
            Spacer(1, 3),
        ])
    left_cell.append(Paragraph(f"<b>{clean_topic}</b>", row2_style))
    left_cell.append(Spacer(1, 2))
    left_cell.append(Paragraph(f"<b>{sheet_type_label}</b>", row3_style))

    logo_element = get_proportional_logo(target_height=75.0, max_width=110.0)
    right_cell = [logo_element] if logo_element else [Paragraph("<b>DA TUITION</b>", row1_style)]

    banner_table = Table([[left_cell, right_cell]], colWidths=[385, 125])
    banner_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(banner_table)
    story.append(Spacer(1, 10))

    meta_table = Table([
        [
            Paragraph("<b>Student Name:</b> ____________________________________", meta_style),
            Paragraph("<b>Class:</b> ____________________", meta_style)
        ]
    ], colWidths=[325, 185])
    meta_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 4))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.black, spaceAfter=10))

    sub_sec_style = ParagraphStyle(
        'BSubSectionHdr',
        parent=styles['Normal'],
        fontName='Times-Bold',
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#1A237E"),
        spaceBefore=7,
        spaceAfter=3
    )

    # ========================================================
    # 1. QUESTIONS SECTION (Categorized by Subtopic Sets & Sections)
    # ========================================================
    for grp in groups:
        story.append(Paragraph(grp["set_title"], section_hdr_style))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#333333"), spaceAfter=8))
        sections = get_tiered_sections_for_questions(grp["questions"])

        for sec in sections:
            story.append(Paragraph(f"<b>{sec['section_title']}</b>", sub_sec_style))
            for q in sec["questions"]:
                item_label = q.get('item_label', str(q.get('num', '')))
                raw_text = q.get('text', '')
                options = q.get('options')
                if options and isinstance(options, dict):
                    raw_text = strip_mc_options_from_text(raw_text)
                marks = int(q.get('marks', 1))
                marks_str = f"({marks} mark{'s' if marks > 1 else ''})"
                formatted_q_text = format_math_for_reportlab(raw_text)

                # Two-column layout to guarantee marks align strictly on right edge without breaking
                q_row_table = Table(
                    [[
                        Paragraph(f"<b>{item_label}.</b> {formatted_q_text}", q_text_style),
                        Paragraph(f"<b>{marks_str}</b>", ParagraphStyle('RMark', parent=q_text_style, alignment=2))
                    ]],
                    colWidths=[430, 80]
                )
                q_row_table.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 0),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                    ('TOPPADDING', (0, 0), (-1, -1), 0),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
                ]))
                story.append(q_row_table)
                story.append(Spacer(1, 8))
            story.append(Spacer(1, 4))

    if include_solutions:
        # ========================================================
        # 2. PLAIN ANSWERS SECTION (Quick-check for students)
        # ========================================================
        story.append(PageBreak())
        story.append(Spacer(1, 10))
        story.append(Paragraph("ANSWERS", sol_hdr_style))
        story.append(Spacer(1, 4))
        story.append(Paragraph(f"{subject_clean} • {clean_topic} ({sheet_type_label})", meta_style))
        story.append(Spacer(1, 6))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1A237E"), spaceAfter=12))

        for grp in groups:
            story.append(Paragraph(grp["set_title"], section_hdr_style))
            story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#333333"), spaceAfter=6))
            sections = get_tiered_sections_for_questions(grp["questions"])

            for sec in sections:
                story.append(Paragraph(f"<b>{sec['section_title']}</b>", sub_sec_style))
                for q in sec["questions"]:
                    item_label = q.get('item_label', str(q.get('num', '')))
                    ans = format_math_for_reportlab(q.get('correct_answer', ''))
                    story.append(Paragraph(f"<b>{item_label}.</b> &nbsp; {ans}", ans_text_style))
                    story.append(Spacer(1, 4))
                story.append(Spacer(1, 4))
            story.append(Spacer(1, 6))

        # ========================================================
        # 3. FULLY WORKED SOLUTIONS & MARKING KEY SECTION
        # ========================================================
        story.append(PageBreak())
        story.append(Spacer(1, 10))
        story.append(Paragraph("DA TUITION — FULLY WORKED SOLUTIONS & MARKING KEY", sol_hdr_style))
        story.append(Spacer(1, 4))
        story.append(Paragraph(f"{subject_clean} • {clean_topic} ({sheet_type_label})", meta_style))
        story.append(Spacer(1, 6))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1A237E"), spaceAfter=12))

        for grp in groups:
            story.append(Paragraph(grp["set_title"], section_hdr_style))
            story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#333333"), spaceAfter=8))
            sections = get_tiered_sections_for_questions(grp["questions"])

            for sec in sections:
                story.append(Paragraph(f"<b>{sec['section_title']}</b>", sub_sec_style))
                for q in sec["questions"]:
                    item_label = q.get('item_label', str(q.get('num', '')))
                    ans = format_math_for_reportlab(q.get('correct_answer', ''))
                    working = format_math_for_reportlab(q.get('solution_steps', ''))

                    sol_elements = [
                        Paragraph(f"<b>{item_label}.</b> Final Answer: <b><font color='#0D47A1'>{ans}</font></b>", q_text_style),
                        Spacer(1, 2)
                    ]
                    if working:
                        sol_elements.append(Paragraph(f"<i>Working Steps:</i> {working}", ParagraphStyle('S', parent=q_text_style, fontSize=9, textColor=colors.HexColor("#263238"))))
                    sol_elements.append(Spacer(1, 8))
                    story.append(KeepTogether(sol_elements))
                story.append(Spacer(1, 4))

    def make_canvas(*args, **kwargs):
        c = ExamCanvas(*args, **kwargs)
        c.year_level = subject_clean
        c.school_name = f"{sheet_type_label} - DA TUITION"
        return c

    doc.build(story, canvasmaker=make_canvas)
    return buffer.getvalue()

def generate_worksheet_pdf(
    title: str,
    year_level: str,
    topic: str,
    questions: List[Dict[str, Any]],
    include_solutions: bool = True,
    term: Optional[int] = None,
    week: Optional[int] = None,
    sheet_type: str = "Homework",
    set_number: Optional[int] = 1,
    font_theme: str = "charter"
) -> bytes:
    """
    Top-level worksheet PDF generator.
    Attempts native LaTeX compilation first (matching Bonnyrigg Latin Modern Roman font).
    Falls back to ReportLab serif engine if pdflatex is absent.
    """
    latex_bytes = generate_latex_worksheet_pdf(
        title=title,
        year_level=year_level,
        topic=topic,
        questions=questions,
        include_solutions=include_solutions,
        term=term,
        week=week,
        sheet_type=sheet_type,
        set_number=set_number,
        font_theme=font_theme
    )
    if latex_bytes:
        return latex_bytes
    return generate_reportlab_worksheet_pdf(
        title=title,
        year_level=year_level,
        topic=topic,
        questions=questions,
        include_solutions=include_solutions,
        term=term,
        week=week,
        sheet_type=sheet_type,
        set_number=set_number
    )

def generate_worksheet_docx(
    title: str,
    year_level: str,
    topic: str,
    questions: List[Dict[str, Any]],
    include_solutions: bool = True,
    term: Optional[int] = None,
    week: Optional[int] = None,
    sheet_type: str = "Homework",
    set_number: Optional[int] = 1
) -> Optional[bytes]:
    """Generates an editable Microsoft Word (.docx) worksheet matching the authentic LaTeX layout."""
    tex_str = build_latex_worksheet_source(
        title=title,
        year_level=year_level,
        topic=topic,
        questions=questions,
        include_solutions=include_solutions,
        term=term,
        week=week,
        sheet_type=sheet_type,
        set_number=set_number,
        has_logo=True
    )
    return docx_generator.latex_to_docx(tex_str)

# Answer Sheet Template.pdf Grid Geometry (Page dimensions: 540 x 780 pt)
ANSWER_SHEET_P1_ROWS = [
    687.91, 650.42, 612.93, 575.44, 538.31, 500.82, 463.32, 425.83, 388.83,
    351.34, 313.84, 276.35, 239.22, 201.73, 164.24, 126.75, 88.66, 51.17
]
ANSWER_SHEET_P2_ROWS = [
    711.31, 673.82, 636.33, 598.84, 561.71, 524.21, 486.72, 449.23, 412.23,
    374.73, 337.24, 299.75, 262.62, 225.13, 187.64, 150.14, 112.06, 74.38
]
ANSWER_SHEET_COLS = [
    {"qn_x": 36.1, "ans_x": 123.6, "max_w": 108.0},
    {"qn_x": 209.8, "ans_x": 297.3, "max_w": 108.0},
    {"qn_x": 383.7, "ans_x": 471.2, "max_w": 108.0}
]

def _auto_wrap_math(text: str) -> str:
    """Wraps mathematical text in $ if it contains math commands but lacks delimiters."""
    t = text.strip()
    if not t:
        return ""
    math_indicators = ["\\", "^", "_", "{", "}"]
    if any(ind in t for ind in math_indicators) and "$" not in t and r"\[" not in t:
        return f"${t}$"
    return t

def format_latex_answer_for_cell(ans: str) -> str:
    """
    Formats an answer string for publication-quality rendering within an answer sheet grid cell.
    1. Preserves and cleans LaTeX math expressions.
    2. Formats multi-part answers (e.g. (a) ... (b) ...) into a clean 2-line tabular stack.
    3. Ensures valid math mode wrapping and sanitization.
    """
    if not ans:
        return ""
    s = str(ans).strip()
    s = s.replace("$$", "$")
    s = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", s)

    sub_pat = re.compile(r"(?:(?<=\A)|(?<=[\s,;]))\(([a-h]|i{1,3}|iv|v|vi)\)\s*", re.IGNORECASE)
    matches = list(sub_pat.finditer(s))
    if len(matches) >= 2:
        raw_items = []
        for i in range(len(matches)):
            lbl = matches[i].group(1).lower()
            start = matches[i].end()
            end = matches[i+1].start() if i + 1 < len(matches) else len(s)
            val = s[start:end].strip().rstrip(";,").strip()
            raw_items.append((lbl, val))

        # Merge empty parent parts like (a) followed immediately by (i) -> (a)(i)
        merged = []
        i = 0
        while i < len(raw_items):
            lbl, val = raw_items[i]
            if not val and i + 1 < len(raw_items):
                next_lbl, next_val = raw_items[i+1]
                merged.append((f"{lbl})({next_lbl}", next_val))
                i += 2
            else:
                merged.append((lbl, val))
                i += 1

        chunks = []
        for lbl, val in merged:
            val_clean = sanitize_for_latex(_auto_wrap_math(val))
            chunks.append(f"\\text{{({lbl})}}\\ {val_clean}")

        if len(chunks) == 2:
            return "\\begin{tabular}{@{}c@{}}\n" + f"{chunks[0]} \\\\\n{chunks[1]}" + "\n\\end{tabular}"
        elif len(chunks) == 3:
            return "\\begin{tabular}{@{}c@{}}\n" + f"{chunks[0]} \\quad {chunks[1]} \\\\\n{chunks[2]}" + "\n\\end{tabular}"
        elif len(chunks) >= 4:
            return "\\begin{tabular}{@{}c@{}}\n" + f"{chunks[0]} \\quad {chunks[1]} \\\\\n{chunks[2]} \\quad {chunks[3]}" + "\n\\end{tabular}"

    return sanitize_for_latex(_auto_wrap_math(s))

def build_latex_answer_sheet_overlay_source(
    labels: List[str],
    answers: Optional[List[str]],
    total_pages: int,
    is_teacher: bool,
    term: Optional[int],
    week: Optional[int]
) -> str:
    """Builds LaTeX source with TikZ for exact coordinate overlay onto Answer Sheet Template.pdf."""
    tex_lines = [
        r"\documentclass[10pt]{article}",
        r"\usepackage[paperwidth=540pt, paperheight=780pt, margin=0pt]{geometry}",
        r"\usepackage{amsmath,amssymb,amsfonts}",
        r"\usepackage{adjustbox}",
        r"\usepackage{tikz}",
        r"\usepackage{xcolor}",
        r"\pagestyle{empty}",
        r"\definecolor{danavy}{RGB}{15, 34, 64}",
        r"\definecolor{dagold}{RGB}{179, 134, 0}",
        r"\begin{document}"
    ]

    for page_idx in range(total_pages):
        page_num = page_idx + 1
        row_coords = ANSWER_SHEET_P1_ROWS if page_num == 1 else ANSWER_SHEET_P2_ROWS

        tex_lines.append(r"\noindent\begin{tikzpicture}[x=1pt, y=1pt]")
        tex_lines.append(r"  \clip (0,0) rectangle (540,780);")

        # Header metadata
        if is_teacher:
            tex_lines.append(r"  \node[anchor=west, text=dagold, font=\bfseries\small] at (132, 742) {[ TEACHER ANSWER KEY ]};")

        if term is not None:
            tex_lines.append(f"  \\node[anchor=west, text=black, font=\\bfseries\\small] at (305, 735) {{{term}}};")
        if week is not None:
            tex_lines.append(f"  \\node[anchor=west, text=black, font=\\bfseries\\small] at (365, 735) {{{week}}};")
        tex_lines.append(f"  \\node[anchor=west, text=black, font=\\small] at (498, 757) {{{page_num} / {total_pages}}};")

        start_q = page_idx * 54
        page_labels = labels[start_q : start_q + 54]
        page_answers = answers[start_q : start_q + 54] if answers else None

        for idx, q_label in enumerate(page_labels):
            col_idx = idx // 18
            row_idx = idx % 18
            y_top = row_coords[row_idx]
            y_qn = y_top - 14.20
            y_ans = y_top - 17.00
            col_info = ANSWER_SHEET_COLS[col_idx]

            # Prefilled Question Label centered inside box
            lbl_clean = sanitize_for_latex(str(q_label))
            lbl_font = r"\bfseries\normalsize" if len(str(q_label)) <= 3 else r"\bfseries\small"
            tex_lines.append(f"  \\node[anchor=center, text=black, font={lbl_font}] at ({col_info['qn_x']}, {y_qn:.2f}) {{{lbl_clean}}};")

            # Prefilled Answer if teacher copy
            if is_teacher and page_answers and idx < len(page_answers) and page_answers[idx]:
                cell_ans = format_latex_answer_for_cell(page_answers[idx])
                if cell_ans:
                    tex_lines.append(
                        f"  \\node[anchor=center, text=danavy] at ({col_info['ans_x']}, {y_ans:.2f}) {{"
                        f"\\begin{{adjustbox}}{{max width=105pt, max height=24pt, center}} {cell_ans} \\end{{adjustbox}}}};"
                    )

        tex_lines.append(r"\end{tikzpicture}")
        if page_num < total_pages:
            tex_lines.append(r"\newpage")

    tex_lines.append(r"\end{document}")
    return "\n".join(tex_lines)

def clean_answer_for_answer_sheet(ans: str) -> str:
    """Cleans LaTeX math formatting for clear and compact presentation on the answer sheet grid."""
    if not ans:
        return ""
    s = str(ans).strip()
    s = s.replace("$", "")
    s = re.sub(r"\\(?:text|mathrm|mathbf|textit)\{([^{}]+)\}", r"\1", s)
    s = s.replace(r"^\circ", "°").replace(r"\circ", "°").replace(r"\degree", "°")
    s = s.replace(r"\times", "×").replace(r"\div", "÷").replace(r"\pm", "±")
    s = s.replace(r"\le", "≤").replace(r"\ge", "≥").replace(r"\ne", "≠")
    s = s.replace(r"\approx", "≈").replace(r"\pi", "π")
    s = s.replace(r"\triangle", "△").replace(r"\angle", "∠")
    s = s.replace(r"\therefore", "∴").replace(r"\parallel", "∥").replace(r"\perp", "⊥")
    s = s.replace(r"\sim", "∼").replace(r"\equiv", "≡").replace(r"\cong", "≅")
    s = re.sub(r"\\(?:dfrac|frac)\{([^{}]+)\}\{([^{}]+)\}", r"\1/\2", s)
    s = s.replace(r"\_", "_").replace(r"\%", "%")
    s = s.replace("\\", "")
    return s.strip()

def generate_answer_sheet_pdf(
    question_labels: Optional[List[str]] = None,
    answers: Optional[List[str]] = None,
    num_questions: int = 40,
    term: Optional[int] = None,
    week: Optional[int] = None,
    is_teacher: bool = False,
    items: Optional[List[Dict[str, Any]]] = None
) -> bytes:
    """
    Generates official DA Tuition Answer Sheet (Student Blank or Teacher Key).
    If questions contain items requiring diagrams/sketches or mathematical proofs/reasoning,
    it dynamically generates an adaptive layout providing dedicated sketch canvases (100pt)
    and ruled reasoning boxes (60pt) alongside compact items.
    Otherwise, if all items are compact and Answer Sheet Template.pdf exists,
    it overlays question labels directly onto the template's gold crest grid.
    """
    if question_labels and len(question_labels) > 0:
        labels = [str(l).strip() for l in question_labels]
    else:
        labels = [str(i) for i in range(1, num_questions + 1)]

    # Check whether any item requires dedicated drawing or reasoning space
    has_adaptive_content = False
    if items:
        has_adaptive_content = any(it.get("type") in ["diagram", "reasoning"] for it in items)

    # If adaptive layout is needed, build using dynamic ReportLab engine
    if has_adaptive_content and items:
        return _build_adaptive_answer_sheet_pdf(
            items=items,
            term=term,
            week=week,
            is_teacher=is_teacher
        )

    total_qs = len(labels)
    total_pages = 2 if total_qs > 54 else 1

    template_paths = [
        os.path.join(os.path.dirname(__file__), "Answer Sheet Template.pdf"),
        os.path.join(os.getcwd(), "Answer Sheet Template.pdf"),
        "/Users/bunsea/Documents/Homework Marking/Answer Sheet Template.pdf"
    ]
    template_file = None
    for tp in template_paths:
        if os.path.exists(tp):
            template_file = tp
            break

    if template_file:
        # 1. Primary: High-fidelity LaTeX math overlay
        pdflatex_bin = find_pdflatex()
        if pdflatex_bin:
            tmp_dir = tempfile.mkdtemp()
            try:
                overlay_tex = build_latex_answer_sheet_overlay_source(
                    labels=labels,
                    answers=answers,
                    total_pages=total_pages,
                    is_teacher=is_teacher,
                    term=term,
                    week=week
                )
                tex_path = os.path.join(tmp_dir, "overlay.tex")
                with open(tex_path, "w", encoding="utf-8") as f:
                    f.write(overlay_tex)

                subprocess.run(
                    [pdflatex_bin, "-interaction=nonstopmode", "overlay.tex"],
                    cwd=tmp_dir,
                    capture_output=True,
                    check=False
                )

                overlay_pdf_path = os.path.join(tmp_dir, "overlay.pdf")
                if os.path.exists(overlay_pdf_path):
                    tpl_reader = PdfReader(template_file)
                    overlay_reader = PdfReader(overlay_pdf_path)
                    writer = PdfWriter()

                    for page_idx in range(total_pages):
                        tpl_page = tpl_reader.pages[min(page_idx, len(tpl_reader.pages) - 1)]
                        if page_idx < len(overlay_reader.pages):
                            tpl_page.merge_page(overlay_reader.pages[page_idx])
                        writer.add_page(tpl_page)

                    out_buf = io.BytesIO()
                    writer.write(out_buf)
                    res_bytes = out_buf.getvalue()
                    if res_bytes and res_bytes.startswith(b"%PDF"):
                        return res_bytes
            except Exception:
                pass
            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)

        # 2. Secondary fallback: ReportLab canvas overlay on template_file
        try:
            tpl_reader = PdfReader(template_file)
            writer = PdfWriter()

            for page_idx in range(total_pages):
                tpl_page = tpl_reader.pages[min(page_idx, len(tpl_reader.pages) - 1)]
                packet = io.BytesIO()
                can = canvas.Canvas(packet, pagesize=(540, 780))

                page_num = page_idx + 1
                row_coords = ANSWER_SHEET_P1_ROWS if page_num == 1 else ANSWER_SHEET_P2_ROWS

                # Header text
                if page_num == 1:
                    if term is not None:
                        can.setFont("Helvetica-Bold", 9)
                        can.drawString(305, 735, str(term))
                    if week is not None:
                        can.setFont("Helvetica-Bold", 9)
                        can.drawString(365, 735, str(week))
                    can.setFont("Helvetica", 9)
                    can.drawString(498, 757, f"{page_num} / {total_pages}")

                    if is_teacher:
                        can.setFont("Helvetica-Bold", 9)
                        can.setFillColor(colors.HexColor("#B38600"))
                        can.drawString(132, 742, "[ TEACHER ANSWER KEY ]")
                        can.setFillColor(colors.black)
                else:
                    can.setFont("Helvetica", 9)
                    can.drawString(498, 757, f"{page_num} / {total_pages}")
                    if is_teacher:
                        can.setFont("Helvetica-Bold", 9)
                        can.setFillColor(colors.HexColor("#B38600"))
                        can.drawString(132, 742, "[ TEACHER ANSWER KEY ]")
                        can.setFillColor(colors.black)

                start_q = page_idx * 54
                page_labels = labels[start_q : start_q + 54]
                page_answers = answers[start_q : start_q + 54] if answers else None

                for idx, q_label in enumerate(page_labels):
                    col_idx = idx // 18
                    row_idx = idx % 18
                    y_top = row_coords[row_idx]
                    y_base = y_top - 20.5
                    col_info = ANSWER_SHEET_COLS[col_idx]

                    # Prefilled Question Label
                    can.setFont("Helvetica-Bold", 10 if len(str(q_label)) <= 3 else 8.5)
                    can.setFillColor(colors.black)
                    can.drawCentredString(col_info["qn_x"], y_base, str(q_label))

                    # Prefilled Answer if teacher copy
                    if is_teacher and page_answers and idx < len(page_answers) and page_answers[idx]:
                        clean_ans = clean_answer_for_answer_sheet(page_answers[idx])
                        if clean_ans:
                            font_sz = 9.5
                            while can.stringWidth(clean_ans, "Helvetica-Bold", font_sz) > col_info["max_w"] and font_sz > 6.0:
                                font_sz -= 0.5
                            can.setFont("Helvetica-Bold", font_sz)
                            can.setFillColor(colors.HexColor("#0F2240"))
                            can.drawCentredString(col_info["ans_x"], y_base, clean_ans)
                            can.setFillColor(colors.black)

                can.save()
                packet.seek(0)
                overlay_reader = PdfReader(packet)
                writer.add_page(tpl_page)
                writer.pages[-1].merge_page(overlay_reader.pages[0])

            out_buf = io.BytesIO()
            writer.write(out_buf)
            res_bytes = out_buf.getvalue()
            if res_bytes and res_bytes.startswith(b"%PDF"):
                return res_bytes
        except Exception:
            pass

    # ReportLab dynamic standard grid fallback
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=24,
        leftMargin=24,
        topMargin=24,
        bottomMargin=24
    )

    styles = getSampleStyleSheet()
    ans_style = ParagraphStyle(
        'AnsStyle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=9.5,
        alignment=1, # Center
        textColor=colors.HexColor("#0F2240")
    )
    story = []

    logo_element = get_proportional_logo(target_height=48.0, max_width=70.0)
    badge = " [TEACHER ANSWER KEY]" if is_teacher else ""
    tw_sub = f"Term: <b>{term}</b> &nbsp; Week: <b>{week}</b>" if (term and week) else "Term: ____ &nbsp; Week: ____"

    rows_per_col = 22
    slots_per_page = rows_per_col * 3 # 66 items per page
    num_pages_needed = max(1, (len(labels) + slots_per_page - 1) // slots_per_page)

    for p_idx in range(num_pages_needed):
        p_num = p_idx + 1
        page_hdr_data = [
            [
                logo_element if logo_element else Paragraph("<b>DA TUITION</b>", styles['Normal']),
                Paragraph(f"<b>Answer Sheet{badge}</b><br/>Name: ________________________", styles['Normal']),
                Paragraph(f"Class Time: ____________<br/>{tw_sub}", styles['Normal']),
                Paragraph(f"Page <b>{p_num} / {num_pages_needed}</b>", styles['Normal'])
            ]
        ]
        hdr_table = Table(page_hdr_data, colWidths=[75, 195, 190, 87])
        hdr_table.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(hdr_table)
        story.append(Spacer(1, 8))

        p_start = p_idx * slots_per_page
        p_labels = labels[p_start : p_start + slots_per_page]
        p_answers = (answers[p_start : p_start + slots_per_page] if answers else [])

        while len(p_labels) < slots_per_page:
            p_labels.append("")
        while len(p_answers) < slots_per_page:
            p_answers.append("")

        grid_data = [["Qn", "Answer", "Qn", "Answer", "Qn", "Answer"]]

        for r in range(rows_per_col):
            q1 = p_labels[r] if r < len(p_labels) else ""
            raw_a1 = clean_answer_for_answer_sheet(p_answers[r]) if (is_teacher and r < len(p_answers)) else ""
            a1 = Paragraph(raw_a1, ans_style) if raw_a1 else ""

            q2 = p_labels[r + rows_per_col] if (r + rows_per_col) < len(p_labels) else ""
            raw_a2 = clean_answer_for_answer_sheet(p_answers[r + rows_per_col]) if (is_teacher and (r + rows_per_col) < len(p_answers)) else ""
            a2 = Paragraph(raw_a2, ans_style) if raw_a2 else ""

            q3 = p_labels[r + 2 * rows_per_col] if (r + 2 * rows_per_col) < len(p_labels) else ""
            raw_a3 = clean_answer_for_answer_sheet(p_answers[r + 2 * rows_per_col]) if (is_teacher and (r + 2 * rows_per_col) < len(p_answers)) else ""
            a3 = Paragraph(raw_a3, ans_style) if raw_a3 else ""

            grid_data.append([q1, a1, q2, a2, q3, a3])

        col_widths = [35, 147, 35, 147, 35, 148]
        grid_table = Table(grid_data, colWidths=col_widths, rowHeights=[18] + [28] * rows_per_col)
        grid_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#EEEEEE")),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8.5),
        ]))
        story.append(grid_table)

        if p_num < num_pages_needed:
            story.append(PageBreak())

    doc.build(story)
    return buffer.getvalue()


def _build_adaptive_answer_sheet_pdf(
    items: List[Dict[str, Any]],
    term: Optional[int] = None,
    week: Optional[int] = None,
    is_teacher: bool = False
) -> bytes:
    """
    Renders an adaptive DA Tuition Answer Sheet with tailored workspaces:
    - Compact items: rendered in efficient 3-column rows
    - Reasoning items: rendered in dedicated wide boxes with ruled working rows
    - Diagram items: rendered in generous boxed sketch canvases (height 100pt)
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=24,
        leftMargin=24,
        topMargin=24,
        bottomMargin=24
    )

    styles = getSampleStyleSheet()
    ans_style = ParagraphStyle(
        'AdaptiveAnsStyle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=10.5,
        alignment=1, # Center
        textColor=colors.HexColor("#0F2240")
    )
    teacher_exp_style = ParagraphStyle(
        'TeacherExpStyle',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=8.5,
        leading=11.0,
        textColor=colors.HexColor("#0F2240")
    )
    prompt_style = ParagraphStyle(
        'PromptStyle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.0,
        leading=10.0,
        textColor=colors.HexColor("#555555")
    )

    badge = " [TEACHER ANSWER KEY]" if is_teacher else ""
    tw_sub = f"Term: <b>{term}</b> &nbsp; Week: <b>{week}</b>" if (term and week) else "Term: ____ &nbsp; Week: ____"
    logo_element = get_proportional_logo(target_height=42.0, max_width=70.0)

    # Group items into adaptive chunks and partition across pages
    # Available page height = ~794pt - margins(48pt) - header(55pt) = ~690pt
    MAX_PAGE_HEIGHT = 680.0
    pages_blocks: List[List[Any]] = [[]]
    cur_page_h = 0.0

    idx = 0
    while idx < len(items):
        item = items[idx]
        itype = item.get("type", "compact")

        if itype == "compact":
            # Collect consecutive compact items up to 9 items (3 rows of 3 cols)
            compact_group = []
            while idx < len(items) and items[idx].get("type") == "compact" and len(compact_group) < 9:
                compact_group.append(items[idx])
                idx += 1

            rows_count = (len(compact_group) + 2) // 3
            block_h = 18.0 + rows_count * 28.0 + 8.0

            if cur_page_h + block_h > MAX_PAGE_HEIGHT and pages_blocks[-1]:
                pages_blocks.append([])
                cur_page_h = 0.0

            # Build compact sub-table
            grid_data = [["Qn", "Answer", "Qn", "Answer", "Qn", "Answer"]]
            padded = compact_group + [{"label": "", "answer": ""}] * (rows_count * 3 - len(compact_group))
            for r in range(rows_count):
                row = []
                for c in range(3):
                    cell_it = padded[r * 3 + c]
                    c_lbl = cell_it.get("label", "")
                    raw_ans = clean_answer_for_answer_sheet(cell_it.get("answer", "")) if is_teacher else ""
                    c_ans = Paragraph(raw_ans, ans_style) if raw_ans else ""
                    row.extend([c_lbl, c_ans])
                grid_data.append(row)

            col_widths = [35, 147, 35, 147, 35, 148]
            t = Table(grid_data, colWidths=col_widths, rowHeights=[18.0] + [28.0] * rows_count)
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#EEEEEE")),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8.5),
            ]))
            pages_blocks[-1].append(t)
            pages_blocks[-1].append(Spacer(1, 8))
            cur_page_h += block_h

        elif itype == "reasoning":
            block_h = 75.0
            if cur_page_h + block_h > MAX_PAGE_HEIGHT and pages_blocks[-1]:
                pages_blocks.append([])
                cur_page_h = 0.0

            lbl = item.get("label", "")
            raw_ans = clean_answer_for_answer_sheet(item.get("answer", ""))
            header_cell = Paragraph(f"<b>Question {lbl}</b> — <i>Mathematical Reasoning & Proof</i>", styles['Normal'])

            if is_teacher and raw_ans:
                content_cell = Paragraph(f"<b>Model Proof / Justification:</b><br/>{raw_ans}", teacher_exp_style)
            else:
                content_cell = Paragraph(
                    "<font color='#B38600'>[ Working & Reasoning Space — state theorems, steps, and reasons ]</font><br/><br/>"
                    "____________________________________________________________________________________________<br/><br/>"
                    "____________________________________________________________________________________________",
                    prompt_style
                )

            t = Table([[header_cell], [content_cell]], colWidths=[547], rowHeights=[20.0, 52.0])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#F5F1EB")),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor("#B38600")),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('LEFTPADDING', (0, 0), (-1, -1), 8),
                ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ]))
            pages_blocks[-1].append(t)
            pages_blocks[-1].append(Spacer(1, 8))
            cur_page_h += block_h
            idx += 1

        elif itype == "diagram":
            block_h = 125.0
            if cur_page_h + block_h > MAX_PAGE_HEIGHT and pages_blocks[-1]:
                pages_blocks.append([])
                cur_page_h = 0.0

            lbl = item.get("label", "")
            raw_ans = clean_answer_for_answer_sheet(item.get("answer", ""))
            header_cell = Paragraph(f"<b>Question {lbl}</b> — <i>Diagram, Graph & Sketch Canvas</i>", styles['Normal'])

            if is_teacher and raw_ans:
                content_cell = Paragraph(
                    f"<b>Key Sketch Elements / Target Features:</b><br/>{raw_ans}<br/><br/>"
                    "<font color='#666666'><i>(Evaluate student's diagram: correct axis labels, coordinates, vertex, intercepts, curvature)</i></font>",
                    teacher_exp_style
                )
            else:
                content_cell = Paragraph(
                    "<font color='#0F2240'><b>[ Drawing & Construction Canvas ]</b> — draw with ruler, pencil, and label all key features.</font>",
                    prompt_style
                )

            t = Table([[header_cell], [content_cell]], colWidths=[547], rowHeights=[20.0, 100.0])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#EAEFF5")),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor("#0F2240")),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('LEFTPADDING', (0, 0), (-1, -1), 8),
                ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ]))
            pages_blocks[-1].append(t)
            pages_blocks[-1].append(Spacer(1, 8))
            cur_page_h += block_h
            idx += 1

    total_pages = len(pages_blocks)
    story: List[Any] = []

    for p_idx, page_flowables in enumerate(pages_blocks):
        p_num = p_idx + 1
        page_hdr_data = [
            [
                logo_element if logo_element else Paragraph("<b>DA TUITION</b>", styles['Normal']),
                Paragraph(f"<b>Answer Sheet{badge}</b><br/>Name: ________________________", styles['Normal']),
                Paragraph(f"Class Time: ____________<br/>{tw_sub}", styles['Normal']),
                Paragraph(f"Page <b>{p_num} / {total_pages}</b>", styles['Normal'])
            ]
        ]
        hdr_table = Table(page_hdr_data, colWidths=[75, 195, 190, 87])
        hdr_table.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(hdr_table)
        story.append(Spacer(1, 8))

        for fl in page_flowables:
            story.append(fl)

        if p_num < total_pages:
            story.append(PageBreak())

    doc.build(story)
    return buffer.getvalue()


def generate_blank_answer_sheet_pdf(
    question_labels: Optional[List[str]] = None,
    num_questions: int = 40,
    term: Optional[int] = None,
    week: Optional[int] = None,
    items: Optional[List[Dict[str, Any]]] = None
) -> bytes:
    """Generates official DA Tuition Student Blank Answer Sheet with prefilled question numbers."""
    return generate_answer_sheet_pdf(
        question_labels=question_labels,
        answers=None,
        num_questions=num_questions,
        term=term,
        week=week,
        is_teacher=False,
        items=items
    )

def generate_teacher_answer_sheet_pdf(
    question_labels: Optional[List[str]] = None,
    answers: Optional[List[str]] = None,
    num_questions: int = 40,
    term: Optional[int] = None,
    week: Optional[int] = None,
    items: Optional[List[Dict[str, Any]]] = None
) -> bytes:
    """Generates official DA Tuition Teacher Answer Sheet with prefilled question numbers AND answers."""
    return generate_answer_sheet_pdf(
        question_labels=question_labels,
        answers=answers,
        num_questions=num_questions,
        term=term,
        week=week,
        is_teacher=True,
        items=items
    )

def _format_correction_fraction(val_str: str) -> str:
    """Formats common fraction notation into clean Unicode fractions if applicable (e.g. 1/2 -> ½)."""
    if not val_str:
        return ""
    # Standard Latin-1 fractions supported by all fonts
    latin1_fracs = {"1/2": "½", "1/4": "¼", "3/4": "¾"}
    # Extended Unicode Number Forms
    ext_fracs = {
        "1/3": "⅓", "2/3": "⅔",
        "1/5": "⅕", "2/5": "⅖", "3/5": "⅗", "4/5": "⅘",
        "1/6": "⅙", "5/6": "⅚",
        "1/8": "⅛", "3/8": "⅜", "5/8": "⅝", "7/8": "⅞"
    }
    frac_map = dict(latin1_fracs)
    if HAS_UNICODE_FONT:
        frac_map.update(ext_fracs)

    s = str(val_str).strip()
    for frac, uni in frac_map.items():
        # Match standalone fraction or mixed numeral like "16 1/2"
        s = re.sub(rf'(?<=\b){re.escape(frac)}(?=\b)', uni, s)
        s = re.sub(rf'(?<=\d)\s*{re.escape(frac)}(?=\b)', f" {uni}", s)

    if not HAS_UNICODE_FONT:
        # If font does not support extended unicode fractions, revert to ASCII so it doesn't render missing boxes
        for frac, uni in ext_fracs.items():
            s = s.replace(uni, frac)

    return s


def generate_student_report_pdf(
    student_name: str,
    term_week_header: str,
    score: float,
    total_marks: float,
    accuracy_pct: float,
    mistakes: List[Dict[str, Any]],
    summary_text: str = "",
    class_name: str = "",
    concept_breakdown: Optional[List[Dict[str, Any]]] = None
) -> bytes:
    """
    Generates official DA Tuition Student Performance Breakdown Report matching the official template:
    - Top header: Crest logo on left, centered PERFORMANCE BREAKDOWN & Term/Week subtitle.
    - Horizontal divider rule.
    - STUDENT NAME: [left] and Student Name: [right].
    - CONCEPT MASTERY & DIAGNOSTIC BREAKDOWN (if concept_breakdown provided):
      Table mapping each concept area to designated homework questions, correct count, accuracy %, and Strength/Weakness status.
    - AREAS FOR CORRECTION: heading.
    - Bordered light-gray table listing question, status, and correct answers in parentheses.
    - Centered bottom summary: Accuracy Percentage: X% and Total Score: X out of Y.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=50,
        leftMargin=50,
        topMargin=40,
        bottomMargin=40
    )

    styles = getSampleStyleSheet()

    # Typography matching official Arial/Helvetica layout
    title_main_style = ParagraphStyle(
        'RepTitleMain',
        parent=styles['Heading1'],
        fontName=REPORT_FONT_BOLD,
        fontSize=13.5,
        leading=17,
        alignment=1, # Center
        textColor=colors.HexColor("#111827")
    )

    title_sub_style = ParagraphStyle(
        'RepTitleSub',
        parent=styles['Normal'],
        fontName=REPORT_FONT,
        fontSize=11.5,
        leading=15,
        alignment=1, # Center
        textColor=colors.HexColor("#1F2937")
    )

    student_lbl_style = ParagraphStyle(
        'RepStudentLbl',
        parent=styles['Normal'],
        fontName=REPORT_FONT,
        fontSize=10.5,
        leading=14,
        textColor=colors.HexColor("#111827")
    )

    student_val_style = ParagraphStyle(
        'RepStudentVal',
        parent=styles['Normal'],
        fontName=REPORT_FONT_BOLD,
        fontSize=11,
        leading=14,
        alignment=2, # Right aligned
        textColor=colors.HexColor("#111827")
    )

    sec_head_style = ParagraphStyle(
        'RepSecHead',
        parent=styles['Normal'],
        fontName=REPORT_FONT_BOLD,
        fontSize=10.5,
        leading=14,
        textColor=colors.HexColor("#111827")
    )

    item_row_style = ParagraphStyle(
        'RepItemRow',
        parent=styles['Normal'],
        fontName=REPORT_FONT_BOLD,
        fontSize=10,
        leading=13.5,
        textColor=colors.HexColor("#111827")
    )

    score_stat_style = ParagraphStyle(
        'RepScoreStat',
        parent=styles['Normal'],
        fontName=REPORT_FONT_BOLD,
        fontSize=11,
        leading=16,
        alignment=1, # Center
        textColor=colors.HexColor("#111827")
    )

    story = []

    # 1. Top Header: Logo on left, Centered Title on right
    logo_element = get_proportional_logo(target_height=56.0, max_width=75.0)

    clean_header = term_week_header.strip() if term_week_header else "Homework Report"
    # Ensure title line matches "PERFORMANCE BREAKDOWN"
    title_cell = [
        Paragraph("<b>PERFORMANCE BREAKDOWN</b>", title_main_style),
        Spacer(1, 2),
        Paragraph(format_math_for_reportlab(clean_header), title_sub_style)
    ]

    header_table = Table([[logo_element if logo_element else "", title_cell]], colWidths=[75, 420])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (1, 0), (1, 0), 'CENTER'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 10))

    # 2. Horizontal Divider
    story.append(HRFlowable(width="100%", thickness=0.75, color=colors.HexColor("#D1D5DB"), spaceBefore=0, spaceAfter=8))

    # 3. Student details row: keep the name beside its label and include the
    # class so printed reports can be identified without relying on the file
    # name.
    name_display = student_name.strip()
    class_display = str(class_name or "").strip()
    left_meta = "STUDENT NAME:"
    right_meta = f"<b>{name_display}</b>"
    if class_display:
        right_meta += f"  <font color='#6B7280'>Class: {class_display}</font>"

    meta_table = Table([[
        Paragraph(left_meta, student_lbl_style),
        Paragraph(right_meta, student_val_style)
    ]], colWidths=[200, 295])
    meta_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 12))

    # Optional Concept Breakdown Section
    if concept_breakdown:
        story.append(Paragraph("<b>CONCEPT MASTERY & DIAGNOSTIC BREAKDOWN:</b>", sec_head_style))
        story.append(Spacer(1, 6))

        c_head_style = ParagraphStyle(
            'RepCHead',
            parent=styles['Normal'],
            fontName=REPORT_FONT_BOLD,
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor("#374151")
        )
        c_cell_style = ParagraphStyle(
            'RepCCell',
            parent=styles['Normal'],
            fontName=REPORT_FONT,
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#1F2937")
        )

        c_rows = [[
            Paragraph("<b>Concept Area</b>", c_head_style),
            Paragraph("<b>Designated Questions</b>", c_head_style),
            Paragraph("<b>Correct / Total</b>", c_head_style),
            Paragraph("<b>Accuracy</b>", c_head_style),
            Paragraph("<b>Status</b>", c_head_style)
        ]]

        for c in concept_breakdown:
            c_name = c.get("concept_name", "General")
            q_list = ", ".join([f"Q{q}" for q in c.get("questions_designated", [])])
            corr = c.get("correct_count", 0)
            tot = c.get("total_questions", 0)
            acc = c.get("accuracy_pct", 0.0)
            st_text = c.get("status", "Moderate")

            if st_text == "Strength":
                status_color = "#15803D"
                status_label = "Strength"
            elif st_text == "Weakness":
                status_color = "#B91C1C"
                status_label = "Weakness"
            else:
                status_color = "#B45309"
                status_label = "Moderate"

            c_rows.append([
                Paragraph(f"<b>{c_name}</b>", c_cell_style),
                Paragraph(q_list, c_cell_style),
                Paragraph(f"{corr} / {tot}", c_cell_style),
                Paragraph(f"{acc:.0f}%", c_cell_style),
                Paragraph(f"<font color='{status_color}'><b>{status_label}</b></font>", c_cell_style)
            ])

        c_table = Table(c_rows, colWidths=[180, 115, 70, 60, 70])
        c_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#F3F4F6")),
            ('TOPPADDING', (0, 0), (-1, -1), 3.5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(c_table)
        story.append(Spacer(1, 12))

    # 4. AREAS FOR CORRECTION:
    story.append(Paragraph("<b>AREAS FOR CORRECTION:</b>", sec_head_style))
    story.append(Spacer(1, 6))

    if mistakes:
        table_rows = []
        for m in mistakes:
            # Determine Question label (e.g. "A Qn 2b", "Qn 3", etc.)
            q_raw = str(m.get('question_num', '')).strip()
            if not q_raw.lower().startswith("qn") and not (" " in q_raw and "qn" in q_raw.lower()):
                # If question label is just "2b" or "3", add "Qn " prefix
                if len(q_raw) > 0 and q_raw[0].isalpha() and len(q_raw) > 1 and q_raw[1].isspace():
                    # Format like "A 2b" -> "A Qn 2b"
                    parts = q_raw.split(None, 1)
                    q_label = f"{parts[0]} Qn {parts[1]}"
                else:
                    q_label = f"Qn {q_raw}"
            else:
                q_label = q_raw

            status = m.get('status', 'Incorrect').strip()
            # Normalize status text: e.g. "Incorrect", "Partial", "Missing", "Correct*"
            if status.lower() in ["correct*", "benefit_of_doubt", "corrected"]:
                status_str = "Correct*"
            elif status.lower() == "partial":
                status_str = "Partial"
            elif status.lower() == "missing":
                status_str = "Missing"
            else:
                status_str = "Incorrect"

            # Clean correct answer
            ans_raw = str(m.get('correct_answer', '')).strip()
            ans_fmt = _format_correction_fraction(ans_raw)
            if not ans_fmt:
                ans_fmt = str(m.get('student_answer', '')).strip()

            line_text = f"{q_label} | {status_str} ({ans_fmt})"
            p = Paragraph(format_math_for_reportlab(line_text), item_row_style)
            table_rows.append([p])

        corrections_table = Table(table_rows, colWidths=[495])
        corrections_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.75, colors.HexColor("#E5E7EB")), # Clean subtle border
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F9FAFB")), # Light gray background
            ('TOPPADDING', (0, 0), (-1, -1), 4.5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4.5),
            ('LEFTPADDING', (0, 0), (-1, -1), 12),
            ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ]))
        story.append(corrections_table)
    elif float(accuracy_pct) < 80.0:
        correction_required_style = ParagraphStyle(
            'RepCorrectionRequired',
            parent=styles['Normal'],
            fontName=REPORT_FONT_BOLD,
            fontSize=11.5,
            leading=16,
            alignment=1,
            textColor=colors.HexColor("#B91C1C")
        )
        story.append(Spacer(1, 10))
        story.append(Paragraph("Correction required", correction_required_style))
        story.append(Spacer(1, 4))
        story.append(Paragraph(
            "The overall score is below 80%, but the marker did not return question-level corrections. Review the submitted work against the teacher answer key.",
            ParagraphStyle(
                'RepCorrectionNote',
                parent=styles['Normal'],
                fontName=REPORT_FONT,
                fontSize=9.5,
                leading=13,
                alignment=1,
                textColor=colors.HexColor("#374151")
            )
        ))
    else:
        perfect_style = ParagraphStyle(
            'RepPerfect',
            parent=styles['Normal'],
            fontName=REPORT_FONT_BOLD,
            fontSize=11.5,
            leading=16,
            alignment=1, # Center
            textColor=colors.HexColor("#15803D")
        )
        story.append(Spacer(1, 12))
        story.append(Paragraph("Perfect Score! No corrections needed.", perfect_style))

    story.append(Spacer(1, 30))

    # 5. Centered Bottom Summary
    acc_val = round(accuracy_pct)
    score_clean = int(score) if score == int(score) else score
    total_clean = int(total_marks) if total_marks == int(total_marks) else total_marks

    story.append(Paragraph(f"<b>Accuracy Percentage: {acc_val}%</b>", score_stat_style))
    story.append(Spacer(1, 3))
    story.append(Paragraph(f"<b>Total Score: {score_clean} out of {total_clean}</b>", score_stat_style))

    doc.build(story)
    return buffer.getvalue()


# --- HIGH SCHOOL MATHEMATICS LESSON COVER SHEET GENERATOR (3 VARIATIONS) ---

def _trim_text(text: str, max_len: int) -> str:
    if not text or len(text) <= max_len:
        return text or ""
    trimmed = text[:max_len].rsplit(' ', 1)[0]
    return trimmed + "..."

def _chk_mark(val, target=True, is_blank=False) -> str:
    if is_blank:
        return "[  ]"
    if target is True:
        return "[X]" if val else "[  ]"
    val_str = str(val).lower()
    target_str = str(target).lower()
    if target_str in val_str:
        return "[X]"
    # Course level mappings for Secondary Mathematics (Years 7–12)
    if target_str == "stage 4" and any(x in val_str for x in ["stage 4", "stg 4", "yr 7", "yr 8", "year 7", "year 8", "7", "8"]):
        return "[X]"
    if target_str == "stage 5" and any(x in val_str for x in ["stage 5", "stg 5", "yr 9", "yr 10", "year 9", "year 10", "5.1", "5.2", "5.3", "9", "10"]):
        return "[X]"
    if target_str == "standard" and "standard" in val_str:
        return "[X]"
    if target_str == "advanced" and "advanced" in val_str and "extension" not in val_str and "ext" not in val_str:
        return "[X]"
    if target_str == "extension 1" and ("ext 1" in val_str or "extension 1" in val_str):
        return "[X]"
    if target_str == "extension 2" and ("ext 2" in val_str or "extension 2" in val_str):
        return "[X]"
    return "[  ]"

def _make_math_ruled_lines(num_lines=2, width=531, line_height=17, border_color=None):
    if border_color is None:
        border_color = colors.HexColor("#CBD5E1")
    rows = [[Paragraph("", ParagraphStyle('RL', fontName=FONT_MATH_REG, fontSize=9, leading=line_height))] for _ in range(num_lines)]
    t = Table(rows, colWidths=[width], rowHeights=[line_height]*num_lines)
    t.setStyle(TableStyle([
        ('LINEBELOW', (0, 0), (-1, -1), 0.5, border_color),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
    ]))
    return t

def _build_math_cover_sheet(data: Optional[Dict[str, Any]], mode: str = "2page", variation: str = "blueprint") -> bytes:
    if data is None:
        data = {}
    is_blank = not bool(data.get("student_name") or data.get("topic"))

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=22,
        leftMargin=22,
        topMargin=20,
        bottomMargin=20
    )

    W = 551  # Usable width on A4 (595 - 44)
    var_lower = str(variation).lower()

    # Color Palette & Thematic Identity (Blueprint as Primary Standard for Years 7–12)
    if "sprint" in var_lower:
        PRIMARY = colors.HexColor("#881337")    # Deep Rose / Crimson
        ACCENT = colors.HexColor("#E11D48")     # Vibrant Coral Red
        CARD_BG = colors.HexColor("#FFF1F2")    # Soft Rose Tint
        CARD_BORDER = colors.HexColor("#FECDD3")# Rose Border
        CARD_ALT = colors.HexColor("#FEF3C7")   # Golden Sand Callout
        ALT_BORDER = colors.HexColor("#D97706")
        THEME_TITLE = "HIGH-YIELD EXAM SPRINT"
        THEME_SUB = "YEARS 7–12 • EXAM ACCELERATION"
        THEME_TAGLINE = "Target 100%: Error Check, Working Rigour & Next Steps"
        P2_TITLE = "EXAM SPRINT • STUDENT VOICE & GOALS"
        P2_SUB = "STUDENT FEEDBACK & GOALS (YEARS 7–12)"
        P2_TAGLINE = "Checking test readiness, pacing, and focus areas for next lesson."
    elif "journal" in var_lower or "executive" in var_lower:
        PRIMARY = colors.HexColor("#0F172A")    # Deep Slate Navy
        ACCENT = colors.HexColor("#D97706")     # Honey Amber
        CARD_BG = colors.HexColor("#F8FAFC")    # Slate Soft Tint
        CARD_BORDER = colors.HexColor("#CBD5E1")# Slate Border
        CARD_ALT = colors.HexColor("#FEF3C7")   # Warm Amber Callout
        ALT_BORDER = colors.HexColor("#D97706")
        THEME_TITLE = "MATHS LESSON JOURNAL"
        THEME_SUB = "YEARS 7–12 • HIGH SCHOOL & HSC"
        THEME_TAGLINE = "High-Signal Progress: Syllabus Mastery, Student Independence & Parent Update"
        P2_TITLE = "STUDENT REFLECTION & MATHS JOURNAL"
        P2_SUB = "STUDENT FEEDBACK & GOALS (YEARS 7–12)"
        P2_TAGLINE = "Checking lesson difficulty, understanding & upcoming school tests."
    else:  # Blueprint (Default & Recommended for Years 7–12)
        PRIMARY = colors.HexColor("#1E3A8A")    # Cobalt Navy
        ACCENT = colors.HexColor("#0284C7")     # Electric Cyan
        CARD_BG = colors.HexColor("#F0F9FF")    # Ice Blue
        CARD_BORDER = colors.HexColor("#BAE6FD")# Sky Border
        CARD_ALT = colors.HexColor("#FEF3C7")   # Warm Amber Callout
        ALT_BORDER = colors.HexColor("#D97706")
        THEME_TITLE = "MATHEMATICS LESSON BLUEPRINT"
        THEME_SUB = "YEARS 7–12 • HIGH SCHOOL & HSC"
        THEME_TAGLINE = "Clear Lesson Progress for Teachers, Students & Parents • Syllabus, Independence & Next Steps"
        P2_TITLE = "MATHEMATICS BLUEPRINT • STUDENT VOICE"
        P2_SUB = "STUDENT FEEDBACK & GOALS (YEARS 7–12)"
        P2_TAGLINE = "Checking lesson pace, explanation clarity, confidence & upcoming school tests."

    # Typography with generous sizing and line heights
    t_main = ParagraphStyle('TMainM', fontName=FONT_MATH_TITLE, fontSize=18.5, leading=21, alignment=1, textColor=PRIMARY)
    t_sub = ParagraphStyle('TSubM', fontName=FONT_MATH_BOLD, fontSize=8.5, leading=10, alignment=1, textColor=ACCENT)
    t_tag = ParagraphStyle('TTagM', fontName=FONT_MATH_REG, fontSize=8.5, leading=10.5, alignment=1, textColor=colors.HexColor("#475569"))

    c_head = ParagraphStyle('CHeadM', fontName=FONT_MATH_BOLD, fontSize=11, leading=14, textColor=PRIMARY)
    c_body = ParagraphStyle('CBodyM', fontName=FONT_MATH_REG, fontSize=10.5, leading=14.5, textColor=colors.HexColor("#1E293B"))
    c_sound = ParagraphStyle('CSoundM', fontName=FONT_MATH_OBL, fontSize=11.5, leading=16, textColor=colors.HexColor("#78350F"))
    c_foot = ParagraphStyle('CFootM', fontName=FONT_MATH_OBL, fontSize=9, leading=11.5, textColor=colors.HexColor("#64748B"))

    if mode == "1page":
        c_head = ParagraphStyle('CHead1pM', fontName=FONT_MATH_BOLD, fontSize=9.5, leading=12, textColor=PRIMARY)
        c_body = ParagraphStyle('CBody1pM', fontName=FONT_MATH_REG, fontSize=8.5, leading=11.5, textColor=colors.HexColor("#1E293B"))
        c_sound = ParagraphStyle('CSound1pM', fontName=FONT_MATH_OBL, fontSize=9, leading=12, textColor=colors.HexColor("#78350F"))

    # Field Extractions with Blank Handling
    s_name = data.get("student_name", "")
    t_name = data.get("tutor_name", "")
    term = data.get("term", "")
    week = data.get("week", "")
    date_str = data.get("lesson_date", "")
    course = data.get("course_level", "" if is_blank else "Extension 1")
    topic = data.get("topic", "")
    subtopic = data.get("subtopic", "")
    outcome = data.get("syllabus_outcomes", "")
    hw_score = data.get("homework_score", "" if is_blank else "18/20 (90%)")
    drill_score = data.get("drill_score", "" if is_blank else "14/15 (93%)")
    autonomy = data.get("cognitive_autonomy", "" if is_blank else "Independent")
    rc_tags = data.get("root_cause_tags", [])
    stumble = data.get("specific_stumbling_block", "")
    soundbite = data.get("parent_soundbite", "")
    hw_set = data.get("homework_assigned", "")
    due_date = data.get("homework_due", "Next Lesson" if not is_blank else "____ / ____")
    target_acc = data.get("target_accuracy", "90%" if not is_blank else "____ %")

    story = []

    # 1. HEADER
    brand_logo = get_proportional_logo(target_height=30.0, max_width=50.0)
    brand_text = Paragraph(f"<b><font size=15 color='{PRIMARY.hexval()}'>DA</font></b><br/><font size=7.5 color='{ACCENT.hexval()}'><b>MATHEMATICS</b></font>", ParagraphStyle('BHM', fontName='Helvetica-Bold', leading=11, alignment=0))
    brand_cell = [brand_logo, brand_text] if brand_logo else brand_text

    title_flow = [
        Paragraph(f"<b>{THEME_TITLE}</b>", t_main),
        Spacer(1, 2),
        Paragraph(f"<font color='white' backColor='{PRIMARY.hexval()}'>&nbsp;&nbsp;<b>{THEME_SUB}</b>&nbsp;&nbsp;</font>", t_sub),
        Spacer(1, 2),
        Paragraph(THEME_TAGLINE, t_tag)
    ]
    math_badge = Paragraph(f"<font size=8.5 color='{ACCENT.hexval()}'><b>YEARS 7–12</b><br/><font size=7.5 color='#64748B'>HIGH SCHOOL &amp; HSC</font></font>", ParagraphStyle('MIM', fontName='Helvetica-Bold', leading=11, alignment=2))
    
    h_table = Table([[brand_cell, title_flow, math_badge]], colWidths=[80, 391, 80])
    h_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(h_table)
    story.append(Spacer(1, 6 if mode == '1page' else 9))

    # 2. CONTEXT RIBBON WITH COURSE LEVEL PILLS FOR YEARS 7-12
    lvl_pills = (
        f"<b>Course Level:</b> &nbsp; "
        f"{_chk_mark(course, 'Stage 4', is_blank)} Yr 7–8 (Stg 4) &nbsp;&nbsp; "
        f"{_chk_mark(course, 'Stage 5', is_blank)} Yr 9–10 (Stg 5) &nbsp;&nbsp; "
        f"{_chk_mark(course, 'Standard', is_blank)} Standard &nbsp;&nbsp; "
        f"{_chk_mark(course, 'Advanced', is_blank)} Advanced &nbsp;&nbsp; "
        f"{_chk_mark(course, 'Extension 1', is_blank)} <b>Ext 1</b> &nbsp;&nbsp; "
        f"{_chk_mark(course, 'Extension 2', is_blank)} <b>Ext 2 (HSC)</b>"
    )
    meta_table = Table([
        [
            Paragraph(f"<b>Student:</b> {s_name if s_name else '___________________________'}", c_body),
            Paragraph(f"<b>Term:</b> {term if term else '____'} &nbsp;&nbsp; <b>Week:</b> {week if week else '____'}", c_body),
            Paragraph(f"<b>Date:</b> {date_str if date_str else '____ / ____ / 20____'}", c_body),
            Paragraph(f"<b>Tutor:</b> {t_name if t_name else '__________________'}", c_body)
        ],
        [
            Paragraph(lvl_pills, c_body),
            "", "", ""
        ]
    ], colWidths=[185, 110, 126, 130])
    meta_table.setStyle(TableStyle([
        ('SPAN', (0, 1), (3, 1)),
        ('BOX', (0,0), (-1,-1), 1, CARD_BORDER),
        ('BACKGROUND', (0,0), (-1,-1), CARD_BG),
        ('TOPPADDING', (0,0), (-1,-1), 4 if mode == '1page' else 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4 if mode == '1page' else 6),
        ('LEFTPADDING', (0,0), (-1,-1), 9),
        ('RIGHTPADDING', (0,0), (-1,-1), 9),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 6 if mode == '1page' else 10))

    has_rc = lambda t: "[X]" if any(t.lower() in x.lower() for x in rc_tags) else "[  ]"

    # =========================================================================
    # 1-PAGE CONDENSED EDITION
    # =========================================================================
    if mode == "1page":
        col_w = 271
        c1_txt = (
            f"<b><font color='white' backColor='{PRIMARY.hexval()}'>&nbsp;1&nbsp;</font> WHAT WAS TAUGHT TODAY</b><br/>"
            f"• <b>NSW Code:</b> <b>{outcome if outcome else 'Stage 4–6 (e.g. ME-V1 / MA5.2-1WM)'}</b><br/>"
            f"• <b>Topic:</b> {topic if topic else '___________________________________'}<br/>"
            f"• <b>Subtopic:</b> {subtopic if subtopic else '________________________________'}<br/>"
            f"• <b>Materials:</b> {_chk_mark(True, True, is_blank)} DA Booklet &nbsp; {_chk_mark(True, True, is_blank)} Exam / Quiz Pack"
        )
        c2_txt = (
            f"<b><font color='white' backColor='{PRIMARY.hexval()}'>&nbsp;2&nbsp;</font> STUDENT UNDERSTANDING & INDEPENDENCE</b><br/>"
            f"• <b>Independence Level:</b><br/>"
            f"&nbsp; {_chk_mark(autonomy, 'Modeled', is_blank)} Modeled &nbsp;&nbsp; {_chk_mark(autonomy, 'Guided', is_blank)} Guided<br/>"
            f"&nbsp; {_chk_mark(autonomy, 'Independent', is_blank)} <b>Independent</b> &nbsp;&nbsp; {_chk_mark(autonomy, 'Exam Ready', is_blank)} <b>Exam Ready</b><br/>"
            f"• <b>HW:</b> {hw_score if hw_score else '____ / ____'} &nbsp; <b>Drill:</b> {drill_score if drill_score else '____ / ____'} (Target: {target_acc})<br/>"
            f"• <b>Focus:</b> {data.get('score_engagement', '5') if not is_blank else '____'}/5 &nbsp; <b>Confidence:</b> {data.get('score_confidence', '4') if not is_blank else '____'}/5"
        )
        sound_snippet = soundbite if soundbite else ("Student demonstrated strong focus today; understood key concepts and worked independently. On track for upcoming tests!" if not is_blank else "“ ____________________________________________________________________ ”")
        if not is_blank:
            sound_snippet = _trim_text(sound_snippet, 150)
        sound_txt = (
            f"<b><font color='white' backColor='{ACCENT.hexval()}'>&nbsp;PARENT UPDATE&nbsp;</font></b> &nbsp; <b>15-SECOND PARENT UPDATE</b><br/>"
            f"<i>\"{sound_snippet}\"</i>"
        )

        left_cards = Table([
            [Paragraph(c1_txt, c_body)],
            [Paragraph(c2_txt, c_body)],
            [Paragraph(sound_txt, c_sound)]
        ], colWidths=[col_w])
        left_cards.setStyle(TableStyle([
            ('BOX', (0,0), (-1,0), 1, CARD_BORDER),
            ('BACKGROUND', (0,0), (-1,0), CARD_BG),
            ('BOX', (0,1), (-1,1), 1, CARD_BORDER),
            ('BACKGROUND', (0,1), (-1,1), CARD_BG),
            ('BOX', (0,2), (-1,2), 1.2, ALT_BORDER),
            ('BACKGROUND', (0,2), (-1,2), CARD_ALT),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('LEFTPADDING', (0,0), (-1,-1), 6),
            ('RIGHTPADDING', (0,0), (-1,-1), 6),
        ]))

        c3_txt = (
            f"<b><font color='white' backColor='{PRIMARY.hexval()}'>&nbsp;3&nbsp;</font> WHY MARKS WERE LOST</b><br/>"
            f"• <b>Common Mistakes Observed:</b><br/>"
            f"&nbsp; {_chk_mark(has_rc('Slip')=='[X]', True, is_blank)} <b>Careless Sign Slip</b> &nbsp;&nbsp; {_chk_mark(has_rc('Pacing')=='[X]', True, is_blank)} <b>Time Pressure</b><br/>"
            f"&nbsp; {_chk_mark(has_rc('Void')=='[X]', True, is_blank)} <b>Missing Rule/Formula</b> &nbsp;&nbsp; [  ] <b>Misread Question</b><br/>"
            f"• <b>Challenge Today:</b> {stumble if stumble else ('None observed — high working accuracy' if not is_blank else '__________________________________')}"
        )
        next_pri = _trim_text(data.get('next_lesson_priority', 'Extension Practice' if not is_blank else '____________________'), 30)
        c4_txt = (
            f"<b><font color='white' backColor='{PRIMARY.hexval()}'>&nbsp;4&nbsp;</font> WHAT THE TUTOR DID & NEXT STEPS</b><br/>"
            f"• <b>Tutor Action:</b> {_chk_mark(True, True, is_blank)} Step-by-Step Examples &nbsp; {_chk_mark(True, True, is_blank)} Visual Sketches<br/>"
            f"• <b>Homework:</b> {hw_set if hw_set else '___________________________________'}<br/>"
            f"• <b>Due:</b> {due_date} &nbsp; <b>Next:</b> {next_pri}"
        )
        s_diff = data.get("student_difficulty", "" if is_blank else "Sweet Spot")
        s_conf = data.get("student_confidence_shift", "" if is_blank else "Higher")
        s_clarity = data.get("student_clarity", "" if is_blank else "Crystal Clear")
        student_goal = _trim_text(data.get('student_request_note', 'Practice trial proofs') or 'Practice proofs', 65)
        c5_txt = (
            f"<b><font color='white' backColor='{PRIMARY.hexval()}'>&nbsp;5&nbsp;</font> STUDENT VOICE & LESSON FEEL</b><br/>"
            f"• <b>Lesson Pace:</b> {_chk_mark(s_diff, 'Sweet Spot', is_blank)} Just Right &nbsp; {_chk_mark(s_diff, 'Too Easy', is_blank)} Easy<br/>"
            f"• <b>Confidence Shift:</b> {_chk_mark(s_conf, 'Higher', is_blank)} Much Higher &nbsp; [  ] Same<br/>"
            f"• <b>Teaching Clarity:</b> {_chk_mark(s_clarity, 'Crystal Clear', is_blank)} Crystal Clear &nbsp; Support: {('10/10' if not is_blank else '__/10')}<br/>"
            f"• <b>Student Goal:</b> <i>{student_goal}</i>"
        )
        right_cards = Table([
            [Paragraph(c3_txt, c_body)],
            [Paragraph(c4_txt, c_body)],
            [Paragraph(c5_txt, c_body)]
        ], colWidths=[col_w])
        right_cards.setStyle(TableStyle([
            ('BOX', (0,0), (-1,0), 1, CARD_BORDER),
            ('BACKGROUND', (0,0), (-1,0), CARD_BG),
            ('BOX', (0,1), (-1,1), 1, CARD_BORDER),
            ('BACKGROUND', (0,1), (-1,1), CARD_BG),
            ('BOX', (0,2), (-1,2), 1, CARD_BORDER),
            ('BACKGROUND', (0,2), (-1,2), CARD_BG),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('LEFTPADDING', (0,0), (-1,-1), 6),
            ('RIGHTPADDING', (0,0), (-1,-1), 6),
        ]))

        grid_1p = Table([[left_cards, right_cards]], colWidths=[col_w, col_w+9])
        grid_1p.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('TOPPADDING', (0,0), (-1,-1), 0),
            ('BOTTOMPADDING', (0,0), (-1,-1), 0),
            ('LEFTPADDING', (0,0), (-1,-1), 0),
            ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ]))
        story.append(grid_1p)
        story.append(Spacer(1, 6))

        foot_tbl = Table([
            [
                Paragraph("<b>Attention Flag:</b> <b>[ALL CLEAR] On Track — Making Strong Progress</b>", c_body),
                Paragraph(f"<b>Tutor Sign:</b> {t_name if t_name else '_________________'} &nbsp; <b>Student Sign:</b> _____________", ParagraphStyle('FR1pM', parent=c_body, alignment=2))
            ]
        ], colWidths=[260, 291])
        foot_tbl.setStyle(TableStyle([
            ('LINEABOVE', (0,0), (-1,-1), 0.5, CARD_BORDER),
            ('TOPPADDING', (0,0), (-1,-1), 3),
            ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ]))
        story.append(foot_tbl)

        doc.build(story)
        return buffer.getvalue()

    # =========================================================================
    # 2-PAGE DOUBLE SIDED EDITION: PAGE 1 (TUTOR DIAGNOSTIC & PROGRESS)
    # =========================================================================
    # CARD 1: WHAT WAS TAUGHT TODAY
    c1_txt = (
        f"<b><font color='white' backColor='{PRIMARY.hexval()}'>&nbsp;1&nbsp;</font> WHAT WAS TAUGHT TODAY</b><br/>"
        f"• <b>Topic & Key Concepts:</b> {topic if topic else ('__________________________________________________________________________' if not is_blank else '__________________________________________________________________________')}<br/>"
        f"• <b>Subtopic & Specific Skills:</b> {subtopic if subtopic else ('__________________________________________________________________________' if not is_blank else '__________________________________________________________________________')}<br/>"
        f"• <b>NSW Syllabus Code:</b> <b>{outcome if outcome else ('Stage 4/5/6 Core' if not is_blank else '________________')}</b> &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; "
        f"<b>Materials:</b> {_chk_mark(True, True, is_blank)} DA Booklet &nbsp;&nbsp; {_chk_mark(True, True, is_blank)} Exam Pack &nbsp;&nbsp; [  ] School Papers"
    )
    c1_tbl = Table([[Paragraph(c1_txt, c_body)]], colWidths=[W])
    c1_tbl.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 1, CARD_BORDER),
        ('BACKGROUND', (0,0), (-1,-1), CARD_BG),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('RIGHTPADDING', (0,0), (-1,-1), 10),
    ]))
    story.append(c1_tbl)
    story.append(Spacer(1, 10))

    # CARD 2: WHAT THE STUDENT UNDERSTOOD & INDEPENDENCE
    auton_badge = (
        f"<b>How Independent Was the Student?</b><br/>"
        f"&nbsp; {_chk_mark(autonomy, 'Modeled', is_blank)} <b>Modeled</b> (Tutor showed step-by-step)<br/>"
        f"&nbsp; {_chk_mark(autonomy, 'Guided', is_blank)} <b>Guided</b> (Solved with tutor hints & prompts)<br/>"
        f"&nbsp; {_chk_mark(autonomy, 'Independent', is_blank)} <b>Independent</b> (Solved on their own)<br/>"
        f"&nbsp; {_chk_mark(autonomy, 'Exam Ready', is_blank)} <b>Exam Ready</b> (Fast, accurate & test-ready)"
    )
    scores_badge = (
        f"<b>Practice & Mastery Checks:</b><br/>"
        f"• <b>Previous Homework:</b> {hw_score if hw_score else '____ / ____'} &nbsp; Completed: {_chk_mark(True, True, is_blank)} Fully &nbsp; [  ] Partially<br/>"
        f"• <b>In-Class Practice Drill:</b> {drill_score if drill_score else '____ / ____'} &nbsp;&nbsp;&nbsp; <b>Target:</b> {target_acc}<br/>"
        f"• <b>Engagement & Focus:</b> <b>{(str(data.get('score_engagement', '5')) + '/5') if not is_blank else '__/5'}</b> &nbsp;&nbsp; "
        f"<b>Confidence:</b> <b>{(str(data.get('score_confidence', '4')) + '/5') if not is_blank else '__/5'}</b><br/>"
        f"• <b>Working & Steps:</b> {_chk_mark(True, True, is_blank)} Full working shown clearly &nbsp; [  ] Needs to show full steps"
    )
    c2_tbl = Table([
        [Paragraph(f"<b><font color='white' backColor='{PRIMARY.hexval()}'>&nbsp;2&nbsp;</font> WHAT THE STUDENT UNDERSTOOD & INDEPENDENCE</b>", c_head), ""],
        [Paragraph(auton_badge, c_body), Paragraph(scores_badge, c_body)]
    ], colWidths=[240, 311])
    c2_tbl.setStyle(TableStyle([
        ('SPAN', (0,0), (1,0)),
        ('BOX', (0,0), (-1,-1), 1, CARD_BORDER),
        ('BACKGROUND', (0,0), (-1,-1), CARD_BG),
        ('TOPPADDING', (0,0), (-1,-1), 7),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('RIGHTPADDING', (0,0), (-1,-1), 10),
    ]))
    story.append(c2_tbl)
    story.append(Spacer(1, 10))

    # CARD 3: WHY MARKS WERE LOST & WHAT TO WATCH OUT FOR
    err_badge = (
        f"<b>Common Mistakes & Mark Loss Reasons:</b><br/>"
        f"&nbsp; {_chk_mark(has_rc('Slip')=='[X]', True, is_blank)} <b>Careless Slip / Sign Error</b> (+/- mistake, arithmetic) &nbsp;&nbsp;&nbsp;&nbsp; "
        f"{_chk_mark(has_rc('Pacing')=='[X]', True, is_blank)} <b>Time Pressure</b> (rushed working, pacing)<br/>"
        f"&nbsp; {_chk_mark(has_rc('Void')=='[X]', True, is_blank)} <b>Missing Rule or Formula</b> (forgot rule, needs revision) &nbsp;&nbsp;&nbsp; "
        f"[  ] <b>Misread Question</b> (missed key details / units)<br/>"
        f"• <b>Specific Challenge Today & How It Was Solved:</b><br/>"
        f"&nbsp; <i>{stumble if stumble else ('Initially made a sign error during algebraic expansion, but identified and fixed the mistake after checking steps.' if not is_blank else '__________________________________________________________________________')}</i>"
    )
    c3_tbl = Table([
        [Paragraph(f"<b><font color='white' backColor='{PRIMARY.hexval()}'>&nbsp;3&nbsp;</font> WHY MARKS WERE LOST & WHAT TO WATCH OUT FOR</b>", c_head)],
        [Paragraph(err_badge, c_body)]
    ], colWidths=[W])
    c3_tbl.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 1, CARD_BORDER),
        ('BACKGROUND', (0,0), (-1,-1), CARD_BG),
        ('TOPPADDING', (0,0), (-1,-1), 7),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('RIGHTPADDING', (0,0), (-1,-1), 10),
    ]))
    story.append(c3_tbl)
    story.append(Spacer(1, 10))

    # CARD 4: WHAT THE TUTOR DID TO HELP & NEXT STEPS
    int_badge = (
        f"• <b>What the Tutor Did to Help:</b> {_chk_mark(True, True, is_blank)} Worked through step-by-step examples &nbsp;&nbsp; {_chk_mark(True, True, is_blank)} Drew visual diagrams & geometry sketches<br/>"
        f"• <b>Homework Assigned:</b> <b>{hw_set if hw_set else '__________________________________________________________________________'}</b><br/>"
        f"• <b>Due Date:</b> {due_date} &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; <b>Next Lesson Focus:</b> {data.get('next_lesson_priority', 'Extension Practice & Exam Timing Drills' if not is_blank else '____________________')}"
    )
    c4_tbl = Table([
        [Paragraph(f"<b><font color='white' backColor='{PRIMARY.hexval()}'>&nbsp;4&nbsp;</font> WHAT THE TUTOR DID TO HELP & NEXT STEPS</b>", c_head)],
        [Paragraph(int_badge, c_body)]
    ], colWidths=[W])
    c4_tbl.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 1, CARD_BORDER),
        ('BACKGROUND', (0,0), (-1,-1), CARD_BG),
        ('TOPPADDING', (0,0), (-1,-1), 7),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('RIGHTPADDING', (0,0), (-1,-1), 10),
    ]))
    story.append(c4_tbl)
    story.append(Spacer(1, 10))

    # CARD 5: 15-SECOND UPDATE FOR PARENTS (Warm Amber Callout Card)
    if is_blank:
        sound_body = "“ ____________________________________________________________________________________________________ ”"
    else:
        sb = soundbite if soundbite else "Alex had a great lesson on Vectors today. He understood the dot product concept well and worked through questions independently. We focused on slowing down to avoid negative sign errors, and he is on track for his upcoming assessment."
        sound_body = f"“{sb}”"
    sound_txt = (
        f"<b><font color='white' backColor='{ACCENT.hexval()}'>&nbsp;PARENT UPDATE&nbsp;</font></b> &nbsp; "
        f"<b><font color='#78350F'>15-SECOND UPDATE FOR PARENTS</font></b> &nbsp; "
        f"<font size=8.5 color='#78350F'>(When parents ask: <i>“How has my child been going?”</i>)</font><br/>"
        f"<b>{sound_body}</b>"
    )
    c5_tbl = Table([[Paragraph(sound_txt, c_sound)]], colWidths=[W])
    c5_tbl.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 1.2, ALT_BORDER),
        ('BACKGROUND', (0,0), (-1,-1), CARD_ALT),
        ('TOPPADDING', (0,0), (-1,-1), 9),
        ('BOTTOMPADDING', (0,0), (-1,-1), 9),
        ('LEFTPADDING', (0,0), (-1,-1), 12),
        ('RIGHTPADDING', (0,0), (-1,-1), 12),
    ]))
    story.append(c5_tbl)
    story.append(Spacer(1, 9))

    # FOOTER
    foot_tbl = Table([
        [
            Paragraph("<b>Attention Flag:</b> <b>[ALL CLEAR] On Track — Making Strong Progress</b>", c_body),
            Paragraph(f"<b>Tutor Signature:</b> {t_name if t_name else '____________________'} &nbsp;&nbsp;&nbsp; <b>DA Mathematics (Years 7–12)</b>", ParagraphStyle('FR1M', parent=c_body, alignment=2))
        ]
    ], colWidths=[260, 291])
    foot_tbl.setStyle(TableStyle([
        ('LINEABOVE', (0,0), (-1,-1), 0.5, CARD_BORDER),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(foot_tbl)

    # =========================================================================
    # PAGE 2: STUDENT FEEDBACK & GOALS (YEARS 7–12)
    # =========================================================================
    story.append(PageBreak())

    p2_brand = Paragraph(f"<b><font size=16 color='{PRIMARY.hexval()}'>DA</font></b><br/><font size=7.5 color='{ACCENT.hexval()}'><b>MATHEMATICS</b></font>", ParagraphStyle('BH2M', fontName='Helvetica-Bold', leading=11, alignment=0))
    p2_brand_cell = [brand_logo, p2_brand] if brand_logo else p2_brand
    p2_title_flow = [
        Paragraph(f"<b>{P2_TITLE}</b>", t_main),
        Spacer(1, 2),
        Paragraph(f"<font color='white' backColor='{PRIMARY.hexval()}'>&nbsp;&nbsp;<b>{P2_SUB}</b>&nbsp;&nbsp;</font>", t_sub),
        Spacer(1, 2),
        Paragraph(P2_TAGLINE, t_tag)
    ]
    p2_badge = Paragraph(f"<font size=8.5 color='{ACCENT.hexval()}'><b>STUDENT VOICE</b><br/><font size=7.5 color='#64748B'>GROWTH &amp; GOALS</font></font>", ParagraphStyle('MI2M', fontName='Helvetica-Bold', leading=11, alignment=2))
    
    p2_h_table = Table([[p2_brand_cell, p2_title_flow, p2_badge]], colWidths=[80, 391, 80])
    p2_h_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(p2_h_table)
    story.append(Spacer(1, 9))

    p2_meta = Table([
        [
            Paragraph(f"<b>Student:</b> {s_name if s_name else '___________________________'}", c_body),
            Paragraph(f"<b>Course:</b> {course if course else '________________'} &nbsp;&nbsp; <b>Term:</b> {term if term else '__'} &nbsp; <b>Wk:</b> {week if week else '__'}", c_body),
            Paragraph(f"<b>Date:</b> {date_str if date_str else '____ / ____ / 20____'}", c_body)
        ]
    ], colWidths=[235, 175, 141])
    p2_meta.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 1, CARD_BORDER),
        ('BACKGROUND', (0,0), (-1,-1), CARD_BG),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(p2_meta)
    story.append(Spacer(1, 9))

    # P2 CARD 1: HOW DID TODAY'S LESSON FEEL? (Pacing & Challenge)
    s_diff = data.get("student_difficulty", "" if is_blank else "Sweet Spot")
    s_conf = data.get("student_confidence_shift", "" if is_blank else "Higher")
    p2_c1 = (
        f"<b><font color='white' backColor='{PRIMARY.hexval()}'>&nbsp;1&nbsp;</font> HOW DID TODAY'S LESSON FEEL? (Pacing & Challenge)</b><br/>"
        f"• <b>How was the lesson pace and challenge today?</b><br/>"
        f"&nbsp; {_chk_mark(s_diff, 'Too Easy', is_blank)} <b>Too Easy</b> — Understood everything quickly, ready for harder challenge questions!<br/>"
        f"&nbsp; {_chk_mark(s_diff, 'Sweet Spot', is_blank)} <b>Just Right (Challenging)</b> — Pushed my thinking, tutor explained tricky steps clearly.<br/>"
        f"&nbsp; {_chk_mark(s_diff, 'Tricky', is_blank)} <b>A Bit Tricky</b> — Took a while to click, need extra practice on multi-step questions.<br/>"
        f"&nbsp; {_chk_mark(s_diff, 'Overwhelming', is_blank)} <b>Too Fast / Hard</b> — Felt overwhelmed, need to slow down and review the basics.<br/>"
        f"• <b>How is your confidence on this topic after today's lesson?</b><br/>"
        f"&nbsp; {_chk_mark(s_conf, 'Higher', is_blank)} <b>Much More Confident (Ready for tests)</b> &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; "
        f"{_chk_mark(s_conf, 'Same', is_blank)} <b>About the Same</b> &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; [  ] <b>Still Unsure</b>"
    )
    p2_c1_tbl = Table([[Paragraph(p2_c1, c_body)]], colWidths=[W])
    p2_c1_tbl.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 1, CARD_BORDER),
        ('BACKGROUND', (0,0), (-1,-1), CARD_BG),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 7),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('RIGHTPADDING', (0,0), (-1,-1), 10),
    ]))
    story.append(p2_c1_tbl)
    story.append(Spacer(1, 9))

    # P2 CARD 2: TEACHING QUALITY & CLASSROOM SUPPORT
    s_clarity = data.get("student_clarity", "" if is_blank else "Crystal Clear")
    s_supp = data.get("student_support", "" if is_blank else "Very Supported")
    s_quest = data.get("student_questions", "" if is_blank else "Always (100%)")
    rating_display = "Low &nbsp; 1 · 2 · 3 · 4 · 5 · 6 · 7 · 8 · 9 · <b>[10]</b> &nbsp; High" if not is_blank else "Low &nbsp; 1 · 2 · 3 · 4 · 5 · 6 · 7 · 8 · 9 · 10 &nbsp; High"
    p2_c2_grid = [
        [Paragraph(f"<b><font color='white' backColor='{PRIMARY.hexval()}'>&nbsp;2&nbsp;</font> TEACHING QUALITY & CLASSROOM SUPPORT</b>", c_head), ""],
        [
            Paragraph(f"<b>1. Tutor's Explanations Today:</b><br/>{_chk_mark(s_clarity, 'Crystal Clear', is_blank)} Crystal clear & easy to follow<br/>{_chk_mark(s_clarity, 'Mostly Clear', is_blank)} Mostly clear<br/>{_chk_mark(s_clarity, 'Cloudy', is_blank)} Hard to follow / confusing", c_body),
            Paragraph(f"<b>2. When Stuck or Making Mistakes:</b><br/>{_chk_mark(s_supp, 'Very Supported', is_blank)} Patient & guided me step-by-step<br/>{_chk_mark(s_supp, 'Okay', is_blank)} Okay<br/>{_chk_mark(s_supp, 'Stressed', is_blank)} Felt rushed or stressed", c_body)
        ],
        [
            Paragraph(f"<b>3. Comfort Asking Questions:</b><br/>{_chk_mark(s_quest, 'Always (100%)', is_blank)} 100% comfortable asking anything<br/>{_chk_mark(s_quest, 'Sometimes', is_blank)} Usually comfortable<br/>{_chk_mark(s_quest, 'Hesitant', is_blank)} Felt shy / hesitant to ask", c_body),
            Paragraph(f"<b>4. Support Rating Today (1 to 10):</b><br/>{rating_display}<br/><i>Tutor gave thorough individual attention</i>", c_body)
        ]
    ]
    p2_c2_tbl = Table(p2_c2_grid, colWidths=[275, 276])
    p2_c2_tbl.setStyle(TableStyle([
        ('SPAN', (0,0), (1,0)),
        ('BOX', (0,0), (-1,-1), 1, CARD_BORDER),
        ('BACKGROUND', (0,0), (-1,-1), CARD_BG),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('RIGHTPADDING', (0,0), (-1,-1), 10),
    ]))
    story.append(p2_c2_tbl)
    story.append(Spacer(1, 9))

    # P2 CARD 3: BREAKTHROUGHS — WHAT CLICKED TODAY?
    p2_c3_flow = [
        Paragraph(f"<b><font color='white' backColor='{PRIMARY.hexval()}'>&nbsp;3&nbsp;</font> BREAKTHROUGHS — WHAT CLICKED TODAY?</b>", c_head),
        Spacer(1, 2),
        Paragraph("• <b>What question, formula, or concept finally made total sense today?</b>", c_body),
        Paragraph(f"&nbsp; <i>{(data.get('student_request_note') and 'Using the dot product orthogonality condition (u · v = 0) to prove perpendicular vectors and expanding brackets without sign mistakes.') or ''}</i>", c_body),
        _make_math_ruled_lines(num_lines=2, width=W-20, line_height=17, border_color=CARD_BORDER)
    ]
    p2_c3_tbl = Table([[p2_c3_flow]], colWidths=[W])
    p2_c3_tbl.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 1, CARD_BORDER),
        ('BACKGROUND', (0,0), (-1,-1), CARD_BG),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 7),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('RIGHTPADDING', (0,0), (-1,-1), 10),
    ]))
    story.append(p2_c3_tbl)
    story.append(Spacer(1, 9))

    # P2 CARD 4: UPCOMING SCHOOL MATH TESTS & GOALS
    s_note = data.get("student_request_note", "")
    p2_c4_flow = [
        Paragraph(f"<b><font color='white' backColor='{PRIMARY.hexval()}'>&nbsp;4&nbsp;</font> UPCOMING SCHOOL MATH TESTS & GOALS</b>", c_head),
        Spacer(1, 2),
        Paragraph(f"• <b>Upcoming School Test or Exam:</b> {_chk_mark(True, True, is_blank)} Yes, in <b>{('3' if not is_blank else '____')}</b> weeks &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; [  ] None right now<br/>"
                  f"• <b>Assessment Topic:</b> {('Vectors in 2D/3D & Complex Numbers (Trial Prep)' if not is_blank else '____________________________________________________')}<br/>"
                  f"• <b>The #1 question or skill I want help with next lesson:</b><br/>"
                  f"&nbsp; <i>{s_note if s_note else ''}</i>", c_body),
        _make_math_ruled_lines(num_lines=1, width=W-20, line_height=17, border_color=CARD_BORDER)
    ]
    p2_c4_tbl = Table([[p2_c4_flow]], colWidths=[W])
    p2_c4_tbl.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 1, CARD_BORDER),
        ('BACKGROUND', (0,0), (-1,-1), CARD_BG),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 7),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('RIGHTPADDING', (0,0), (-1,-1), 10),
    ]))
    story.append(p2_c4_tbl)
    story.append(Spacer(1, 9))

    # P2 CARD 5: MESSAGE TO TUTOR OR DIRECTOR (Optional)
    p2_c5_flow = [
        Paragraph(f"<b><font color='white' backColor='{PRIMARY.hexval()}'>&nbsp;5&nbsp;</font> MESSAGE TO TUTOR OR DIRECTOR (Optional)</b>", c_head),
        Spacer(1, 2),
        Paragraph("<i>Is there anything about the lesson pace, class size, or topics you'd like us to know?</i>", c_foot),
        _make_math_ruled_lines(num_lines=2, width=W-20, line_height=17, border_color=CARD_BORDER)
    ]
    p2_c5_tbl = Table([[p2_c5_flow]], colWidths=[W])
    p2_c5_tbl.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 1, CARD_BORDER),
        ('BACKGROUND', (0,0), (-1,-1), CARD_BG),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 7),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('RIGHTPADDING', (0,0), (-1,-1), 10),
    ]))
    story.append(p2_c5_tbl)
    story.append(Spacer(1, 8))

    p2_foot = Table([
        [
            Paragraph("<b>Every step shown clearly builds mathematical confidence! • DA Secondary Mathematics</b>", c_foot),
            Paragraph("<b>Student Signature:</b> ___________________________", ParagraphStyle('FootR2M', parent=c_body, alignment=2))
        ]
    ], colWidths=[280, 271])
    p2_foot.setStyle(TableStyle([
        ('LINEABOVE', (0,0), (-1,-1), 0.5, CARD_BORDER),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(p2_foot)

    doc.build(story)
    return buffer.getvalue()


def build_math_executive(data: Optional[Dict[str, Any]] = None, mode: str = "2page") -> bytes:
    """Variation 1: The Studio Math Journal (Slate Navy & Amber, Warm Editorial)"""
    return _build_math_cover_sheet(data, mode, "journal")


def build_math_blueprint(data: Optional[Dict[str, Any]] = None, mode: str = "2page") -> bytes:
    """Variation 2: The Mathematics Lesson Blueprint for Years 7–12 (Cobalt & Cyan, Modern STEM Matrix)"""
    return _build_math_cover_sheet(data, mode, "blueprint")


def build_math_sprint(data: Optional[Dict[str, Any]] = None, mode: str = "2page") -> bytes:
    """Variation 3: The High-Yield Exam Sprint (Crimson & Coral, Trial Acceleration)"""
    return _build_math_cover_sheet(data, mode, "sprint")


def generate_lesson_cover_sheet_pdf(
    cover_data: Optional[Dict[str, Any]] = None,
    mode: str = "2page",
    variation: str = "blueprint"
) -> bytes:
    """
    Generates High School Mathematics Lesson Cover Sheet in 3 distinct design variations:
    - variation="blueprint": Primary Standard: Mathematics Lesson Blueprint for Years 7–12 (Cobalt & Cyan)
    - variation="executive" / "journal": Variation 1: The Studio Math Journal (Slate Navy & Amber, warm editorial)
    - variation="sprint": Variation 3: The High-Yield Exam Sprint (Crimson & Coral, mark preservation diagnostic)

    Modes:
    - mode="2page": Complete double-sided edition (Page 1: Tutor Diagnostic; Page 2: Student Voice)
    - mode="1page": 1-page condensed edition
    All variations feature large, readable typography (10.5pt-18.5pt) and generous card padding strictly budget-checked for A4.
    """
    if cover_data is None:
        cover_data = {}
    
    var_lower = str(variation).lower()
    if "journal" in var_lower or "executive" in var_lower:
        return build_math_executive(cover_data, mode)
    elif "sprint" in var_lower:
        return build_math_sprint(cover_data, mode)
    else:
        return build_math_blueprint(cover_data, mode)


# =========================================================================
# THEORY BOOKLET GENERATOR (TEACHER & STUDENT EDITIONS)
# =========================================================================

def build_latex_theory_booklet_source(
    booklet_data: Dict[str, Any],
    mode: str = "teacher",
    term: Optional[int] = None,
    week: Optional[int] = None,
    has_logo: bool = True,
    font_theme: str = "charter"
) -> str:
    """Builds the complete LaTeX source string for an official DA Tuition Theory Booklet."""
    booklet_data = sanitize_out_of_syllabus_abs_y(booklet_data)
    year_level = booklet_data.get("year_level", "Mathematics")
    topic = booklet_data.get("topic", "Theory & Practice Booklet")
    concepts = booklet_data.get("concepts", [])
    mode_clean = str(mode).strip().lower()
    is_teacher = (mode_clean == "teacher")
    is_student_private = (mode_clean in ["student_private", "private", "student private"])
    is_student_class = (mode_clean in ["student_class", "class", "student class", "student"] and not is_student_private)
    empty_theory_box = is_student_class
    if is_teacher:
        edition_label = r"TEACHER MASTER THEORY \& NOTES"
        short_edition = "Teacher Master"
        badge_bg = "danavy"
    elif is_student_private:
        edition_label = r"THEORY STUDENT PRIVATE (COMPLETE NOTES)"
        short_edition = "Student Private"
        badge_bg = "dablue"
    else:
        edition_label = r"THEORY STUDENT CLASS (IN-CLASS WORKBOOK)"
        short_edition = "Student Class"
        badge_bg = "dagreen"
    year_str = str(year_level).strip()
    if year_str.lower().endswith("maths") or year_str.lower().endswith("mathematics"):
        subject_clean = year_str
    else:
        subject_clean = f"{year_str} Maths"
    clean_topic = clean_worksheet_topic_title(topic)
    topic_header = f"{subject_clean} --- {clean_topic}"

    font_key = booklet_data.get("font_theme") or font_theme or "charter"
    font_lines = get_font_latex_preamble(font_key)
    theory_box_title = (
        r"Core Concept \& Strategy"
        if is_student_class
        else r"\quad\dalightning\ DA SIGNATURE MASTERCLASS NOTES \quad\textbar\quad \ifstrempty{#1}{CORE INTUITION \& STRATEGY}{#1}"
    )

    tex_lines = [
        r"\documentclass[11pt,a4paper]{article}",
        r"\usepackage[top=1.8cm, bottom=1.8cm, left=1.5cm, right=1.5cm, headsep=7mm, footskip=8mm]{geometry}",
        r"\usepackage[utf8]{inputenc}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage{amsmath,amssymb,amsfonts}",
        *font_lines,
        r"\usepackage{fancyhdr}",
        r"\usepackage{graphicx}",
        r"\usepackage{adjustbox}",
        r"\usepackage{enumitem}",
        r"\usepackage{xcolor}",
        r"\usepackage{multicol}",
        r"\usepackage{needspace}",
        r"\usepackage{setspace}",
        r"\setstretch{1.18}",
        r"\setlength{\parskip}{0.3em plus 0.1em minus 0.05em}",
        r"\setlength{\headheight}{14.5pt}",
        r"\addtolength{\topmargin}{-2.5pt}",
        r"\hyphenpenalty=10000",
        r"\exhyphenpenalty=10000",
        r"\binoppenalty=10000",
        r"\relpenalty=10000",
        r"\tolerance=9999",
        r"\emergencystretch=2.5em",
        r"\usepackage{tcolorbox}",
        r"\tcbuselibrary{skins,breakable}",
        r"\usepackage{varwidth}",
        r"\usepackage{tikz}",
        r"\usetikzlibrary{arrows.meta,calc,angles,quotes,shapes.geometric,patterns,decorations.pathreplacing}",
        r"\usepackage{etoolbox}",
        r"\usepackage{eso-pic}",
        "",
        r"\pagestyle{fancy}",
        r"\fancyhf{}",
        f"\\fancyhead[L]{{\\parbox[b]{{0.62\\textwidth}}{{\\raggedright\\footnotesize\\bfseries {sanitize_for_latex(topic_header)}}}}}",
        f"\\fancyhead[R]{{\\parbox[b]{{0.36\\textwidth}}{{\\raggedleft\\footnotesize\\bfseries DA Tuition --- {short_edition}}}}}",
        r"\fancyfoot[C]{\thepage}",
        r"\renewcommand{\headrulewidth}{0.4pt}",
        "",
        r"\newcommand{\qmark}[1]{\unskip\hfill\penalty-50\null\hfill\mbox{\textbf{(#1~mark\ifnum#1>1s\fi)}}}",
        "",
        r"\definecolor{danavy}{RGB}{15, 23, 42}",
        r"\definecolor{dablue}{RGB}{30, 58, 138}",
        r"\definecolor{dagreen}{RGB}{5, 150, 105}",
        r"\definecolor{dagold}{RGB}{197, 155, 39}",
        r"\definecolor{dawine}{RGB}{136, 19, 55}",
        r"\definecolor{dalightbg}{RGB}{248, 250, 252}",
        r"\definecolor{slatebg}{RGB}{248, 250, 252}",
        r"\definecolor{goldbg}{RGB}{255, 252, 242}",
        r"\definecolor{pinkbg}{RGB}{255, 241, 242}",
        r"\definecolor{grayborder}{RGB}{226, 232, 240}",
        "",
        r"\newcommand{\dalightning}{\raisebox{-0.5pt}{\tikz[baseline=-0.2ex,scale=0.6]{\path[fill=dagold] (0,1.2ex) -- (0.8ex,1.2ex) -- (0.2ex,0.3ex) -- (0.9ex,0.3ex) -- (-0.1ex,-1.0ex) -- (0.3ex,-0.1ex) -- (-0.4ex,-0.1ex) -- cycle;}}}",
        r"\newcommand{\damastery}{\raisebox{-0.5pt}{\tikz[baseline=-0.2ex,scale=0.6]{\draw[fill=white,draw=dawine,thick] (0,0.4ex) circle (0.8ex); \fill[dawine] (0,0.4ex) circle (0.4ex);}}}",
        r"\newcommand{\datrap}{\raisebox{-0.5pt}{\tikz[baseline=-0.2ex,scale=0.6]{\path[fill=dawine] (0,1.2ex) -- (1.1ex,-0.7ex) -- (-1.1ex,-0.7ex) -- cycle; \node[font=\tiny\bfseries,text=white,inner sep=0pt] at (0,-0.1ex) {!};}}}",
        r"\DeclareUnicodeCharacter{26A1}{\dalightning}",
        r"\DeclareUnicodeCharacter{2713}{\ensuremath{\checkmark}}",
        r"\DeclareUnicodeCharacter{25B6}{\ensuremath{\blacktriangleright}}",
        r"\DeclareUnicodeCharacter{2022}{\textbullet}",
        "",
        r"\newtcolorbox{tocbox}[1][]{",
        r"    enhanced,",
        r"    colback=slatebg,",
        r"    colframe=danavy!30,",
        r"    boxrule=0.7pt,",
        r"    arc=4pt,",
        r"    left=14pt, right=14pt, top=12pt, bottom=12pt,",
        r"    title={\textbf{\color{danavy}\small \quad \ifstrempty{#1}{Table of Contents}{#1}}},",
        r"    coltitle=danavy,",
        r"    colbacktitle=slatebg,",
        r"    attach boxed title to top left={yshift=-2mm, xshift=4mm},",
        r"    boxed title style={boxrule=0pt, colframe=slatebg, arc=2pt},",
        r"    varwidth boxed title=0.88\linewidth,",
        r"    breakable",
        r"}",
        "",
        r"\newtcolorbox{theorybox}[1][]{",
        r"    enhanced,",
        r"    colback=white,",
        r"    colframe=danavy,",
        r"    boxrule=0.9pt,",
        r"    leftrule=3.5pt,",
        r"    arc=3.5pt,",
        r"    left=9pt, right=9pt, top=8pt, bottom=8pt,",
        r"    colbacktitle=danavy,",
        r"    coltitle=white,",
        r"    fonttitle=\bfseries\small\sffamily,",
        f"    title={{{theory_box_title}}},",
        r"    before skip=1pt,",
        r"    after skip=6pt,",
        r"    breakable,",
        r"    pad at break=2mm",
        r"}",
        "",
        r"\newtcolorbox{solutionbox}[1][]{",
        r"    enhanced,",
        r"    standard jigsaw,",
        r"    opacityback=0,",
        r"    colframe=dagreen,",
        r"    leftrule=3.5pt, rightrule=0.5pt, toprule=0.5pt, bottomrule=0.5pt,",
        r"    arc=3pt,",
        r"    left=8pt, right=8pt, top=7pt, bottom=7pt,",
        r"    title={\textbf{\color{dagreen!90!black}\small \ensuremath{\checkmark}~\ifstrempty{#1}{Model Worked Solution}{#1}}},",
        r"    coltitle=dagreen!90!black,",
        r"    colbacktitle=white,",
        r"    attach boxed title to top left={yshift=-2mm, xshift=4mm},",
        r"    boxed title style={boxrule=0.5pt, colframe=dagreen!30, arc=2pt},",
        r"    before skip=1pt,",
        r"    breakable",
        r"}",
        "",
        r"\newtcolorbox{practicesolutionbox}[1][]{",
        r"    enhanced,",
        r"    standard jigsaw,",
        r"    opacityback=0,",
        r"    colframe=dagreen!80!black,",
        r"    leftrule=2.8pt, rightrule=0.4pt, toprule=0.4pt, bottomrule=0.4pt,",
        r"    arc=2.5pt,",
        r"    left=6pt, right=6pt, top=4pt, bottom=4pt,",
        r"    boxsep=0.5pt,",
        r"    title={\textbf{\color{dagreen!90!black}\scriptsize \ensuremath{\checkmark}~\ifstrempty{#1}{Model Solution \& Marking}{#1}}},",
        r"    coltitle=dagreen!90!black,",
        r"    colbacktitle=white,",
        r"    attach boxed title to top left={yshift=-1.8mm, xshift=3mm},",
        r"    boxed title style={boxrule=0.4pt, colframe=dagreen!35, arc=2pt},",
        r"    varwidth boxed title=0.92\linewidth",
        r"}",
        "",
        r"\newtcolorbox{workingbox}[2][]{",
        r"    enhanced,",
        r"    standard jigsaw,",
        r"    opacityback=0,",
        r"    colframe=grayborder,",
        r"    boxrule=0.6pt,",
        r"    arc=3pt,",
        r"    left=8pt, right=8pt, top=6pt, bottom=6pt,",
        r"    height=#2,",
        r"    underlay={",
        r"        \node[anchor=north east, font=\bfseries\tiny\color{gray!45}] at (frame.north east) [xshift=-6pt, yshift=-5pt] {STUDENT WORKING SPACE};",
        r"    }",
        r"}",
        "",
        r"\AddToShipoutPictureBG{%",
        r"  \AtPageCenter{%",
        r"    \tikz[remember picture, overlay]{\node[opacity=0.08] at (0, 0) {\includegraphics[width=19.2cm,keepaspectratio]{da_logo_bw.png}};}%",
        r"  }%",
        r"}",
        "",
        r"\begin{document}",
        r"\thispagestyle{plain}",
        ""
    ]
    tex_lines.append(r"\raggedbottom")

    header_lines = [
        r"\noindent",
        r"\begin{minipage}[t]{0.70\textwidth}",
        r"\vspace{0pt}",
        r"\raggedright",
        f"{{\\huge \\textbf{{\\color{{danavy}}{sanitize_for_latex(subject_clean)}}}}}\\\\[0.1cm]",
        f"{{\\LARGE \\textbf{{\\color{{danavy}}{sanitize_for_latex(clean_topic)}}}}}\\\\[0.15cm]",

    ]
    meta_pills = []
    if term and week:
        meta_pills.append(f"\\tikz[baseline=-0.6ex]{{\\node[fill=danavy!10, text=danavy, rounded corners=3pt, inner sep=3pt, font=\\scriptsize\\bfseries] {{Term {term} $\\bullet$ Week {week}}};}}")
    elif term:
        meta_pills.append(f"\\tikz[baseline=-0.6ex]{{\\node[fill=danavy!10, text=danavy, rounded corners=3pt, inner sep=3pt, font=\\scriptsize\\bfseries] {{Term {term}}};}}")
    elif week:
        meta_pills.append(f"\\tikz[baseline=-0.6ex]{{\\node[fill=danavy!10, text=danavy, rounded corners=3pt, inner sep=3pt, font=\\scriptsize\\bfseries] {{Week {week}}};}}")
    meta_pills.append(f"\\tikz[baseline=-0.6ex]{{\\node[fill={badge_bg}!15, draw={badge_bg}!60, rounded corners=3pt, inner sep=3pt, font=\\scriptsize\\bfseries\\color{{{badge_bg}!90!black}}] {{{edition_label}}};}}")
    header_lines.append(" \\quad ".join(meta_pills))
    header_lines.extend([
        r"\end{minipage}%",
        r"\hfill",
        r"\begin{minipage}[t]{0.28\textwidth}",
        r"\vspace{0pt}",
        r"\raggedleft"
    ])
    tex_lines.extend(header_lines)

    if has_logo:
        tex_lines.append(r"\includegraphics[height=2.8cm,keepaspectratio]{da_logo.png}")
    else:
        tex_lines.append(r"{\Large \textbf{\color{danavy}DA TUITION}}")

    tex_lines.extend([
        r"\end{minipage}",
        r"\vspace{0.25cm}",
        r"\noindent",
        r"\tikz\draw[thick, color=danavy!25] (0,0) -- (\linewidth,0);",
        r"\vspace{0.15cm}",
        r"\noindent"
    ])

    if is_teacher:
        tex_lines.append(r"\textbf{Teacher Name:} \underline{\hspace{7.5cm}} \hfill \textbf{Date:} \underline{\hspace{3.5cm}}\\[0.25cm]")
    else:
        tex_lines.append(r"\textbf{Student Name:} \underline{\hspace{5.5cm}} \hfill \textbf{Class:} \underline{\hspace{2.2cm}} \hfill \textbf{Date:} \underline{\hspace{2.2cm}}\\[0.25cm]")

    tex_lines.append(r"\vspace{0.35cm}")
    tex_lines.append(r"\noindent")

    quick_answers = []
    q_counter = 1  # Global question counter across all Sets/concepts

    for c_idx, concept in enumerate(concepts, 1):
        raw_c_name = concept.get("concept_name") or concept.get("title") or concept.get("name") or f"Concept {c_idx}"
        c_name = clean_subtopic_title(raw_c_name)
        part_letter = chr(ord('A') + (c_idx - 1)) if c_idx <= 26 else f"A{c_idx}"

        # Resilient multi-key extraction for theory content across different LLM responses
        theory_content = ""
        for tk in ["theory_content", "theory_notes", "theory_text", "theory", "notes", "content", "theory_explanation", "explanation", "study_notes", "theory_summary", "concept_theory"]:
            t_val = concept.get(tk)
            if t_val:
                if isinstance(t_val, dict):
                    theory_content = t_val.get("theory_content") or t_val.get("content") or t_val.get("notes") or t_val.get("explanation") or "\n".join(f"- **{sk.replace('_', ' ').title()}**: {sv}" for sk, sv in t_val.items() if isinstance(sv, str))
                elif isinstance(t_val, list):
                    theory_content = "\n".join(str(item) for item in t_val)
                elif isinstance(t_val, str) and t_val.strip():
                    theory_content = t_val.strip()
                if theory_content:
                    break

        key_formulas = concept.get("key_formulas") or concept.get("formulas") or concept.get("formulae") or concept.get("key_formulae") or []
        if isinstance(key_formulas, str):
            key_formulas = [line.strip() for line in key_formulas.splitlines() if line.strip()]

        tutor_tips = concept.get("tutor_tips") or concept.get("tutor_tip") or concept.get("tips") or concept.get("tip") or concept.get("examiner_trap") or concept.get("trap") or ""
        tikz_diag = concept.get("tikz_diagram") or concept.get("diagram_tikz") or concept.get("diagram") or ""
        if isinstance(concept.get("study_notes"), dict):
            tikz_diag = tikz_diag or concept["study_notes"].get("tikz_diagram") or ""
        teacher_examples = concept.get("teacher_examples", [])
        practice_questions = concept.get("practice_questions", [])

        if c_idx > 1:
            tex_lines.append(r"\newpage")
        if len(concepts) == 1:
            heading_title = sanitize_for_latex(c_name)
        else:
            heading_title = f"Concept {part_letter}: {sanitize_for_latex(c_name)}"
        tex_lines.append(f"\\noindent{{\\Large\\textbf{{\\color{{danavy}}\\rule[-2pt]{{3.5pt}}{{14pt}}\\hspace{{6pt}}{heading_title}}}}}\\label{{sec:concept_{c_idx}}}\\\\[0.05cm]")
        if not is_student_class:
            tex_lines.append(r"\nopagebreak")
            tex_lines.append(r"\vspace{-0.22cm}")
            tex_lines.append(r"\nopagebreak")
        else:
            tex_lines.append(r"\vspace{-0.30cm}")

        # 1. Theory Box (Core Concept & Strategy)
        if not is_student_class:
            tex_lines.append(r"\begin{theorybox}[Core Concept \& Strategy]")
            th_box_content = build_masterclass_theory_box_content(
                theory_content=theory_content,
                key_formulas=key_formulas,
                tutor_tips=tutor_tips,
                concept_name=c_name,
                topic=topic,
                year_level=year_level,
                tikz_diagram=tikz_diag,
                is_student_scaffold=empty_theory_box
            )
            if not th_box_content or not str(th_box_content).strip():
                # Mandatory fallback: ensure theory box is NEVER missing or empty
                th_box_content = build_masterclass_theory_box_content(
                    theory_content="",
                    key_formulas=key_formulas,
                    tutor_tips=tutor_tips,
                    concept_name=c_name,
                    topic=topic,
                    year_level=year_level,
                    tikz_diagram=tikz_diag,
                    is_student_scaffold=empty_theory_box
                )
            tex_lines.append(th_box_content)
            tex_lines.append(r"\end{theorybox}")
            tex_lines.append(r"\vspace{0.25cm}")

        # 2. Teacher Demonstration Examples
        if teacher_examples:
            def private_example_reserve(example: Dict[str, Any]) -> str:
                """Reserve enough room for a question and its solution without wasting a short concept page."""
                problem = str(example.get("problem_text", ""))
                solution = str(example.get("worked_solution", ""))
                note = str(example.get("teaching_notes", ""))
                has_diagram = any(example.get(key) for key in (
                    "diagram_tikz", "tikz_diagram", "diagram", "solution_diagram_tikz", "solution_tikz", "solution_diagram"
                ))
                compact = (
                    len(problem) + len(solution) + len(note) < 280
                    and solution.count("\n") <= 2
                    and not has_diagram
                )
                return "6.0cm" if compact else "11.0cm"

            if is_student_private:
                first_reserve = private_example_reserve(teacher_examples[0])
                demo_needspace = "7.0cm" if first_reserve == "6.0cm" else "12.0cm"
                tex_lines.append(f"\\needspace{{{demo_needspace}}}")
            elif is_teacher:
                demo_needspace = "7.0cm"
                tex_lines.append(f"\\needspace{{{demo_needspace}}}")
            if is_student_class:
                tex_lines.append(f"\\noindent{{\\large\\bfseries\\color{{danavy}}Teacher Demonstration Examples}}\\label{{sec:demo_{c_idx}}}\\par\\vspace{{0.10cm}}")
            else:
                tex_lines.append(f"\\subsection*{{Teacher Demonstration Examples}}\\label{{sec:demo_{c_idx}}}")
            for ex in teacher_examples:
                ex_num = ex.get("example_num", 1)
                ex_title = ex.get("title", f"Example {ex_num}")
                ex_heading = format_teacher_example_heading(ex_num, ex_title, year_level=year_level)
                p_text = ex.get("problem_text", "")
                w_sol = ex.get("worked_solution", "")
                t_notes = ex.get("teaching_notes", "")
                ex_diag = ex.get("diagram_tikz") or ex.get("tikz_diagram") or ex.get("diagram")
                if not ex_diag or not str(ex_diag).strip():
                    fallback_diag = synthesize_network_diagram_from_text(p_text, topic=topic, concept_name=c_name)
                    if fallback_diag:
                        ex_diag = fallback_diag
                sol_diag = ex.get("solution_diagram_tikz") or ex.get("solution_tikz") or ex.get("solution_diagram")
                if not sol_diag or not str(sol_diag).strip():
                    if any(k in (p_text + " " + w_sol).lower() for k in ["sketch", "plot the", "draw the graph", "draw the curve", "graph of", "graph the"]):
                        fallback_tikz = get_sketch_solution_fallback_tikz(p_text, w_sol)
                        if fallback_tikz:
                            sol_diag = fallback_tikz

                # Private booklets must keep each demonstration question with
                # its worked solution. Reserve enough room to move the whole
                # example forward instead of leaving the question stranded at
                # the bottom of one page.
                ex_needspace = private_example_reserve(ex) if is_student_private else ("1.5cm" if not is_teacher else "5.0cm")
                tex_lines.append(f"\\needspace{{{ex_needspace}}}")
                if is_student_private:
                    tex_lines.append(r"\begin{samepage}")
                tex_lines.append(f"\\noindent\\textbf{{{ex_heading}}}\\\\[0.15cm]")
                p_lines = format_latex_question_with_subparts(p_text, as_item=False)
                p_body = "\n".join(p_lines)
                if is_student_private or is_student_class:
                    tex_lines.append(p_body + r"\par\vspace{0.02cm}")
                elif p_body.strip().endswith(r"\end{enumerate}"):
                    tex_lines.append(p_body + r"\vspace{-0.25cm}")
                else:
                    tex_lines.append(p_body + r"\par\vspace{-0.12cm}")
                if ex_diag and str(ex_diag).strip():
                    clean_ex_diag = sanitize_tikz_diagram(str(ex_diag).strip())
                    clean_ex_diag = re.sub(r'max totalheight=[0-9\.]+cm', 'max totalheight=2.8cm', clean_ex_diag)
                    clean_ex_diag = re.sub(r'max width=[0-9\.]+\\linewidth', r'max width=0.82\\linewidth', clean_ex_diag)
                    tex_lines.append(clean_ex_diag)
                    tex_lines.append(r"\vspace{0.15cm}")

                if is_teacher or is_student_private:
                    tex_lines.append(r"\begin{solutionbox}[{Model Whiteboard Solution}]")
                    if t_notes:
                        tex_lines.append(f"\\noindent\\textbf{{Teaching Note:}} {sanitize_for_latex(t_notes)}\\\\[0.15cm]")
                    tex_lines.append(format_latex_solution_steps(w_sol))
                    if sol_diag and str(sol_diag).strip():
                        clean_sol_diag = sanitize_tikz_diagram(str(sol_diag).strip())
                        clean_sol_diag = re.sub(r'max totalheight=[0-9\.]+cm', 'max totalheight=2.8cm', clean_sol_diag)
                        clean_sol_diag = re.sub(r'max width=[0-9\.]+\\linewidth', r'max width=0.82\\linewidth', clean_sol_diag)
                        tex_lines.append(r"\par\vspace{0.15cm}")
                        tex_lines.append(clean_sol_diag)
                    tex_lines.append(r"\end{solutionbox}")
                    tex_lines.append(r"\vspace{0.25cm}")
                else:
                    tex_lines.append(r"\vspace{0.10cm}" if is_student_class else r"\vspace{0.20cm}")
                if is_student_private:
                    tex_lines.append(r"\end{samepage}")

        # 3. Checking Understanding: independent student attempts immediately
        # after the demonstrations, with teacher solutions kept separate.
        checking_questions = concept.get("checking_understanding_questions", []) or concept.get("checking_questions", []) or []
        if checking_questions:
            tex_lines.append(r"\needspace{5.0cm}")
            tex_lines.append(r"\subsection*{Checking Understanding}\label{sec:checking_" + str(c_idx) + r"}")
            checking_instruction = (
                "Try each question independently, showing clear working in your exercise book."
                if is_student_class else
                "Try each question independently, showing clear working in the space provided."
            )
            tex_lines.append(f"\\noindent\\textit{{{checking_instruction}}}\\par\\vspace{{0.12cm}}")
            for check_idx, cq in enumerate(checking_questions, 1):
                check_num = cq.get("q_num", check_idx)
                check_text = cq.get("text") or cq.get("question_text") or cq.get("question") or ""
                check_diag = cq.get("diagram_tikz") or cq.get("tikz_diagram") or cq.get("diagram") or ""
                tex_lines.append(r"\needspace{3.5cm}")
                check_body = "\n".join(format_latex_question_with_subparts(check_text, as_item=False))
                tex_lines.append(f"\\noindent\\textbf{{{check_num}.}}\\enspace {check_body}\\par\\vspace{{0.08cm}}")
                if check_diag and str(check_diag).strip():
                    clean_check_diag = sanitize_tikz_diagram(str(check_diag).strip())
                    clean_check_diag = re.sub(r'max totalheight=[0-9\.]+cm', 'max totalheight=2.4cm', clean_check_diag)
                    clean_check_diag = re.sub(r'max width=[0-9\.]+\\linewidth', r'max width=0.78\\linewidth', clean_check_diag)
                    tex_lines.append(clean_check_diag)
                    tex_lines.append(r"\vspace{0.08cm}")
                if is_teacher:
                    tex_lines.append(r"\begin{solutionbox}[{Checking Understanding Solution}]")
                    answer = cq.get("final_answer") or cq.get("answer") or ""
                    worked = cq.get("worked_solution") or cq.get("solution") or ""
                    if answer:
                        tex_lines.append(f"\\textbf{{\\color{{dagreen}}Final Answer:}} {sanitize_for_latex(str(answer))}\\\\[0.05cm]")
                    if worked:
                        tex_lines.append(format_latex_solution_steps(str(worked)))
                    tex_lines.append(r"\end{solutionbox}")
                elif is_student_private:
                    tex_lines.append(r"\begin{workingbox}{3.0cm}")
                    tex_lines.append(r"\end{workingbox}")
                tex_lines.append(r"\vspace{0.18cm}")
            if is_student_class:
                tex_lines.append(r"\vspace{0.16cm}")

        # 4. Student Practice Questions
        if practice_questions:
            practice_questions = ensure_concept_practice_question_variety(practice_questions, c_name, topic)
            part_groups = group_booklet_questions_by_part(practice_questions)
            for part_title, part_qs in part_groups:
                if len(concepts) == 1:
                    heading_str = f"Practice ({part_title})"
                else:
                    heading_str = f"Practice {part_letter} ({part_title})"
                if is_teacher and any(k in part_title for k in ["Exam", "Extension", "Part 5", "Part 4"]):
                    part_needspace = "12.0cm"
                else:
                    part_needspace = "5.0cm" if not is_teacher else "7.0cm"
                tex_lines.append(f"\\needspace{{{part_needspace}}}")
                tex_lines.append(f"\\noindent{{\\textbf{{\\large\\color{{danavy}}{heading_str}}}}}\\par\\vspace{{0.12cm}}")
                itemsep = "0.45em" if is_teacher else "0.22em"
                tex_lines.append(f"\\begin{{enumerate}}[label=\\textbf{{\\arabic*.}}, leftmargin=1.6em, itemsep={itemsep}, start={q_counter}]")
                for pq in part_qs:
                    q_text = pq.get("text") or pq.get("question_text") or pq.get("question") or ""
                    ans = pq.get("final_answer") or pq.get("answer") or ""
                    worked = pq.get("worked_solution") or pq.get("solution") or ""
                    pq_diag = pq.get("diagram_tikz") or pq.get("tikz_diagram") or pq.get("diagram")
                    if not pq_diag or not str(pq_diag).strip():
                        fallback_diag = synthesize_network_diagram_from_text(q_text, topic=topic, concept_name=c_name)
                        if fallback_diag:
                            pq_diag = fallback_diag
                    pq_sol_diag = pq.get("solution_diagram_tikz") or pq.get("solution_tikz") or pq.get("solution_diagram")
                    if not pq_sol_diag or not str(pq_sol_diag).strip():
                        if any(k in (q_text + " " + worked).lower() for k in ["sketch", "plot the", "draw the graph", "draw the curve", "graph of", "graph the"]):
                            fallback_tikz = get_sketch_solution_fallback_tikz(q_text, worked)
                            if fallback_tikz:
                                pq_sol_diag = fallback_tikz

                    quick_answers.append({
                        "part": "" if len(concepts) == 1 else f"Part {part_letter}",
                        "concept": c_name,
                        "q_num": q_counter,
                        "ans": ans
                    })

                    # Split sub-parts (a), (b), (c) onto separate lines with math-safe parser
                    q_subpart_lines = format_latex_question_with_subparts(q_text, as_item=False)
                    item_body = "\n".join(q_subpart_lines)

                    # For practice questions, sanitize diagram and constrain height to 2.6cm and width to 0.82\linewidth
                    clean_pq_diag = ""
                    if pq_diag and str(pq_diag).strip():
                        diag_raw = sanitize_tikz_diagram(str(pq_diag).strip())
                        clean_pq_diag = re.sub(r'max totalheight=[0-9\.]+cm', 'max totalheight=2.6cm', diag_raw)
                        clean_pq_diag = re.sub(r'max width=[0-9\.]+\\linewidth', r'max width=0.82\\linewidth', clean_pq_diag)

                    item_lines = [
                        r"\needspace{3.2cm}",
                        r"\begin{samepage}",
                        r"\item",
                        item_body
                    ]
                    if clean_pq_diag:
                        item_lines.append(r"\vspace{0.06cm}")
                        item_lines.append(clean_pq_diag)
                    if is_teacher:
                        item_lines.append(r"\par\vspace{0.08cm}")
                        item_lines.append(r"\begin{practicesolutionbox}")
                        if ans:
                            item_lines.append(f"{{\\small\\textbf{{\\color{{dagreen}}Final Answer:}} {sanitize_for_latex(ans)}}}\\\\[0.05cm]")
                        if worked:
                            fmt_w = format_latex_practice_solution(worked)
                            item_lines.append(f"{{\\footnotesize\\color{{danavy!85!black}}\\textbf{{Step-by-Step Working:}}\\par\\vspace{{0.03cm}}\n{fmt_w}}}")
                        if pq_sol_diag and str(pq_sol_diag).strip():
                            clean_pq_sol_diag = sanitize_tikz_diagram(str(pq_sol_diag).strip())
                            clean_pq_sol_diag = re.sub(r'max totalheight=[0-9\.]+cm', 'max totalheight=2.6cm', clean_pq_sol_diag)
                            clean_pq_sol_diag = re.sub(r'max width=[0-9\.]+\\linewidth', r'max width=0.82\\linewidth', clean_pq_sol_diag)
                            item_lines.append(r"\par\vspace{0.08cm}")
                            item_lines.append(clean_pq_sol_diag)
                        item_lines.append(r"\end{practicesolutionbox}")
                    item_lines.append(r"\end{samepage}")
                    tex_lines.append("\n".join(item_lines))
                    q_counter += 1
                tex_lines.append(r"\end{enumerate}")
                tex_lines.append(r"\vspace{0.25cm}")

    # Quick Answers for Student
    if is_student_private and quick_answers:
        tex_lines.append(r"\newpage")
        tex_lines.append(r"\section*{Plain Answers (For Student Self-Checking)}\label{sec:answers}")
        tex_lines.append(r"\noindent Use these answers to verify your final results after completing full working in your exercise book.\\[0.3cm]")
        if len(quick_answers) <= 6:
            tex_lines.append(r"\begin{enumerate}[labelindent=0pt, labelwidth=2.5cm, labelsep=0.3cm, leftmargin=*, align=left, itemsep=0.45em]")
            for qa in quick_answers:
                if qa.get("part"):
                    tex_lines.append(f"\\item[\\textbf{{{qa['part']} Q{qa['q_num']}.}}] {format_answer_parts_latex(sanitize_for_latex(qa['ans']))}")
                else:
                    tex_lines.append(f"\\item[\\textbf{{Q{qa['q_num']}.}}] {format_answer_parts_latex(sanitize_for_latex(qa['ans']))}")
            tex_lines.append(r"\end{enumerate}")
        else:
            chunk_size = 56
            for chunk_start in range(0, len(quick_answers), chunk_size):
                if chunk_start > 0:
                    tex_lines.append(r"\newpage")
                chunk = quick_answers[chunk_start:chunk_start + chunk_size]
                half = (len(chunk) + 1) // 2
                col1 = chunk[:half]
                col2 = chunk[half:]
                tex_lines.append(r"\noindent")
                tex_lines.append(r"\begin{minipage}[t]{0.485\linewidth}")
                tex_lines.append(r"\begin{enumerate}[labelindent=0pt, labelwidth=2.5cm, labelsep=0.2cm, leftmargin=*, align=left, itemsep=0.22em, parsep=0pt]")
                for qa in col1:
                    if qa.get("part"):
                        tex_lines.append(f"\\item[\\textbf{{{qa['part']} Q{qa['q_num']}.}}] {format_answer_parts_latex(sanitize_for_latex(qa['ans']))}")
                    else:
                        tex_lines.append(f"\\item[\\textbf{{Q{qa['q_num']}.}}] {format_answer_parts_latex(sanitize_for_latex(qa['ans']))}")
                tex_lines.append(r"\end{enumerate}")
                tex_lines.append(r"\end{minipage}\hfill")
                tex_lines.append(r"\begin{minipage}[t]{0.485\linewidth}")
                tex_lines.append(r"\begin{enumerate}[labelindent=0pt, labelwidth=2.5cm, labelsep=0.2cm, leftmargin=*, align=left, itemsep=0.22em, parsep=0pt]")
                for qa in col2:
                    if qa.get("part"):
                        tex_lines.append(f"\\item[\\textbf{{{qa['part']} Q{qa['q_num']}.}}] {format_answer_parts_latex(sanitize_for_latex(qa['ans']))}")
                    else:
                        tex_lines.append(f"\\item[\\textbf{{Q{qa['q_num']}.}}] {format_answer_parts_latex(sanitize_for_latex(qa['ans']))}")
                tex_lines.append(r"\end{enumerate}")
                tex_lines.append(r"\end{minipage}")

    tex_lines.append(r"\end{document}")
    return "\n".join(tex_lines)


def count_unescaped_dollars(s: str) -> int:
    """Counts unescaped $ signs in a string, accounting for preceding backslashes."""
    count = 0
    i = 0
    while i < len(s):
        if s[i] == "$":
            bs = 0
            k = i - 1
            while k >= 0 and s[k] == "\\":
                bs += 1
                k -= 1
            if bs % 2 == 0:
                count += 1
        i += 1
    return count


def sanitize_latex_compilation_safety(tex: str) -> str:
    """
    Final document-level safety net applied before passing .tex to pdflatex.
    Guarantees:
    1. Literal '\\n' artifacts from LLM outputs are converted to real linebreaks or spaces.
    2. Paired '$$...$$' are normalized to '\\[...\\]' and stray '$$' are reduced to '$'.
    3. Trailing '.$' or ',$' misplaced outside math delimiters are corrected to '$.' and '$,'.
    4. Each line/paragraph has balanced unescaped '$' so an open inline math block never
       crosses into subsequent lines, environments, or paragraphs.
    5. Any unclosed display math '\\[ ... \\]' is safely closed before box boundaries or \\end{document}.
    6. Any unclosed tracked LaTeX environments (tcolorbox, solutionbox, practicesolutionbox,
       enumerate, itemize, tabular, center) are safely unwound and closed before \\end{document}.
    """
    if not tex:
        return ""

    # 1. Fix accidental double dollars
    tex = re.sub(r"\$\$(.*?)\$\$", r"\\[\1\\]", tex, flags=re.DOTALL)
    tex = tex.replace("$$", "$")

    # 3. Fix accidental trailing ".$" or ",$" at end of line/box
    tex = re.sub(r"\.\$(?=\s*(?:\\par|\\\\|\n|$))", r"$.", tex)
    tex = re.sub(r",\$(?=\s*(?:\\par|\\\\|\n|$))", r"$,", tex)

    # Clean up percentage math wrappers and strip accidental lone dollar before percent ($5.4% -> 5.4%)
    tex = re.sub(r"(?<!\\)\$(\s*\d+(?:\.\d+)?\s*)\\?%\$", r"\1\\%", tex)
    tex = re.sub(r"(?<!\\)\$(?=\s*\d+(?:\.\d+)?\s*\\?%)", "", tex)

    # Pre-convert any stray unescaped currency dollars ($7500, $7 500, $ 50, $7,500.50, $100 000) to \$
    # Must NOT match percentages, closing dollars, decimal points, or comma-separated lists of math numbers like ($1, 2, 3, 4$)
    curr_pat = re.compile(
        r"(?<!\\)\$"
        r"(?="
        r"\s*\d+(?:[,\s]\d{3})*(?:\.\d+)?"
        r"(?![0-9]|\.[0-9])"                 # Must not leave digits or decimal behind!
        r"(?!\s*!)"                          # $6!$ and $6! = ...$ are factorial math, not currency
        r"(?!\s*\$)"                         # Must not be followed by closing $ (e.g. $0.4$, $0.006$)
        r"(?!\s*[,+\-*/=^<>](?:\s*\d|\s*[a-zA-Z]|\s*\\))"
        r"(?:"
          r"\s*%"
          r"|\s+[a-zA-Z]+"
          r"|/[a-zA-Z]+"
          r"|[.,;:?!)\]\}\s]"
          r"|$"
        r")"
        r")"
    )
    tex = curr_pat.sub(r"\\$", tex)

    # Strip accidental stray dollar sign inside parenthesized number lists like ($1, 2, 3, 4) -> (1, 2, 3, 4)
    tex = re.sub(r"\(\$(\d+(?:\s*,\s*\d+)*)\)", r"(\1)", tex)

    # 4. Line-by-line unescaped dollar balancing
    lines = tex.split("\n")
    fixed_lines = []
    in_verbatim = False
    in_tikz = False

    for line in lines:
        if r"\begin{verbatim}" in line:
            in_verbatim = True
        elif r"\end{verbatim}" in line:
            in_verbatim = False
        elif r"\begin{tikzpicture}" in line:
            in_tikz = True
        elif r"\end{tikzpicture}" in line:
            in_tikz = False

        if in_verbatim or in_tikz:
            fixed_lines.append(line)
            continue

        stripped = line.strip()
        if not stripped or stripped.startswith("%"):
            fixed_lines.append(line)
            continue

        # Fix accidental over-escaped percent signs (\\% -> \%) so LaTeX never treats % as a comment
        if not in_tikz:
            line = re.sub(r"\\{2,}%", r"\\%", line)

        c = count_unescaped_dollars(line)
        if c % 2 != 0:
            # Odd number of $ on a single line!
            # Check if line has a trailing lone .$ or double $ that can be cleaned
            if re.search(r"\$\.\$$", stripped):
                line = re.sub(r"\$\.\$$", "$.", line)
            elif stripped.startswith(r"\begin{") or stripped.startswith(r"\end{"):
                line = line + "$"
            elif re.search(r"\}\s*(?:\\\\(?:\[[^\]]*\])?)?\s*$", line):
                # When closing brace precedes \\ or line-end, balance $ inside the brace
                m_b = re.search(r"(\}\s*(?:\\\\(?:\[[^\]]*\])?)?\s*)$", line)
                line = line[:m_b.start(1)] + "$" + line[m_b.start(1):]
            elif line.endswith(r"\par") or line.endswith(r"\\"):
                m_end = re.search(r"(\\par|\\\\)\s*$", line)
                if m_end:
                    idx = m_end.start()
                    line = line[:idx] + "$" + line[idx:]
                else:
                    line = line + "$"
            elif re.search(r"\\hfill\{.*?\}\s*$", line):
                m_hf = re.search(r"(\\hfill\{.*?\}\s*)$", line)
                if m_hf:
                    idx = m_hf.start()
                    line = line[:idx] + "$" + line[idx:]
                else:
                    line = line + "$"
            else:
                line = line + "$"

        fixed_lines.append(line)

    tex = "\n".join(fixed_lines)

    # 5. Fix unclosed display math \[ ... \]
    open_disp = 0
    result_lines = []
    for line in tex.split("\n"):
        open_count = len(re.findall(r"(?<!\\)\\\[(?![\d\.\-a-zA-Z]+\s*\])", line))
        close_count = len(re.findall(r"(?<!\\)\\\]", line))
        open_disp += open_count - close_count

        if open_disp > 0 and any(kw in line for kw in [
            r"\end{tcolorbox}", r"\end{solutionbox}", r"\end{practicesolutionbox}",
            r"\end{whiteboardsolutionbox}", r"\end{conceptbox}", r"\end{document}"
        ]):
            line = (r"\]" * open_disp) + "\n" + line
            open_disp = 0
        elif open_disp < 0:
            open_disp = 0
        result_lines.append(line)

    tex = "\n".join(result_lines)

    # 6. Auto-close environments before \end{document}
    TRACKED_ENVS = {
        "tcolorbox", "solutionbox", "practicesolutionbox", "conceptbox",
        "whiteboardsolutionbox", "theorybox", "tocbox", "workingbox",
        "studentworkingbox", "practicemodelsolutionbox", "markingrubricbox",
        "enumerate", "itemize", "center",
        "tabular", "tabular*", "adjustbox", "minipage"
    }
    env_stack = []
    final_lines = []
    for line in tex.split("\n"):
        if r"\end{document}" in line:
            while env_stack:
                env = env_stack.pop()
                final_lines.append(f"\\end{{{env}}}")
            final_lines.append(line)
            continue

        begins = re.findall(r"\\begin\{([a-zA-Z0-9\*]+)\}", line)
        ends = re.findall(r"\\end\{([a-zA-Z0-9\*]+)\}", line)

        for b in begins:
            if b in TRACKED_ENVS:
                env_stack.append(b)

        for e in ends:
            if e in TRACKED_ENVS:
                if env_stack and env_stack[-1] == e:
                    env_stack.pop()
                elif e in env_stack:
                    while env_stack and env_stack[-1] != e:
                        unwound = env_stack.pop()
                        final_lines.append(f"\\end{{{unwound}}}")
                    if env_stack:
                        env_stack.pop()

        final_lines.append(line)

    tex = "\n".join(final_lines)
    # Strip any trailing blank page causes (redundant page breaks or large vspaces right before \end{document})
    tex = re.sub(r"(?:\\newpage\s*|\\clearpage\s*|\\vspace\{[^}]*\}\s*)+\\end\{document\}", r"\\end{document}", tex)
    return tex


def strip_all_tikz_diagrams(tex: str) -> str:
    """
    Robustly removes all TikZ diagrams and their enclosing wrappers from LaTeX source
    without leaving orphaned environments, broken adjustboxes, or unclosed colorboxes.
    """
    if not tex:
        return ""

    # 1. Cleanly strip Card 2.5 (Visual Model & Key Diagram) by matching colorbox/parbox braces
    idx = 0
    while True:
        pos = tex.find("VISUAL MODEL", idx)
        if pos == -1:
            break
        start_box = tex.rfind(r"\noindent\colorbox{slatebg}", 0, pos)
        if start_box == -1:
            idx = pos + 12
            continue
        # Find first arg {slatebg}
        b1 = tex.find("{", start_box)
        b1_end = tex.find("}", b1) if b1 != -1 else -1
        if b1 == -1 or b1_end == -1:
            idx = pos + 12
            continue
        # Find second arg {\parbox...}
        b2 = tex.find("{", b1_end)
        if b2 == -1:
            idx = pos + 12
            continue
        count = 0
        end_box = -1
        for i in range(b2, len(tex)):
            if tex[i] == "{" and (i == 0 or tex[i-1] != "\\"):
                count += 1
            elif tex[i] == "}" and (i == 0 or tex[i-1] != "\\"):
                count -= 1
                if count == 0:
                    end_box = i + 1
                    break
        if end_box != -1:
            while end_box < len(tex) and tex[end_box] in ("\n", "\r", " "):
                end_box += 1
            trail_glue = r"\par\vspace{0.12cm}\noindent"
            if tex[end_box:end_box+len(trail_glue)] == trail_glue:
                end_box += len(trail_glue)
                while end_box < len(tex) and tex[end_box] in ("\n", "\r", " "):
                    end_box += 1
            tex = tex[:start_box] + tex[end_box:]
            idx = start_box
        else:
            idx = pos + 12

    # 2. Strip adjustbox blocks containing tikzpicture (with or without centering)
    tex = re.sub(
        r"\\begin\{center\}\s*\\begin\{adjustbox\}\{[^}]*\}\s*\\begin\{tikzpicture\}[\s\S]*?\\end\{tikzpicture\}\s*\\end\{adjustbox\}\s*\\end\{center\}",
        "",
        tex
    )
    tex = re.sub(
        r"\\begin\{adjustbox\}\{[^}]*\}\s*\\begin\{tikzpicture\}[\s\S]*?\\end\{tikzpicture\}\s*\\end\{adjustbox\}",
        "",
        tex
    )

    # 3. Strip any standalone tikzpicture environments
    tex = re.sub(r"\\begin\{center\}\s*\\begin\{tikzpicture\}[\s\S]*?\\end\{tikzpicture\}\s*\\end\{center\}", "", tex)
    tex = re.sub(r"\\begin\{tikzpicture\}[\s\S]*?\\end\{tikzpicture\}", "", tex)

    # 4. Clean up any empty adjustbox or center leftovers
    tex = re.sub(r"\\begin\{adjustbox\}\{[^}]*\}\s*\\end\{adjustbox\}", "", tex)
    tex = re.sub(r"\\begin\{center\}\s*\\end\{center\}", "", tex)
    tex = re.sub(r"(\\vspace\{[^}]*\}\s*){2,}", r"\1", tex)

    return sanitize_latex_compilation_safety(tex)


def generate_latex_theory_booklet_pdf(
    booklet_data: Dict[str, Any],
    mode: str = "teacher",
    term: Optional[int] = None,
    week: Optional[int] = None,
    font_theme: str = "charter"
) -> Optional[bytes]:
    """Compiles publication-quality Theory Booklet PDF with LaTeX, TikZ, and Matplotlib graphs."""
    pdflatex_bin = find_pdflatex()
    if not pdflatex_bin:
        return None

    tmp_dir = tempfile.mkdtemp()
    try:
        has_logo = False
        if os.path.exists(LOGO_PATH):
            shutil.copy(LOGO_PATH, os.path.join(tmp_dir, "da_logo.png"))
            has_logo = True
        if os.path.exists(LOGO_TRANSPARENT_PATH):
            shutil.copy(LOGO_TRANSPARENT_PATH, os.path.join(tmp_dir, "da_logo_transparent.png"))
        elif os.path.exists(LOGO_PATH):
            shutil.copy(LOGO_PATH, os.path.join(tmp_dir, "da_logo_transparent.png"))
        bw_logo_src = ensure_bw_logo()
        if os.path.exists(bw_logo_src):
            shutil.copy(bw_logo_src, os.path.join(tmp_dir, "da_logo_bw.png"))

        full_tex = build_latex_theory_booklet_source(
            booklet_data=booklet_data,
            mode=mode,
            term=term,
            week=week,
            has_logo=has_logo,
            font_theme=font_theme
        )
        full_tex = inject_python_graphs(full_tex, tmp_dir)
        full_tex = sanitize_latex_compilation_safety(full_tex)

        tex_path = os.path.join(tmp_dir, "theory_booklet.tex")
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(full_tex)

        expected_theoryboxes = full_tex.count(r"\begin{theorybox}")

        for _ in range(2):
            subprocess.run(
                [pdflatex_bin, "-interaction=nonstopmode", "theory_booklet.tex"],
                cwd=tmp_dir,
                capture_output=True,
                check=False
            )

        pdf_path = os.path.join(tmp_dir, "theory_booklet.pdf")
        log_path = os.path.join(tmp_dir, "theory_booklet.log")

        def _verify_all_boxes_rendered(path: str, expected_cnt: int) -> bool:
            if not os.path.exists(path) or expected_cnt == 0:
                return os.path.exists(path)
            try:
                import pypdfium2 as pdfium
                doc = pdfium.PdfDocument(path)
                found = 0
                for p in doc:
                    txt = p.get_textpage().get_text_range()
                    if "DA SIGNATURE MASTERCLASS NOTES" in txt or "CORE INTUITION & STRATEGY" in txt or "THE BIG IDEA" in txt:
                        found += 1
                return found >= expected_cnt
            except Exception:
                return False

        has_tcb_savebox_error = False
        if os.path.exists(log_path):
            try:
                with open(log_path, "r", encoding="utf-8", errors="ignore") as lf:
                    log_txt = lf.read()
                if r"\begin{tcb@savebox}" in log_txt or "ended by \\end{theorybox}" in log_txt:
                    has_tcb_savebox_error = True
            except Exception:
                pass

        needs_fallback = (
            not os.path.exists(pdf_path)
            or has_tcb_savebox_error
            or not _verify_all_boxes_rendered(pdf_path, expected_theoryboxes)
        )

        if needs_fallback:
            # Resilient fallback: if a TikZ diagram or internal macro had fatal errors that dropped theory boxes, strip TikZ cleanly and recompile
            repaired_tex = strip_all_tikz_diagrams(full_tex)
            with open(tex_path, "w", encoding="utf-8") as f:
                f.write(repaired_tex)
            for _ in range(2):
                subprocess.run(
                    [pdflatex_bin, "-interaction=nonstopmode", "theory_booklet.tex"],
                    cwd=tmp_dir,
                    capture_output=True,
                    check=False
                )

        if os.path.exists(pdf_path):
            with open(pdf_path, "rb") as f:
                raw_bytes = f.read()
            topic_str = str(booklet_data.get("topic", ""))
            yl_str = str(booklet_data.get("year_level", ""))
            return prune_trailing_blank_pages(raw_bytes, topic=topic_str, year_level=yl_str)
        else:
            log_path = os.path.join(tmp_dir, "theory_booklet.log")
            if os.path.exists(log_path):
                try:
                    shutil.copy(log_path, "scratch/last_theory_compile_error.log")
                except Exception:
                    pass
            if os.path.exists(tex_path):
                try:
                    shutil.copy(tex_path, "scratch/last_theory_compile_error.tex")
                except Exception:
                    pass
            safe_print("[Theory Booklet LaTeX Error] Compilation failed. Saved log to scratch/last_theory_compile_error.log")

    except Exception as e:
        safe_print(f"[Theory Booklet LaTeX Exception] {e}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return None


def generate_theory_booklet_docx(
    booklet_data: Dict[str, Any],
    mode: str = "student",
    term: Optional[int] = None,
    week: Optional[int] = None
) -> Optional[bytes]:
    """Generates an authentic editable Microsoft Word (.docx) Theory Booklet."""
    full_tex = build_latex_theory_booklet_source(
        booklet_data=booklet_data,
        mode=mode,
        term=term,
        week=week,
        has_logo=True
    )
    return docx_generator.latex_to_docx(full_tex)


def generate_reportlab_theory_booklet_pdf(
    booklet_data: Dict[str, Any],
    mode: str = "teacher",
    term: Optional[int] = None,
    week: Optional[int] = None
) -> bytes:
    """ReportLab fallback engine for Theory Booklet PDF generation."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()
    story = []
    mode_clean = str(mode).strip().lower()
    is_teacher = (mode_clean == "teacher")
    is_student_private = (mode_clean in ["student_private", "private", "student private"])
    is_student_class = (mode_clean in ["student_class", "class", "student class", "student"] and not is_student_private)
    if is_teacher:
        edition_label = "TEACHER MASTER THEORY & NOTES"
        badge_color = "#0F2240"
    elif is_student_private:
        edition_label = "THEORY STUDENT PRIVATE (COMPLETE NOTES)"
        badge_color = "#1C4E9C"
    else:
        edition_label = "THEORY STUDENT CLASS (IN-CLASS WORKBOOK)"
        badge_color = "#226E3E"
    year_level = booklet_data.get("year_level", "Mathematics")
    topic = booklet_data.get("topic", "Theory & Practice Booklet")
    clean_topic = clean_worksheet_topic_title(topic)
    concepts = booklet_data.get("concepts", [])

    logo_el = get_proportional_logo(target_height=42.0, max_width=65.0)
    tw_sub = f"Term {term} &nbsp; Week {week} &nbsp; • &nbsp; " if (term and week) else ""
    hdr_html = f"""
    <font size="14"><b>{year_level} Mathematics</b></font><br/>
    <font size="10">{tw_sub}<b>{clean_topic}</b></font><br/>
    <font size="9" color="{badge_color}"><b>{edition_label}</b></font>
    """
    hdr_table = Table(
        [[logo_el if logo_el else Paragraph("<b>DA TUITION</b>", styles['Normal']),
          Paragraph(hdr_html, styles['Normal'])]],
        colWidths=[70, 450]
    )
    hdr_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6)
    ]))
    story.append(hdr_table)
    story.append(Spacer(1, 10))

    quick_answers = []

    for c_idx, c in enumerate(concepts, 1):
        c_name = clean_subtopic_title(c.get("concept_name", f"Concept {c_idx}"))
        part_letter = chr(ord('A') + (c_idx - 1)) if c_idx <= 26 else f"A{c_idx}"
        story.append(Paragraph(f"<b>Part {part_letter}: {c_name}</b>", styles['Heading2']))
        story.append(Spacer(1, 4))

        if not is_student_class:
            th_text = format_math_for_reportlab(c.get("theory_content", ""))
            # Space out double newlines
            th_text = th_text.replace("\n\n", "<br/><br/>")
            theory_paras = [Paragraph(f"<b>Core Theory &amp; Rules:</b><br/>{th_text}", styles['Normal'])]
            if c.get("tutor_tips"):
                tip_txt = format_math_for_reportlab(c.get("tutor_tips", ""))
                theory_paras.append(Paragraph(f"<i>Exam Tips: {tip_txt}</i>", styles['Normal']))

            th_box = Table([[p] for p in theory_paras], colWidths=[520])
            th_box.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F2F6FC")),
                ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#1C4E9C")),
                ('PADDING', (0,0), (-1,-1), 8)
            ]))
            story.append(th_box)
            story.append(Spacer(1, 8))

        if not is_student_class and c.get("key_formulas"):
            kf_lines = "<br/>• " + "<br/>• ".join([format_math_for_reportlab(f) for f in c.get("key_formulas", [])])
            f_box = Table([[Paragraph(f"<b>Essential Formulae:</b>{kf_lines}", styles['Normal'])]], colWidths=[520])
            f_box.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#FFFFFF")),
                ('BOX', (0,0), (-1,-1), 1.2, colors.HexColor("#0F2240")),
                ('PADDING', (0,0), (-1,-1), 8)
            ]))
            story.append(f_box)
            story.append(Spacer(1, 10))

        if c.get("teacher_examples"):
            story.append(Paragraph("<b>Teacher Demonstration Examples</b>", styles['Heading3']))
        for ex in c.get("teacher_examples", []):
            ex_num = ex.get("example_num", 1)
            raw_ex_title = ex.get("title", f"Example {ex_num}")
            clean_t = clean_ex_title(raw_ex_title)
            p_text = format_math_for_reportlab(ex.get("problem_text", ""))
            story.append(Paragraph(f"<b>Example {ex_num}: {clean_t}</b>", styles['Heading3']))
            story.append(Paragraph(p_text, styles['Normal']))
            story.append(Spacer(1, 4))

            if is_teacher or is_student_private:
                sol_txt = format_math_for_reportlab(ex.get("worked_solution", ""))
                sol_box = Table([[Paragraph(f"<b>Model Solution:</b><br/>{sol_txt}", styles['Normal'])]], colWidths=[520])
                sol_box.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#EBF5EE")),
                    ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#226E3E")),
                    ('PADDING', (0,0), (-1,-1), 6)
                ]))
                story.append(sol_box)
            elif is_student_class:
                pass
            else:
                work_box = Table([[Paragraph("<i>Class Working &amp; Notes:</i>", styles['Normal'])]], colWidths=[520], rowHeights=[100])
                work_box.setStyle(TableStyle([
                    ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#CCCCCC")),
                    ('VALIGN', (0,0), (-1,-1), 'TOP'),
                    ('PADDING', (0,0), (-1,-1), 6)
                ]))
                story.append(work_box)
            story.append(Spacer(1, 10))

        checking_questions = c.get("checking_understanding_questions", []) or c.get("checking_questions", []) or []
        if checking_questions:
            story.append(Paragraph("<b>Checking Understanding</b>", styles['Heading3']))
            checking_instruction = (
                "Try each question independently, showing clear working in your exercise book."
                if is_student_class else
                "Try each question independently, showing clear working in the space provided."
            )
            story.append(Paragraph(f"<i>{checking_instruction}</i>", styles['Normal']))
            for check_idx, cq in enumerate(checking_questions, 1):
                check_num = cq.get("q_num", check_idx)
                check_text = format_math_for_reportlab(cq.get("text") or cq.get("question_text") or cq.get("question") or "")
                story.append(Paragraph(f"<b>{check_num}.</b> {check_text}", styles['Normal']))
                if is_teacher:
                    ans_txt = format_math_for_reportlab(cq.get("final_answer") or cq.get("answer") or "")
                    sol_txt = format_math_for_reportlab(cq.get("worked_solution") or cq.get("solution") or "")
                    story.append(Paragraph(f"<b>Solution:</b><br/>{sol_txt}<br/><b>Final Answer:</b> {ans_txt}", styles['Normal']))
                elif is_student_private:
                    work_box = Table([[Paragraph("<i>Student working:</i>", styles['Normal'])]], colWidths=[520], rowHeights=[90])
                    work_box.setStyle(TableStyle([
                        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#CCCCCC")),
                        ('VALIGN', (0,0), (-1,-1), 'TOP'),
                        ('PADDING', (0,0), (-1,-1), 6)
                    ]))
                    story.append(work_box)
                story.append(Spacer(1, 8))

        for pq in c.get("practice_questions", []):
            pq_num = pq.get("q_num", 1)
            diff = pq.get("difficulty", "Medium")
            part_tier = get_booklet_part_tier(diff)
            q_text = format_math_for_reportlab(pq.get("text", ""))
            quick_answers.append({"label": f"Part {part_letter} Q{pq_num}", "ans": pq.get("final_answer", "")})

            h_label = f"Practice {part_letter} ({part_tier}) --- Q{pq_num}" if len(concepts) > 1 else f"Practice ({part_tier}) --- Q{pq_num}"
            story.append(Paragraph(f"<b>{h_label}</b>", styles['Heading4']))
            story.append(Paragraph(q_text, styles['Normal']))
            story.append(Spacer(1, 4))

            if is_teacher:
                w_txt = format_math_for_reportlab(pq.get("worked_solution", ""))
                ans_txt = format_math_for_reportlab(pq.get("final_answer", ""))
                pr_box = Table([[Paragraph(f"<b>Solution:</b><br/>{w_txt}<br/><b>Final Answer:</b> {ans_txt}", styles['Normal'])]], colWidths=[520])
                pr_box.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F0F4FA")),
                    ('BOX', (0,0), (-1,-1), 0.8, colors.HexColor("#0F2240")),
                    ('PADDING', (0,0), (-1,-1), 6)
                ]))
                story.append(pr_box)
            elif is_student_class:
                pass
            else:
                h = 110 if diff == "Hard" else 85
                work_box = Table([[Paragraph("<i>Working Space:</i>", styles['Normal'])]], colWidths=[520], rowHeights=[h])
                work_box.setStyle(TableStyle([
                    ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#CCCCCC")),
                    ('VALIGN', (0,0), (-1,-1), 'TOP'),
                    ('PADDING', (0,0), (-1,-1), 6)
                ]))
                story.append(work_box)
            story.append(Spacer(1, 10))

    if is_student_private and quick_answers:
        story.append(PageBreak())
        story.append(Paragraph("<b>Plain Answers (For Quick Self-Checking)</b>", styles['Heading2']))
        story.append(Spacer(1, 8))
        ans_rows = [[Paragraph(f"<b>{qa['label']}:</b> {format_math_for_reportlab(qa['ans'])}", styles['Normal'])] for qa in quick_answers]
        ans_table = Table(ans_rows, colWidths=[520])
        story.append(ans_table)

    doc.build(story)
    return buffer.getvalue()


def generate_theory_booklet_pdf(
    booklet_data: Dict[str, Any],
    mode: str = "teacher",
    term: Optional[int] = None,
    week: Optional[int] = None,
    font_theme: str = "charter"
) -> bytes:
    """
    Generates an official DA Tuition Theory Booklet PDF in either 'teacher' or 'student' mode.
    Attempts native LaTeX compilation first with tcolorbox.
    Falls back to ReportLab if pdflatex is unavailable.
    """
    latex_bytes = generate_latex_theory_booklet_pdf(
        booklet_data=booklet_data,
        mode=mode,
        term=term,
        week=week,
        font_theme=font_theme
    )
    topic_str = str(booklet_data.get("topic", ""))
    yl_str = str(booklet_data.get("year_level", ""))
    if latex_bytes:
        return prune_trailing_blank_pages(latex_bytes, topic=topic_str, year_level=yl_str)
    rl_bytes = generate_reportlab_theory_booklet_pdf(
        booklet_data=booklet_data,
        mode=mode,
        term=term,
        week=week
    )
    return prune_trailing_blank_pages(rl_bytes, topic=topic_str, year_level=yl_str)


# ==============================================================================
# REVIEW BOOKLET GENERATION (REVISION & EXAM PREP)
# ==============================================================================

def build_latex_review_booklet_source(
    booklet_data: Dict[str, Any],
    mode: str = "teacher",
    term: Optional[int] = None,
    week: Optional[int] = None,
    has_logo: bool = True,
    font_theme: str = "charter"
) -> str:
    """Builds the complete LaTeX source string for an official DA Tuition Review Booklet."""
    booklet_data = sanitize_out_of_syllabus_abs_y(booklet_data)
    year_level = booklet_data.get("year_level", "Mathematics")
    topic = booklet_data.get("topic", "Topic Review & Exam Revision Booklet")
    concepts = booklet_data.get("concepts", [])
    mode_clean = str(mode).strip().lower()
    is_teacher = (mode_clean == "teacher")
    is_student_class = (mode_clean in ["student_class", "class", "student class"])
    if is_teacher:
        edition_label = r"TEACHER MASTER REVISION \& EXAM REVIEW"
        short_edition = "Teacher Revision"
        badge_bg = "dawine"
    elif is_student_class:
        edition_label = r"STUDENT CLASS COMPACT REVISION (WORK IN EXERCISE BOOK)"
        short_edition = "Student Class"
        badge_bg = "dagreen"
    else:
        edition_label = r"STUDENT TOPIC REVISION \& MASTERY REVIEW"
        short_edition = "Student Revision"
        badge_bg = "danavy"
    clean_topic = clean_worksheet_topic_title(topic)
    subject_clean = f"{year_level} Maths"
    topic_header = f"{subject_clean} --- {clean_topic}"

    font_key = booklet_data.get("font_theme") or font_theme or "charter"
    font_lines = get_font_latex_preamble(font_key)

    tex_lines = [
        r"\documentclass[11pt,a4paper]{article}",
        r"\usepackage[top=1.8cm, bottom=1.8cm, left=1.5cm, right=1.5cm, headsep=7mm, footskip=8mm]{geometry}",
        r"\usepackage[utf8]{inputenc}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage{amsmath,amssymb,amsfonts}",
        *font_lines,
        r"\usepackage{fancyhdr}",
        r"\usepackage{graphicx}",
        r"\usepackage{adjustbox}",
        r"\usepackage{enumitem}",
        r"\usepackage{xcolor}",
        r"\usepackage{multicol}",
        r"\usepackage{needspace}",
        r"\usepackage{setspace}",
        r"\setstretch{1.18}",
        r"\setlength{\parskip}{0.3em plus 0.1em minus 0.05em}",
        r"\setlength{\headheight}{14.5pt}",
        r"\addtolength{\topmargin}{-2.5pt}",
        r"\hyphenpenalty=10000",
        r"\exhyphenpenalty=10000",
        r"\binoppenalty=10000",
        r"\relpenalty=10000",
        r"\tolerance=9999",
        r"\emergencystretch=2.5em",
        r"\usepackage{tcolorbox}",
        r"\tcbuselibrary{skins,breakable}",
        r"\usepackage{varwidth}",
        r"\usepackage{tikz}",
        r"\usetikzlibrary{arrows.meta,calc,angles,quotes,shapes.geometric,patterns,decorations.pathreplacing}",
        r"\usepackage{etoolbox}",
        r"\usepackage{eso-pic}",
        "",
        r"\pagestyle{fancy}",
        r"\fancyhf{}",
        f"\\fancyhead[L]{{\\parbox[b]{{0.62\\textwidth}}{{\\raggedright\\footnotesize\\bfseries {sanitize_for_latex(topic_header)} Revision}}}}",
        f"\\fancyhead[R]{{\\parbox[b]{{0.36\\textwidth}}{{\\raggedleft\\footnotesize\\bfseries DA Tuition --- {short_edition}}}}}",
        r"\fancyfoot[C]{\thepage}",
        r"\renewcommand{\headrulewidth}{0.4pt}",
        "",
        r"\definecolor{danavy}{RGB}{15, 23, 42}",
        r"\definecolor{dawine}{RGB}{136, 19, 55}",
        r"\definecolor{dablue}{RGB}{30, 58, 138}",
        r"\definecolor{dagreen}{RGB}{5, 150, 105}",
        r"\definecolor{dagold}{RGB}{197, 155, 39}",
        r"\definecolor{dareviewbg}{RGB}{248, 250, 252}",
        r"\definecolor{slatebg}{RGB}{248, 250, 252}",
        r"\definecolor{goldbg}{RGB}{255, 252, 242}",
        r"\definecolor{datipsbg}{RGB}{255, 252, 242}",
        r"\definecolor{grayborder}{RGB}{226, 232, 240}",
        "",
        r"\newcommand{\dalightning}{\raisebox{-0.5pt}{\tikz[baseline=-0.2ex,scale=0.6]{\path[fill=dagold] (0,1.2ex) -- (0.8ex,1.2ex) -- (0.2ex,0.3ex) -- (0.9ex,0.3ex) -- (-0.1ex,-1.0ex) -- (0.3ex,-0.1ex) -- (-0.4ex,-0.1ex) -- cycle;}}}",
        r"\newcommand{\damastery}{\raisebox{-0.5pt}{\tikz[baseline=-0.2ex,scale=0.6]{\draw[fill=white,draw=dawine,thick] (0,0.4ex) circle (0.8ex); \fill[dawine] (0,0.4ex) circle (0.4ex);}}}",
        r"\DeclareUnicodeCharacter{26A1}{\dalightning}",
        r"\DeclareUnicodeCharacter{2713}{\ensuremath{\checkmark}}",
        r"\DeclareUnicodeCharacter{25B6}{\ensuremath{\blacktriangleright}}",
        r"\DeclareUnicodeCharacter{2022}{\textbullet}",
        "",
        r"\newtcolorbox{reviewcontentsbox}[1][]{",
        r"    enhanced,",
        r"    colback=slatebg,",
        r"    colframe=danavy!30,",
        r"    boxrule=0.7pt,",
        r"    arc=4pt,",
        r"    left=14pt, right=14pt, top=12pt, bottom=12pt,",
        r"    title={\textbf{\color{danavy}\small \quad \ifstrempty{#1}{Table of Contents}{#1}}},",
        r"    coltitle=danavy,",
        r"    colbacktitle=slatebg,",
        r"    attach boxed title to top left={yshift=-2mm, xshift=4mm},",
        r"    boxed title style={boxrule=0pt, colframe=slatebg, arc=2pt},",
        r"    varwidth boxed title=0.88\linewidth,",
        r"    breakable",
        r"}",
        "",
        r"\newtcolorbox{reviewbox}[1][]{",
        r"    enhanced,",
        r"    standard jigsaw,",
        r"    opacityback=0,",
        r"    colframe=danavy,",
        r"    before skip=1pt,",
        r"    after skip=6pt,",
        r"    leftrule=3.5pt, rightrule=0.5pt, toprule=0.5pt, bottomrule=0.5pt,",
        r"    arc=3pt,",
        r"    left=10pt, right=10pt, top=9pt, bottom=9pt,",
        r"    title={\textbf{\color{danavy}\small \quad \ifstrempty{#1}{Core Concept \& Strategy}{#1}}},",
        r"    coltitle=danavy,",
        r"    colbacktitle=white,",
        r"    attach boxed title to top left={yshift=-2mm, xshift=4mm},",
        r"    boxed title style={boxrule=0.5pt, colframe=danavy!30, arc=2pt},",
        r"    varwidth boxed title=0.88\linewidth,",
        r"    breakable,",
        r"    pad at break=2mm,",
        r"    lines before break=2",
        r"}",
        "",
        r"\newtcolorbox{tipstricksbox}[1][]{",
        r"    enhanced,",
        r"    standard jigsaw,",
        r"    opacityback=0,",
        r"    colframe=dagold,",
        r"    leftrule=3.5pt, rightrule=0.5pt, toprule=0.5pt, bottomrule=0.5pt,",
        r"    arc=3pt,",
        r"    left=9pt, right=9pt, top=7pt, bottom=7pt,",
        r"    title={\textbf{\color{dagold!90!black}\small \quad \dalightning~\ifstrempty{#1}{DA Exam Secrets \& Traps}{#1}}},",
        r"    coltitle=dagold!90!black,",
        r"    colbacktitle=white,",
        r"    attach boxed title to top left={yshift=-2mm, xshift=4mm},",
        r"    boxed title style={boxrule=0.5pt, colframe=dagold!40, arc=2pt},",
        r"    breakable,",
        r"    pad at break=2mm,",
        r"    lines before break=2",
        r"}",
        "",
        r"\newtcolorbox{masteryexamplebox}[1][]{",
        r"    enhanced,",
        r"    standard jigsaw,",
        r"    opacityback=0,",
        r"    colframe=dawine,",
        r"    leftrule=3.5pt, rightrule=0.5pt, toprule=0.5pt, bottomrule=0.5pt,",
        r"    arc=3pt,",
        r"    left=8pt, right=8pt, top=7pt, bottom=7pt,",
        r"    title={\textbf{\color{dawine!90!black}\small \quad \damastery~\ifstrempty{#1}{Mastery Demonstration}{#1}}},",
        r"    coltitle=dawine!90!black,",
        r"    colbacktitle=white,",
        r"    attach boxed title to top left={yshift=-2mm, xshift=4mm},",
        r"    boxed title style={boxrule=0.5pt, colframe=dawine!30, arc=2pt},",
        r"    breakable,",
        r"    pad at break=2mm,",
        r"    lines before break=2",
        r"}",
        "",
        r"\newtcolorbox{reviewsolutionbox}[1][]{",
        r"    enhanced,",
        r"    standard jigsaw,",
        r"    opacityback=0,",
        r"    colframe=dagreen,",
        r"    leftrule=3.5pt, rightrule=0.5pt, toprule=0.5pt, bottomrule=0.5pt,",
        r"    arc=3pt,",
        r"    left=8pt, right=8pt, top=7pt, bottom=7pt,",
        r"    title={\textbf{\color{dagreen!90!black}\small \quad \ensuremath{\checkmark}~\ifstrempty{#1}{Model Worked Solution \& Marking Criteria}{#1}}},",
        r"    coltitle=dagreen!90!black,",
        r"    colbacktitle=white,",
        r"    attach boxed title to top left={yshift=-2mm, xshift=4mm},",
        r"    boxed title style={boxrule=0.5pt, colframe=dagreen!30, arc=2pt},",
        r"    breakable",
        r"}",
        "",
        r"\newtcolorbox{reviewworkingbox}[2][]{",
        r"    enhanced,",
        r"    standard jigsaw,",
        r"    opacityback=0,",
        r"    colframe=grayborder,",
        r"    boxrule=0.6pt,",
        r"    arc=3pt,",
        r"    left=8pt, right=8pt, top=6pt, bottom=6pt,",
        r"    height=#2,",
        r"    underlay={",
        r"        \node[anchor=north east, font=\bfseries\tiny\color{gray!45}] at (frame.north east) [xshift=-6pt, yshift=-5pt] {STUDENT WORKING SPACE};",
        r"    }",
        r"}",
        "",
        r"\AddToShipoutPictureBG{%",
        r"  \AtPageCenter{%",
        r"    \tikz[remember picture, overlay]{\node[opacity=0.08] at (0, 0) {\includegraphics[width=19.2cm,keepaspectratio]{da_logo_bw.png}};}%",
        r"  }%",
        r"}",
        "",
        r"\begin{document}",
        r"\thispagestyle{plain}",
        ""
    ]

    clean_topic = clean_worksheet_topic_title(topic)
    header_lines = [
        r"\noindent",
        r"\begin{minipage}[t]{0.70\textwidth}",
        r"\vspace{0pt}",
        r"\raggedright",
        f"{{\\huge \\textbf{{\\color{{danavy}}{subject_clean}}}}}\\\\[0.1cm]",
        f"{{\\LARGE \\textbf{{\\color{{danavy}}{sanitize_for_latex(clean_topic)}}}}}\\\\[0.15cm]",
    ]
    meta_pills = []
    if term and week:
        meta_pills.append(f"\\tikz[baseline=-0.6ex]{{\\node[fill=danavy!10, text=danavy, rounded corners=3pt, inner sep=3pt, font=\\scriptsize\\bfseries] {{Term {term} $\\bullet$ Week {week}}};}}")
    elif term:
        meta_pills.append(f"\\tikz[baseline=-0.6ex]{{\\node[fill=danavy!10, text=danavy, rounded corners=3pt, inner sep=3pt, font=\\scriptsize\\bfseries] {{Term {term}}};}}")
    elif week:
        meta_pills.append(f"\\tikz[baseline=-0.6ex]{{\\node[fill=danavy!10, text=danavy, rounded corners=3pt, inner sep=3pt, font=\\scriptsize\\bfseries] {{Week {week}}};}}")
    meta_pills.append(f"\\tikz[baseline=-0.6ex]{{\\node[fill={badge_bg}!15, draw={badge_bg}!60, rounded corners=3pt, inner sep=3pt, font=\\scriptsize\\bfseries\\color{{{badge_bg}!90!black}}] {{{edition_label}}};}}")
    header_lines.append(" \\quad ".join(meta_pills))
    header_lines.extend([
        r"\end{minipage}%",
        r"\hfill",
        r"\begin{minipage}[t]{0.28\textwidth}",
        r"\vspace{0pt}",
        r"\raggedleft"
    ])
    tex_lines.extend(header_lines)

    if has_logo:
        tex_lines.append(r"\includegraphics[height=2.8cm,keepaspectratio]{da_logo.png}")
    else:
        tex_lines.append(r"{\Large \textbf{\color{danavy}DA TUITION}}")

    tex_lines.extend([
        r"\end{minipage}",
        r"\vspace{0.25cm}",
        r"\noindent",
        r"\tikz\draw[thick, color=danavy!25] (0,0) -- (\linewidth,0);",
        r"\vspace{0.15cm}",
        r"\noindent"
    ])

    if is_teacher:
        tex_lines.append(r"\textbf{Teacher Name:} \underline{\hspace{7.5cm}} \hfill \textbf{Date:} \underline{\hspace{3.5cm}}\\[0.25cm]")
    else:
        tex_lines.append(r"\textbf{Student Name:} \underline{\hspace{5.5cm}} \hfill \textbf{Class:} \underline{\hspace{2.2cm}} \hfill \textbf{Date:} \underline{\hspace{2.2cm}}\\[0.25cm]")

    tex_lines.append(r"\vspace{0.35cm}")
    tex_lines.append(r"\noindent")

    quick_answers = []
    q_counter = 1  # Global question counter across all Sets/concepts

    for c_idx, concept in enumerate(concepts, 1):
        raw_c_name = concept.get("concept_name") or concept.get("name", f"Review Concept {c_idx}")
        c_name = clean_subtopic_title(raw_c_name)
        part_letter = chr(ord('A') + (c_idx - 1)) if c_idx <= 26 else f"A{c_idx}"
        revision_summary = concept.get("revision_summary") or concept.get("theory_content", "")
        key_formulas = concept.get("key_formulas", [])
        tips_tricks = concept.get("tips_and_tricks") or concept.get("tutor_tips", "")
        common_pitfalls = concept.get("common_pitfalls", [])
        tikz_diag = concept.get("tikz_diagram", "")
        mastery_examples = concept.get("mastery_examples") or concept.get("teacher_examples", [])
        review_questions = concept.get("review_questions") or concept.get("practice_questions", [])

        if c_idx > 1:
            tex_lines.append(r"\newpage")
        if len(concepts) == 1:
            heading_title = sanitize_for_latex(c_name)
        else:
            heading_title = f"Review Part {part_letter}: {sanitize_for_latex(c_name)}"
        tex_lines.append(f"\\noindent{{\\Large\\textbf{{\\color{{danavy}}\\rule[-2pt]{{3.5pt}}{{14pt}}\\hspace{{6pt}}{heading_title}}}}}\\label{{sec:rev_concept_{c_idx}}}\\\\[0.05cm]")
        tex_lines.append(r"\nopagebreak")
        tex_lines.append(r"\vspace{-0.22cm}")
        tex_lines.append(r"\nopagebreak")

        # 1. High-Yield Revision Summary Box
        tex_lines.append(r"\begin{reviewbox}[Core Concept \& Strategy]")
        if revision_summary:
            tex_lines.append(format_latex_theory_notes(revision_summary))

        if key_formulas:
            if revision_summary:
                tex_lines.append(r"\vspace{0.15cm}")
            tex_lines.append(r"\noindent\textbf{\color{danavy}Essential Exam Formulae \& Results:}")
            tex_lines.append(r"\begin{itemize}[leftmargin=1.5em, itemsep=0.25em]")
            for kf in key_formulas:
                tex_lines.append(f"\\item {format_theory_formula(kf)}")
            tex_lines.append(r"\end{itemize}")

        if not tikz_diag:
            tikz_diag = get_concept_fallback_tikz(c_name, topic)
        if tikz_diag:
            tex_lines.append(r"\vspace{0.2cm}")
            tex_lines.append(sanitize_tikz_diagram(tikz_diag))

        tex_lines.append(r"\end{reviewbox}")
        tex_lines.append(r"\vspace{0.25cm}")

        # 2. Tips, Tricks & Pitfalls Box
        if tips_tricks or common_pitfalls:
            tex_lines.append(r"\begin{tipstricksbox}[💡 Tutor Secrets, Exam Shortcuts \& Common Traps]")
            if tips_tricks:
                tex_lines.append(f"\\noindent\\textbf{{\\color{{dagold}}High-Yield Shortcut:}} {sanitize_for_latex(tips_tricks)}\\par")
            if common_pitfalls:
                if tips_tricks:
                    tex_lines.append(r"\vspace{0.15cm}")
                tex_lines.append(r"\noindent\textbf{\color{dawine}Common Examination Traps to Avoid:}")
                tex_lines.append(r"\begin{itemize}[leftmargin=1.5em, itemsep=0.25em]")
                for pf in common_pitfalls:
                    tex_lines.append(f"\\item {sanitize_for_latex(str(pf))}")
                tex_lines.append(r"\end{itemize}")
            tex_lines.append(r"\end{tipstricksbox}")
            tex_lines.append(r"\vspace{0.25cm}")

        # 3. Mastery Model Demonstration Examples
        if mastery_examples:
            tex_lines.append(r"\subsection*{Exam Mastery Demonstrations}\label{sec:rev_demo_" + str(c_idx) + "}")
            for e_idx, ex in enumerate(mastery_examples, 1):
                p_text = ex.get("problem_text", "")
                sol = ex.get("worked_solution", "")
                comm = ex.get("exam_commentary") or ex.get("teaching_notes", "")
                raw_ex_title = ex.get("title", f"Example {e_idx}")
                cleaned_ex_t = clean_ex_title(raw_ex_title)
                ex_num_str = f"Mastery Example {e_idx}" if len(concepts) == 1 else f"Mastery Example {part_letter}.{e_idx}"
                ex_heading = f"{ex_num_str}: {sanitize_for_latex(cleaned_ex_t)}" if cleaned_ex_t else ex_num_str
                ex_diag = ex.get("diagram_tikz") or ex.get("tikz_diagram") or ex.get("diagram")
                if not ex_diag or not str(ex_diag).strip():
                    fallback_diag = synthesize_network_diagram_from_text(p_text, topic=topic, concept_name=c_name)
                    if fallback_diag:
                        ex_diag = fallback_diag
                sol_diag = ex.get("solution_diagram_tikz") or ex.get("solution_tikz") or ex.get("solution_diagram")
                if not sol_diag or not str(sol_diag).strip():
                    if any(k in (p_text + " " + sol).lower() for k in ["sketch", "plot the", "draw the graph", "draw the curve", "graph of", "graph the"]):
                        fallback_tikz = get_sketch_solution_fallback_tikz(p_text, sol)
                        if fallback_tikz:
                            sol_diag = fallback_tikz

                tex_lines.append(r"\needspace{4.5cm}")
                tex_lines.append(f"\\begin{{masteryexamplebox}}[{{{sanitize_for_latex(ex_heading)}}}]")
                p_lines = format_latex_question_with_subparts(p_text, as_item=False)
                tex_lines.append(f"\\textbf{{Problem Statement:}}\\\\ " + "\n".join(p_lines))
                if ex_diag and str(ex_diag).strip():
                    tex_lines.append(r"\vspace{0.15cm}")
                    tex_lines.append(sanitize_tikz_diagram(str(ex_diag).strip()))

                if is_teacher or sol:
                    tex_lines.append(r"\vspace{0.2cm}")
                    tex_lines.append(r"\begin{reviewsolutionbox}[Model Worked Solution \& Exam Criteria]")
                    tex_lines.append(format_latex_solution_steps(sol))
                    if sol_diag and str(sol_diag).strip():
                        tex_lines.append(r"\par\vspace{0.15cm}")
                        tex_lines.append(sanitize_tikz_diagram(str(sol_diag).strip()))
                    if comm:
                        tex_lines.append(r"\vspace{0.15cm}")
                        tex_lines.append(f"\\par\\textbf{{\\color{{dagreen}}Tutor Commentary:}} \\textit{{{sanitize_for_latex(comm)}}}")
                    tex_lines.append(r"\end{reviewsolutionbox}")

                tex_lines.append(r"\end{masteryexamplebox}")
                tex_lines.append(r"\vspace{0.25cm}")

        # 4. Revision Practice Questions
        if review_questions:
            part_groups = group_booklet_questions_by_part(review_questions)
            for part_title, part_qs in part_groups:
                if len(concepts) == 1:
                    heading_str = f"Revision ({part_title})"
                else:
                    heading_str = f"Revision {part_letter} ({part_title})"
                tex_lines.append(r"\needspace{4.2cm}")
                tex_lines.append(f"\\noindent{{\\textbf{{\\large\\color{{danavy}}{heading_str}}}}}\\par\\vspace{{0.15cm}}")
                tex_lines.append(r"\setlength{\columnsep}{0.85cm}")
                tex_lines.append(r"\begin{multicols}{2}")
                tex_lines.append(r"\raggedbottom")
                itemsep = "1.8cm" if (not is_teacher and not is_student_class) else ("0.8em" if is_teacher else "0.6em")
                tex_lines.append(f"\\begin{{enumerate}}[label=\\textbf{{\\arabic*.}}, leftmargin=1.6em, itemsep={itemsep}, start={q_counter}]")
                for q in part_qs:
                    q_text = q.get("text") or q.get("question_text") or q.get("question") or ""
                    ans = q.get("final_answer") or q.get("answer") or ""
                    sol = q.get("worked_solution") or q.get("solution") or ""
                    q_diag = q.get("diagram_tikz") or q.get("tikz_diagram") or q.get("diagram")
                    if not q_diag or not str(q_diag).strip():
                        fallback_diag = synthesize_network_diagram_from_text(q_text, topic=topic, concept_name=c_name)
                        if fallback_diag:
                            q_diag = fallback_diag
                    q_sol_diag = q.get("solution_diagram_tikz") or q.get("solution_tikz") or q.get("solution_diagram")
                    if not q_sol_diag or not str(q_sol_diag).strip():
                        if any(k in (q_text + " " + sol).lower() for k in ["sketch", "plot the", "draw the graph", "draw the curve", "graph of", "graph the"]):
                            fallback_tikz = get_sketch_solution_fallback_tikz(q_text, sol)
                            if fallback_tikz:
                                q_sol_diag = fallback_tikz

                    if ans:
                        quick_answers.append({
                            "part": "" if len(concepts) == 1 else f"Part {part_letter}",
                            "q_num": q_counter,
                            "ans": ans
                        })

                    # Split sub-parts (a), (b), (c) onto separate lines with math-safe parser
                    q_subpart_lines = format_latex_question_with_subparts(q_text, as_item=False)
                    item_body = "\n".join(q_subpart_lines)
                    has_subparts = bool(re.search(r'\([a-d]\)', q_text))
                    use_minipage = not has_subparts and (not is_teacher or len(sol) < 500)
                    if use_minipage:
                        item_lines = [
                            r"\item \begin{minipage}[t]{\linewidth}",
                            item_body
                        ]
                    else:
                        item_lines = [
                            r"\item",
                            item_body
                        ]
                    if q_diag and str(q_diag).strip():
                        item_lines.append(r"\vspace{0.1cm}")
                        item_lines.append(sanitize_tikz_diagram(str(q_diag).strip()))
                    if is_teacher:
                        item_lines.append(r"\\[0.1cm]")
                        if ans:
                            item_lines.append(f"{{\\small\\textbf{{\\color{{dagreen}}Final Answer:}} {sanitize_for_latex(ans)}}}\\\\[0.05cm]")
                        if sol:
                            fmt_w = format_latex_practice_solution(sol)
                            item_lines.append(f"{{\\footnotesize\\color{{gray!80!black}}\\textit{{Work:}}\\par\\vspace{{0.03cm}}\n{fmt_w}}}")
                        if q_sol_diag and str(q_sol_diag).strip():
                            item_lines.append(r"\par\vspace{0.1cm}")
                            item_lines.append(sanitize_tikz_diagram(str(q_sol_diag).strip()))
                    if use_minipage:
                        item_lines.append(r"\end{minipage}")
                    tex_lines.append("\n".join(item_lines))
                    q_counter += 1
                tex_lines.append(r"\end{enumerate}")
                tex_lines.append(r"\end{multicols}")
                if not is_teacher and not is_student_class:
                    tex_lines.append(r"\vspace{1.0cm}")
                else:
                    tex_lines.append(r"\vspace{0.3cm}")

    # Quick Answers for Student Edition
    if not is_teacher and quick_answers:
        tex_lines.append(r"\newpage")
        tex_lines.append(r"\section*{Quick Verification Answers (Student Self-Checking)}\label{sec:answers}")
        if is_student_class:
            tex_lines.append(r"\noindent Use these answers to verify your final solutions after completing full working in your exercise book.\\[0.4cm]")
        else:
            tex_lines.append(r"\noindent Use these answers to verify your final solutions after completing full working in the spaces provided.\\[0.4cm]")
        tex_lines.append(r"\begin{enumerate}[labelindent=0pt, labelwidth=2.5cm, labelsep=0.3cm, leftmargin=*, align=left, itemsep=0.6em]")
        for qa in quick_answers:
            if qa.get("part"):
                tex_lines.append(f"\\item[\\textbf{{{qa['part']} Q{qa['q_num']}.}}] {format_answer_parts_latex(sanitize_for_latex(qa['ans']))}")
            else:
                tex_lines.append(f"\\item[\\textbf{{Q{qa['q_num']}.}}] {format_answer_parts_latex(sanitize_for_latex(qa['ans']))}")
        tex_lines.append(r"\end{enumerate}")

    tex_lines.append(r"\end{document}")
    return "\n".join(tex_lines)


def generate_latex_review_booklet_pdf(
    booklet_data: Dict[str, Any],
    mode: str = "teacher",
    term: Optional[int] = None,
    week: Optional[int] = None,
    font_theme: str = "charter"
) -> Optional[bytes]:
    """Compiles publication-quality Review & Exam Revision Booklet PDF with LaTeX."""
    pdflatex_bin = find_pdflatex()
    if not pdflatex_bin:
        return None

    tmp_dir = tempfile.mkdtemp()
    try:
        has_logo = False
        if os.path.exists(LOGO_PATH):
            shutil.copy(LOGO_PATH, os.path.join(tmp_dir, "da_logo.png"))
            has_logo = True
        if os.path.exists(LOGO_TRANSPARENT_PATH):
            shutil.copy(LOGO_TRANSPARENT_PATH, os.path.join(tmp_dir, "da_logo_transparent.png"))
        elif os.path.exists(LOGO_PATH):
            shutil.copy(LOGO_PATH, os.path.join(tmp_dir, "da_logo_transparent.png"))
        bw_logo_src = ensure_bw_logo()
        if os.path.exists(bw_logo_src):
            shutil.copy(bw_logo_src, os.path.join(tmp_dir, "da_logo_bw.png"))

        full_tex = build_latex_review_booklet_source(
            booklet_data=booklet_data,
            mode=mode,
            term=term,
            week=week,
            has_logo=has_logo,
            font_theme=font_theme
        )
        full_tex = inject_python_graphs(full_tex, tmp_dir)
        full_tex = sanitize_latex_compilation_safety(full_tex)

        tex_path = os.path.join(tmp_dir, "review_booklet.tex")
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(full_tex)

        for _ in range(2):
            subprocess.run(
                [pdflatex_bin, "-interaction=nonstopmode", "review_booklet.tex"],
                cwd=tmp_dir,
                capture_output=True,
                check=False
            )

        pdf_path = os.path.join(tmp_dir, "review_booklet.pdf")
        if not os.path.exists(pdf_path):
            # Resilient fallback: strip any broken TikZ diagrams and recompile
            tex_lines_no_tikz = []
            skip_tikz = False
            for line in full_tex.splitlines():
                if r"\begin{tikzpicture}" in line:
                    skip_tikz = True
                    continue
                if r"\end{tikzpicture}" in line:
                    skip_tikz = False
                    continue
                if not skip_tikz:
                    tex_lines_no_tikz.append(line)
            repaired_tex = sanitize_latex_compilation_safety("\n".join(tex_lines_no_tikz))
            with open(tex_path, "w", encoding="utf-8") as f:
                f.write(repaired_tex)
            for _ in range(2):
                subprocess.run(
                    [pdflatex_bin, "-interaction=nonstopmode", "review_booklet.tex"],
                    cwd=tmp_dir,
                    capture_output=True,
                    check=False
                )

        if os.path.exists(pdf_path):
            with open(pdf_path, "rb") as f:
                raw_bytes = f.read()
            topic_str = str(booklet_data.get("topic", ""))
            yl_str = str(booklet_data.get("year_level", ""))
            return prune_trailing_blank_pages(raw_bytes, topic=topic_str, year_level=yl_str)

    except Exception:
        pass
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return None


def generate_review_booklet_docx(
    booklet_data: Dict[str, Any],
    mode: str = "student",
    term: Optional[int] = None,
    week: Optional[int] = None
) -> Optional[bytes]:
    """Generates an authentic editable Microsoft Word (.docx) Review Booklet."""
    full_tex = build_latex_review_booklet_source(
        booklet_data=booklet_data,
        mode=mode,
        term=term,
        week=week,
        has_logo=True
    )
    return docx_generator.latex_to_docx(full_tex)


def generate_reportlab_review_booklet_pdf(
    booklet_data: Dict[str, Any],
    mode: str = "teacher",
    term: Optional[int] = None,
    week: Optional[int] = None
) -> bytes:
    """ReportLab fallback engine for Review Booklet PDF generation."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )
    styles = getSampleStyleSheet()
    story = []

    year_level = booklet_data.get("year_level", "Mathematics")
    topic = booklet_data.get("topic", "Topic Review & Exam Revision Booklet")
    clean_topic = clean_worksheet_topic_title(topic)
    mode_clean = str(mode).strip().lower()
    is_teacher = (mode_clean == "teacher")
    is_student_class = (mode_clean in ["student_class", "class", "student class"])
    if is_teacher:
        edition_label = "TEACHER MASTER REVISION & EXAM REVIEW"
    elif is_student_class:
        edition_label = "STUDENT CLASS COMPACT REVISION (WORK IN EXERCISE BOOK)"
    else:
        edition_label = "STUDENT TOPIC REVISION & MASTERY REVIEW"

    story.append(Paragraph(f"<b>DA TUITION --- {edition_label}</b>", styles["Heading1"]))
    story.append(Paragraph(f"<b>{year_level} | {clean_topic}</b>", styles["Heading2"]))
    if term and week:
        story.append(Paragraph(f"Term {term}, Week {week}", styles["Normal"]))
    story.append(Spacer(1, 14))

    for c_idx, c in enumerate(booklet_data.get("concepts", []), 1):
        c_name = clean_subtopic_title(c.get("concept_name") or c.get("name", f"Concept {c_idx}"))
        part_letter = chr(ord('A') + (c_idx - 1)) if c_idx <= 26 else f"A{c_idx}"
        story.append(Paragraph(f"<b>Review Part {part_letter}: {c_name}</b>", styles["Heading2"]))
        summary = c.get("revision_summary") or c.get("theory_content", "")
        if summary:
            story.append(Paragraph(f"<b>Revision Summary:</b> {summary}", styles["Normal"]))
            story.append(Spacer(1, 6))

        for kf in c.get("key_formulas", []):
            story.append(Paragraph(f"• <i>{kf}</i>", styles["Normal"]))

        tips = c.get("tips_and_tricks") or c.get("tutor_tips", "")
        if tips:
            story.append(Paragraph(f"<b>💡 Tips & Tricks:</b> {tips}", styles["Normal"]))

        story.append(Spacer(1, 10))

        # Practice questions
        last_doc_level = None
        concepts_list = booklet_data.get("concepts", [])
        for q_idx, q in enumerate(c.get("review_questions", []) or c.get("practice_questions", []), 1):
            diff = q.get("difficulty", "Standard")
            part_tier = get_booklet_part_tier(diff)
            if part_tier and part_tier != last_doc_level:
                last_doc_level = part_tier
                rev_prefix = f"Revision {part_letter} ({part_tier})" if len(concepts_list) > 1 else f"Revision ({part_tier})"
                story.append(Paragraph(f"<b><u>{rev_prefix}</u></b>", styles["Normal"]))
                story.append(Spacer(1, 4))
            q_label = f"Q{q_idx}" if len(concepts_list) == 1 else f"Q{part_letter}.{q_idx}"
            story.append(Paragraph(f"<b>{q_label}:</b> {q.get('text', '')}", styles["Normal"]))
            if is_teacher:
                story.append(Paragraph(f"<b>Worked Solution:</b> {q.get('worked_solution', '')}", styles["Normal"]))
                story.append(Paragraph(f"<b>Answer:</b> {q.get('final_answer', '')}", styles["Normal"]))
            story.append(Spacer(1, 8))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def generate_review_booklet_pdf(
    booklet_data: Dict[str, Any],
    mode: str = "teacher",
    term: Optional[int] = None,
    week: Optional[int] = None,
    font_theme: str = "charter"
) -> bytes:
    """
    Generates an official DA Tuition Review Booklet PDF in either 'teacher' or 'student' mode.
    Attempts native LaTeX compilation first with tcolorbox.
    Falls back to ReportLab if pdflatex is unavailable.
    """
    latex_bytes = generate_latex_review_booklet_pdf(
        booklet_data=booklet_data,
        mode=mode,
        term=term,
        week=week,
        font_theme=font_theme
    )
    if latex_bytes:
        return latex_bytes
    return generate_reportlab_review_booklet_pdf(
        booklet_data=booklet_data,
        mode=mode,
        term=term,
        week=week
    )


def get_theory_booklet_download_filename(booklet: dict, mode: str = "student", extension: str = "pdf") -> str:
    """
    Formats the theory booklet download filename according to the DA Tuition convention:
    e.g. 'Sequences & Series Theory Student (Cambridge).pdf'
         'Sequences & Series Theory Teacher (Cambridge).docx'
    Strictly removes all '_' and replaces them with clean spaces.
    """
    topic = booklet.get("topic") or booklet.get("title") or "Mathematics"
    clean_topic = re.sub(r'^(?:Chapter|Unit|Topic\s*)?(?:\d+[\.\:\-]\s*|\d+[A-Za-z][\.\:\-]\s*|\d+\s+)', '', str(topic)).strip()
    clean_topic = re.sub(r'\s*(Theory & Practice Booklet|Theory Booklet|Practice Booklet|Booklet)\s*$', '', clean_topic, flags=re.IGNORECASE).strip()
    clean_topic = re.sub(r'^Year\s+\d+\s*(?:\([^\)]+\))?\s*(?:Mathematics)?\s*[\-\–\—\:]\s*', '', clean_topic, flags=re.IGNORECASE).strip()
    if not clean_topic:
        clean_topic = "Mathematics"
    
    mode_str = str(mode).strip().lower()
    if mode_str == "teacher":
        mode_label = "Teacher"
    elif mode_str in ["student_class", "class", "student class", "student no space", "student_no_space"]:
        mode_label = "Student no space"
    else:
        mode_label = "Student with space"

    tb_raw = booklet.get("textbook") or booklet.get("curriculum_series") or ""
    if not tb_raw and "content" in booklet and isinstance(booklet["content"], dict):
        tb_raw = booklet["content"].get("textbook", "")
    if not tb_raw:
        combined_text = (str(booklet.get("title", "")) + " " + str(booklet.get("custom_notes", ""))).lower()
        if "focus" in combined_text:
            tb_raw = "Maths in Focus"
        elif "century" in combined_text:
            tb_raw = "New Century Maths"
        elif "quest" in combined_text:
            tb_raw = "Maths Quest"
        elif "signpost" in combined_text or "singpost" in combined_text:
            tb_raw = "Signpost"
        elif "oxford" in combined_text:
            tb_raw = "Oxford"
        elif "mathscape" in combined_text:
            tb_raw = "Mathscape"
        else:
            tb_raw = "Cambridge"
    
    tb_lower = str(tb_raw).lower()
    if "cambridge" in tb_lower:
        tb_short = "Cambridge"
    elif "maths in focus" in tb_lower or "focus" in tb_lower:
        tb_short = "Maths in Focus"
    elif "new century" in tb_lower:
        tb_short = "New Century Maths"
    elif "quest" in tb_lower:
        tb_short = "Maths Quest"
    elif "signpost" in tb_lower or "singpost" in tb_lower:
        tb_short = "Signpost"
    elif "oxford" in tb_lower:
        tb_short = "Oxford"
    elif "mathscape" in tb_lower:
        tb_short = "Mathscape"
    else:
        cleaned_tb = re.sub(r'\(.*?\)', '', str(tb_raw)).strip()
        tb_short = cleaned_tb or "Cambridge"

    ext = extension.lstrip(".")
    filename = f"{clean_topic} Theory {mode_label} ({tb_short}).{ext}"
    filename = filename.replace("_", " ")
    filename = re.sub(r'\s+', ' ', filename).strip()
    return filename


def get_topic_exam_download_filename(
    exam: dict,
    mode: str = "student",
    extension: str = "pdf",
    theory_booklet: Optional[dict] = None
) -> str:
    """
    Formats the End-of-Topic Mastery Exam download filename according to the DA Tuition convention:
    e.g. 'Functions End-of-Topic Mastery Exam Student (Cambridge).pdf'
         'Functions End-of-Topic Mastery Exam Teacher Solutions (Cambridge).pdf'
    Strictly removes all '_' and replaces them with clean spaces.
    """
    topic = exam.get("topic") or (theory_booklet.get("topic") if theory_booklet else "") or exam.get("title") or "Mathematics"
    # Clean up leading chapter prefix (e.g. "1. ", "6: ", "10A. ", "1 ") without stripping "2D" or "3D"
    clean_topic = re.sub(r'^(?:Chapter|Unit|Topic\s*)?(?:\d+[\.\:\-]\s*|\d+[A-Za-z][\.\:\-]\s*|\d+\s+)', '', str(topic)).strip()
    # Remove trailing exam phrases if present in title fallback
    clean_topic = re.sub(r'\s*(End-of-Topic Mastery Exam|Topic Mastery Exam|Mastery Exam|Exam|Worksheet)\s*$', '', clean_topic, flags=re.IGNORECASE).strip()
    # Remove year level prefix if present
    clean_topic = re.sub(r'^Year\s+\d+\s*(?:\([^\)]+\))?\s*(?:Mathematics)?\s*[\-\–\—\:]\s*', '', clean_topic, flags=re.IGNORECASE).strip()
    if not clean_topic:
        clean_topic = "Mathematics"

    mode_str = str(mode).strip().lower()
    if mode_str in ["teacher", "solutions", "teacher_solutions", "teacher solutions"]:
        mode_label = "Teacher Solutions"
    else:
        mode_label = "Student"

    # Identify textbook series
    tb_raw = exam.get("textbook") or (theory_booklet.get("textbook") if theory_booklet else "") or exam.get("curriculum_series") or ""
    if not tb_raw and "content" in exam and isinstance(exam["content"], dict):
        tb_raw = exam["content"].get("textbook", "")
    if not tb_raw and theory_booklet and "content" in theory_booklet and isinstance(theory_booklet["content"], dict):
        tb_raw = theory_booklet["content"].get("textbook", "")
    if not tb_raw:
        combined_text = (str(exam.get("title", "")) + " " + str(exam.get("custom_instructions", "")) + " " + str(theory_booklet.get("title", "") if theory_booklet else "")).lower()
        if "focus" in combined_text:
            tb_raw = "Maths in Focus"
        elif "century" in combined_text:
            tb_raw = "New Century Maths"
        elif "quest" in combined_text:
            tb_raw = "Maths Quest"
        elif "signpost" in combined_text or "singpost" in combined_text:
            tb_raw = "Signpost"
        elif "oxford" in combined_text:
            tb_raw = "Oxford"
        elif "mathscape" in combined_text:
            tb_raw = "Mathscape"
        else:
            tb_raw = "Cambridge"

    tb_lower = str(tb_raw).lower()
    if "cambridge" in tb_lower:
        tb_short = "Cambridge"
    elif "maths in focus" in tb_lower or "focus" in tb_lower:
        tb_short = "Maths in Focus"
    elif "new century" in tb_lower:
        tb_short = "New Century Maths"
    elif "quest" in tb_lower:
        tb_short = "Maths Quest"
    elif "signpost" in tb_lower or "singpost" in tb_lower:
        tb_short = "Signpost"
    elif "oxford" in tb_lower:
        tb_short = "Oxford"
    elif "mathscape" in tb_lower:
        tb_short = "Mathscape"
    else:
        cleaned_tb = re.sub(r'\(.*?\)', '', str(tb_raw)).strip()
        tb_short = cleaned_tb or "Cambridge"

    ext = extension.lstrip(".")
    filename = f"{clean_topic} End-of-Topic Mastery Exam {mode_label} ({tb_short}).{ext}"
    filename = filename.replace("_", " ")
    filename = re.sub(r'\s+', ' ', filename).strip()
    return filename


def get_worksheet_download_filename(
    worksheet: dict,
    sheet_type: str = "homework",
    mode: str = "student",
    extension: str = "pdf",
    theory_booklet: Optional[dict] = None
) -> str:
    """
    Formats download filenames for worksheets according to the DA Tuition convention:
    e.g. 'Functions In-Class Exercise Student (Cambridge).pdf'
         'Functions In-Class Exercise Teacher Solutions (Cambridge).pdf'
         'Functions In-Class Exercise Quick Answers (Cambridge).pdf'
         'Functions Homework Set 1 Student (Cambridge).pdf'
         'Functions Homework Set 1 Teacher Solutions (Cambridge).pdf'
         'Functions Homework Set 1 Quick Answers (Cambridge).pdf'
    Strictly removes all '_' and replaces them with clean spaces.
    """
    topic = worksheet.get("topic") or (theory_booklet.get("topic") if theory_booklet else "") or worksheet.get("title") or "Mathematics"
    clean_topic = re.sub(r'^(?:Chapter|Unit|Topic\s*)?(?:\d+[\.\:\-]\s*|\d+[A-Za-z][\.\:\-]\s*|\d+\s+)', '', str(topic)).strip()
    clean_topic = re.sub(r'\s*(End-of-Topic Mastery Exam|Topic Mastery Exam|Mastery Exam|Exam|In-Class Practice|In-Class Exercise|In-Class|Homework|Worksheet)\s*$', '', clean_topic, flags=re.IGNORECASE).strip()
    clean_topic = re.sub(r'^Year\s+\d+\s*(?:\([^\)]+\))?\s*(?:Mathematics)?\s*[\-\–\—\:]\s*', '', clean_topic, flags=re.IGNORECASE).strip()
    if not clean_topic:
        clean_topic = "Mathematics"

    st_raw = (worksheet.get("assessment_type") or worksheet.get("sheet_type") or sheet_type or "homework").lower()
    set_num = worksheet.get("set_number", 1) or 1

    if "in_class" in st_raw or "in-class" in st_raw or "class" in st_raw:
        type_label = "In-Class Exercise"
    elif "topic_exam" in st_raw or "exam" in st_raw:
        type_label = "End-of-Topic Mastery Exam"
    else:
        type_label = f"Homework Set {set_num}"

    mode_str = str(mode).strip().lower()
    if mode_str in ["teacher", "solutions", "teacher_solutions", "teacher solutions"]:
        mode_label = "Teacher Solutions"
    elif mode_str in ["teacher_answers", "teacher_answer_sheet", "teacher answer sheet", "teacher_answer_key", "teacher answer key", "answer_key"]:
        mode_label = "Teacher Answer Key"
    elif mode_str in ["student_answer_sheet", "student answer sheet"]:
        mode_label = "Student Answer Sheet"
    elif mode_str in ["answers", "answer_sheet", "quick_answers", "quick answers"]:
        mode_label = "Quick Answers"
    else:
        mode_label = "Student"

    # Identify textbook series
    tb_raw = worksheet.get("textbook") or (theory_booklet.get("textbook") if theory_booklet else "") or worksheet.get("curriculum_series") or ""
    if not tb_raw and "content" in worksheet and isinstance(worksheet["content"], dict):
        tb_raw = worksheet["content"].get("textbook", "")
    if not tb_raw and theory_booklet and "content" in theory_booklet and isinstance(theory_booklet["content"], dict):
        tb_raw = theory_booklet["content"].get("textbook", "")
    if not tb_raw:
        combined_text = (str(worksheet.get("title", "")) + " " + str(worksheet.get("custom_instructions", ""))).lower()
        if "focus" in combined_text:
            tb_raw = "Maths in Focus"
        elif "century" in combined_text:
            tb_raw = "New Century Maths"
        elif "quest" in combined_text:
            tb_raw = "Maths Quest"
        elif "signpost" in combined_text or "singpost" in combined_text:
            tb_raw = "Signpost"
        elif "oxford" in combined_text:
            tb_raw = "Oxford"
        elif "mathscape" in combined_text:
            tb_raw = "Mathscape"
        else:
            tb_raw = "Cambridge"

    tb_lower = str(tb_raw).lower()
    if "cambridge" in tb_lower:
        tb_short = "Cambridge"
    elif "maths in focus" in tb_lower or "focus" in tb_lower:
        tb_short = "Maths in Focus"
    elif "new century" in tb_lower:
        tb_short = "New Century Maths"
    elif "quest" in tb_lower:
        tb_short = "Maths Quest"
    elif "signpost" in tb_lower or "singpost" in tb_lower:
        tb_short = "Signpost"
    elif "oxford" in tb_lower:
        tb_short = "Oxford"
    elif "mathscape" in tb_lower:
        tb_short = "Mathscape"
    else:
        cleaned_tb = re.sub(r'\(.*?\)', '', str(tb_raw)).strip()
        tb_short = cleaned_tb or "Cambridge"

    ext = extension.lstrip(".")
    filename = f"{clean_topic} {type_label} {mode_label} ({tb_short}).{ext}"
    filename = filename.replace("_", " ")
    filename = re.sub(r'\s+', ' ', filename).strip()
    return filename


def extract_review_booklet_answer_sheet_data(booklet_data: Dict[str, Any]) -> Tuple[List[str], List[str], Dict[str, Any]]:
    """
    Extracts question labels, answers, and marking key from a review booklet
    to generate matching Answer Sheet Template overlays and marking key exports.
    """
    concepts = booklet_data.get("concepts", [])
    labels = []
    answers = []
    marking_key = {}

    total_idx = 1
    for c_idx, concept in enumerate(concepts, 1):
        part_letter = chr(ord('A') + (c_idx - 1)) if c_idx <= 26 else f"A{c_idx}"
        rqs = concept.get("review_questions", []) or concept.get("practice_questions", [])
        for q_idx, q in enumerate(rqs, 1):
            if len(concepts) == 1:
                lbl = str(total_idx)
            else:
                lbl = f"{part_letter}{q_idx}"
            ans = str(q.get("final_answer", "")).strip()
            labels.append(lbl)
            answers.append(ans)
            marking_key[lbl] = ans
            total_idx += 1

    return labels, answers, marking_key


def detect_question_response_type(question_text: str, answer_text: str = "") -> str:
    """
    Detects whether a question requires a diagram/sketch, extended reasoning/proof, or compact response.
    Returns: 'diagram', 'reasoning', or 'compact'.
    Only triggers 'diagram' when the student is explicitly instructed to draw, sketch, construct,
    plot, or complete a diagram/graph (not when a diagram is simply provided as part of the question stimulus).
    """
    # A supplied TikZ diagram contains commands such as \draw. Those describe
    # the printed figure; they are not instructions for the student to draw it.
    question_prose = re.sub(
        r"\\begin\{tikzpicture\}[\s\S]*?\\end\{tikzpicture\}",
        " ", str(question_text or ""), flags=re.IGNORECASE
    )
    q_lower = question_prose.lower()

    # Explicit drawing/sketching commands directed at the student
    # Note: phrases like "as shown in the diagram below" or "refer to the diagram" MUST NOT trigger a canvas!
    diagram_active_patterns = [
        r"\b(?:draw|sketch|construct|plot)\s+(?:a|an|the|this|your|curves?|graphs?|diagrams?|flowcharts?|trees?|lines?|planes?|figures?|histograms?|polygons?)\b",
        r"\b(?:label|complete)\s+the\s+(?:diagram|figure|graph|tree|canvas|sketch|number\s+line)\b",
        r"\b(?:draw\s+a\s+tree\s+diagram|draw\s+a\s+venn\s+diagram|draw\s+a\s+flowchart|draw\s+a\s+box\s+plot|sketch\s+the\s+curve|sketch\s+the\s+graph|plot\s+the\s+points)\b",
        r"\b(?:on\s+the\s+(?:grid|cartesian\s+plane|axes|number\s+line)\s+(?:provided|below|draw|sketch))\b"
    ]

    # Passive references to diagrams that should NOT trigger a drawing canvas:
    # e.g., "as shown in the diagram below", "in the diagram below", "refer to the figure below"
    has_active_diagram = False
    for pat in diagram_active_patterns:
        if re.search(pat, q_lower):
            # Verify it's not a false positive like "draw a card" or "draw a marble"
            if re.search(r"\bdraw(?:s|ing)?\s+(?:a\s+)?(?:card|marble|ball|ticket|counter|token|letter|name|slip|coin)\b", q_lower):
                continue
            has_active_diagram = True
            break

    if has_active_diagram:
        return "diagram"

    # Reasoning / Proof detection keywords: student is asked to prove, justify, or explain with steps
    reasoning_patterns = [
        r"\b(?:prove\s+that|proof\b|show\s+that|demonstrate\s+that)\b",
        r"\b(?:justify(?:\s+your\s+answer)?|give\s+reasons?|state\s+reasons?|with\s+reasons)\b",
        r"\b(?:explain\b|show\s+your\s+working)\b",
        r"\b(?:by\s+mathematical\s+induction|deduce\s+that)\b",
        r"\b(?:congruence\s+proof|similarity\s+proof)\b"
    ]
    for pat in reasoning_patterns:
        if re.search(pat, q_lower):
            return "reasoning"

    return "compact"


def extract_worksheet_answer_sheet_data(
    questions: List[Dict[str, Any]],
    marking_key: Optional[Dict[str, Any]] = None
) -> Tuple[List[str], List[str], Dict[str, Any], List[Dict[str, Any]]]:
    """
    Expands multi-part questions (e.g. Question 1 with subparts (a), (b), (c))
    into individual subpart entries: 1(a), 1(b), 1(c) for Answer Sheets and Marking Keys.
    Returns: (labels, answers, marking_key, items)
    where items is a list of dicts with:
      {'label': lbl, 'answer': ans, 'type': 'compact'|'reasoning'|'diagram', 'prompt': prompt_text}
    """
    labels = []
    answers = []
    expanded_key = {}
    items = []
    raw_key = marking_key or {}
    questions = order_and_renumber_worksheet_questions(questions)

    for idx, q in enumerate(questions, 1):
        q_label = str(q.get("item_label") or idx).strip()
        q_text = str(q.get("text") or q.get("question") or "").strip()
        q_ans = str(q.get("correct_answer") or q.get("final_answer") or raw_key.get(q_label, "")).strip()

        _, subparts_q = split_question_subparts(q_text)
        _, subparts_a = split_question_subparts(q_ans)

        if subparts_q:
            ans_dict = dict(subparts_a) if subparts_a else {}
            for s_idx, (sub_lbl, sub_txt) in enumerate(subparts_q):
                full_lbl = f"{q_label}({sub_lbl})"
                if sub_lbl in ans_dict:
                    sub_ans = ans_dict[sub_lbl]
                elif s_idx < len(subparts_a):
                    sub_ans = subparts_a[s_idx][1]
                else:
                    sub_ans = q_ans if len(subparts_q) == 1 else ""

                item_type = detect_question_response_type(sub_txt or q_text, sub_ans)
                labels.append(full_lbl)
                answers.append(sub_ans)
                expanded_key[full_lbl] = sub_ans
                items.append({
                    "label": full_lbl,
                    "answer": sub_ans,
                    "type": item_type,
                    "prompt": sub_txt or q_text
                })
        elif subparts_a and len(subparts_a) >= 2:
            for sub_lbl, sub_ans in subparts_a:
                full_lbl = f"{q_label}({sub_lbl})"
                item_type = detect_question_response_type(q_text, sub_ans)
                labels.append(full_lbl)
                answers.append(sub_ans)
                expanded_key[full_lbl] = sub_ans
                items.append({
                    "label": full_lbl,
                    "answer": sub_ans,
                    "type": item_type,
                    "prompt": q_text
                })
        else:
            item_type = detect_question_response_type(q_text, q_ans)
            labels.append(q_label)
            answers.append(q_ans)
            expanded_key[q_label] = q_ans
            items.append({
                "label": q_label,
                "answer": q_ans,
                "type": item_type,
                "prompt": q_text
            })

    return labels, answers, expanded_key, items


def get_review_booklet_download_filename(booklet: dict, mode: str = "student", prefix: Optional[str] = None, extension: str = "pdf") -> str:
    """
    Formats the review booklet download filename:
    e.g. 'Sequences & Series Review Student (Cambridge).pdf'
         'DA Student Answer Sheet Sequences & Series Review (Cambridge).pdf'
         'DA Teacher Answer Sheet Sequences & Series Review (Cambridge).pdf'
         'Marking Key Sequences & Series Review (Cambridge).json'
    Strictly removes all '_' and replaces them with clean spaces.
    """
    topic = booklet.get("topic") or booklet.get("title") or "Mathematics"
    clean_topic = re.sub(r'^(?:Chapter|Unit|Topic\s*)?(?:\d+[\.\:\-]\s*|\d+[A-Za-z][\.\:\-]\s*|\d+\s+)', '', str(topic)).strip()
    clean_topic = re.sub(r'\s*(Topic Review & Exam Revision Booklet|Review & Exam Revision Booklet|Topic Review Booklet|Review Booklet|Revision Booklet|Booklet)\s*$', '', clean_topic, flags=re.IGNORECASE).strip()
    clean_topic = re.sub(r'^Year\s+\d+\s*(?:\([^\)]+\))?\s*(?:Mathematics)?\s*[\-\–\—\:]\s*', '', clean_topic, flags=re.IGNORECASE).strip()
    if not clean_topic:
        clean_topic = "Mathematics"

    mode_str = str(mode).strip().lower()

    tb_raw = booklet.get("textbook") or booklet.get("curriculum_series") or ""
    if not tb_raw and "content" in booklet and isinstance(booklet["content"], dict):
        tb_raw = booklet["content"].get("textbook", "")
    if not tb_raw:
        combined_text = (str(booklet.get("title", "")) + " " + str(booklet.get("custom_notes", ""))).lower()
        if "focus" in combined_text:
            tb_raw = "Maths in Focus"
        elif "century" in combined_text:
            tb_raw = "New Century Maths"
        elif "quest" in combined_text:
            tb_raw = "Maths Quest"
        elif "signpost" in combined_text or "singpost" in combined_text:
            tb_raw = "Signpost"
        elif "oxford" in combined_text:
            tb_raw = "Oxford"
        elif "mathscape" in combined_text:
            tb_raw = "Mathscape"
        else:
            tb_raw = "Cambridge"

    tb_lower = str(tb_raw).lower()
    if "cambridge" in tb_lower:
        tb_short = "Cambridge"
    elif "maths in focus" in tb_lower or "focus" in tb_lower:
        tb_short = "Maths in Focus"
    elif "new century" in tb_lower:
        tb_short = "New Century Maths"
    elif "quest" in tb_lower:
        tb_short = "Maths Quest"
    elif "signpost" in tb_lower or "singpost" in tb_lower:
        tb_short = "Signpost"
    elif "oxford" in tb_lower:
        tb_short = "Oxford"
    elif "mathscape" in tb_lower:
        tb_short = "Mathscape"
    else:
        cleaned_tb = re.sub(r'\(.*?\)', '', str(tb_raw)).strip()
        tb_short = cleaned_tb or "Cambridge"

    ext = extension.lstrip(".")

    if prefix:
        filename = f"{prefix} {clean_topic} Review ({tb_short}).{ext}"
    elif mode_str in ["student_answer_sheet", "student_ans", "answer_sheet"]:
        filename = f"DA Student Answer Sheet {clean_topic} Review ({tb_short}).{ext}"
    elif mode_str in ["teacher_answer_sheet", "teacher_ans", "sample_answer_sheet", "sample_ans"]:
        filename = f"DA Teacher Answer Sheet {clean_topic} Review ({tb_short}).{ext}"
    elif mode_str in ["marking_key", "key"]:
        filename = f"Marking Key {clean_topic} Review ({tb_short}).{ext}"
    else:
        if mode_str == "teacher":
            mode_label = "Teacher"
        elif mode_str in ["student_class", "class", "student class", "student no space", "student_no_space"]:
            mode_label = "Student no space"
        else:
            mode_label = "Student with space"
        filename = f"{clean_topic} Review {mode_label} ({tb_short}).{ext}"

    filename = filename.replace("_", " ")
    filename = re.sub(r'\s+', ' ', filename).strip()
    return filename


# ==============================================================================
# COMPLETE EXAM REVISION & PRACTICE PACKAGE GENERATOR (ANTI-TEXTBOOK • DUAL BOOKLETS)
# ==============================================================================

def build_latex_exam_theory_source(
    package_data: Dict[str, Any],
    mode: str = "student",
    term: Optional[int] = None,
    week: Optional[int] = None,
    has_logo: bool = True,
    font_theme: str = "charter"
) -> str:
    """
    Builds the complete LaTeX source for Booklet 1: Theory, Study Notes, Neon Exam Hacks,
    Coloured Speech Bubble Traps, and Worked Past Paper Examples with full marking guidelines.
    """
    year_level = package_data.get("year_level", "Mathematics")
    topic = package_data.get("topic", "Complete Exam Revision Package")
    concepts = package_data.get("concepts", [])
    mode_clean = str(mode).strip().lower()
    is_teacher = (mode_clean in ["teacher", "solutions", "master"])

    if is_teacher:
        edition_label = r"TEACHER MASTER ANNOTATED EXAM REVISION NOTES"
        short_edition = "Teacher Notes"
        badge_bg = "dawine"
    else:
        edition_label = r"EXAM REVISION NOTES \& WORKED PAST PAPERS"
        short_edition = "Exam Study Notes"
        badge_bg = "danavy"

    clean_topic = clean_worksheet_topic_title(topic)
    subject_clean = year_level if ("math" in year_level.lower()) else f"{year_level} Maths"
    topic_header = f"{subject_clean} --- {clean_topic}"

    font_key = package_data.get("font_theme") or font_theme or "charter"
    font_lines = get_font_latex_preamble(font_key)

    tex_lines = [
        r"\documentclass[11pt,a4paper]{article}",
        r"\usepackage[top=1.8cm, bottom=1.8cm, left=1.5cm, right=1.5cm, headsep=7mm, footskip=8mm]{geometry}",
        r"\usepackage[utf8]{inputenc}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage{amsmath,amssymb,amsfonts}",
        r"\usepackage{etoolbox}",
        *font_lines,
        r"\usepackage{fancyhdr}",
        r"\usepackage{graphicx}",
        r"\usepackage{adjustbox}",
        r"\usepackage{enumitem}",
        r"\usepackage{xcolor}",
        r"\usepackage{needspace}",
        r"\usepackage{setspace}",
        r"\setstretch{1.18}",
        r"\setlength{\parskip}{0.35em plus 0.1em minus 0.05em}",
        r"\setlength{\headheight}{14.5pt}",
        r"\addtolength{\topmargin}{-2.5pt}",
        r"\usepackage{tcolorbox}",
        r"\tcbuselibrary{skins,breakable}",
        r"\usepackage{varwidth}",
        r"\usepackage{tikz}",
        r"\usetikzlibrary{arrows.meta,calc,angles,quotes,shapes.geometric,patterns,decorations.pathreplacing}",
        "",
        r"\pagestyle{fancy}",
        r"\fancyhf{}",
        f"\\fancyhead[L]{{\\parbox[b]{{0.65\\textwidth}}{{\\raggedright\\footnotesize\\bfseries {sanitize_for_latex(topic_header)} Study Notes}}}}",
        f"\\fancyhead[R]{{\\parbox[b]{{0.33\\textwidth}}{{\\raggedleft\\footnotesize\\bfseries DA Tuition --- {short_edition}}}}}",
        r"\fancyfoot[C]{\thepage}",
        r"\renewcommand{\headrulewidth}{0.4pt}",
        "",
        r"\definecolor{danavy}{RGB}{15, 23, 42}",
        r"\definecolor{dawine}{RGB}{136, 19, 55}",
        r"\definecolor{dablue}{RGB}{30, 58, 138}",
        r"\definecolor{dagreen}{RGB}{5, 150, 105}",
        r"\definecolor{dagold}{RGB}{197, 155, 39}",
        r"\definecolor{neoncyan}{RGB}{6, 182, 212}",
        r"\definecolor{cyanbg}{RGB}{240, 253, 250}",
        r"\definecolor{neonpink}{RGB}{225, 29, 72}",
        r"\definecolor{pinkbg}{RGB}{255, 241, 242}",
        r"\definecolor{neonmint}{RGB}{16, 185, 129}",
        r"\definecolor{mintbg}{RGB}{236, 253, 245}",
        r"\definecolor{slatebg}{RGB}{248, 250, 252}",
        r"\definecolor{grayborder}{RGB}{226, 232, 240}",
        "",
        r"\newcommand{\neontipicon}{\raisebox{-0.5pt}{\tikz[baseline=-0.2ex,scale=0.6]{\path[fill=white] (0,1.2ex) -- (0.8ex,1.2ex) -- (0.2ex,0.3ex) -- (0.9ex,0.3ex) -- (-0.1ex,-1.0ex) -- (0.3ex,-0.1ex) -- (-0.4ex,-0.1ex) -- cycle;}}}",
        r"\newcommand{\speechbubbleicon}{\raisebox{-0.8pt}{\tikz[baseline=-0.2ex,scale=0.55]{\draw[fill=white,draw=none] (0,0.4ex) ellipse (1.0ex and 0.8ex); \fill[white] (-0.5ex,-0.2ex) -- (-0.9ex,-0.8ex) -- (-0.1ex,-0.3ex) -- cycle;}}}",
        r"\newcommand{\rubricicon}{\raisebox{-0.5pt}{\tikz[baseline=-0.2ex,scale=0.6]{\draw[draw=white,thick] (0,0.4ex) circle (0.8ex); \draw[draw=white,thick] (-0.4ex,0.4ex) -- (-0.1ex,0.1ex) -- (0.4ex,0.7ex);}}}",
        r"\newcommand{\pastpapericon}{\raisebox{-0.5pt}{\tikz[baseline=-0.2ex,scale=0.6]{\draw[fill=white,draw=white,thick] (-0.7ex,-0.9ex) rectangle (0.7ex,0.9ex); \draw[draw=dawine,thick] (-0.4ex,0.4ex) -- (0.4ex,0.4ex); \draw[draw=dawine,thick] (-0.4ex,0.0ex) -- (0.4ex,0.0ex); \draw[draw=dawine,thick] (-0.4ex,-0.4ex) -- (0.1ex,-0.4ex);}}}",
        "",
        r"\newtcolorbox{neonconceptcard}[1][]{",
        r"    enhanced,",
        r"    colback=slatebg,",
        r"    colframe=danavy,",
        r"    before skip=1pt,",
        r"    after skip=6pt,",
        r"    leftrule=3.5pt, rightrule=0.6pt, toprule=0.6pt, bottomrule=0.6pt,",
        r"    arc=4pt,",
        r"    left=11pt, right=11pt, top=9pt, bottom=9pt,",
        r"    title={\textbf{\sffamily\color{danavy}\small \quad \ifstrempty{#1}{Theory \& Comprehensive Study Notes (Self-Learning Guide)}{#1}}},",
        r"    coltitle=danavy,",
        r"    colbacktitle=slatebg,",
        r"    attach boxed title to top left={yshift=-2mm, xshift=4mm},",
        r"    boxed title style={boxrule=0pt, colframe=slatebg, arc=2pt},",
        r"    breakable,",
        r"    enforce breakable,",
        r"    pad at break=2mm,",
        r"    before upper={%",
        r"        \setlength{\abovedisplayskip}{3.5pt plus 1pt minus 1pt}%",
        r"        \setlength{\belowdisplayskip}{3.5pt plus 1pt minus 1pt}%",
        r"        \setlength{\abovedisplayshortskip}{2pt}%",
        r"        \setlength{\belowdisplayshortskip}{2pt}%",
        r"    }",
        r"}",
        "",
        r"\newtcolorbox{neonhackbox}[1][]{",
        r"    enhanced,",
        r"    colback=cyanbg,",
        r"    colframe=neoncyan,",
        r"    boxrule=1.5pt,",
        r"    arc=5pt,",
        r"    left=11pt, right=11pt, top=10pt, bottom=10pt,",
        r"    title={\textbf{\sffamily\color{white}\small \quad \neontipicon\ \ifstrempty{#1}{⚡ EXAM HACK \& TUTOR SHORTCUT}{⚡ EXAM HACK: #1}}},",
        r"    coltitle=white,",
        r"    colbacktitle=neoncyan,",
        r"    attach boxed title to top left={yshift=-2.5mm, xshift=5mm},",
        r"    boxed title style={boxrule=0pt, colframe=neoncyan, arc=3pt},",
        r"    breakable,",
        r"    pad at break=2mm",
        r"}",
        "",
        r"\newtcolorbox{speechbubbletrap}[1][]{",
        r"    enhanced,",
        r"    colback=pinkbg,",
        r"    colframe=neonpink,",
        r"    boxrule=1.5pt,",
        r"    arc=6pt,",
        r"    left=11pt, right=11pt, top=10pt, bottom=10pt,",
        r"    title={\textbf{\sffamily\color{white}\small \quad \speechbubbleicon\ \ifstrempty{#1}{💬 COMMON EXAM PITFALL \& DEADLY TRAP}{💬 COMMON EXAM TRAP: #1}}},",
        r"    coltitle=white,",
        r"    colbacktitle=neonpink,",
        r"    attach boxed title to top left={yshift=-2.5mm, xshift=5mm},",
        r"    boxed title style={boxrule=0pt, colframe=neonpink, arc=3pt},",
        r"    underlay={",
        r"        \fill[neonpink] ([xshift=18pt]frame.south west) -- ++(8pt,-8pt) -- ++(8pt,8pt) -- cycle;",
        r"        \fill[pinkbg] ([xshift=19pt, yshift=1.2pt]frame.south west) -- ++(7pt,-7pt) -- ++(7pt,7pt) -- cycle;",
        r"    },",
        r"    breakable,",
        r"    pad at break=2mm",
        r"}",
        "",
        r"\newtcolorbox{workedpastpaperbox}[1][]{",
        r"    enhanced,",
        r"    colback=white,",
        r"    colframe=dawine,",
        r"    leftrule=3.5pt, rightrule=0.6pt, toprule=0.6pt, bottomrule=0.6pt,",
        r"    arc=4pt,",
        r"    left=9pt, right=9pt, top=6pt, bottom=6pt,",
        r"    title={\textbf{\sffamily\color{white}\small \quad \pastpapericon\ \ifstrempty{#1}{Worked Past Paper Demonstration}{#1}}},",
        r"    coltitle=white,",
        r"    colbacktitle=dawine,",
        r"    attach boxed title to top left={yshift=-2.5mm, xshift=4mm},",
        r"    boxed title style={boxrule=0pt, colframe=dawine, arc=3pt},",
        r"    breakable,",
        r"    enforce breakable,",
        r"    pad at break=2mm,",
        r"    before upper={%",
        r"        \setlength{\abovedisplayskip}{3.5pt plus 1pt minus 1pt}%",
        r"        \setlength{\belowdisplayskip}{3.5pt plus 1pt minus 1pt}%",
        r"        \setlength{\abovedisplayshortskip}{2pt}%",
        r"        \setlength{\belowdisplayshortskip}{2pt}%",
        r"    }",
        r"}",
        "",
        r"\newtcolorbox{markingrubricbox}[1][]{",
        r"    enhanced,",
        r"    colback=mintbg,",
        r"    colframe=neonmint,",
        r"    leftrule=3pt, rightrule=0.6pt, toprule=0.6pt, bottomrule=0.6pt,",
        r"    arc=3pt,",
        r"    left=8pt, right=8pt, top=5pt, bottom=5pt,",
        r"    title={\textbf{\sffamily\color{white}\footnotesize \quad \rubricicon\ \ifstrempty{#1}{HSC Marking Criteria \& Rubric}{#1}}},",
        r"    coltitle=white,",
        r"    colbacktitle=neonmint,",
        r"    attach boxed title to top left={yshift=-2mm, xshift=4mm},",
        r"    boxed title style={boxrule=0pt, colframe=neonmint, arc=2pt},",
        r"    breakable,",
        r"    pad at break=2mm",
        r"}",
        "",
        r"\newtcolorbox{examtocbox}[1][]{",
        r"    enhanced,",
        r"    colback=slatebg,",
        r"    colframe=danavy!35,",
        r"    boxrule=0.8pt,",
        r"    arc=5pt,",
        r"    left=14pt, right=14pt, top=12pt, bottom=12pt,",
        r"    title={\textbf{\sffamily\color{danavy}\small \quad \ifstrempty{#1}{Exam Revision Package Blueprint}{#1}}},",
        r"    coltitle=danavy,",
        r"    colbacktitle=slatebg,",
        r"    attach boxed title to top left={yshift=-2mm, xshift=5mm},",
        r"    boxed title style={boxrule=0pt, colframe=slatebg, arc=2pt},",
        r"    breakable",
        r"}",
        "",
        r"\begin{document}",
        r"\thispagestyle{plain}",
        ""
    ]

    header_lines = [
        r"\noindent",
        r"\begin{minipage}[t]{0.70\textwidth}",
        r"\vspace{0pt}",
        r"\raggedright",
        f"{{\\huge \\textbf{{\\color{{danavy}}{subject_clean}}}}}\\\\[0.1cm]",
        f"{{\\LARGE \\textbf{{\\color{{danavy}}{sanitize_for_latex(clean_topic)}}}}}\\\\[0.15cm]",
        r"{\small \color{gray!80!black} \textbf{NSW SYLLABUS $\bullet$ EXAM REVISION \& STUDY NOTES}}\\[0.2cm]",
    ]
    meta_pills = []
    if term and week:
        meta_pills.append(f"\\tikz[baseline=-0.6ex]{{\\node[fill=danavy!10, text=danavy, rounded corners=3pt, inner sep=3pt, font=\\scriptsize\\bfseries] {{Term {term} $\\bullet$ Week {week}}};}}")
    elif term:
        meta_pills.append(f"\\tikz[baseline=-0.6ex]{{\\node[fill=danavy!10, text=danavy, rounded corners=3pt, inner sep=3pt, font=\\scriptsize\\bfseries] {{Term {term}}};}}")
    elif week:
        meta_pills.append(f"\\tikz[baseline=-0.6ex]{{\\node[fill=danavy!10, text=danavy, rounded corners=3pt, inner sep=3pt, font=\\scriptsize\\bfseries] {{Week {week}}};}}")
    meta_pills.append(f"\\tikz[baseline=-0.6ex]{{\\node[fill={badge_bg}!15, draw={badge_bg}!60, rounded corners=3pt, inner sep=3pt, font=\\scriptsize\\bfseries\\color{{{badge_bg}!90!black}}] {{{edition_label}}};}}")
    header_lines.append(" \\quad ".join(meta_pills))
    header_lines.extend([
        r"\end{minipage}%",
        r"\hfill",
        r"\begin{minipage}[t]{0.28\textwidth}",
        r"\vspace{0pt}",
        r"\raggedleft"
    ])
    tex_lines.extend(header_lines)

    if has_logo:
        tex_lines.append(r"\includegraphics[height=2.8cm,keepaspectratio]{da_logo.png}")
    else:
        tex_lines.append(r"{\Large \textbf{\color{danavy}DA TUITION}}")

    tex_lines.extend([
        r"\end{minipage}",
        r"\vspace{0.25cm}",
        r"\noindent",
        r"\tikz\draw[thick, color=danavy!25] (0,0) -- (\linewidth,0);",
        r"\vspace{0.15cm}",
        r"\noindent"
    ])

    if is_teacher:
        tex_lines.append(r"\textbf{Teacher Name:} \underline{\hspace{7.5cm}} \hfill \textbf{Date:} \underline{\hspace{3.5cm}}\\[0.25cm]")
    else:
        tex_lines.append(r"\textbf{Student Name:} \underline{\hspace{5.5cm}} \hfill \textbf{Class:} \underline{\hspace{2.2cm}} \hfill \textbf{Date:} \underline{\hspace{2.2cm}}\\[0.25cm]")

    # Table of Contents / Blueprint Card
    tex_lines.append(r"\vspace{0.3cm}")
    tex_lines.append(r"\begin{examtocbox}[Exam Study Notes \& Worked Examples Blueprint]")
    tex_lines.append(r"\vspace{0.1cm}")
    tex_lines.append(r"\begin{itemize}[leftmargin=1.2em, itemsep=0.55em, label={\color{danavy}\small$\blacktriangleright$}]")
    for c_idx_toc, c_toc in enumerate(concepts, 1):
        p_let = chr(ord('A') + (c_idx_toc - 1)) if c_idx_toc <= 26 else f"A{c_idx_toc}"
        c_name_clean = clean_subtopic_title(c_toc.get("concept_name") or c_toc.get("name", f"Concept {c_idx_toc}"))
        tex_lines.append(f"\\item \\textbf{{Part {p_let}: {sanitize_for_latex(c_name_clean)}}} \\dotfill p.~\\pageref{{sec:exam_concept_{c_idx_toc}}}")
    tex_lines.extend([
        r"\end{itemize}",
        r"\vspace{0.1cm}",
        r"\end{examtocbox}",
        r"\newpage",
        ""
    ])

    for c_idx, concept in enumerate(concepts, 1):
        raw_c_name = concept.get("concept_name") or concept.get("name", f"Concept {c_idx}")
        c_name = clean_subtopic_title(raw_c_name)
        part_letter = chr(ord('A') + (c_idx - 1)) if c_idx <= 26 else f"A{c_idx}"
        
        study_notes = concept.get("study_notes", {})
        if isinstance(study_notes, dict):
            summary_points = study_notes.get("summary_points", [])
            essential_formulas = study_notes.get("essential_formulas", [])
        else:
            summary_points = [str(study_notes)] if study_notes else []
            essential_formulas = concept.get("key_formulas", [])

        exam_hacks = concept.get("exam_hacks", [])
        common_mistakes = concept.get("common_mistakes", [])
        past_examples = concept.get("worked_past_paper_examples") or concept.get("mastery_examples", [])
        tikz_diag = concept.get("tikz_diagram", "")
        if not tikz_diag and isinstance(study_notes, dict):
            tikz_diag = study_notes.get("tikz_diagram", "")
        if not tikz_diag:
            tikz_diag = get_concept_fallback_tikz(c_name, topic)

        if c_idx > 1:
            tex_lines.append(r"\clearpage")
        
        heading_title = f"Part {part_letter}: {sanitize_for_latex(c_name)}"
        tex_lines.append(f"\\noindent{{\\Large\\textbf{{\\color{{danavy}}\\rule[-2pt]{{3.5pt}}{{14pt}}\\hspace{{6pt}}{heading_title}}}}}\\label{{sec:exam_concept_{c_idx}}}\\\\[0.05cm]")
        tex_lines.append(r"\nopagebreak")
        tex_lines.append(r"\vspace{-0.22cm}")
        tex_lines.append(r"\nopagebreak")

        # 1. Executive Study Notes Card
        tex_lines.append(r"\begin{neonconceptcard}[Theory \& Comprehensive Study Notes (Self-Learning Guide)]")
        if summary_points:
            for pt in summary_points:
                formatted_pt = format_theory_summary_point_latex(pt)
                if formatted_pt:
                    tex_lines.append(formatted_pt)

        if essential_formulas:
            tex_lines.append(r"\vspace{0.15cm}")
            tex_lines.append(r"\noindent\textbf{\color{danavy}Essential Examination Formulae:}")
            tex_lines.append(r"\begin{itemize}[leftmargin=1.5em, itemsep=0.25em]")
            for kf in essential_formulas:
                if isinstance(kf, dict):
                    f_name = kf.get("name", "")
                    f_form = kf.get("formula", "")
                    f_note = kf.get("note", "")
                    note_str = f" \\quad \\textit{{({sanitize_for_latex(f_note)})}}" if f_note else ""
                    if f_name:
                        tex_lines.append(f"\\item \\textbf{{{sanitize_for_latex(f_name)}}}: {format_theory_formula(f_form)}{note_str}")
                    else:
                        tex_lines.append(f"\\item {format_theory_formula(f_form)}{note_str}")
                else:
                    tex_lines.append(f"\\item {format_theory_formula(str(kf))}")
            tex_lines.append(r"\end{itemize}")

        if tikz_diag:
            tex_lines.append(r"\vspace{0.2cm}")
            tex_lines.append(sanitize_tikz_diagram(tikz_diag))

        tex_lines.append(r"\end{neonconceptcard}")
        tex_lines.append(r"\vspace{0.35cm}")

        # 2. Neon UI Frame: Exam Hacks & Shortcuts
        if exam_hacks:
            for h in exam_hacks:
                if isinstance(h, dict):
                    h_title = h.get("title", "High-Yield Shortcut")
                    h_content = h.get("hack_content", "")
                else:
                    h_title = "High-Yield Shortcut"
                    h_content = str(h)
                
                tex_lines.append(r"\needspace{3.5cm}")
                tex_lines.append(f"\\begin{{neonhackbox}}[{sanitize_for_latex(h_title)}]")
                tex_lines.append(f"\\noindent {sanitize_for_latex(h_content)}")
                tex_lines.append(r"\end{neonhackbox}")
                tex_lines.append(r"\vspace{0.35cm}")

        # 3. Coloured Speech Bubble: Common Exam Pitfalls & Traps
        if common_mistakes:
            for m in common_mistakes:
                if isinstance(m, dict):
                    m_title = m.get("trap_title", "Common Marking Trap")
                    m_content = m.get("trap_explanation", "")
                else:
                    m_title = "Common Marking Trap"
                    m_content = str(m)

                tex_lines.append(r"\needspace{3.5cm}")
                tex_lines.append(f"\\begin{{speechbubbletrap}}[{sanitize_for_latex(m_title)}]")
                tex_lines.append(f"\\noindent {sanitize_for_latex(m_content)}")
                tex_lines.append(r"\end{speechbubbletrap}")
                tex_lines.append(r"\vspace{0.35cm}")

        # 4. Worked Past Paper Examples with Full Marking Guidelines (Starts cleanly on next page)
        if past_examples:
            tex_lines.append(r"\clearpage")
            tex_lines.append(f"\\noindent{{\\Large\\textbf{{\\color{{dawine}}\\rule[-2pt]{{3.5pt}}{{14pt}}\\hspace{{6pt}}Part {part_letter} Worked Past Paper Exam Demonstrations}}}}\\\\[0.25cm]")
            tex_lines.append(r"\nopagebreak")
            tex_lines.append(r"\vspace{-0.1cm}")
            for e_idx, ex in enumerate(past_examples, 1):
                raw_ex_title = ex.get("title", f"Example {e_idx}")
                cleaned_ex_t = clean_ex_title(raw_ex_title)
                source_tag = ex.get("source_tag", "Authentic HSC / Trial Standard")
                source_tag = re.sub(r'\bSynthesizer\b', 'Synthesiser', str(source_tag), flags=re.IGNORECASE)
                marks_val = ex.get("marks", 3)
                p_text = ex.get("problem_text", "")
                sol = ex.get("worked_solution", "")
                criteria_list = ex.get("marking_guidelines", [])
                comm = ex.get("examiner_tip") or ex.get("exam_commentary", "")
                ex_diag = ex.get("diagram_tikz")
                if not ex_diag or not str(ex_diag).strip():
                    fallback_diag = synthesize_network_diagram_from_text(p_text, topic=topic, concept_name=c_name)
                    if fallback_diag:
                        ex_diag = fallback_diag
                sol_diag = ex.get("solution_diagram_tikz") or ex.get("solution_tikz") or ex.get("solution_diagram")
                if not sol_diag or not str(sol_diag).strip():
                    if any(k in (p_text + " " + sol).lower() for k in ["sketch", "plot the", "draw the graph", "draw the curve", "graph of", "graph the"]):
                        fallback_tikz = get_sketch_solution_fallback_tikz(p_text, sol)
                        if fallback_tikz:
                            sol_diag = fallback_tikz

                if e_idx > 1:
                    tex_lines.append(r"\needspace{6.5cm}")
                ex_box_title = f"Past Paper Example {part_letter}.{e_idx}: {cleaned_ex_t}" if cleaned_ex_t else f"Past Paper Example {part_letter}.{e_idx}"
                tex_lines.append(f"\\begin{{workedpastpaperbox}}[{sanitize_for_latex(ex_box_title)}]")
                
                # Source pill & Marks
                tex_lines.append(f"\\noindent \\tikz[baseline=-0.6ex]{{\\node[fill=dawine!10, text=dawine, rounded corners=2pt, inner sep=2pt, font=\\scriptsize\\bfseries] {{{sanitize_for_latex(source_tag)}}};}} \\hfill \\textbf{{[{marks_val} Mark{'s' if marks_val != 1 else ''}]}}\\\\[0.2cm]")
                p_formatted = format_question_parts_latex(sanitize_for_latex(p_text))
                tex_lines.append(f"\\textbf{{Problem Statement:}}\\\\[0.1cm]\n{p_formatted}\\par")
                if ex_diag and str(ex_diag).strip():
                    tex_lines.append(r"\vspace{0.15cm}")
                    tex_lines.append(sanitize_tikz_diagram(str(ex_diag).strip()))
                    tex_lines.append(r"\par")

                if sol:
                    tex_lines.append(r"\par\vspace{0.22cm}")
                    tex_lines.append(r"\noindent\textbf{\color{dawine}Step-by-Step Model Whiteboard Solution:}\\[0.12cm]")
                    tex_lines.append(format_hsc_solution_latex(sol))
                    if sol_diag and str(sol_diag).strip():
                        tex_lines.append(r"\par\vspace{0.15cm}")
                        tex_lines.append(sanitize_tikz_diagram(str(sol_diag).strip()))

                # Full Marking Guidelines & Rubric Box
                if criteria_list:
                    tex_lines.append(r"\vspace{0.18cm}")
                    tex_lines.append(r"\begin{markingrubricbox}[Official HSC Marking Criteria & Rubric]")
                    tex_lines.append(r"\begin{itemize}[leftmargin=1.5em, itemsep=0.15em]")
                    for crit in criteria_list:
                        if isinstance(crit, dict):
                            c_m = crit.get("marks", 1)
                            c_desc = crit.get("criteria", "")
                            tex_lines.append(f"\\item \\textbf{{{c_m} Mark:}} {sanitize_for_latex(c_desc)}")
                        else:
                            tex_lines.append(f"\\item {sanitize_for_latex(str(crit))}")
                    tex_lines.append(r"\end{itemize}")
                    tex_lines.append(r"\end{markingrubricbox}")

                if comm:
                    tex_lines.append(r"\vspace{0.18cm}")
                    tex_lines.append(f"\\noindent\\textbf{{\\color{{dagreen}}Examiner Advice:}} \\textit{{{sanitize_for_latex(comm)}}}")

                tex_lines.append(r"\end{workedpastpaperbox}")
                tex_lines.append(r"\vspace{0.35cm}")

        tex_lines.append(r"\vspace{0.4cm}")

    tex_lines.append(r"\end{document}")
    return "\n".join(tex_lines)


def build_latex_exam_practice_source(
    package_data: Dict[str, Any],
    mode: str = "student",
    term: Optional[int] = None,
    week: Optional[int] = None,
    has_logo: bool = True,
    font_theme: str = "charter"
) -> str:
    """
    Builds the complete LaTeX source for Booklet 2: Practice Questions & Authentic Past Papers.
    Supports two modes:
    1. 'student': Clean questions with generous unclustered student working space boxes.
    2. 'solutions' / 'teacher': Complete step-by-step whiteboard solutions and official marking rubrics.
    """
    year_level = package_data.get("year_level", "Mathematics")
    topic = package_data.get("topic", "Exam Practice Booklet")
    concepts = package_data.get("concepts", [])
    mode_clean = str(mode).strip().lower()
    is_solutions = (mode_clean in ["solutions", "teacher", "master", "marking_guidelines"])

    if is_solutions:
        edition_label = r"COMPLETE SOLUTIONS \& MARKING GUIDELINES EDITION"
        short_edition = "Solutions & Rubrics"
        badge_bg = "dawine"
    else:
        edition_label = r"STUDENT PRACTICE \& PAST PAPER BOOKLET"
        short_edition = "Student Practice"
        badge_bg = "danavy"

    clean_topic = clean_worksheet_topic_title(topic)
    subject_clean = year_level if ("math" in year_level.lower()) else f"{year_level} Maths"
    topic_header = f"{subject_clean} --- {clean_topic}"

    font_key = package_data.get("font_theme") or font_theme or "charter"
    font_lines = get_font_latex_preamble(font_key)

    tex_lines = [
        r"\documentclass[11pt,a4paper]{article}",
        r"\usepackage[top=1.8cm, bottom=1.8cm, left=1.5cm, right=1.5cm, headsep=7mm, footskip=8mm]{geometry}",
        r"\usepackage[utf8]{inputenc}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage{amsmath,amssymb,amsfonts}",
        r"\usepackage{etoolbox}",
        *font_lines,
        r"\usepackage{fancyhdr}",
        r"\usepackage{graphicx}",
        r"\usepackage{adjustbox}",
        r"\usepackage{enumitem}",
        r"\usepackage{xcolor}",
        r"\usepackage{needspace}",
        r"\usepackage{setspace}",
        r"\setstretch{1.18}",
        r"\setlength{\parskip}{0.35em plus 0.1em minus 0.05em}",
        r"\setlength{\headheight}{14.5pt}",
        r"\addtolength{\topmargin}{-2.5pt}",
        r"\usepackage{tcolorbox}",
        r"\tcbuselibrary{skins,breakable}",
        r"\usepackage{varwidth}",
        r"\usepackage{tikz}",
        r"\usetikzlibrary{arrows.meta,calc,angles,quotes,shapes.geometric,patterns,decorations.pathreplacing}",
        "",
        r"\pagestyle{fancy}",
        r"\fancyhf{}",
        f"\\fancyhead[L]{{\\parbox[b]{{0.65\\textwidth}}{{\\raggedright\\footnotesize\\bfseries {sanitize_for_latex(topic_header)} Practice}}}}",
        f"\\fancyhead[R]{{\\parbox[b]{{0.33\\textwidth}}{{\\raggedleft\\footnotesize\\bfseries DA Tuition --- {short_edition}}}}}",
        r"\fancyfoot[C]{\thepage}",
        r"\renewcommand{\headrulewidth}{0.4pt}",
        "",
        r"\definecolor{danavy}{RGB}{15, 23, 42}",
        r"\definecolor{dawine}{RGB}{136, 19, 55}",
        r"\definecolor{dablue}{RGB}{30, 58, 138}",
        r"\definecolor{dagreen}{RGB}{5, 150, 105}",
        r"\definecolor{neonmint}{RGB}{16, 185, 129}",
        r"\definecolor{mintbg}{RGB}{236, 253, 245}",
        r"\definecolor{neonpink}{RGB}{225, 29, 72}",
        r"\definecolor{pinkbg}{RGB}{255, 241, 242}",
        r"\definecolor{slatebg}{RGB}{248, 250, 252}",
        r"\definecolor{grayborder}{RGB}{226, 232, 240}",
        "",
        r"\newcommand{\rubricicon}{\raisebox{-0.5pt}{\tikz[baseline=-0.2ex,scale=0.6]{\draw[draw=white,thick] (0,0.4ex) circle (0.8ex); \draw[draw=white,thick] (-0.4ex,0.4ex) -- (-0.1ex,0.1ex) -- (0.4ex,0.7ex);}}}",
        r"\newcommand{\solutionicon}{\raisebox{-0.5pt}{\tikz[baseline=-0.2ex,scale=0.6]{\draw[draw=white,thick] (0,0.4ex) circle (0.8ex); \draw[draw=white,very thick] (-0.35ex,0.4ex) -- (-0.1ex,0.15ex) -- (0.35ex,0.65ex);}}}",
        "",
        r"\newtcolorbox{studentworkingbox}[2][]{",
        r"    enhanced,",
        r"    standard jigsaw,",
        r"    opacityback=0,",
        r"    colframe=grayborder,",
        r"    boxrule=0.7pt,",
        r"    arc=4pt,",
        r"    left=9pt, right=9pt, top=7pt, bottom=7pt,",
        r"    height=#2,",
        r"    underlay={",
        r"        \node[anchor=north east, font=\sffamily\bfseries\tiny\color{gray!45}] at (frame.north east) [xshift=-6pt, yshift=-5pt] {STUDENT WORKING SPACE};",
        r"    }",
        r"}",
        "",
        r"\newtcolorbox{practicemodelsolutionbox}[1][]{",
        r"    enhanced,",
        r"    colback=mintbg!50!white,",
        r"    colframe=neonmint!90!black,",
        r"    leftrule=3.5pt, rightrule=0.6pt, toprule=0.6pt, bottomrule=0.6pt,",
        r"    arc=3pt,",
        r"    left=9pt, right=9pt, top=7pt, bottom=7pt,",
        r"    title={\textbf{\sffamily\color{neonmint!90!black}\small \quad \ensuremath{\checkmark}~\ifstrempty{#1}{Model Worked Solution}{#1}}},",
        r"    coltitle=neonmint!90!black,",
        r"    colbacktitle=mintbg!50!white,",
        r"    attach boxed title to top left={yshift=-2mm, xshift=4mm},",
        r"    boxed title style={boxrule=0pt, colframe=mintbg!50!white, arc=2pt},",
        r"    breakable,",
        r"    enforce breakable,",
        r"    pad at break=2mm,",
        r"    before upper={%",
        r"        \setlength{\abovedisplayskip}{3.5pt plus 1pt minus 1pt}%",
        r"        \setlength{\belowdisplayskip}{3.5pt plus 1pt minus 1pt}%",
        r"        \setlength{\abovedisplayshortskip}{2pt}%",
        r"        \setlength{\belowdisplayshortskip}{2pt}%",
        r"    }",
        r"}",
        "",
        r"\newtcolorbox{markingrubricbox}[1][]{",
        r"    enhanced,",
        r"    colback=mintbg,",
        r"    colframe=neonmint,",
        r"    leftrule=3pt, rightrule=0.6pt, toprule=0.6pt, bottomrule=0.6pt,",
        r"    arc=3pt,",
        r"    left=9pt, right=9pt, top=7pt, bottom=7pt,",
        r"    title={\textbf{\sffamily\color{white}\footnotesize \quad \rubricicon\ \ifstrempty{#1}{HSC Marking Criteria \& Rubric}{#1}}},",
        r"    coltitle=white,",
        r"    colbacktitle=neonmint,",
        r"    attach boxed title to top left={yshift=-2mm, xshift=4mm},",
        r"    boxed title style={boxrule=0pt, colframe=neonmint, arc=2pt},",
        r"    breakable,",
        r"    pad at break=2mm",
        r"}",
        "",
        r"\begin{document}",
        r"\thispagestyle{plain}",
        ""
    ]

    header_lines = [
        r"\noindent",
        r"\begin{minipage}[t]{0.70\textwidth}",
        r"\vspace{0pt}",
        r"\raggedright",
        f"{{\\huge \\textbf{{\\color{{danavy}}{subject_clean}}}}}\\\\[0.1cm]",
        f"{{\\LARGE \\textbf{{\\color{{danavy}}{sanitize_for_latex(clean_topic)}}}}}\\\\[0.15cm]",
        r"{\small \color{gray!80!black} \textbf{EXAM PRACTICE \& PAST PAPERS}}\\[0.2cm]",
    ]
    meta_pills = []
    if term and week:
        meta_pills.append(f"\\tikz[baseline=-0.6ex]{{\\node[fill=danavy!10, text=danavy, rounded corners=3pt, inner sep=3pt, font=\\scriptsize\\bfseries] {{Term {term} $\\bullet$ Week {week}}};}}")
    elif term:
        meta_pills.append(f"\\tikz[baseline=-0.6ex]{{\\node[fill=danavy!10, text=danavy, rounded corners=3pt, inner sep=3pt, font=\\scriptsize\\bfseries] {{Term {term}}};}}")
    elif week:
        meta_pills.append(f"\\tikz[baseline=-0.6ex]{{\\node[fill=danavy!10, text=danavy, rounded corners=3pt, inner sep=3pt, font=\\scriptsize\\bfseries] {{Week {week}}};}}")
    meta_pills.append(f"\\tikz[baseline=-0.6ex]{{\\node[fill={badge_bg}!15, draw={badge_bg}!60, rounded corners=3pt, inner sep=3pt, font=\\scriptsize\\bfseries\\color{{{badge_bg}!90!black}}] {{{edition_label}}};}}")
    header_lines.append(" \\quad ".join(meta_pills))
    header_lines.extend([
        r"\end{minipage}%",
        r"\hfill",
        r"\begin{minipage}[t]{0.28\textwidth}",
        r"\vspace{0pt}",
        r"\raggedleft"
    ])
    tex_lines.extend(header_lines)

    if has_logo:
        tex_lines.append(r"\includegraphics[height=2.8cm,keepaspectratio]{da_logo.png}")
    else:
        tex_lines.append(r"{\Large \textbf{\color{danavy}DA TUITION}}")

    tex_lines.extend([
        r"\end{minipage}",
        r"\vspace{0.25cm}",
        r"\noindent",
        r"\tikz\draw[thick, color=danavy!25] (0,0) -- (\linewidth,0);",
        r"\vspace{0.15cm}",
        r"\noindent"
    ])

    if is_solutions:
        tex_lines.append(r"\textbf{Marker / Teacher Name:} \underline{\hspace{7.5cm}} \hfill \textbf{Date:} \underline{\hspace{3.5cm}}\\[0.25cm]")
    else:
        tex_lines.append(r"\textbf{Student Name:} \underline{\hspace{5.5cm}} \hfill \textbf{Class:} \underline{\hspace{2.2cm}} \hfill \textbf{Date:} \underline{\hspace{2.2cm}}\\[0.25cm]")

    quick_answers = []

    for c_idx, concept in enumerate(concepts, 1):
        raw_c_name = concept.get("concept_name") or concept.get("name", f"Part {c_idx}")
        c_name = clean_subtopic_title(raw_c_name)
        part_letter = chr(ord('A') + (c_idx - 1)) if c_idx <= 26 else f"A{c_idx}"
        practice_questions = concept.get("practice_questions") or concept.get("review_questions", [])

        if not practice_questions:
            continue

        if c_idx > 1:
            tex_lines.append(r"\clearpage")

        heading_title = f"Part {part_letter}: {sanitize_for_latex(c_name)} --- Exam Practice"
        tex_lines.append(f"\\noindent{{\\Large\\textbf{{\\color{{danavy}}\\rule[-2pt]{{3.5pt}}{{14pt}}\\hspace{{6pt}}{heading_title}}}}}\\\\[0.35cm]")

        if is_solutions:
            for q_idx, q in enumerate(practice_questions, 1):
                diff = q.get("difficulty", "Section 2 - Further Practice")
                diff_display = format_practice_difficulty(diff)
                source_tag = q.get("source_tag", "Authentic Past Paper Style")
                source_tag = re.sub(r'\bSynthesizer\b', 'Synthesiser', str(source_tag), flags=re.IGNORECASE)
                marks = q.get("marks", 2)
                q_text = q.get("text", "")
                sol = q.get("worked_solution", "")
                ans = q.get("final_answer", "")
                criteria_list = q.get("marking_guidelines", [])
                pitfall = q.get("examiner_pitfall", "")
                q_diag = q.get("diagram_tikz")
                if not q_diag or not str(q_diag).strip():
                    fallback_diag = synthesize_network_diagram_from_text(q_text, topic=topic, concept_name=c_name)
                    if fallback_diag:
                        q_diag = fallback_diag
                q_sol_diag = q.get("solution_diagram_tikz") or q.get("solution_tikz") or q.get("solution_diagram")
                if not q_sol_diag or not str(q_sol_diag).strip():
                    if any(k in (q_text + " " + sol).lower() for k in ["sketch", "plot the", "draw the graph", "draw the curve", "graph of", "graph the"]):
                        fallback_tikz = get_sketch_solution_fallback_tikz(q_text, sol)
                        if fallback_tikz:
                            q_sol_diag = fallback_tikz

                if ans:
                    quick_answers.append({
                        "part": f"Part {part_letter}",
                        "q_num": q_idx,
                        "ans": ans
                    })

                tex_lines.append(r"\needspace{5.0cm}")
                q_label = f"Question {part_letter}.{q_idx}"
                
                # Question Header: Question number + Source Tag immediately after, then \hfill, then Difficulty & Marks on the far right
                source_badge = f"\\tikz[baseline=-0.6ex]{{\\node[fill=danavy!10, text=danavy, rounded corners=2pt, inner sep=2.5pt, font=\\scriptsize\\bfseries] {{{sanitize_for_latex(source_tag)}}};}}"
                diff_marks_tag = f"\\mbox{{\\textbf{{[{diff_display} $\\bullet$ {marks}~mark{'s' if marks > 1 else ''}]}}}}"
                tex_lines.append(f"\\noindent\\textbf{{{q_label}}} \\quad {source_badge} \\hfill {diff_marks_tag}\\\\[0.18cm]")
                formatted_q_text = format_question_parts_latex(sanitize_for_latex(q_text))
                tex_lines.append(formatted_q_text + r"\par\vspace{0.18cm}")
                if q_diag and str(q_diag).strip():
                    tex_lines.append(sanitize_tikz_diagram(str(q_diag).strip()))
                    tex_lines.append(r"\vspace{0.15cm}")

                # Complete Solutions & Marking Guidelines Mode
                if sol:
                    tex_lines.append(r"\begin{practicemodelsolutionbox}[Step-by-Step Whiteboard Solution]")
                    tex_lines.append(format_hsc_solution_latex(sol))
                    if q_sol_diag and str(q_sol_diag).strip():
                        tex_lines.append(r"\par\vspace{0.15cm}")
                        tex_lines.append(sanitize_tikz_diagram(str(q_sol_diag).strip()))
                    if ans:
                        tex_lines.append(r"\par\vspace{0.1cm}")
                        tex_lines.append(f"\\noindent\\textbf{{Final Answer:}} {sanitize_for_latex(ans)}")
                    tex_lines.append(r"\end{practicemodelsolutionbox}")
                    tex_lines.append(r"\vspace{0.2cm}")

                if criteria_list:
                    tex_lines.append(r"\begin{markingrubricbox}[Marking Criteria \& Rubric]")
                    tex_lines.append(r"\begin{itemize}[leftmargin=1.5em, itemsep=0.2em]")
                    for crit in criteria_list:
                        if isinstance(crit, dict):
                            c_m = crit.get("marks", 1)
                            c_desc = crit.get("criteria", "")
                            tex_lines.append(f"\\item \\textbf{{{c_m} Mark:}} {sanitize_for_latex(c_desc)}")
                        else:
                            tex_lines.append(f"\\item {sanitize_for_latex(str(crit))}")
                    tex_lines.append(r"\end{itemize}")
                    tex_lines.append(r"\end{markingrubricbox}")
                    tex_lines.append(r"\vspace{0.2cm}")

                if pitfall:
                    tex_lines.append(f"\\noindent\\textbf{{\\color{{neonpink}}Examiner Deduction Warning:}} \\textit{{{sanitize_for_latex(pitfall)}}}\\\\[0.25cm]")

                tex_lines.append(r"\vspace{0.35cm}")
        else:
            # Student Practice Mode: Roomy, unclustered working space boxes enlarged dynamically
            pages_plan = paginate_exam_practice_questions(practice_questions, is_first_concept=(c_idx == 1))
            global_q_idx = 1
            for p_num, page_info in enumerate(pages_plan):
                if p_num > 0:
                    tex_lines.append(r"\clearpage")
                page_qs = page_info["questions"]
                box_heights = page_info["box_heights"]
                for q, b_h in zip(page_qs, box_heights):
                    diff = q.get("difficulty", "Section 2 - Further Practice")
                    diff_display = format_practice_difficulty(diff)
                    source_tag = q.get("source_tag", "Authentic Past Paper Style")
                    source_tag = re.sub(r'\bSynthesizer\b', 'Synthesiser', str(source_tag), flags=re.IGNORECASE)
                    marks = q.get("marks", 2)
                    q_text = q.get("text", "")
                    ans = q.get("final_answer", "")
                    q_diag = q.get("diagram_tikz")
                    if not q_diag or not str(q_diag).strip():
                        fallback_diag = synthesize_network_diagram_from_text(q_text, topic=topic, concept_name=c_name)
                        if fallback_diag:
                            q_diag = fallback_diag

                    if ans:
                        quick_answers.append({
                            "part": f"Part {part_letter}",
                            "q_num": global_q_idx,
                            "ans": ans
                        })

                    q_label = f"Question {part_letter}.{global_q_idx}"
                    source_badge = f"\\tikz[baseline=-0.6ex]{{\\node[fill=danavy!10, text=danavy, rounded corners=2pt, inner sep=2.5pt, font=\\scriptsize\\bfseries] {{{sanitize_for_latex(source_tag)}}};}}"
                    diff_marks_tag = f"\\mbox{{\\textbf{{[{diff_display} $\\bullet$ {marks}~mark{'s' if marks > 1 else ''}]}}}}"
                    tex_lines.append(r"\needspace{4.0cm}")
                    tex_lines.append(f"\\noindent\\textbf{{{q_label}}} \\quad {source_badge} \\hfill {diff_marks_tag}\\\\[0.18cm]\\nopagebreak")
                    formatted_q_text = format_question_parts_latex(sanitize_for_latex(q_text))
                    tex_lines.append(formatted_q_text + r"\par\nopagebreak\vspace{0.18cm}\nopagebreak")
                    if q_diag and str(q_diag).strip():
                        tex_lines.append(sanitize_tikz_diagram(str(q_diag).strip()))
                        tex_lines.append(r"\nopagebreak\vspace{0.15cm}\nopagebreak")

                    tex_lines.append(f"\\nopagebreak\\begin{{studentworkingbox}}{{{b_h:.1f}cm}}\\end{{studentworkingbox}}")
                    tex_lines.append(r"\vspace{0.25cm}")
                    global_q_idx += 1

        tex_lines.append(r"\vspace{0.4cm}")

    # Quick Verification Answers for Student Practice Edition
    if not is_solutions and quick_answers:
        tex_lines.append(r"\newpage")
        tex_lines.append(r"\section*{Quick Verification Answers (Student Self-Checking)}\label{sec:answers}")
        tex_lines.append(r"\noindent Use these answers to verify your final solutions after completing full working in the spaces provided.\\[0.4cm]")
        tex_lines.append(r"\begin{enumerate}[leftmargin=3.0cm, labelwidth=2.7cm, labelsep=0.3cm, align=left, itemsep=0.55em]")
        for qa in quick_answers:
            tex_lines.append(f"\\item[\\textbf{{{qa['part']} Q{qa['q_num']}.}}] {format_answer_parts_latex(sanitize_for_latex(qa['ans']))}")
        tex_lines.append(r"\end{enumerate}")

    tex_lines.append(r"\end{document}")
    return "\n".join(tex_lines)


def generate_latex_exam_theory_pdf(
    package_data: Dict[str, Any],
    mode: str = "student",
    term: Optional[int] = None,
    week: Optional[int] = None,
    font_theme: str = "charter"
) -> Optional[bytes]:
    """Compiles publication-quality Booklet 1 (Theory & Worked Examples) with LaTeX."""
    pdflatex_bin = find_pdflatex()
    if not pdflatex_bin:
        return None

    tmp_dir = tempfile.mkdtemp()
    try:
        has_logo = False
        if os.path.exists(LOGO_PATH):
            shutil.copy(LOGO_PATH, os.path.join(tmp_dir, "da_logo.png"))
            has_logo = True

        full_tex = build_latex_exam_theory_source(
            package_data=package_data,
            mode=mode,
            term=term,
            week=week,
            has_logo=has_logo,
            font_theme=font_theme
        )
        full_tex = inject_python_graphs(full_tex, tmp_dir)

        tex_path = os.path.join(tmp_dir, "exam_theory.tex")
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(full_tex)

        for _ in range(2):
            subprocess.run(
                [pdflatex_bin, "-interaction=nonstopmode", "exam_theory.tex"],
                cwd=tmp_dir,
                capture_output=True,
                check=False
            )

        pdf_path = os.path.join(tmp_dir, "exam_theory.pdf")
        if not os.path.exists(pdf_path):
            # Resilient fallback: strip broken TikZ diagrams and recompile
            tex_lines_no_tikz = []
            skip_tikz = False
            for line in full_tex.splitlines():
                if r"\begin{tikzpicture}" in line:
                    skip_tikz = True
                    continue
                if r"\end{tikzpicture}" in line:
                    skip_tikz = False
                    continue
                if not skip_tikz:
                    tex_lines_no_tikz.append(line)
            with open(tex_path, "w", encoding="utf-8") as f:
                f.write("\n".join(tex_lines_no_tikz))
            for _ in range(2):
                subprocess.run(
                    [pdflatex_bin, "-interaction=nonstopmode", "exam_theory.tex"],
                    cwd=tmp_dir,
                    capture_output=True,
                    check=False
                )

        if os.path.exists(pdf_path):
            with open(pdf_path, "rb") as f:
                raw_bytes = f.read()
            topic_str = str(package_data.get("topic", ""))
            yl_str = str(package_data.get("year_level", ""))
            return prune_trailing_blank_pages(raw_bytes, topic=topic_str, year_level=yl_str)

    except Exception:
        pass
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    return None


def generate_latex_exam_practice_pdf(
    package_data: Dict[str, Any],
    mode: str = "student",
    term: Optional[int] = None,
    week: Optional[int] = None,
    font_theme: str = "charter"
) -> Optional[bytes]:
    """Compiles publication-quality Booklet 2 (Practice & Past Papers) with LaTeX."""
    pdflatex_bin = find_pdflatex()
    if not pdflatex_bin:
        return None

    tmp_dir = tempfile.mkdtemp()
    try:
        has_logo = False
        if os.path.exists(LOGO_PATH):
            shutil.copy(LOGO_PATH, os.path.join(tmp_dir, "da_logo.png"))
            has_logo = True

        full_tex = build_latex_exam_practice_source(
            package_data=package_data,
            mode=mode,
            term=term,
            week=week,
            has_logo=has_logo,
            font_theme=font_theme
        )
        full_tex = inject_python_graphs(full_tex, tmp_dir)

        tex_path = os.path.join(tmp_dir, "exam_practice.tex")
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(full_tex)

        for _ in range(2):
            subprocess.run(
                [pdflatex_bin, "-interaction=nonstopmode", "exam_practice.tex"],
                cwd=tmp_dir,
                capture_output=True,
                check=False
            )

        pdf_path = os.path.join(tmp_dir, "exam_practice.pdf")
        if not os.path.exists(pdf_path):
            tex_lines_no_tikz = []
            skip_tikz = False
            for line in full_tex.splitlines():
                if r"\begin{tikzpicture}" in line:
                    skip_tikz = True
                    continue
                if r"\end{tikzpicture}" in line:
                    skip_tikz = False
                    continue
                if not skip_tikz:
                    tex_lines_no_tikz.append(line)
            with open(tex_path, "w", encoding="utf-8") as f:
                f.write("\n".join(tex_lines_no_tikz))
            for _ in range(2):
                subprocess.run(
                    [pdflatex_bin, "-interaction=nonstopmode", "exam_practice.tex"],
                    cwd=tmp_dir,
                    capture_output=True,
                    check=False
                )

        if os.path.exists(pdf_path):
            with open(pdf_path, "rb") as f:
                raw_bytes = f.read()
            topic_str = str(package_data.get("topic", ""))
            yl_str = str(package_data.get("year_level", ""))
            return prune_trailing_blank_pages(raw_bytes, topic=topic_str, year_level=yl_str)

    except Exception:
        pass
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    return None


def generate_exam_package_theory_pdf(
    package_data: Dict[str, Any],
    mode: str = "student",
    term: Optional[int] = None,
    week: Optional[int] = None,
    font_theme: str = "charter"
) -> bytes:
    """Generates Booklet 1: Theory, Notes & Worked Examples PDF."""
    latex_bytes = generate_latex_exam_theory_pdf(
        package_data=package_data,
        mode=mode,
        term=term,
        week=week,
        font_theme=font_theme
    )
    if latex_bytes:
        return latex_bytes
    # Fallback to review booklet reportlab compiler if pdflatex fails
    return generate_reportlab_review_booklet_pdf(package_data, mode=mode, term=term, week=week)


def generate_exam_package_practice_pdf(
    package_data: Dict[str, Any],
    mode: str = "student",
    term: Optional[int] = None,
    week: Optional[int] = None,
    font_theme: str = "charter"
) -> bytes:
    """Generates Booklet 2: Practice & Past Papers PDF (Student or Solutions edition)."""
    latex_bytes = generate_latex_exam_practice_pdf(
        package_data=package_data,
        mode=mode,
        term=term,
        week=week,
        font_theme=font_theme
    )
    if latex_bytes:
        return latex_bytes
    return generate_reportlab_review_booklet_pdf(package_data, mode=mode, term=term, week=week)


def generate_exam_package_theory_docx(
    package_data: Dict[str, Any],
    mode: str = "student",
    term: Optional[int] = None,
    week: Optional[int] = None
) -> Optional[bytes]:
    """Generates an editable Word (.docx) Booklet 1: Theory & Worked Examples."""
    full_tex = build_latex_exam_theory_source(
        package_data=package_data,
        mode=mode,
        term=term,
        week=week,
        has_logo=False
    )
    return docx_generator.latex_to_docx(full_tex)


def generate_exam_package_practice_docx(
    package_data: Dict[str, Any],
    mode: str = "student",
    term: Optional[int] = None,
    week: Optional[int] = None
) -> Optional[bytes]:
    """Generates an editable Word (.docx) Booklet 2: Practice Questions (Student or Solutions)."""
    full_tex = build_latex_exam_practice_source(
        package_data=package_data,
        mode=mode,
        term=term,
        week=week,
        has_logo=False
    )
    return docx_generator.latex_to_docx(full_tex)


def get_exam_package_download_filename(
    package: dict,
    booklet_type: str = "theory",
    mode: str = "student",
    extension: str = "pdf"
) -> str:
    """
    Formats the Exam Package download filenames:
    - Theory: 'Vectors & 3D Lines Exam Theory & Notes (Cambridge).pdf'
    - Student Practice: 'Vectors & 3D Lines Exam Practice Student (Cambridge).pdf'
    - Solutions: 'Vectors & 3D Lines Exam Practice Complete Solutions (Cambridge).pdf'
    """
    topic = package.get("topic") or package.get("title") or "Mathematics"
    clean_topic = re.sub(r'^(?:Chapter|Unit|Topic\s*)?(?:\d+[\.\:\-]\s*|\d+[A-Za-z][\.\:\-]\s*|\d+\s+)', '', str(topic)).strip()
    clean_topic = re.sub(r'\s*(Complete Exam Package|Exam Package|Exam Revision|Package|Booklet)\s*$', '', clean_topic, flags=re.IGNORECASE).strip()
    clean_topic = re.sub(r'^Year\s+\d+\s*(?:\([^\)]+\))?\s*(?:Mathematics)?\s*[\-\–\—\:]\s*', '', clean_topic, flags=re.IGNORECASE).strip()
    if not clean_topic:
        clean_topic = "Mathematics"

    tb_raw = package.get("textbook") or package.get("curriculum_series") or ""
    if not tb_raw and "content" in package and isinstance(package["content"], dict):
        tb_raw = package["content"].get("textbook", "")
    if not tb_raw:
        tb_raw = "Cambridge"

    tb_lower = str(tb_raw).lower()
    if "cambridge" in tb_lower:
        tb_short = "Cambridge"
    elif "maths in focus" in tb_lower or "focus" in tb_lower:
        tb_short = "Maths in Focus"
    elif "new century" in tb_lower:
        tb_short = "New Century Maths"
    elif "quest" in tb_lower:
        tb_short = "Maths Quest"
    elif "signpost" in tb_lower:
        tb_short = "Signpost"
    elif "oxford" in tb_lower:
        tb_short = "Oxford"
    elif "mathscape" in tb_lower:
        tb_short = "Mathscape"
    else:
        cleaned_tb = re.sub(r'\(.*?\)', '', str(tb_raw)).strip()
        tb_short = cleaned_tb or "Cambridge"

    ext = extension.lstrip(".")
    b_type = str(booklet_type).strip().lower()
    m_type = str(mode).strip().lower()

    if b_type in ["theory", "notes", "study_notes", "booklet_1", "b1"]:
        mode_label = "Teacher Annotated" if m_type in ["teacher", "master"] else "Study Notes"
        filename = f"{clean_topic} Exam Theory & {mode_label} ({tb_short}).{ext}"
    else:
        # Practice booklet
        if m_type in ["solutions", "teacher", "marking_guidelines", "master"]:
            mode_label = "Complete Solutions & Marking Guidelines"
        else:
            mode_label = "Student Practice"
        filename = f"{clean_topic} Exam Practice {mode_label} ({tb_short}).{ext}"

    filename = filename.replace("_", " ")
    filename = re.sub(r'\s+', ' ', filename).strip()
    return filename


def generate_exam_package_zip_bundle(
    package_data: Dict[str, Any],
    font_theme: str = "charter"
) -> bytes:
    """
    Creates a complete .zip bundle containing:
    1. Booklet 1 (Theory & Worked Examples) PDF
    2. Booklet 2 (Student Practice Edition) PDF
    3. Booklet 2 (Complete Solutions & Marking Guidelines) PDF
    """
    import zipfile
    import io

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. Theory PDF
        try:
            theory_pdf = generate_exam_package_theory_pdf(package_data, mode="student", font_theme=font_theme)
            if theory_pdf:
                zf.writestr(get_exam_package_download_filename(package_data, booklet_type="theory", mode="student", extension="pdf"), theory_pdf)
        except Exception:
            pass

        # 2. Practice Student PDF
        try:
            practice_student_pdf = generate_exam_package_practice_pdf(package_data, mode="student", font_theme=font_theme)
            if practice_student_pdf:
                zf.writestr(get_exam_package_download_filename(package_data, booklet_type="practice", mode="student", extension="pdf"), practice_student_pdf)
        except Exception:
            pass

        # 3. Practice Solutions PDF
        try:
            practice_sol_pdf = generate_exam_package_practice_pdf(package_data, mode="solutions", font_theme=font_theme)
            if practice_sol_pdf:
                zf.writestr(get_exam_package_download_filename(package_data, booklet_type="practice", mode="solutions", extension="pdf"), practice_sol_pdf)
        except Exception:
            pass

    zip_buf.seek(0)
    return zip_buf.getvalue()
