import os
import re
import shutil
import tempfile
import subprocess
from typing import Optional, Dict, Any, List

try:
    import docx
    from docx.shared import Cm, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
except ImportError:
    docx = None

from graph_generator import inject_python_graphs

LOGO_PATH = os.path.join(os.path.dirname(__file__), "da_logo.png")

def find_pandoc() -> Optional[str]:
    """Finds the pandoc executable on the system."""
    pandoc_path = shutil.which("pandoc")
    if pandoc_path:
        return pandoc_path
    for path in ["/opt/homebrew/bin/pandoc", "/usr/local/bin/pandoc", "/usr/bin/pandoc"]:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None

def latex_to_docx(latex_text: str, work_dir: Optional[str] = None) -> Optional[bytes]:
    """
    Converts a LaTeX string into an editable Word document (.docx) using Pandoc and python-docx.
    Automatically resolves and renders any embedded graph blocks, sets 1.5cm margins, and returns bytes.
    """
    pandoc_bin = find_pandoc()
    if not pandoc_bin:
        return None

    own_temp = False
    if not work_dir or not os.path.isdir(work_dir):
        work_dir = tempfile.mkdtemp()
        own_temp = True

    try:
        # Copy logo if present so \includegraphics can find it
        if os.path.exists(LOGO_PATH):
            shutil.copy(LOGO_PATH, os.path.join(work_dir, "da_logo.png"))

        # Inject Matplotlib graphs into work_dir
        clean_latex = inject_python_graphs(latex_text, work_dir)

        tex_filename = os.path.join(work_dir, "document.tex")
        docx_filename = os.path.join(work_dir, "output.docx")

        with open(tex_filename, "w", encoding="utf-8") as f:
            f.write(clean_latex)

        # Run Pandoc
        res = subprocess.run(
            [pandoc_bin, tex_filename, "-o", docx_filename],
            cwd=work_dir,
            capture_output=True,
            timeout=30
        )

        if os.path.exists(docx_filename) and docx is not None:
            # Post-process with python-docx to ensure standard 1.5cm margins
            doc = docx.Document(docx_filename)
            for section in doc.sections:
                section.top_margin = Cm(1.5)
                section.bottom_margin = Cm(1.5)
                section.left_margin = Cm(1.5)
                section.right_margin = Cm(1.5)
            doc.save(docx_filename)

            with open(docx_filename, "rb") as f:
                return f.read()

        return None
    except Exception as e:
        print(f"[docx_generator] Error converting LaTeX to DOCX: {e}")
        return None
    finally:
        if own_temp and os.path.exists(work_dir):
            shutil.rmtree(work_dir, ignore_errors=True)

def build_worksheet_docx(
    title: str,
    year_level: str,
    topic: str,
    questions: List[Dict[str, Any]],
    include_solutions: bool = True,
    term: Optional[int] = None,
    week: Optional[int] = None,
    sheet_type: str = "Homework",
    set_number: Optional[int] = 1,
    latex_source: Optional[str] = None
) -> Optional[bytes]:
    """
    Builds a Word (.docx) document for a worksheet.
    If latex_source is already provided, converts directly; otherwise generates clean LaTeX and converts.
    """
    if latex_source:
        return latex_to_docx(latex_source)

    # Fallback to constructing a clean pandoc LaTeX document
    subject_clean = f"{year_level} Maths"
    term_str = f"Term {term} " if term else ""
    week_str = f"Week {week}" if week else ""
    tw_str = f"({term_str}{week_str})".strip() if (term or week) else ""
    set_str = f"Set {set_number if set_number else 1}"

    tex_body = f"""\\documentclass[11pt]{{article}}
\\usepackage{{amsmath, amssymb, graphicx}}
\\begin{{document}}
\\begin{{center}}
    {{\\LARGE \\textbf{{DA TUITION}}}}\\\\[0.2cm]
    {{\\Large \\textbf{{{subject_clean} --- {topic} ({sheet_type} {set_str})}}}}\\\\[0.1cm]
    {{\\normalsize {tw_str}}}
\\end{{center}}
\\vspace{{0.5cm}}
\\noindent \\textbf{{Student Name:}} \\hrulefill \\quad \\textbf{{Class:}} \\hrulefill \\\\[0.4cm]
\\hrule
\\vspace{{0.5cm}}

\\section*{{Questions}}
\\begin{{enumerate}}
"""
    for q in questions:
        q_text = q.get("question", "")
        marks = q.get("marks", 1)
        tex_body += f"\\item {q_text} \\hfill \\textbf{{({marks} mark{'s' if marks > 1 else ''})}}\\\\[0.8cm]\n"

    tex_body += "\\end{enumerate}\n\\newpage\n\\section*{Answers}\n\\begin{enumerate}\n"
    for q in questions:
        ans = q.get("answer", "")
        tex_body += f"\\item {ans}\n"
    tex_body += "\\end{enumerate}\n"

    if include_solutions:
        tex_body += "\\newpage\n\\section*{Fully Worked Solutions}\n\\begin{enumerate}\n"
        for q in questions:
            sol = q.get("solution", "")
            tex_body += f"\\item {sol}\\\\[0.5cm]\n"
        tex_body += "\\end{enumerate}\n"

    tex_body += "\\end{document}"
    return latex_to_docx(tex_body)
