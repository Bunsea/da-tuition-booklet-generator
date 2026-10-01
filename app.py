import streamlit as st
import os
import io
import re
import json
import time
import base64
import hashlib
import zipfile
from datetime import datetime, date
from typing import Optional, List, Dict, Any, Tuple
from dotenv import load_dotenv

# st.set_page_config must be the FIRST Streamlit command executed
st.set_page_config(
    page_title="DA Tuition - Tutor Hub",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

import pypdfium2
import pandas as pd
import plotly.express as px

# Configure persistent cache for matplotlib
_WORKSPACE_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache", "matplotlib")
os.makedirs(_WORKSPACE_CACHE, exist_ok=True)

import database
import ai_engine
import pdf_generator
import cloud_sync
import docx_generator
import graph_generator

load_dotenv()

def get_theory_booklet_download_filename(booklet: dict, mode: str = "student", extension: str = "pdf") -> str:
    """
    Formats the theory booklet download filename according to the DA Tuition convention:
    e.g. 'Sequences & Series Theory Student (Cambridge).pdf'
         'Sequences & Series Theory Teacher (Cambridge).docx'
    Strictly removes all '_' and replaces them with clean spaces.
    """
    topic = booklet.get("topic") or booklet.get("title") or "Mathematics"
    # Clean up leading chapter prefix (e.g. "1. ", "6: ", "10A. ", "1 ") without stripping "2D" or "3D"
    clean_topic = re.sub(r'^(?:Chapter|Unit|Topic\s*)?(?:\d+[\.\:\-]\s*|\d+[A-Za-z][\.\:\-]\s*|\d+\s+)', '', str(topic)).strip()
    # Remove generic trailing phrases if present in title fallback
    clean_topic = re.sub(r'\s*(Theory & Practice Booklet|Theory Booklet|Practice Booklet|Booklet)\s*$', '', clean_topic, flags=re.IGNORECASE).strip()
    # Also remove year level prefix if it leaked into the topic (e.g. "Year 12 Mathematics - Sequences and Series")
    clean_topic = re.sub(r'^Year\s+\d+\s*(?:\([^\)]+\))?\s*(?:Mathematics)?\s*[\-\–\—\:]\s*', '', clean_topic, flags=re.IGNORECASE).strip()
    if not clean_topic:
        clean_topic = "Mathematics"
    
    mode_str = str(mode).strip().lower()
    if mode_str == "teacher":
        mode_label = "Teacher"
    elif mode_str in ["student_private", "private", "student private"]:
        mode_label = "Student Private"
    else:
        mode_label = "Student Class"

    # Identify textbook series
    tb_raw = booklet.get("textbook") or booklet.get("curriculum_series") or ""
    if not tb_raw and "content" in booklet and isinstance(booklet["content"], dict):
        tb_raw = booklet["content"].get("textbook", "")
    if not tb_raw:
        # Check custom notes or title for textbook mentions
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
        # Strip parenthetical annotations like '(Nelson Cengage)'
        cleaned_tb = re.sub(r'\(.*?\)', '', str(tb_raw)).strip()
        tb_short = cleaned_tb or "Cambridge"

    ext = extension.lstrip(".")
    filename = f"{clean_topic} Theory {mode_label} ({tb_short}).{ext}"
    # Remove all underscores and normalize spaces
    filename = filename.replace("_", " ")
    filename = re.sub(r'\s+', ' ', filename).strip()
    return filename

def get_combined_booklet_filename(booklet: dict, edition: str, homework_set: Optional[int] = None) -> str:
    """Name a joined PDF by its contents and matching audience edition."""
    theory_name = get_theory_booklet_download_filename(booklet, mode=edition)
    topic, _, edition_and_series = theory_name.rpartition(" Theory ")
    sections = "Theory + In-Class"
    if homework_set is not None:
        sections += f" + Homework Set {homework_set}"
    return f"{topic} {sections} {edition_and_series}"

def get_review_booklet_download_filename(booklet: dict, mode: str = "student", prefix: Optional[str] = None, extension: str = "pdf") -> str:
    """
    Formats the review booklet download filename:
    e.g. 'Sequences & Series Review Student (Cambridge).pdf'
         'DA Student Answer Sheet Sequences & Series Review (Cambridge).pdf'
         'DA Teacher Answer Sheet Sequences & Series Review (Cambridge).pdf'
         'Marking Key Sequences & Series Review (Cambridge).json'
    Strictly removes all '_' and replaces them with clean spaces.
    """
    return pdf_generator.get_review_booklet_download_filename(booklet, mode=mode, prefix=prefix, extension=extension)

def get_exam_package_download_filename(package: dict, booklet_type: str = "theory", mode: str = "student", extension: str = "pdf") -> str:
    """
    Formats the complete exam package download filename:
    e.g. 'Vectors & 3D Lines Exam Theory & Study Notes (Cambridge).pdf'
         'Vectors & 3D Lines Exam Practice Student (Cambridge).pdf'
         'Vectors & 3D Lines Exam Practice Complete Solutions (Cambridge).pdf'
    """
    return pdf_generator.get_exam_package_download_filename(package, booklet_type=booklet_type, mode=mode, extension=extension)

def get_topic_exam_download_filename(exam: dict, mode: str = "student", extension: str = "pdf", theory_booklet: Optional[dict] = None) -> str:
    """
    Formats the End-of-Topic Mastery Exam download filename:
    e.g. 'Functions End-of-Topic Mastery Exam Student (Cambridge).pdf'
         'Functions End-of-Topic Mastery Exam Teacher Solutions (Cambridge).pdf'
    Strictly removes all '_' and replaces them with clean spaces.
    """
    return pdf_generator.get_topic_exam_download_filename(exam, mode=mode, extension=extension, theory_booklet=theory_booklet)

def get_worksheet_download_filename(worksheet: dict, sheet_type: str = "homework", mode: str = "student", extension: str = "pdf", theory_booklet: Optional[dict] = None) -> str:
    """
    Formats the worksheet download filename:
    e.g. 'Functions In-Class Exercise Student (Cambridge).pdf'
         'Functions Homework Set 1 Teacher Solutions (Cambridge).pdf'
    Strictly removes all '_' and replaces them with clean spaces.
    """
    return pdf_generator.get_worksheet_download_filename(worksheet, sheet_type=sheet_type, mode=mode, extension=extension, theory_booklet=theory_booklet)



# Initialize Database
database.init_db()

@st.cache_data(show_spinner=False)
def get_cached_worksheet_pdf(
    ws_id: int,
    title: str,
    year_level: str,
    topic: str,
    questions_json: str,
    marking_key_json: str,
    term: Optional[int],
    week: Optional[int],
    sheet_type: str,
    mode: str,
    set_number: int = 1
) -> bytes:
    """Cached compilation helper for worksheet PDFs across all editions."""
    questions = json.loads(questions_json) if questions_json else []
    marking_key = json.loads(marking_key_json) if marking_key_json else {}

    if mode == "student":
        return pdf_generator.generate_worksheet_pdf(
            title=title, year_level=year_level, topic=topic,
            questions=questions, include_solutions=False, sheet_type=sheet_type,
            set_number=set_number, font_theme="charter"
        )
    elif mode == "teacher":
        return pdf_generator.generate_worksheet_pdf(
            title=title, year_level=year_level, topic=topic,
            questions=questions, include_solutions=True, sheet_type=sheet_type,
            set_number=set_number, font_theme="charter"
        )
    elif mode in ["answers", "student_answer_sheet"]:
        labels, answers, _, items = pdf_generator.extract_worksheet_answer_sheet_data(questions, marking_key)
        return pdf_generator.generate_answer_sheet_pdf(
            question_labels=labels, answers=answers,
            num_questions=len(labels), term=term, week=week,
            is_teacher=False, items=items
        )
    elif mode in ["teacher_answers", "teacher_answer_key", "answer_key"]:
        labels, answers, _, items = pdf_generator.extract_worksheet_answer_sheet_data(questions, marking_key)
        return pdf_generator.generate_answer_sheet_pdf(
            question_labels=labels, answers=answers,
            num_questions=len(labels), term=term, week=week,
            is_teacher=True, items=items
        )
    return b""


@st.cache_data(show_spinner=False)
def get_cached_review_pdf(
    rb_id: int,
    content_json: str,
    term: Optional[int],
    week: Optional[int],
    mode: str
) -> bytes:
    """Cached compilation helper for Topic Review Booklets."""
    booklet_data = json.loads(content_json) if content_json else {}
    return pdf_generator.generate_review_booklet_pdf(
        booklet_data=booklet_data, mode=mode,
        term=term, week=week, font_theme="charter"
    )


@st.cache_data(show_spinner=False)
def get_cached_exam_pkg_pdf(
    pkg_id: int,
    content_json: str,
    booklet_type: str,
    term: Optional[int],
    week: Optional[int],
    mode: str = "teacher"
) -> bytes:
    """Cached compilation helper for Exam Preparation Packages."""
    package_data = json.loads(content_json) if content_json else {}
    if booklet_type == "theory":
        return pdf_generator.generate_exam_package_theory_pdf(
            package_data=package_data, term=term, week=week, font_theme="charter"
        )
    else:
        return pdf_generator.generate_exam_package_practice_pdf(
            package_data=package_data, mode=mode, term=term, week=week, font_theme="charter"
        )


@st.cache_data(show_spinner=False)
def build_worksheet_zip_package(
    ws_id: int,
    ws_data_json: str,
    tb_data_json: Optional[str] = None
) -> bytes:
    """Builds a single ZIP file containing all 4 materials for the worksheet."""
    ws = json.loads(ws_data_json)
    tb = json.loads(tb_data_json) if tb_data_json else None

    title = ws.get("title", "Worksheet")
    year_level = ws.get("year_level", "")
    topic = ws.get("topic", "")
    questions = ws.get("questions", [])
    q_json = json.dumps(questions)
    mk_json = json.dumps(ws.get("marking_key", {}))
    term = ws.get("term")
    week = ws.get("week")
    stype = ws.get("assessment_type") or ws.get("sheet_type") or "homework"
    snum = ws.get("set_number", 1)

    pdf_stu = get_cached_worksheet_pdf(ws_id, title, year_level, topic, q_json, mk_json, term, week, stype, "student", snum)
    pdf_tea = get_cached_worksheet_pdf(ws_id, title, year_level, topic, q_json, mk_json, term, week, stype, "teacher", snum)
    pdf_sans = get_cached_worksheet_pdf(ws_id, title, year_level, topic, q_json, mk_json, term, week, stype, "answers", snum)
    pdf_tans = get_cached_worksheet_pdf(ws_id, title, year_level, topic, q_json, mk_json, term, week, stype, "teacher_answers", snum)

    name_stu = get_worksheet_download_filename(ws, sheet_type=stype, mode="student", theory_booklet=tb)
    name_tea = get_worksheet_download_filename(ws, sheet_type=stype, mode="teacher", theory_booklet=tb)
    name_sans = get_worksheet_download_filename(ws, sheet_type=stype, mode="answers", theory_booklet=tb)
    name_tans = get_worksheet_download_filename(ws, sheet_type=stype, mode="teacher_answers", theory_booklet=tb)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if pdf_stu:
            zf.writestr(name_stu, pdf_stu)
        if pdf_tea:
            zf.writestr(name_tea, pdf_tea)
        if pdf_sans:
            zf.writestr(name_sans, pdf_sans)
        if pdf_tans:
            zf.writestr(name_tans, pdf_tans)

    buf.seek(0)
    return buf.getvalue()


@st.cache_data(show_spinner=False)
def build_review_zip_package(
    rb_id: int,
    rb_data_json: str
) -> bytes:
    """Builds a single ZIP file containing Student and Teacher Review Booklets."""
    rb = json.loads(rb_data_json)
    rb_cnt = rb.get("content", rb)
    cnt_json = json.dumps(rb_cnt)
    term = rb.get("term")
    week = rb.get("week")

    pdf_stu = get_cached_review_pdf(rb_id, cnt_json, term, week, "student")
    pdf_tea = get_cached_review_pdf(rb_id, cnt_json, term, week, "teacher")

    name_stu = get_review_booklet_download_filename(rb, mode="student")
    name_tea = get_review_booklet_download_filename(rb, mode="teacher")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if pdf_stu:
            zf.writestr(name_stu, pdf_stu)
        if pdf_tea:
            zf.writestr(name_tea, pdf_tea)

    buf.seek(0)
    return buf.getvalue()


@st.cache_data(show_spinner=False)
def build_exam_zip_package(
    exam_id: int,
    exam_data_json: str,
    tb_data_json: Optional[str] = None
) -> bytes:
    """Builds a single ZIP file containing Student and Teacher Exam Papers."""
    le = json.loads(exam_data_json)
    tb = json.loads(tb_data_json) if tb_data_json else None

    title = le.get("title", "Exam")
    year_level = le.get("year_level", "")
    topic = le.get("topic", "")
    questions = le.get("questions", [])
    q_json = json.dumps(questions)
    mk_json = json.dumps(le.get("marking_key", {}))
    term = le.get("term")
    week = le.get("week")

    pdf_stu = get_cached_worksheet_pdf(exam_id, title, year_level, topic, q_json, mk_json, term, week, "topic_exam", "student")
    pdf_tea = get_cached_worksheet_pdf(exam_id, title, year_level, topic, q_json, mk_json, term, week, "topic_exam", "teacher")

    name_stu = get_topic_exam_download_filename(le, mode="student", theory_booklet=tb)
    name_tea = get_topic_exam_download_filename(le, mode="teacher", theory_booklet=tb)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if pdf_stu:
            zf.writestr(name_stu, pdf_stu)
        if pdf_tea:
            zf.writestr(name_tea, pdf_tea)

    buf.seek(0)
    return buf.getvalue()


@st.cache_data(show_spinner=False)
def build_exam_pkg_zip_package(
    pkg_id: int,
    pkg_data_json: str
) -> bytes:
    """Builds a single ZIP file containing Booklet 1 and Booklet 2 for the Exam Package."""
    pkg = json.loads(pkg_data_json)
    mp_content = pkg.get("content", pkg)
    cnt_json = json.dumps(mp_content)
    term = pkg.get("term")
    week = pkg.get("week")

    pdf_b1 = get_cached_exam_pkg_pdf(pkg_id, cnt_json, "theory", term, week, "student")
    pdf_b2 = get_cached_exam_pkg_pdf(pkg_id, cnt_json, "practice", term, week, "teacher")

    name_b1 = get_exam_package_download_filename(pkg, booklet_type="theory", mode="student")
    name_b2 = get_exam_package_download_filename(pkg, booklet_type="practice", mode="teacher")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if pdf_b1:
            zf.writestr(name_b1, pdf_b1)
        if pdf_b2:
            zf.writestr(name_b2, pdf_b2)

    buf.seek(0)
    return buf.getvalue()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGO_TRANSPARENT = os.path.join(BASE_DIR, "da_logo_transparent.png")
LOGO_FILE = LOGO_TRANSPARENT if os.path.exists(LOGO_TRANSPARENT) else os.path.join(BASE_DIR, "da_logo.png")

@st.cache_data
def get_logo_base64() -> str:
    """Returns base64 string of the high-res transparent logo for crisp, retina-ready rendering."""
    for path in [os.path.join(BASE_DIR, "da_logo_transparent.png"), os.path.join(BASE_DIR, "da_logo.png")]:
        if os.path.exists(path):
            try:
                with open(path, "rb") as f:
                    return base64.b64encode(f.read()).decode("utf-8")
            except Exception:
                pass
    return ""


def render_authentic_pdf_preview(
    pdf_bytes: Optional[bytes] = None,
    key_prefix: str = "pdf_preview",
    available_editions: Optional[Dict[str, bytes]] = None,
    default_edition: Optional[str] = None,
    raw_content_callback: Optional[Any] = None,
    raw_content_title: str = "📝 View Raw Question Data & LaTeX Code"
):
    """
    Renders an authentic, pixel-perfect PDF preview matching the downloaded PDF.
    Always displays all pages as a continuous scroll on a dark slate canvas (#525659)
    with drop shadows, supporting edition switching where multiple editions exist.
    """
    active_bytes = pdf_bytes
    if available_editions and len(available_editions) > 1:
        edition_names = list(available_editions.keys())
        default_idx = 0
        if default_edition and default_edition in edition_names:
            default_idx = edition_names.index(default_edition)

        chosen_edition = st.selectbox(
            "📄 Preview Booklet Edition:",
            edition_names,
            index=default_idx,
            key=f"{key_prefix}_edition_select",
            help="Select which compiled edition you wish to inspect in the authentic preview."
        )
        active_bytes = available_editions.get(chosen_edition)

    if not active_bytes:
        st.info("ℹ️ No compiled PDF available to preview.")
        return

    # Check session state image cache by MD5 hash
    pdf_hash = hashlib.md5(active_bytes).hexdigest()
    cache_key = f"pdf_preview_pages_{pdf_hash}"

    if cache_key not in st.session_state:
        try:
            doc = pypdfium2.PdfDocument(active_bytes)
            pages_b64 = []
            for page in doc:
                img = page.render(scale=1.75).to_pil()
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=85)
                pages_b64.append(base64.b64encode(buf.getvalue()).decode("utf-8"))
            st.session_state[cache_key] = pages_b64
        except Exception as e:
            st.error(f"Unable to render authentic PDF preview: {e}")
            return

    pages_b64 = st.session_state.get(cache_key, [])
    total_pages = len(pages_b64)
    if total_pages == 0:
        st.warning("PDF contains 0 pages.")
        return

    # Always render all pages as a continuous scrollable stack
    pages_snippets = []
    for idx, page_b64 in enumerate(pages_b64):
        pages_snippets.append(
            '<div style="margin-bottom: 24px; width: 100%; max-width: 880px;'
            ' display: flex; flex-direction: column; align-items: center;">'
            '<div style="color: #cbd5e1; font-size: 0.78rem; font-weight: 600;'
            ' margin-bottom: 6px; letter-spacing: 0.6px; text-transform: uppercase;">'
            f'Page {idx + 1} of {total_pages}'
            '</div>'
            '<div style="background: white; border-radius: 3px;'
            ' box-shadow: 0 10px 32px rgba(0,0,0,0.45); width: 100%; overflow: hidden;">'
            f'<img src="data:image/jpeg;base64,{page_b64}"'
            f' style="width: 100%; height: auto; display: block;" alt="PDF Page {idx + 1}" />'
            '</div>'
            '</div>'
        )
    html_markup = (
        '<div style="background-color: #525659; padding: 28px 16px; border-radius: 8px;'
        ' display: flex; flex-direction: column; align-items: center;'
        ' box-shadow: inset 0 2px 8px rgba(0,0,0,0.35); margin: 8px 0 16px 0;">'
        + "".join(pages_snippets)
        + '</div>'
    )
    st.markdown(html_markup, unsafe_allow_html=True)




    # Optional collapsible raw content
    if raw_content_callback:
        with st.expander(raw_content_title, expanded=False):
            raw_content_callback()


YEAR_LEVEL_OPTIONS = [
    "Year 5",
    "Year 6",
    "Year 7",
    "Year 8",
    "Year 9",
    "Year 10 (Standard)",
    "Year 10 (Advanced)",
    "Year 11 (Standard)",
    "Year 11 (Advanced)",
    "Year 11 (Extension)",
    "Year 12 (Standard)",
    "Year 12 (Advanced)",
    "Year 12 (Extension 1)",
    "Year 12 (Extension 2)"
]

DIFFICULTY_OPTIONS = ["Easy", "Medium", "Hard", "Extremely Hard"]

# Custom Styling: Make Sidebar pure white so the logo blends 100% seamlessly
st.markdown("""
<style>
    [data-testid="stSidebar"] {
        background-color: #FFFFFF !important;
    }
    .main-title {
        font-size: 2.3rem;
        font-weight: 700;
        color: #1A237E;
        margin-bottom: 0.1rem;
    }
    .sub-title {
        font-size: 1.05rem;
        color: #546E7A;
        margin-bottom: 1.2rem;
    }
    .metric-card {
        background-color: #F8F9FA;
        border-radius: 8px;
        padding: 16px;
        border-left: 4px solid #1A237E;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        font-weight: 600;
        padding-top: 10px;
        padding-bottom: 10px;
    }
    .subtopic-box {
        background: #F8FAFC;
        padding: 12px 16px;
        border-radius: 8px;
        border: 1px solid #E2E8F0;
        margin-bottom: 10px;
    }
</style>
""", unsafe_allow_html=True)

# Master center environment key (strictly isolated to Admin bunsea)
env_api_key = os.environ.get("GEMINI_API_KEY", "").strip()
if not env_api_key and hasattr(st, "secrets"):
    try:
        env_api_key = str(st.secrets.get("GEMINI_API_KEY", "")).strip()
    except Exception:
        pass

# --- User Authentication Gate ---
if "authenticated_user" not in st.session_state or not st.session_state["authenticated_user"]:
    _, col_login, _ = st.columns([1, 2.2, 1])
    with col_login:
        logo_b64 = get_logo_base64()
        if logo_b64:
            st.markdown(f"""
            <div style="text-align: center; margin-top: 15px; margin-bottom: 18px;">
                <img src="data:image/png;base64,{logo_b64}" style="width: 140px; max-width: 100%; height: auto; display: block; margin: 0 auto 12px auto; filter: drop-shadow(0 4px 10px rgba(0,0,0,0.08));" />
                <h2 style="color: #1A237E; margin: 0 0 6px 0; font-size: 1.8rem; font-weight: 700; letter-spacing: -0.5px;">DA Tuition — Tutor Hub</h2>
                <p style="color: #546E7A; font-size: 0.95rem; margin: 0 0 16px 0;">Sign in to access your assigned classes, marking keys, and curriculum tools.</p>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("<h2 style='text-align: center; color: #1A237E; margin-bottom: 4px;'>DA Tuition — Tutor Hub</h2>", unsafe_allow_html=True)
            st.markdown("<p style='text-align: center; color: #546E7A; font-size: 0.95rem; margin-bottom: 20px;'>Sign in to access your assigned classes, marking keys, and curriculum tools.</p>", unsafe_allow_html=True)

        tab_signin, tab_register = st.tabs(["🔑 Sign In", "📝 New Tutor Registration"])

        with tab_signin:
            with st.form("login_form", clear_on_submit=False):
                username_input = st.text_input("Username", placeholder="e.g. bunsea or tutor_david")
                password_input = st.text_input("Password", type="password", placeholder="••••••••")
                submit_login = st.form_submit_button("Sign In to Tutor Hub", type="primary", use_container_width=True)

                if submit_login:
                    if not username_input or not password_input:
                        st.error("Please enter both your username and password.")
                    else:
                        user = database.authenticate_user(username_input, password_input)
                        if user:
                            st.session_state["authenticated_user"] = user
                            st.rerun()
                        else:
                            st.error("Invalid username or password. Please check your credentials.")

        with tab_register:
            st.caption("Create your tutor account. To protect center credits, each tutor supplies their own free Google Gemini API key.")
            st.link_button(
                "🔑 Get Free Gemini API Key (Google AI Studio)",
                "https://aistudio.google.com/app/apikey",
                use_container_width=True
            )
            st.info(
                "**Quick 3-step setup:**\n"
                "1. Click the button above to visit Google AI Studio in a new tab.\n"
                "2. Sign in with any Google account and click **Create API Key** (100% free with generous monthly quota).\n"
                "3. Copy and paste your key below to complete registration."
            )
            with st.form("register_tutor_form", clear_on_submit=False):
                reg_name = st.text_input("Full Name / Display Name", placeholder="e.g. Ms. Sarah Jenkins")
                reg_username = st.text_input("Desired Username (letters/numbers only)", placeholder="e.g. tutor_sarah").strip().lower()
                reg_pass1 = st.text_input("Create Password", type="password", placeholder="••••••••")
                reg_pass2 = st.text_input("Confirm Password", type="password", placeholder="••••••••")
                reg_api_key = st.text_input(
                    "Personal Google Gemini API Key",
                    type="password",
                    placeholder="AIzaSy...",
                    help="Required so your generations run on your personal quota without burning center credits."
                )
                st.caption("🔗 Get a free API key at [Google AI Studio](https://aistudio.google.com/app/apikey) in under 30 seconds.")
                submit_register = st.form_submit_button("Register & Enter Tutor Hub", type="primary", use_container_width=True)

                if submit_register:
                    if not reg_name or not reg_username or not reg_pass1 or not reg_pass2:
                        st.error("Please fill out all required name and password fields.")
                    elif not re.match(r"^[a-zA-Z0-9_.-]+$", reg_username):
                        st.error("Username can only contain letters, numbers, underscores, and hyphens.")
                    elif reg_pass1 != reg_pass2:
                        st.error("Passwords do not match. Please re-enter your password.")
                    elif len(reg_pass1) < 6:
                        st.error("Password must be at least 6 characters long.")
                    elif database.get_user_by_username(reg_username):
                        st.error(f"Username '{reg_username}' is already taken. Please choose another or sign in.")
                    else:
                        try:
                            uid = database.create_user(
                                username=reg_username,
                                password=reg_pass1,
                                display_name=reg_name,
                                role="tutor",
                                api_key=reg_api_key.strip()
                            )
                            new_user = database.get_user_by_id(uid)
                            st.session_state["authenticated_user"] = new_user
                            st.success(f"🎉 Welcome to DA Tuition, {reg_name}! Your tutor account is ready.")
                            st.rerun()
                        except Exception as err:
                            st.error(f"Registration error: {err}")

        # In production, default accounts are strictly hidden unless explicitly enabled in dev environment
        if os.environ.get("SHOW_DEV_CREDENTIALS", "").lower() in ("true", "1", "yes"):
            with st.expander("ℹ️ Development Credentials (Hidden in Production)", expanded=False):
                st.markdown("""
                - **Admin Account**: `bunsea` | Password: `password123` *(Full center oversight & tutor management)*
                - **Sample Tutor**: `tutor_david` | Password: `password123` *(Isolated to assigned classes)*
                """)
    st.stop()

# Authenticated Session User Context
current_user = st.session_state["authenticated_user"]
current_user_id = current_user["id"]
current_user_role = current_user.get("role", "tutor")
is_admin = current_user_role.lower() == "admin"

# Strict API Key Isolation:
# - Admin: Uses saved DB key or falls back to center master key in .env
# - Tutor: Strictly isolated to their personal saved DB key. NEVER falls back to .env!
if is_admin:
    admin_key = (current_user.get("api_key") or env_api_key or "").strip()
    st.session_state["gemini_api_key"] = admin_key
else:
    tutor_personal_key = (current_user.get("api_key") or "").strip()
    st.session_state["gemini_api_key"] = tutor_personal_key

# --- Sidebar Configuration ---
with st.sidebar:
    logo_b64_side = get_logo_base64()
    if logo_b64_side:
        st.markdown(f"""
        <div style="text-align: center; margin-bottom: 8px;">
            <img src="data:image/png;base64,{logo_b64_side}" style="width: 120px; max-width: 100%; height: auto; display: block; margin: 0 auto; filter: drop-shadow(0 2px 8px rgba(0,0,0,0.06));" />
        </div>
        """, unsafe_allow_html=True)
    elif os.path.exists(LOGO_FILE):
        st.image(LOGO_FILE, use_container_width=True)
    else:
        st.image("https://img.icons8.com/color/96/education.png", width=72)

    st.markdown("<h3 style='text-align: center; color: #1A237E; margin-top: -10px;'>DA TUITION</h3>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #78909C; font-size: 0.85rem;'>Automated Tutor Infrastructure</p>", unsafe_allow_html=True)
    st.markdown("---")

    # Logged In User Profile & Logout
    role_badge = "🛡️ Administrator" if is_admin else "👨‍🏫 Tutor"
    st.markdown(f"**Logged in as:** **{current_user['display_name']}**")
    st.caption(f"Role: `{role_badge}` | @{current_user['username']}")
    if st.button("🚪 Log Out", use_container_width=True, type="secondary"):
        st.session_state["authenticated_user"] = None
        st.session_state["gemini_api_key"] = ""
        st.rerun()

    st.markdown("---")

    # Personal Tutor API Key Management
    has_tutor_key = bool(st.session_state.get("gemini_api_key"))
    with st.expander("🔑 Personal Gemini API Key", expanded=(not has_tutor_key and not is_admin)):
        if is_admin:
            st.caption("Administrator mode: Operating on center master key (or override below).")
        else:
            st.caption("DA Tuition requires each tutor to supply their own free Google Gemini API key. All generations run on your personal quota to protect center credits.")
            st.link_button("🔑 Get Free Key (Google AI Studio)", "https://aistudio.google.com/app/apikey", use_container_width=True)

        tutor_key_val = st.text_input("Gemini API Key", value=current_user.get("api_key") or "", type="password", key="tutor_key_input_box")
        if st.button("Save API Key", use_container_width=True, key="btn_save_tutor_key"):
            if tutor_key_val.strip():
                database.update_user_api_key(current_user_id, tutor_key_val.strip())
                st.session_state["gemini_api_key"] = tutor_key_val.strip()
                current_user["api_key"] = tutor_key_val.strip()
                st.session_state["authenticated_user"] = current_user
                st.success("Personal API key saved!")
                st.rerun()
            else:
                database.update_user_api_key(current_user_id, "")
                current_user["api_key"] = ""
                st.session_state["authenticated_user"] = current_user
                if is_admin:
                    st.session_state["gemini_api_key"] = env_api_key
                    st.info("Reverted to center default API key.")
                else:
                    st.session_state["gemini_api_key"] = ""
                    st.warning("Personal API key removed. AI operations are disabled until a key is supplied.")
                st.rerun()

    # Password Change Management
    with st.expander("🔐 Change Password", expanded=False):
        old_pwd = st.text_input("Current Password", type="password", key="cp_old_pwd")
        new_pwd = st.text_input("New Password", type="password", key="cp_new_pwd")
        confirm_pwd = st.text_input("Confirm New Password", type="password", key="cp_confirm_pwd")
        if st.button("Update Password", use_container_width=True, key="btn_update_pwd"):
            if not old_pwd or not new_pwd:
                st.error("Please fill in current and new password.")
            elif new_pwd != confirm_pwd:
                st.error("New passwords do not match.")
            elif len(new_pwd) < 6:
                st.error("Password must be at least 6 characters.")
            else:
                authed = database.authenticate_user(current_user["username"], old_pwd)
                if not authed:
                    st.error("Current password is incorrect.")
                else:
                    database.update_user_password(current_user_id, new_pwd)
                    st.success("Password updated successfully!")

    # System Status Badges
    if st.session_state.get("gemini_api_key"):
        key_source = "Personal Key" if current_user.get("api_key") else "Center Master (Admin)"
        st.markdown(f"🟢 **AI Engine:** Connected (`{key_source}`)")
    else:
        st.warning("🔴 **AI Engine:** No Key Configured (Required for generation)")

    if cloud_sync.is_cloud_connected():
        st.markdown("☁️ **DA Cloud Sync:** Connected (Supabase)")
    else:
        st.markdown("📁 **Storage Mode:** Local SQLite (Offline)")

    st.markdown("---")
    st.markdown("#### **Platform Navigation**")
    st.markdown("""
    - **1. Materials & Cloud Library**: Theory Booklets, Exam Sheets & Supabase Cloud Repository.
    - **2. 1-Click AI Marking**: Grade student PDFs against class roll.
    - **3. Student Tracking**: Class heatmaps & diagnostic gaps.
    - **4. Remedial Packs**: Targeted revision sheets for weak areas.
    - **5. Classes & Rolls**: Manage teacher rosters & student lists.
    - **6. Lesson Cover Sheets**: FD Elite Lesson Progress & Director Parent Inquiries.
    """)

    if is_admin:
        with st.expander("⚙️ Admin & Cloud Settings", expanded=False):
            admin_key = st.text_input("Master Center Gemini API Key", value="", type="password", key="admin_master_gemini_key")
            if admin_key:
                st.session_state["gemini_api_key"] = admin_key
                os.environ["GEMINI_API_KEY"] = admin_key
                st.success("Center master API key updated!")

            st.markdown("---")
            st.markdown("##### ☁️ Supabase Cloud Configuration")
            cur_sb_url, cur_sb_key = cloud_sync.get_supabase_creds()
            new_sb_url = st.text_input("Supabase Project URL", value=cur_sb_url, placeholder="https://xyz.supabase.co", key="admin_sb_url_input")
            new_sb_key = st.text_input("Supabase Service / Anon Key", value=cur_sb_key, type="password", placeholder="eyJ...", key="admin_sb_key_input")
            if st.button("Save Cloud Credentials", key="btn_save_sb_creds", use_container_width=True):
                os.environ["SUPABASE_URL"] = new_sb_url.strip()
                os.environ["SUPABASE_SERVICE_ROLE_KEY"] = new_sb_key.strip()
                cloud_sync._cached_client = None
                try:
                    env_path = os.path.join(os.path.dirname(__file__), ".env")
                    with open(env_path, "a", encoding="utf-8") as f:
                        f.write(f"\nSUPABASE_URL={new_sb_url.strip()}\nSUPABASE_SERVICE_ROLE_KEY={new_sb_key.strip()}\n")
                except Exception:
                    pass
                st.success("Supabase credentials saved!")
                st.rerun()

# Main Header with Clear, Prominent Brand Logo
col_hdr_logo, col_hdr_text = st.columns([1, 5])
with col_hdr_logo:
    if os.path.exists(LOGO_FILE):
        st.image(LOGO_FILE, width=150)
with col_hdr_text:
    st.markdown('<div class="main-title">DA Tuition — Integrated Tutor Hub</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-title">Authentic Exam Worksheets • 1-Click AI Handwriting Marking • Student Diagnostics & Remediation</div>', unsafe_allow_html=True)

main_section = st.radio(
    "Go to feature",
    [
        "📖 1. Theory & Practice Materials",
        "🚀 2. 1-Click AI Marking",
        "📊 3. Student Tracking & Analytics",
        "🎯 4. Remedial Revision Packs",
        "👥 5. Classes & Student Rolls",
        "📋 6. Lesson Cover Sheets & Progress"
    ],
    horizontal=True,
    key="main_section_navigation",
    label_visibility="collapsed"
)

# ==========================================
# TAB 1: THEORY & PRACTICE MATERIALS
# ==========================================
if main_section == "📖 1. Theory & Practice Materials":
    sub_tab_theory, sub_tab_worksheet, sub_tab_review, sub_tab_package, sub_tab_cloud = st.tabs([
        "📖 1. Generate Theory Booklet (Teacher & Student)",
        "📝 2. Generate Practice Worksheet (Homework / In-Class)",
        "🔄 3. Generate Review Booklet (Revision & Exam Prep)",
        "📦 4. Complete Exam Revision & Practice Package",
        "☁️ 5. Cloud Exam Library"
    ])

    with sub_tab_theory:
        st.markdown("### 📖 Generate Theory Booklet (Teacher & Student Editions)")
        st.caption("Aligned with NSW Syllabus textbooks (CambridgeMATHS & Maths in Focus). Generates complete concept explanations, key formula callout boxes, tutor tips, TikZ geometry diagrams, teacher demonstration examples (with full step-by-step whiteboard solutions), and tiered student practice questions (Easy, Medium, Hard).")

        # Saved Theory Booklets Library
        saved_tbs = database.get_theory_booklets()
        if saved_tbs:
            with st.expander("📚 Saved Theory Booklets Library (Load Existing Booklet)", expanded=False):
                tb_lib_opts = {
                    f"#{b['id']} — {b['title']} ({b.get('year_level', '')} • {b.get('topic', '')})": b['id']
                    for b in saved_tbs
                }
                selected_lib_tb_label = st.selectbox("Select a Saved Theory Booklet:", list(tb_lib_opts.keys()), key="sel_lib_tb")
                sel_lib_tb_id = tb_lib_opts[selected_lib_tb_label]
                if st.session_state.get("pending_delete_tb_id") != sel_lib_tb_id:
                    st.session_state.pop("pending_delete_tb_id", None)
                tb_load_col, tb_del_col = st.columns(2)
                with tb_load_col:
                    if st.button("📂 Load Selected Theory Booklet", key=f"btn_load_lib_tb_{sel_lib_tb_id}", type="primary", use_container_width=True):
                        loaded_tb = database.get_theory_booklet_by_id(sel_lib_tb_id)
                        if loaded_tb:
                            content_dict = loaded_tb.get("content", {})
                            if isinstance(content_dict, dict):
                                full_tb = {**content_dict, **loaded_tb}
                            else:
                                full_tb = loaded_tb
                            full_tb["id"] = loaded_tb["id"]
                            st.session_state["latest_theory_booklet"] = full_tb
                            st.session_state["latest_theory_booklet_id"] = loaded_tb["id"]
                            st.session_state.pop("latest_tb_cache_key", None)
                            st.success(f"Loaded Theory Booklet #{loaded_tb['id']}: {loaded_tb.get('title')}!")
                            st.rerun()
                with tb_del_col:
                    if st.button("🗑️ Delete Selected Theory Booklet", key=f"btn_del_lib_tb_{sel_lib_tb_id}", use_container_width=True):
                        st.session_state["pending_delete_tb_id"] = sel_lib_tb_id
                        st.rerun()

                if st.session_state.get("pending_delete_tb_id") == sel_lib_tb_id:
                    st.warning(f"Delete Theory Booklet #{sel_lib_tb_id}: `{selected_lib_tb_label}`? This cannot be undone.")
                    del_children_cb = st.checkbox("Also delete linked companion worksheets (In-Class, Homework, Topic Exams)", key=f"del_tb_children_{sel_lib_tb_id}", value=True)
                    tb_c1, tb_c2 = st.columns(2)
                    with tb_c1:
                        if st.button("Confirm Delete Theory Booklet", key=f"confirm_del_tb_{sel_lib_tb_id}", type="primary", use_container_width=True):
                            database.delete_theory_booklet(sel_lib_tb_id, delete_linked_worksheets=del_children_cb)
                            if st.session_state.get("latest_theory_booklet_id") == sel_lib_tb_id:
                                for k in ("latest_theory_booklet", "latest_theory_booklet_id", "latest_tb_cache_key", "latest_tb_artifacts"):
                                    st.session_state.pop(k, None)
                            st.session_state.pop("pending_delete_tb_id", None)
                            st.success(f"Deleted Theory Booklet #{sel_lib_tb_id} successfully!")
                            st.rerun()
                    with tb_c2:
                        if st.button("Cancel", key=f"cancel_del_tb_{sel_lib_tb_id}", use_container_width=True):
                            st.session_state.pop("pending_delete_tb_id", None)
                            st.rerun()

        col_yl, col_tb = st.columns([1.2, 1.8])
        with col_yl:
            default_theory_yl_index = YEAR_LEVEL_OPTIONS.index("Year 11 (Extension)") if "Year 11 (Extension)" in YEAR_LEVEL_OPTIONS else 8
            theory_year_level = st.selectbox(
                "Year Level",
                YEAR_LEVEL_OPTIONS,
                index=default_theory_yl_index,
                key="theory_select_year_level"
            )

        with col_tb:
            available_theory_tbs = ai_engine.get_textbooks_for_year(theory_year_level)
            theory_textbook = st.selectbox(
                "📚 Choose Textbook Curriculum Series",
                available_theory_tbs,
                index=0,
                key=f"theory_tb_{theory_year_level}"
            )

        if ai_engine.is_year_11_advanced(theory_year_level):
            st.info("🔒 **Strict NSW Stage 6 Syllabus Boundary Enforced**: Pure Year 11 Mathematics Advanced & Stage 5.3 prerequisites only. Zero Year 12 calculus (no integration, product/quotient/chain rules), zero Extension 1 (no vectors, induction, combinatorics, polynomials division), and zero tertiary content.")

        col2, col3 = st.columns([2, 1.2])
        with col2:
            theory_available_topics = ai_engine.get_topics_for_year(theory_year_level, textbook=theory_textbook)

            theory_custom_topics_key = f"theory_custom_topics_{theory_textbook}_{theory_year_level}"
            if theory_custom_topics_key not in st.session_state:
                st.session_state[theory_custom_topics_key] = []
            theory_all_topic_options = (theory_available_topics or []) + [t for t in st.session_state[theory_custom_topics_key] if t not in (theory_available_topics or [])]

            col_th_top_sel, col_th_top_custom = st.columns([3.2, 1.2])
            with col_th_top_sel:
                theory_selected_topics = st.multiselect(
                    f"Topic(s) / Chapter(s) ({theory_textbook}) — choose 1 or more:",
                    theory_all_topic_options,
                    default=[],
                    key=f"theory_topics_multi_{theory_textbook}_{theory_year_level}",
                    help="Select one or more syllabus chapters to synthesize into a single comprehensive Theory Booklet."
                )
            with col_th_top_custom:
                st.write("")
                with st.popover("➕ Add Topic"):
                    new_th_top_val = st.text_input("New Topic Name", placeholder="e.g. Vectors", key=f"txt_new_th_topic_{theory_textbook}_{theory_year_level}")
                    if st.button("Add Topic", key=f"btn_add_th_top_{theory_textbook}_{theory_year_level}") and new_th_top_val.strip():
                        trimmed_top = new_th_top_val.strip()
                        if trimmed_top not in st.session_state[theory_custom_topics_key]:
                            st.session_state[theory_custom_topics_key].append(trimmed_top)
                            st.rerun()

            th_combined_default = ai_engine.format_combined_topics(theory_selected_topics) if theory_selected_topics else ""
            theory_topic_input = st.text_input(
                "Booklet Topic Title (appears on cover & headers):",
                value=th_combined_default,
                placeholder="Select topic(s) above or type custom topic title...",
                key=f"theory_title_input_{theory_textbook}_{theory_year_level}_{'_'.join([str(t)[:8] for t in theory_selected_topics]) if theory_selected_topics else 'none'}",
                help="Custom title displayed on the front cover and header of the generated booklets."
            )

        with col3:
            has_theory_term_week = st.checkbox("📅 Specify Term & Week (Optional)", value=False, key="theory_has_tw")
            if has_theory_term_week:
                col_t, col_w = st.columns(2)
                with col_t:
                    theory_term_num = st.number_input("Term", min_value=1, max_value=4, value=1, step=1, key="theory_term")
                with col_w:
                    theory_week_num = st.number_input("Week", min_value=1, max_value=12, value=1, step=1, key="theory_week")
            else:
                theory_term_num = None
                theory_week_num = None
                st.caption("ℹ️ General resource (no term/week)")

        # Number of examples & practice questions
        col_ex, col_pr, col_chk = st.columns(3)
        with col_ex:
            theory_ex_count = st.number_input(
                "Teacher Examples per Concept",
                min_value=1,
                max_value=5,
                value=2,
                step=1,
                key="theory_ex_count",
                help="Demonstration examples with step-by-step whiteboard solutions (+1 Exam-Style example is automatically added)."
            )
            st.caption("ℹ️ *+ 1 Exam-Style example automatically included per subtopic*")
        with col_pr:
            theory_pr_count = st.number_input(
                "Student Practice Questions per Concept",
                min_value=1,
                max_value=6,
                value=3,
                step=1,
                key="theory_pr_count",
                help="Tiered questions (Level 1, Level 2, Level 3...) with marks and solutions (+1 Exam-Style question is automatically added)."
            )
            st.caption("ℹ️ *+ 1 Exam-Style question automatically included per subtopic*")
        with col_chk:
            theory_checking_count = st.number_input(
                "Checking Understanding per Concept",
                min_value=0,
                max_value=6,
                value=2,
                step=1,
                key="theory_checking_count",
                help="Short questions placed immediately after the demonstrations. Students receive an empty working box to solve them independently."
            )
            st.caption("ℹ️ Student attempts with working space")

        # Concepts / Subtopics to include
        st.markdown("---")
        st.markdown("#### 📋 Select Concepts / Subtopics to Include in this Booklet")
        if not theory_selected_topics:
            st.info("👆 **Please select at least one topic/chapter above** to view and customize curriculum concepts.")
        else:
            st.caption(f"Concepts available from **{theory_textbook}** for **{theory_year_level} — {theory_topic_input}**:")

        theory_all_subtopics = []
        is_multi_theory = len(theory_selected_topics) > 1
        for top_item in theory_selected_topics:
            try:
                subs = ai_engine.get_curriculum_subtopics(theory_year_level, top_item, textbook=theory_textbook)
            except Exception:
                subs = []
            if not subs:
                subs = [f"{top_item} Foundations", f"{top_item} Problem Solving"]

            if is_multi_theory:
                top_tag = ai_engine.clean_topic_title(top_item)
                for s in subs:
                    tagged_s = f"[{top_tag}] {s}"
                    if tagged_s not in theory_all_subtopics:
                        theory_all_subtopics.append(tagged_s)
            else:
                for s in subs:
                    if s not in theory_all_subtopics:
                        theory_all_subtopics.append(s)

        theory_subtopics_cache_key = f"theory_subs_{theory_textbook}_{theory_year_level}_{hash(tuple(theory_selected_topics))}"
        if theory_subtopics_cache_key not in st.session_state:
            st.session_state[theory_subtopics_cache_key] = list(theory_all_subtopics)

        theory_active_subtopics = st.session_state[theory_subtopics_cache_key]

        col_th_act_a, col_th_act_b = st.columns([1, 1])
        with col_th_act_a:
            if st.button("🤖 AI Suggest More Subtopics", key=f"btn_ai_theory_subs_{theory_subtopics_cache_key}"):
                cur_key = st.session_state.get("gemini_api_key", "")
                with st.spinner(f"Fetching {theory_textbook} subtopics with AI..."):
                    ai_subs = ai_engine.suggest_subtopics_ai(theory_year_level, theory_topic_input, cur_key, textbook=theory_textbook)
                    for s in ai_subs:
                        if s not in theory_active_subtopics:
                            theory_active_subtopics.append(s)
                    st.session_state[theory_subtopics_cache_key] = theory_active_subtopics
                    st.rerun()

        with col_th_act_b:
            with st.popover("➕ Add Custom Concept / Subtopic"):
                new_sub_name = st.text_input("Concept Title", placeholder="e.g. Geometric Proofs Using Vectors", key=f"txt_theory_new_sub_{theory_subtopics_cache_key}")
                if st.button("Add to List", key=f"btn_add_theory_{theory_subtopics_cache_key}") and new_sub_name.strip():
                    if new_sub_name.strip() not in theory_active_subtopics:
                        theory_active_subtopics.append(new_sub_name.strip())
                        st.session_state[theory_subtopics_cache_key] = theory_active_subtopics
                        st.rerun()

        selected_theory_subtopics = st.multiselect(
            "Select Concepts / Subtopics to Include:",
            options=theory_active_subtopics,
            default=theory_active_subtopics,
            key=f"theory_sel_subs_{theory_subtopics_cache_key}"
        )

        st.markdown("##### 🎯 Practice Question Counts per Level")
        st.caption("Configure question counts for each difficulty level:")
        col_th_l1, col_th_l2, col_th_l3, col_th_l4, col_th_exam = st.columns(5)
        with col_th_l1:
            th_q_l1 = st.number_input("Level 1 - Commit to Memory", min_value=0, max_value=20, value=1, step=1, key="th_q_l1")
        with col_th_l2:
            th_q_l2 = st.number_input("Level 2 - Further Practice", min_value=0, max_value=20, value=1, step=1, key="th_q_l2")
        with col_th_l3:
            th_q_l3 = st.number_input("Level 3 - Application", min_value=0, max_value=20, value=1, step=1, key="th_q_l3")
        with col_th_l4:
            th_q_l4 = st.number_input("Level 4 - Thinking Creatively", min_value=0, max_value=20, value=0, step=1, key="th_q_l4")
        with col_th_exam:
            th_q_exam = st.number_input("Level 5 - Exam Questions", min_value=0, max_value=20, value=1, step=1, key="th_q_exam")

        theory_level_distribution = {
            "Level 1 - Commit to Memory": int(th_q_l1),
            "Level 2 - Further Practice": int(th_q_l2),
            "Level 3 - Application": int(th_q_l3),
            "Level 4 - Thinking Creatively": int(th_q_l4),
            "Level 5 - Exam Questions": int(th_q_exam),
        }
        th_total_practice_default = sum(theory_level_distribution.values())
        if th_total_practice_default == 0:
            th_total_practice_default = 1
            theory_level_distribution["Level 1 - Commit to Memory"] = 1

        theory_custom_distribution = {}
        with st.expander("⚙️ Customize Question Counts Per Subtopic (Optional)", expanded=False):
            st.caption("Override question counts for specific individual concepts:")
            for idx, sub in enumerate(selected_theory_subtopics):
                sub_safe_key = f"th_sub_dist_{hash(sub)}_{idx}"
                sub_override = st.checkbox(f"Custom counts for **{sub}**", value=False, key=f"chk_{sub_safe_key}")
                if sub_override:
                    sc1, sc2, sc3, sc4, sc5 = st.columns(5)
                    with sc1:
                        sq1 = st.number_input("L1 - Commit to Memory", min_value=0, max_value=20, value=int(th_q_l1), key=f"sq1_{sub_safe_key}")
                    with sc2:
                        sq2 = st.number_input("L2 - Further Practice", min_value=0, max_value=20, value=int(th_q_l2), key=f"sq2_{sub_safe_key}")
                    with sc3:
                        sq3 = st.number_input("L3 - Application", min_value=0, max_value=20, value=int(th_q_l3), key=f"sq3_{sub_safe_key}")
                    with sc4:
                        sq4 = st.number_input("L4 - Thinking Creatively", min_value=0, max_value=20, value=int(th_q_l4), key=f"sq4_{sub_safe_key}")
                    with sc5:
                        sqe = st.number_input("L5 - Exam Questions", min_value=0, max_value=20, value=int(th_q_exam), key=f"sqe_{sub_safe_key}")
                    theory_custom_distribution[sub] = {
                        "Level 1 - Commit to Memory": int(sq1),
                        "Level 2 - Further Practice": int(sq2),
                        "Level 3 - Application": int(sq3),
                        "Level 4 - Thinking Creatively": int(sq4),
                        "Level 5 - Exam Questions": int(sqe)
                    }
                else:
                    theory_custom_distribution[sub] = dict(theory_level_distribution)

        th_total_q_sum = sum(sum(t.values()) for t in theory_custom_distribution.values()) if theory_custom_distribution else (len(selected_theory_subtopics) * th_total_practice_default)
        st.info(f"📊 **Selected Concepts:** **{len(selected_theory_subtopics)} concepts** | Total: {len(selected_theory_subtopics) * int(theory_ex_count)} teacher examples & {th_total_q_sum} practice questions")

        theory_custom_notes = st.text_area(
            "Specific Curriculum Requirements / Teaching Focus (Optional)",
            placeholder="e.g. Focus on Cartesian and column vector notation, geometric proofs, and HSC-style questions.",
            key="theory_custom_notes"
        )

        theory_reference_uploads = st.file_uploader(
            "📚 Optional textbook chapter PDFs for exercise alignment",
            type=["pdf"],
            accept_multiple_files=True,
            key="theory_reference_uploads",
            help="Upload the selected textbook's chapter or exercise pages. The first questions from each exercise will guide the Teacher Demonstration Examples."
        )
        uploaded_reference_text = ai_engine.extract_uploaded_textbook_reference(theory_reference_uploads)
        if uploaded_reference_text:
            st.info(f"Textbook exercise reference loaded from {len(theory_reference_uploads)} uploaded PDF(s).")

        if st.button("🚀 Generate Theory Booklet (Teacher, Student & Class Editions)", type="primary", key="btn_generate_theory_booklet"):
            current_api_key = (st.session_state.get("gemini_api_key") or "").strip()
            if not current_api_key:
                st.error("⚠️ Gemini API Key Required: Please enter your personal Google Gemini API key in the left sidebar under '🔑 Personal Gemini API Key' (Get a free key in 30s at https://aistudio.google.com/app/apikey).")
            elif not theory_selected_topics:
                st.error("Please select at least one topic/chapter for the Theory Booklet.")
            elif not selected_theory_subtopics:
                st.error("Please select at least one concept/subtopic to include in the Theory Booklet.")
            else:
                with st.spinner(f"Generating comprehensive Theory Booklet for {theory_year_level} — {theory_topic_input} ({theory_textbook}) with theory expositions, teacher examples, whiteboard solutions, and tiered practice questions..."):
                    try:
                        booklet_data = ai_engine.generate_theory_booklet(
                            year_level=theory_year_level,
                            topic=theory_topic_input,
                            subtopics=selected_theory_subtopics,
                            examples_per_concept=int(theory_ex_count),
                            practice_per_concept=int(th_total_practice_default),
                            checking_per_concept=int(theory_checking_count),
                            term=int(theory_term_num) if theory_term_num is not None else None,
                            week=int(theory_week_num) if theory_week_num is not None else None,
                            custom_instructions=theory_custom_notes,
                            textbook=theory_textbook,
                            api_key=current_api_key,
                            question_distribution=theory_custom_distribution,
                            level_distribution=theory_level_distribution,
                            textbook_reference=uploaded_reference_text
                        )

                        booklet_data["textbook"] = theory_textbook
                        
                        # Save to database to acquire permanent booklet ID
                        booklet_id = database.save_theory_booklet(
                            title=booklet_data.get("title", f"{theory_topic_input} Theory Booklet"),
                            term=int(theory_term_num) if theory_term_num is not None else None,
                            week=int(theory_week_num) if theory_week_num is not None else None,
                            year_level=theory_year_level,
                            topic=theory_topic_input,
                            content=booklet_data
                        )
                        booklet_data["id"] = booklet_id
                        
                        # Automatically register tiered practice questions into assessable worksheets table
                        practice_ws_id = database.register_theory_practice_worksheet(booklet_id, booklet_data)
                        booklet_data["practice_worksheet_id"] = practice_ws_id
                        
                        st.session_state["latest_theory_booklet"] = booklet_data
                        st.session_state["latest_theory_booklet_id"] = booklet_id
                        tb_gen_cost = booklet_data.get('meta_cost', 0.0)
                        tb_gen_tokens = booklet_data.get('meta_tokens', 0)
                        reference_note = " Textbook exercise reference applied." if booklet_data.get("textbook_reference_used") else " No local textbook chapter reference was found; syllabus guidance was used."
                        st.success(f"🎉 Generated & Saved Theory Booklet #{booklet_id}: {booklet_data.get('title')}! (💰 Cost: ${tb_gen_cost:.4f} AUD • {tb_gen_tokens:,} tokens) — Practice Worksheet #{practice_ws_id} registered.{reference_note}")
                    except Exception as e:
                        st.error(f"Error generating theory booklet: {e}")

        # Preview & Download Latest Generated Theory Booklet
        if "latest_theory_booklet" in st.session_state:
            tb = st.session_state["latest_theory_booklet"]
            st.markdown("---")
            st.markdown(f"#### 📖 {tb.get('title', 'Theory Booklet')}")
            tw_label = f"Term {tb.get('term')} Week {tb.get('week')}" if (tb.get('term') and tb.get('week')) else "General Resource"
            st.caption(f"**Year Level:** {tb.get('year_level')} | **Topic:** {tb.get('topic')} | **{tw_label}** | **{len(tb.get('concepts', []))} Concepts**")

            tb_font_theme = "charter"

            tb_cache_key = f"v23_{tb.get('id', 0)}_{tb.get('title', '')}_{tb_font_theme}"
            if st.session_state.get("latest_tb_cache_key") != tb_cache_key or "latest_tb_artifacts" not in st.session_state:
                with st.spinner("Compiling Theory Booklet PDFs & Materials (one-time)..."):
                    _tb_t_pdf = pdf_generator.generate_theory_booklet_pdf(
                        booklet_data=tb, mode="teacher", term=tb.get("term"), week=tb.get("week"), font_theme=tb_font_theme
                    )
                    _tb_sc_pdf = pdf_generator.generate_theory_booklet_pdf(
                        booklet_data=tb, mode="student_class", term=tb.get("term"), week=tb.get("week"), font_theme=tb_font_theme
                    )
                    _tb_sp_pdf = pdf_generator.generate_theory_booklet_pdf(
                        booklet_data=tb, mode="student_private", term=tb.get("term"), week=tb.get("week"), font_theme=tb_font_theme
                    )
                    _tb_t_docx = pdf_generator.generate_theory_booklet_docx(
                        booklet_data=tb, mode="teacher", term=tb.get("term"), week=tb.get("week")
                    )
                    _tb_sc_docx = pdf_generator.generate_theory_booklet_docx(
                        booklet_data=tb, mode="student_class", term=tb.get("term"), week=tb.get("week")
                    )
                    _tb_sp_docx = pdf_generator.generate_theory_booklet_docx(
                        booklet_data=tb, mode="student_private", term=tb.get("term"), week=tb.get("week")
                    )
                    st.session_state["latest_tb_cache_key"] = tb_cache_key
                    st.session_state["latest_tb_artifacts"] = {
                        "t_pdf": _tb_t_pdf,
                        "sc_pdf": _tb_sc_pdf,
                        "sp_pdf": _tb_sp_pdf,
                        "t_docx": _tb_t_docx,
                        "sc_docx": _tb_sc_docx,
                        "sp_docx": _tb_sp_docx,
                    }

            _cached_tb = st.session_state["latest_tb_artifacts"]
            teacher_pdf_bytes = _cached_tb["t_pdf"]
            student_class_pdf_bytes = _cached_tb["sc_pdf"]
            student_private_pdf_bytes = _cached_tb["sp_pdf"]
            teacher_docx_bytes = _cached_tb["t_docx"]
            student_class_docx_bytes = _cached_tb["sc_docx"]
            student_private_docx_bytes = _cached_tb["sp_docx"]

            p_col1, p_col2, p_col3 = st.columns(3)
            with p_col1:
                teacher_dl_name = get_theory_booklet_download_filename(tb, mode="teacher")
                st.download_button(
                    "📥 Theory Teacher (PDF)",
                    data=teacher_pdf_bytes,
                    file_name=teacher_dl_name,
                    mime="application/pdf",
                    key="dl_latest_teacher_booklet",
                    use_container_width=True
                )
                if teacher_docx_bytes:
                    teacher_docx_name = teacher_dl_name.rsplit(".", 1)[0] + ".docx"
                    st.download_button(
                        "📄 Theory Teacher (.docx)",
                        data=teacher_docx_bytes,
                        file_name=teacher_docx_name,
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        key="dl_latest_teacher_booklet_docx",
                        use_container_width=True
                    )
                st.caption("✅ Includes complete theory, formula boxes, model examples with full whiteboard solutions, and practice questions with worked solutions & marking criteria.")

            with p_col2:
                class_dl_name = get_theory_booklet_download_filename(tb, mode="student_class")
                st.download_button(
                    "📥 Theory Student Class (PDF)",
                    data=student_class_pdf_bytes,
                    file_name=class_dl_name,
                    mime="application/pdf",
                    key="dl_latest_student_class_booklet",
                    use_container_width=True
                )
                if student_class_docx_bytes:
                    class_docx_name = class_dl_name.rsplit(".", 1)[0] + ".docx"
                    st.download_button(
                        "📄 Theory Student Class (.docx)",
                        data=student_class_docx_bytes,
                        file_name=class_docx_name,
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        key="dl_latest_student_class_booklet_docx",
                        use_container_width=True
                    )
                st.caption("🏫 **In-Class Edition**: Teacher Demonstration Examples, Checking Understanding, and practice questions. Students use their own exercise books for working.")

            with p_col3:
                private_dl_name = get_theory_booklet_download_filename(tb, mode="student_private")
                st.download_button(
                    "📥 Theory Student Private (PDF)",
                    data=student_private_pdf_bytes,
                    file_name=private_dl_name,
                    mime="application/pdf",
                    key="dl_latest_student_private_booklet",
                    use_container_width=True
                )
                if student_private_docx_bytes:
                    private_docx_name = private_dl_name.rsplit(".", 1)[0] + ".docx"
                    st.download_button(
                        "📄 Theory Student Private (.docx)",
                        data=student_private_docx_bytes,
                        file_name=private_docx_name,
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        key="dl_latest_student_private_booklet_docx",
                        use_container_width=True
                    )
                st.caption("📖 **Private Tutoring Edition**: Complete theory and worked demonstrations, with space for Checking Understanding and quick answers at the back.")

            if tb.get("meta_cost") is not None or tb.get("meta_tokens"):
                st.info(f"💰 **Generation Cost:** **${tb.get('meta_cost', 0.0):.4f} AUD** • **{tb.get('meta_tokens', 0):,} tokens** ({tb.get('model_used', 'Gemini 3.8 Flash')})")

            if cloud_sync.is_cloud_connected():
                if st.button("☁️ Save Theory Booklet to DA Cloud Library", key=f"btn_cloud_save_tb_{tb.get('id', 0)}", use_container_width=True):
                    with st.spinner("Saving to DA Cloud Library (Supabase)..."):
                        ok, msg = cloud_sync.save_exam_to_cloud(
                            subject=f"{tb.get('year_level', '')} Maths",
                            year_level=tb.get('year_level', ''),
                            topic=f"{tb.get('topic', '')} Theory",
                            teacher_name=current_user.get("display_name", "DA Tutor"),
                            pdf_bytes=teacher_pdf_bytes,
                            docx_bytes=teacher_docx_bytes,
                            difficulty="Theory",
                            num_questions=len(tb.get("concepts", [])),
                            extra_instructions=tb.get("custom_instructions") or theory_custom_notes or "",
                            cost=tb.get("meta_cost", 0.0),
                            model=tb.get("model_used", "gemini-3.8-flash")
                        )
                        if ok:
                            st.success(msg)
                        else:
                            st.error(msg)

            # Ensure practice questions are registered in worksheets database
            tb_id_val = tb.get("id")
            if tb_id_val:
                practice_ws_id = tb.get("practice_worksheet_id")
                if not practice_ws_id:
                    practice_ws_id = database.register_theory_practice_worksheet(tb_id_val, tb)
                    tb["practice_worksheet_id"] = practice_ws_id
                    st.session_state["latest_practice_ws_id"] = practice_ws_id

            st.markdown("---")
            st.markdown("#### ⚡ 1-Click Marking & Cohort Analytics Actions")
            st.caption("Directly grade student responses to this Theory Booklet's tiered practice questions or audit class cohort concept mastery.")

            col_act_mark, col_act_mat = st.columns(2)
            with col_act_mark:
                if st.button("🚀 Mark Practice Questions in Tab 2", key=f"btn_nav_mark_tb_{tb.get('id', 0)}", type="primary", use_container_width=True):
                    target_ws_id = tb.get("practice_worksheet_id")
                    if not target_ws_id and tb.get("id"):
                        target_ws_id = database.register_theory_practice_worksheet(tb["id"], tb)
                    st.session_state["preselected_marking_ws_id"] = target_ws_id
                    st.session_state["active_tab_hint"] = "marking"
                    st.info(f"✅ Pre-selected Assignment #{target_ws_id}! Please click **Tab 2 (1-Click AI Marking)** above to grade student scans.")

            with col_act_mat:
                if st.button("📊 View Topic Analysis & Coverage in Tab 3", key=f"btn_nav_matrix_tb_{tb.get('id', 0)}", use_container_width=True):
                    target_ws_id = tb.get("practice_worksheet_id")
                    if not target_ws_id and tb.get("id"):
                        target_ws_id = database.register_theory_practice_worksheet(tb["id"], tb)
                    st.session_state["preselected_matrix_ws_id"] = target_ws_id
                    st.session_state["active_tab_hint"] = "analytics"
                    st.info(f"✅ Pre-selected Assessment #{target_ws_id}! Please click **Tab 3 (Student Tracking & Analytics)** above to view concept mastery & reteach blueprints.")

            st.markdown("---")
            st.markdown("#### 🎓 100% Aligned Companion Practice & Assessment Suite")
            st.caption("Generate coordinated practice and assessment materials linked directly to this Theory Booklet's concepts with custom question counts for each concept.")

            tb_id = tb.get("id")
            tb_concepts_list = tb.get("concepts", [])
            if not tb_concepts_list and isinstance(tb.get("content"), dict):
                tb_concepts_list = tb["content"].get("concepts", [])

            suite_tab_ic, suite_tab_hw, suite_tab_review, suite_tab_exam, suite_tab_prep = st.tabs([
                "📝 In-Class Exercise Booklet",
                "🏠 Homework Exercise Booklet",
                "🔁 Topic Review Booklet",
                "🎯 Topic Test Booklet",
                "📦 Exam Preparation Booklet"
            ])

            # === 1. IN-CLASS EXERCISE BOOKLET TAB ===
            with suite_tab_ic:
                st.info("💡 **Classroom Whiteboard & Guided Practice**: Stepped, scaffolded exercises directly matched to the teacher examples in this Theory Booklet. Question 1 per concept provides direct guidance; subsequent questions provide gradual release of responsibility.")

                linked_in_class = database.get_theory_linked_worksheets(tb_id, assessment_type="in_class") if tb_id else []
                if linked_in_class:
                    st.success(f"📋 **{len(linked_in_class)} In-Class Booklet(s)** linked to this Theory Booklet.")
                    for lic in linked_in_class:
                        with st.expander(
                            f"📝 In-Class Booklet #{lic['id']}: {lic['title']} ({lic['total_questions']} Questions)",
                            expanded=(lic["id"] == st.session_state.get("latest_generated_ic_id")),
                        ):
                            lic_qs = lic.get("questions", [])
                            lic_title = lic["title"]
                            lic_year = lic["year_level"]
                            lic_topic = lic["topic"]
                            lic_term = lic.get("term")
                            lic_week = lic.get("week")
                            lic_q_json = json.dumps(lic_qs)
                            lic_mk_json = json.dumps(lic.get("marking_key") or {})

                            stu_pdf = get_cached_worksheet_pdf(lic['id'], lic_title, lic_year, lic_topic, lic_q_json, lic_mk_json, lic_term, lic_week, "in_class", "student")
                            tea_pdf = get_cached_worksheet_pdf(lic['id'], lic_title, lic_year, lic_topic, lic_q_json, lic_mk_json, lic_term, lic_week, "in_class", "teacher")
                            sans_pdf = get_cached_worksheet_pdf(lic['id'], lic_title, lic_year, lic_topic, lic_q_json, lic_mk_json, lic_term, lic_week, "in_class", "answers")
                            tans_pdf = get_cached_worksheet_pdf(lic['id'], lic_title, lic_year, lic_topic, lic_q_json, lic_mk_json, lic_term, lic_week, "in_class", "teacher_answers")

                            name_stu = get_worksheet_download_filename(lic, sheet_type="in_class", mode="student", theory_booklet=tb)
                            name_tea = get_worksheet_download_filename(lic, sheet_type="in_class", mode="teacher", theory_booklet=tb)
                            name_sans = get_worksheet_download_filename(lic, sheet_type="in_class", mode="answers", theory_booklet=tb)
                            name_tans = get_worksheet_download_filename(lic, sheet_type="in_class", mode="teacher_answers", theory_booklet=tb)

                            col_ic1, col_ic2, col_ic3, col_ic4 = st.columns(4)
                            with col_ic1:
                                st.download_button("📥 Student Worksheet", data=stu_pdf, file_name=name_stu, mime="application/pdf", key=f"dl_c_stu_ic_{lic['id']}", use_container_width=True)
                            with col_ic2:
                                st.download_button("📥 Teacher Solutions", data=tea_pdf, file_name=name_tea, mime="application/pdf", key=f"dl_c_tea_ic_{lic['id']}", use_container_width=True)
                            with col_ic3:
                                st.download_button("📥 Student Answer Sheet", data=sans_pdf, file_name=name_sans, mime="application/pdf", key=f"dl_c_ans_ic_{lic['id']}", use_container_width=True)
                            with col_ic4:
                                st.download_button("🔑 Teacher Answer Key", data=tans_pdf, file_name=name_tans, mime="application/pdf", key=f"dl_c_tea_ans_ic_{lic['id']}", use_container_width=True)

                            compiled_ic_key = f"compiled_theory_ic_{tb_id}_{lic['id']}"
                            if st.button("📚 Compile Theory + In-Class Booklets", key=f"btn_compile_ic_{lic['id']}", use_container_width=True):
                                st.session_state.pop(compiled_ic_key, None)
                                with st.spinner("Joining matching teacher and student booklets..."):
                                    try:
                                        theory_pdfs = {"teacher": teacher_pdf_bytes, "student_class": student_class_pdf_bytes, "student_private": student_private_pdf_bytes}
                                        in_class_pdfs = {"teacher": tea_pdf, "student": stu_pdf}
                                        st.session_state[compiled_ic_key] = {
                                            edition: pdf_generator.combine_companion_booklets(theory_pdfs, in_class_pdfs, edition)
                                            for edition in ("student_class", "student_private", "teacher")
                                        }
                                    except Exception as exc:
                                        st.error(f"Could not compile these booklets: {exc}")
                            if compiled_ic_key in st.session_state:
                                st.caption("Combined in order: Theory → In-Class Practice")
                                bundle_cols = st.columns(3)
                                for bundle_col, edition, label in zip(
                                    bundle_cols,
                                    ("student_class", "student_private", "teacher"),
                                    ("Student Class", "Student Private", "Teacher Solutions")
                                ):
                                    with bundle_col:
                                        st.download_button(
                                            f"📥 Combined {label}",
                                            data=st.session_state[compiled_ic_key][edition],
                                            file_name=get_combined_booklet_filename(tb, edition),
                                            mime="application/pdf",
                                            key=f"dl_compiled_ic_{lic['id']}_{edition}",
                                            use_container_width=True,
                                        )

                            # 1-Click ZIP bundle & 1-Click Marking Navigation & Delete
                            col_ic_z, col_ic_m, col_ic_d = st.columns([1.4, 1.0, 0.8])
                            with col_ic_z:
                                ic_zip_bytes = build_worksheet_zip_package(lic['id'], json.dumps(lic), json.dumps(tb) if tb else None)
                                clean_ic_topic = re.sub(r'^(?:Chapter|Unit|Topic\s*)?(?:\d+[\.\:\-]\s*|\d+[A-Za-z][\.\:\-]\s*|\d+\s+)', '', str(lic_topic)).strip()
                                zip_ic_filename = f"{clean_ic_topic} In-Class Complete Package.zip".replace("_", " ")
                                st.download_button("📦 Download All as ZIP (Complete In-Class Package)", data=ic_zip_bytes, file_name=zip_ic_filename, mime="application/zip", key=f"dl_zip_ic_{lic['id']}", use_container_width=True)
                            with col_ic_m:
                                if st.button(f"⚡ Mark Submissions", key=f"btn_mark_sub_ic_{lic['id']}", use_container_width=True):
                                    st.session_state["preselected_marking_ws_id"] = lic['id']
                                    st.session_state["active_tab_hint"] = "marking"
                                    st.info(f"✅ Selected In-Class Booklet #{lic['id']}! Head to **Tab 2 (1-Click AI Homework Marking)** to grade student scans.")
                            with col_ic_d:
                                if st.button(f"🗑️ Delete", key=f"btn_del_ic_{lic['id']}", use_container_width=True):
                                    database.delete_worksheet(lic['id'], force=True)
                                    if st.session_state.get("preselected_marking_ws_id") == lic['id']:
                                        st.session_state.pop("preselected_marking_ws_id", None)
                                    st.success(f"Deleted In-Class Booklet #{lic['id']}!")
                                    st.rerun()

                st.markdown("##### 📝 Select Total In-Class Practice Questions")
                num_ic_concepts = len(tb_concepts_list) if tb_concepts_list else 3
                default_total_ic = max(2, num_ic_concepts * 2)

                col_ic_tot, col_ic_mode = st.columns([1, 1])
                with col_ic_tot:
                    total_ic_target = st.number_input(
                        "Total Questions in In-Class Booklet",
                        min_value=1,
                        max_value=40,
                        value=default_total_ic,
                        step=1,
                        key=f"total_ic_q_{tb_id}",
                        help="Select total number of practice questions to generate across the concepts."
                    )
                with col_ic_mode:
                    allocation_mode_ic = st.radio(
                        "Distribution Mode",
                        ["Evenly Distribute", "Custom per Concept"],
                        index=0,
                        key=f"ic_alloc_mode_{tb_id}",
                        horizontal=True
                    )

                ic_counts = {}
                if tb_concepts_list:
                    if allocation_mode_ic == "Evenly Distribute":
                        base_count = total_ic_target // num_ic_concepts
                        remainder = total_ic_target % num_ic_concepts
                        
                        alloc_summary = []
                        for c_idx, c in enumerate(tb_concepts_list):
                            c_name = c.get("concept_name") or c.get("name") or f"Concept {c_idx+1}"
                            cnt = base_count + (1 if c_idx < remainder else 0)
                            ic_counts[c_name] = cnt
                            alloc_summary.append(f"**{c_name[:25]}**: `{cnt} Qs`")
                        
                        st.caption("Distribution across concepts: " + " • ".join(alloc_summary))
                    else:
                        st.caption("Customize the exact question count for each concept:")
                        ic_cols = st.columns(2)
                        for c_idx, c in enumerate(tb_concepts_list, 1):
                            c_name = c.get("concept_name") or c.get("name") or f"Concept {c_idx}"
                            col_target = ic_cols[(c_idx - 1) % 2]
                            with col_target:
                                q_cnt = st.number_input(
                                    f"Concept {c_idx}: {c_name[:30]}{'...' if len(c_name)>30 else ''}",
                                    min_value=0, max_value=15, value=2, step=1,
                                    key=f"ic_q_cnt_{tb_id}_{c_idx}",
                                    help=f"Full concept name: {c_name}"
                                )
                                ic_counts[c_name] = q_cnt
                else:
                    st.info("No explicit concepts found in booklet content; generating questions across standard curriculum subtopics.")

                total_ic_questions = sum(ic_counts.values()) if ic_counts else total_ic_target
                st.write(f"📊 **Total In-Class Questions Selected**: `{total_ic_questions}`")

                btn_ic_label = f"🚀 Generate Aligned In-Class Exercise Booklet ({total_ic_questions} Questions)"
                if st.button(btn_ic_label, key=f"btn_gen_ic_{tb_id}", type="primary", use_container_width=True):
                    current_api_key = (st.session_state.get("gemini_api_key") or "").strip()
                    if not current_api_key:
                        st.error("🔑 Personal Gemini API Key required. Please configure your key in the sidebar.")
                    elif total_ic_questions <= 0:
                        st.warning("Please select at least 1 question across your concepts.")
                    else:
                        with st.spinner("Generating Aligned In-Class Practice Booklet via Gemini..."):
                            try:
                                ic_data = ai_engine.generate_aligned_companion_worksheet(
                                    theory_booklet=tb,
                                    sheet_type="In-Class",
                                    concept_counts=ic_counts,
                                    year_level=tb.get("year_level"),
                                    topic=tb.get("topic"),
                                    textbook=tb.get("textbook", "CambridgeMATHS NSW"),
                                    term=tb.get("term"),
                                    week=tb.get("week"),
                                    api_key=current_api_key
                                )
                                new_ic_id = database.save_worksheet(
                                    title=ic_data["title"],
                                    term=ic_data.get("term"),
                                    week=ic_data.get("week"),
                                    year_level=ic_data["year_level"],
                                    topic=ic_data["topic"],
                                    difficulty="Graduated (Stepped Practice)",
                                    questions=ic_data["questions"],
                                    marking_key=ic_data["marking_key"],
                                    set_number=1,
                                    custom_instructions="In-Class Guided Whiteboard Practice (100% Theory-Aligned)",
                                    cost=ic_data.get("meta_cost", 0.0),
                                    model=ic_data.get("model_used"),
                                    tokens=ic_data.get("meta_tokens"),
                                    source_theory_id=tb_id,
                                    assessment_type="in_class"
                                )
                                st.session_state["latest_worksheet"] = {**ic_data, "id": new_ic_id}
                                st.session_state["latest_generated_ic_id"] = new_ic_id
                                ic_cost = ic_data.get('meta_cost', 0.0)
                                ic_tokens = ic_data.get('meta_tokens', 0)
                                st.success(f"🎉 Successfully generated In-Class Practice Booklet #{new_ic_id}! (💰 Cost: ${ic_cost:.4f} AUD • {ic_tokens:,} tokens)")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Failed to generate In-Class booklet: {e}")

            # === 2. HOMEWORK EXERCISE BOOKLET TAB ===
            with suite_tab_hw:
                st.info("💡 **Numerical Twin Variations & Independent Mastery**: Generates isomorphic variations of the theory booklet examples with fresh numbers and coefficients. Students can consult their Theory Booklet notes at home to easily self-guide through each problem.")

                linked_hw = database.get_theory_linked_worksheets(tb_id, assessment_type="homework") if tb_id else []
                if linked_hw:
                    st.success(f"📋 **{len(linked_hw)} Homework Booklet(s)** linked to this Theory Booklet.")
                    for lhw in linked_hw:
                        set_label = f"Set {lhw.get('set_number', 1)}"
                        hw_cost_str = f" • 💰 ${lhw.get('cost', 0.0):.4f} AUD" if lhw.get('cost') else ""
                        with st.expander(
                            f"🏠 Homework Booklet #{lhw['id']} ({set_label}): {lhw['title']} ({lhw['total_questions']} Questions{hw_cost_str})",
                            expanded=(lhw["id"] == st.session_state.get("latest_generated_hw_id")),
                        ):
                            lhw_qs = lhw.get("questions", [])
                            lhw_title = lhw["title"]
                            lhw_year = lhw["year_level"]
                            lhw_topic = lhw["topic"]
                            lhw_term = lhw.get("term")
                            lhw_week = lhw.get("week")
                            lhw_set_num = lhw.get("set_number", 1)
                            lhw_q_json = json.dumps(lhw_qs)
                            lhw_mk_json = json.dumps(lhw.get("marking_key") or {})

                            hw_stu_pdf = get_cached_worksheet_pdf(lhw['id'], lhw_title, lhw_year, lhw_topic, lhw_q_json, lhw_mk_json, lhw_term, lhw_week, "homework", "student", lhw_set_num)
                            hw_tea_pdf = get_cached_worksheet_pdf(lhw['id'], lhw_title, lhw_year, lhw_topic, lhw_q_json, lhw_mk_json, lhw_term, lhw_week, "homework", "teacher", lhw_set_num)
                            hw_sans_pdf = get_cached_worksheet_pdf(lhw['id'], lhw_title, lhw_year, lhw_topic, lhw_q_json, lhw_mk_json, lhw_term, lhw_week, "homework", "answers", lhw_set_num)
                            hw_tans_pdf = get_cached_worksheet_pdf(lhw['id'], lhw_title, lhw_year, lhw_topic, lhw_q_json, lhw_mk_json, lhw_term, lhw_week, "homework", "teacher_answers", lhw_set_num)

                            hw_stu_name = get_worksheet_download_filename(lhw, sheet_type="homework", mode="student", theory_booklet=tb)
                            hw_tea_name = get_worksheet_download_filename(lhw, sheet_type="homework", mode="teacher", theory_booklet=tb)
                            hw_sans_name = get_worksheet_download_filename(lhw, sheet_type="homework", mode="answers", theory_booklet=tb)
                            hw_tea_ans_name = get_worksheet_download_filename(lhw, sheet_type="homework", mode="teacher_answers", theory_booklet=tb)

                            col_hw1, col_hw2, col_hw3, col_hw4 = st.columns(4)
                            with col_hw1:
                                st.download_button("📥 Student Worksheet", data=hw_stu_pdf, file_name=hw_stu_name, mime="application/pdf", key=f"dl_c_stu_hw_{lhw['id']}", use_container_width=True)
                            with col_hw2:
                                st.download_button("📥 Teacher Solutions", data=hw_tea_pdf, file_name=hw_tea_name, mime="application/pdf", key=f"dl_c_tea_hw_{lhw['id']}", use_container_width=True)
                            with col_hw3:
                                st.download_button("📥 Student Answer Sheet", data=hw_sans_pdf, file_name=hw_sans_name, mime="application/pdf", key=f"dl_c_ans_hw_{lhw['id']}", use_container_width=True)
                            with col_hw4:
                                st.download_button("🔑 Teacher Answer Key", data=hw_tans_pdf, file_name=hw_tea_ans_name, mime="application/pdf", key=f"dl_c_tea_ans_hw_{lhw['id']}", use_container_width=True)

                            if linked_in_class:
                                in_class_options = {item["id"]: item for item in linked_in_class}
                                selected_ic_id = st.selectbox(
                                    "In-Class booklet to include with this homework set",
                                    options=list(in_class_options),
                                    format_func=lambda item_id: f"#{item_id} — {in_class_options[item_id]['title']}",
                                    key=f"compile_ic_choice_hw_{lhw['id']}",
                                )
                                compiled_all_key = f"compiled_theory_ic_hw_{tb_id}_{selected_ic_id}_{lhw['id']}"
                                if st.button("📚 Compile Theory + In-Class + Homework Booklets", key=f"btn_compile_all_{lhw['id']}", use_container_width=True):
                                    st.session_state.pop(compiled_all_key, None)
                                    with st.spinner("Joining matching teacher and student booklets..."):
                                        try:
                                            chosen_ic = in_class_options[selected_ic_id]
                                            chosen_q_json = json.dumps(chosen_ic.get("questions", []))
                                            chosen_key_json = json.dumps(chosen_ic.get("marking_key") or {})
                                            chosen_pdf_args = (
                                                chosen_ic["id"], chosen_ic["title"], chosen_ic["year_level"], chosen_ic["topic"],
                                                chosen_q_json, chosen_key_json, chosen_ic.get("term"), chosen_ic.get("week"),
                                                "in_class",
                                            )
                                            in_class_pdfs = {
                                                "student": get_cached_worksheet_pdf(*chosen_pdf_args, "student"),
                                                "teacher": get_cached_worksheet_pdf(*chosen_pdf_args, "teacher"),
                                            }
                                            theory_pdfs = {"teacher": teacher_pdf_bytes, "student_class": student_class_pdf_bytes, "student_private": student_private_pdf_bytes}
                                            homework_pdfs = {"student": hw_stu_pdf, "teacher": hw_tea_pdf}
                                            st.session_state[compiled_all_key] = {
                                                edition: pdf_generator.combine_companion_booklets(
                                                    theory_pdfs, in_class_pdfs, edition, homework_pdfs,
                                                    homework_label=f"Homework Set {lhw_set_num}",
                                                )
                                                for edition in ("student_class", "student_private", "teacher")
                                            }
                                        except Exception as exc:
                                            st.error(f"Could not compile these booklets: {exc}")
                                if compiled_all_key in st.session_state:
                                    st.caption(f"Combined in order: Theory → In-Class Practice → Homework Set {lhw_set_num}")
                                    bundle_cols = st.columns(3)
                                    for bundle_col, edition, label in zip(
                                        bundle_cols,
                                        ("student_class", "student_private", "teacher"),
                                        ("Student Class", "Student Private", "Teacher Solutions")
                                    ):
                                        with bundle_col:
                                            st.download_button(
                                                f"📥 Combined {label}",
                                                data=st.session_state[compiled_all_key][edition],
                                                file_name=get_combined_booklet_filename(tb, edition, homework_set=lhw_set_num),
                                                mime="application/pdf",
                                                key=f"dl_compiled_all_{selected_ic_id}_{lhw['id']}_{edition}",
                                                use_container_width=True,
                                            )
                            else:
                                st.caption("Generate an In-Class booklet linked to this theory booklet to compile all three.")

                            # 1-Click ZIP bundle & 1-Click Marking Navigation & Delete
                            col_hw_z, col_hw_m, col_hw_d = st.columns([1.4, 1.0, 0.8])
                            with col_hw_z:
                                hw_zip_bytes = build_worksheet_zip_package(lhw['id'], json.dumps(lhw), json.dumps(tb) if tb else None)
                                clean_hw_topic = re.sub(r'^(?:Chapter|Unit|Topic\s*)?(?:\d+[\.\:\-]\s*|\d+[A-Za-z][\.\:\-]\s*|\d+\s+)', '', str(lhw_topic)).strip()
                                zip_hw_filename = f"{clean_hw_topic} Homework {set_label} Complete Package.zip".replace("_", " ")
                                st.download_button(f"📦 Download All as ZIP (Complete Homework {set_label} Package)", data=hw_zip_bytes, file_name=zip_hw_filename, mime="application/zip", key=f"dl_zip_hw_{lhw['id']}", use_container_width=True)
                            with col_hw_m:
                                if st.button(f"⚡ Mark Submissions", key=f"btn_mark_sub_hw_{lhw['id']}", use_container_width=True):
                                    st.session_state["preselected_marking_ws_id"] = lhw['id']
                                    st.session_state["active_tab_hint"] = "marking"
                                    st.info(f"✅ Selected Homework #{lhw['id']} ({set_label})! Head to **Tab 2 (1-Click AI Homework Marking)** to grade student scans.")
                            with col_hw_d:
                                if st.button(f"🗑️ Delete", key=f"btn_del_hw_{lhw['id']}", use_container_width=True):
                                    database.delete_worksheet(lhw['id'], force=True)
                                    if st.session_state.get("preselected_marking_ws_id") == lhw['id']:
                                        st.session_state.pop("preselected_marking_ws_id", None)
                                    st.success(f"Deleted Homework Booklet #{lhw['id']}!")
                                    st.rerun()

                col_hw_opt1, col_hw_opt2 = st.columns([1, 2])
                with col_hw_opt1:
                    hw_set_sel = st.selectbox("Homework Set", [1, 2], index=0, key=f"hw_set_sel_{tb_id}", format_func=lambda s: f"Set {s}")
                with col_hw_opt2:
                    st.caption("Each set produces distinct numerical twin problems, allowing re-tests or separated weekly homework sets.")

                st.markdown("##### 📝 Select Homework Questions")
                num_concepts = len(tb_concepts_list) if tb_concepts_list else 3
                default_total_hw = max(3, num_concepts * 3)

                allocation_mode = st.radio(
                    "Distribution Mode",
                    (["Evenly Distribute", "Custom per Concept", "Custom by Difficulty"]
                     if tb_concepts_list else ["Evenly Distribute"]),
                    index=0,
                    key=f"hw_alloc_mode_{tb_id}",
                    horizontal=True
                )
                if allocation_mode == "Evenly Distribute":
                    total_hw_target = st.number_input(
                        "Total Questions in Homework Booklet",
                        min_value=1,
                        max_value=40,
                        value=min(default_total_hw, 40),
                        step=1,
                        key=f"total_hw_q_{tb_id}",
                        help="Select the total number of homework questions across all concepts."
                    )
                else:
                    total_hw_target = 0
                    st.caption("The total is calculated from your concept selections below.")

                hw_counts = {}
                hw_difficulty_counts = None
                if tb_concepts_list:
                    if allocation_mode == "Evenly Distribute":
                        base_count = total_hw_target // num_concepts
                        remainder = total_hw_target % num_concepts
                        
                        alloc_summary = []
                        for c_idx, c in enumerate(tb_concepts_list):
                            c_name = c.get("concept_name") or c.get("name") or f"Concept {c_idx+1}"
                            cnt = base_count + (1 if c_idx < remainder else 0)
                            hw_counts[c_name] = cnt
                            alloc_summary.append(f"**{c_name[:25]}**: `{cnt} Qs`")
                        
                        st.caption("Distribution across concepts: " + " • ".join(alloc_summary))
                    elif allocation_mode == "Custom per Concept":
                        st.caption("Customize the exact question count for each concept:")
                        hw_cols = st.columns(2)
                        for c_idx, c in enumerate(tb_concepts_list, 1):
                            c_name = c.get("concept_name") or c.get("name") or f"Concept {c_idx}"
                            col_target = hw_cols[(c_idx - 1) % 2]
                            with col_target:
                                q_cnt = st.number_input(
                                    f"Concept {c_idx}: {c_name[:30]}{'...' if len(c_name)>30 else ''}",
                                    min_value=0, max_value=15, value=3, step=1,
                                    key=f"hw_q_cnt_{tb_id}_{c_idx}",
                                    help=f"Full concept name: {c_name}"
                                )
                                hw_counts[c_name] = q_cnt
                    else:
                        st.caption("Choose how many questions to generate at each difficulty for every concept. Enter 0 to skip a level or concept.")
                        hw_difficulty_counts = {}
                        difficulty_levels = ("Easy", "Medium", "Hard", "Extremely Hard")
                        default_levels = (1, 1, 1, 0)
                        for c_idx, c in enumerate(tb_concepts_list, 1):
                            c_name = c.get("concept_name") or c.get("name") or f"Concept {c_idx}"
                            st.markdown(f"**Concept {c_idx}: {c_name}**")
                            tier_cols = st.columns(4)
                            tier_counts = {}
                            for tier_idx, level in enumerate(difficulty_levels):
                                with tier_cols[tier_idx]:
                                    tier_counts[level] = st.number_input(
                                        level,
                                        min_value=0,
                                        max_value=15,
                                        value=default_levels[tier_idx],
                                        step=1,
                                        key=f"hw_difficulty_{tb_id}_{c_idx}_{tier_idx}",
                                        help=f"Number of {level.lower()} questions for {c_name}."
                                    )
                            hw_difficulty_counts[c_name] = tier_counts
                            hw_counts[c_name] = sum(tier_counts.values())
                            st.caption(f"{hw_counts[c_name]} questions for this concept")
                else:
                    st.info("No explicit concepts found in booklet content; generating questions across standard curriculum subtopics.")

                total_hw_questions = sum(hw_counts.values()) if hw_counts else total_hw_target
                st.write(f"📊 **Total Homework Questions Selected**: `{total_hw_questions}`")

                btn_label = f"🚀 Generate Aligned Homework Booklet ({total_hw_questions} Questions - Set {hw_set_sel})"
                if st.button(btn_label, key=f"btn_gen_hw_{tb_id}", type="primary", use_container_width=True):
                    current_api_key = (st.session_state.get("gemini_api_key") or "").strip()
                    if not current_api_key:
                        st.error("🔑 Personal Gemini API Key required. Please configure your key in the sidebar.")
                    elif total_hw_questions <= 0:
                        st.warning("Please select at least 1 question across your concepts.")
                    elif total_hw_questions > 40:
                        st.warning("Please select no more than 40 homework questions in one booklet.")
                    else:
                        with st.spinner(f"Generating Aligned Homework Booklet (Set {hw_set_sel}) via Gemini..."):
                            try:
                                hw_data = ai_engine.generate_aligned_companion_worksheet(
                                    theory_booklet=tb,
                                    sheet_type="Homework",
                                    concept_counts=hw_counts,
                                    difficulty_counts=hw_difficulty_counts,
                                    set_number=hw_set_sel,
                                    year_level=tb.get("year_level"),
                                    topic=tb.get("topic"),
                                    textbook=tb.get("textbook", "CambridgeMATHS NSW"),
                                    term=tb.get("term"),
                                    week=tb.get("week"),
                                    api_key=current_api_key
                                )
                                new_hw_id = database.save_worksheet(
                                    title=hw_data["title"],
                                    term=hw_data.get("term"),
                                    week=hw_data.get("week"),
                                    year_level=hw_data["year_level"],
                                    topic=hw_data["topic"],
                                    difficulty="Balanced Mastery (Numerical Twins)",
                                    questions=hw_data["questions"],
                                    marking_key=hw_data["marking_key"],
                                    set_number=hw_set_sel,
                                    custom_instructions=f"Homework Numerical Twins - Set {hw_set_sel} (100% Theory-Aligned)",
                                    cost=hw_data.get("meta_cost", 0.0),
                                    model=hw_data.get("model_used"),
                                    tokens=hw_data.get("meta_tokens"),
                                    source_theory_id=tb_id,
                                    assessment_type="homework"
                                )
                                st.session_state["latest_worksheet"] = {**hw_data, "id": new_hw_id}
                                st.session_state["latest_generated_hw_id"] = new_hw_id
                                hw_cost = hw_data.get('meta_cost', 0.0)
                                hw_tokens = hw_data.get('meta_tokens', 0)
                                st.success(f"🎉 Successfully generated Homework Booklet #{new_hw_id} (Set {hw_set_sel})! (💰 Cost: ${hw_cost:.4f} AUD • {hw_tokens:,} tokens)")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Failed to generate Homework booklet: {e}")

            # === 3. TOPIC REVIEW BOOKLET TAB ===
            with suite_tab_review:
                st.info("💡 **Diagnostic Revision & Consolidation**: Generates high-yield concept summaries, vital formula cheat-sheets, tutor secrets & exam shortcuts, common pitfall traps, worked exam-style mastery examples, and revision questions across all concepts in this Theory Booklet.")

                all_revs = database.get_review_booklets()
                matching_revs = [
                    r for r in all_revs 
                    if str(r.get("topic", "")).lower() == str(tb.get("topic", "")).lower()
                    and str(r.get("year_level", "")).lower() == str(tb.get("year_level", "")).lower()
                ]
                if matching_revs:
                    st.success(f"📋 **{len(matching_revs)} Topic Review Booklet(s)** found for this topic.")
                    for mrb in matching_revs:
                            rb_cnt = mrb.get("content", mrb)
                            rb_c_str = f" • 💰 ${rb_cnt.get('meta_cost', 0.0):.4f} AUD" if rb_cnt.get('meta_cost') else ""
                            with st.expander(f"🔁 Review Booklet #{mrb['id']}: {mrb.get('title', 'Topic Review')}{rb_c_str}", expanded=False):
                                rb_cnt_json = json.dumps(rb_cnt)
                                rb_term = mrb.get("term")
                                rb_week = mrb.get("week")

                                rb_s_pdf = get_cached_review_pdf(mrb['id'], rb_cnt_json, rb_term, rb_week, "student")
                                rb_t_pdf = get_cached_review_pdf(mrb['id'], rb_cnt_json, rb_term, rb_week, "teacher")

                                rb_stu_name = get_review_booklet_download_filename(mrb, mode="student")
                                rb_tea_name = get_review_booklet_download_filename(mrb, mode="teacher")

                                col_rb1, col_rb2 = st.columns(2)
                                with col_rb1:
                                    st.download_button("📥 Student Review Booklet (PDF)", data=rb_s_pdf, file_name=rb_stu_name, mime="application/pdf", key=f"dl_c_stu_rb_{mrb['id']}", use_container_width=True)
                                with col_rb2:
                                    st.download_button("📥 Teacher Solutions (PDF)", data=rb_t_pdf, file_name=rb_tea_name, mime="application/pdf", key=f"dl_c_tea_rb_{mrb['id']}", use_container_width=True)

                                # 1-Click ZIP bundle & Delete
                                col_rb_z, col_rb_d = st.columns([2, 1])
                                with col_rb_z:
                                    rb_zip_bytes = build_review_zip_package(mrb['id'], json.dumps(mrb))
                                    clean_rb_topic = re.sub(r'^(?:Chapter|Unit|Topic\s*)?(?:\d+[\.\:\-]\s*|\d+[A-Za-z][\.\:\-]\s*|\d+\s+)', '', str(mrb.get('topic') or tb.get('topic') or 'Topic Review')).strip()
                                    zip_rb_filename = f"{clean_rb_topic} Review Complete Package.zip".replace("_", " ")
                                    st.download_button("📦 Download All as ZIP (Complete Review Package)", data=rb_zip_bytes, file_name=zip_rb_filename, mime="application/zip", key=f"dl_zip_rb_{mrb['id']}", use_container_width=True)
                                with col_rb_d:
                                    if st.button("🗑️ Delete Review Booklet", key=f"btn_del_rb_{mrb['id']}", use_container_width=True):
                                        database.delete_review_booklet(mrb['id'])
                                        st.success(f"Deleted Review Booklet #{mrb['id']}!")
                                        st.rerun()

                col_rq1, col_rq2 = st.columns([1, 2])
                with col_rq1:
                    rev_q_per_c = st.number_input("Revision Questions per Concept", min_value=1, max_value=10, value=3, step=1, key=f"rev_q_per_c_{tb_id}")
                with col_rq2:
                    st.caption("Balanced distribution across Level 1 (Foundations), Level 2 (Application), and Level 3 (Extension / Trap questions).")

                tot_rev_q = (len(tb_concepts_list) if tb_concepts_list else 4) * int(rev_q_per_c)
                st.write(f"📊 **Total Revision Questions to Generate**: `{tot_rev_q}`")

                if st.button("🚀 Generate Aligned Topic Review Booklet", key=f"btn_gen_rev_from_tb_{tb_id}", type="primary", use_container_width=True):
                    current_api_key = (st.session_state.get("gemini_api_key") or "").strip()
                    if not current_api_key:
                        st.error("🔑 Personal Gemini API Key required. Please configure your key in the sidebar.")
                    else:
                        with st.spinner("Generating Aligned Topic Review & Revision Booklet via Gemini..."):
                            try:
                                rev_subtopics = [c.get("concept_name") or c.get("name") for c in tb_concepts_list] if tb_concepts_list else None
                                rev_data = ai_engine.generate_review_booklet(
                                    year_level=tb.get("year_level"),
                                    topic=tb.get("topic"),
                                    subtopics=rev_subtopics,
                                    examples_per_concept=1,
                                    practice_per_concept=int(rev_q_per_c),
                                    term=tb.get("term"),
                                    week=tb.get("week"),
                                    textbook=tb.get("textbook", "CambridgeMATHS NSW"),
                                    api_key=current_api_key
                                )
                                rev_id = database.save_review_booklet(
                                    title=rev_data.get("title", f"{tb.get('topic')} Review Booklet"),
                                    term=tb.get("term"),
                                    week=tb.get("week"),
                                    year_level=tb.get("year_level"),
                                    topic=tb.get("topic"),
                                    content=rev_data
                                )
                                rev_data["id"] = rev_id
                                st.session_state["latest_review_booklet"] = rev_data
                                st.session_state["latest_review_booklet_id"] = rev_id
                                rev_cost = rev_data.get('meta_cost', 0.0)
                                rev_tokens = rev_data.get('meta_tokens', 0)
                                st.success(f"🎉 Successfully generated Topic Review Booklet #{rev_id}! (💰 Cost: ${rev_cost:.4f} AUD • {rev_tokens:,} tokens)")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Failed to generate Topic Review Booklet: {e}")

            # === 4. TOPIC TEST BOOKLET (MASTERY EXAM) TAB ===
            with suite_tab_exam:
                st.info("💡 **Pedagogical Twin Alignment**: Tests every taught concept in this Theory Booklet with zero blind spots across tiered cognitive levels (Level 1 Memory, Level 2 Application, Level 3 Extension). Every question is tagged for automated gap analysis in Tab 3.")

                linked_exams = database.get_theory_linked_worksheets(tb_id, assessment_type="topic_exam") if tb_id else []
                if linked_exams:
                    st.success(f"📋 **{len(linked_exams)} End-of-Topic Mastery Exam(s)** linked to this Theory Booklet in the database.")
                    for le in linked_exams:
                        le_cost_str = f" • 💰 ${le.get('cost', 0.0):.4f} AUD" if le.get('cost') else ""
                        with st.expander(f"📑 Exam #{le['id']}: {le['title']} ({le['total_questions']} Questions{le_cost_str})", expanded=False):
                            le_qs = le.get("questions", [])
                            le_title = le["title"]
                            le_year = le["year_level"]
                            le_topic = le["topic"]
                            le_term = le.get("term")
                            le_week = le.get("week")
                            le_q_json = json.dumps(le_qs)
                            le_mk_json = json.dumps(le.get("marking_key") or {})

                            exam_pdf = get_cached_worksheet_pdf(le['id'], le_title, le_year, le_topic, le_q_json, le_mk_json, le_term, le_week, "topic_exam", "student")
                            sol_pdf = get_cached_worksheet_pdf(le['id'], le_title, le_year, le_topic, le_q_json, le_mk_json, le_term, le_week, "topic_exam", "teacher")

                            stu_dl_name = get_topic_exam_download_filename(le, mode="student", theory_booklet=tb)
                            tea_dl_name = get_topic_exam_download_filename(le, mode="teacher", theory_booklet=tb)

                            col_le1, col_le2 = st.columns(2)
                            with col_le1:
                                st.download_button("📥 Student Exam Paper (PDF)", data=exam_pdf, file_name=stu_dl_name, mime="application/pdf", key=f"dl_c_stu_{le['id']}", use_container_width=True)
                            with col_le2:
                                st.download_button("📥 Teacher Solutions (PDF)", data=sol_pdf, file_name=tea_dl_name, mime="application/pdf", key=f"dl_c_tea_{le['id']}", use_container_width=True)

                            # 1-Click ZIP bundle & 1-Click Marking Navigation & Delete
                            col_ex_z, col_ex_m, col_ex_d = st.columns([1.4, 1.0, 0.8])
                            with col_ex_z:
                                exam_zip_bytes = build_exam_zip_package(le['id'], json.dumps(le), json.dumps(tb) if tb else None)
                                clean_exam_topic = re.sub(r'^(?:Chapter|Unit|Topic\s*)?(?:\d+[\.\:\-]\s*|\d+[A-Za-z][\.\:\-]\s*|\d+\s+)', '', str(le_topic)).strip()
                                zip_exam_filename = f"{clean_exam_topic} Mastery Exam Complete Package.zip".replace("_", " ")
                                st.download_button("📦 Download All as ZIP (Complete Exam Package)", data=exam_zip_bytes, file_name=zip_exam_filename, mime="application/zip", key=f"dl_zip_exam_{le['id']}", use_container_width=True)
                            with col_ex_m:
                                if st.button(f"⚡ Mark Submissions", key=f"btn_mark_sub_exam_{le['id']}", use_container_width=True):
                                    st.session_state["preselected_marking_ws_id"] = le['id']
                                    st.session_state["active_tab_hint"] = "marking"
                                    st.info(f"✅ Selected Mastery Exam #{le['id']}! Head to **Tab 2 (1-Click AI Homework Marking)** to grade student scans.")
                            with col_ex_d:
                                if st.button(f"🗑️ Delete", key=f"btn_del_exam_{le['id']}", use_container_width=True):
                                    database.delete_worksheet(le['id'], force=True)
                                    if st.session_state.get("preselected_marking_ws_id") == le['id']:
                                        st.session_state.pop("preselected_marking_ws_id", None)
                                    st.success(f"Deleted Mastery Exam #{le['id']}!")
                                    st.rerun()

                col_ex_g1, col_ex_g2 = st.columns([2.5, 1])
                with col_ex_g1:
                    st.caption("Standard exam configuration generates balanced questions across cognitive tiers (Level 1 Memory, Level 2 Application, Level 3 Extension) per concept.")
                with col_ex_g2:
                    q_per_concept_sel = st.selectbox(
                        "Questions per Concept",
                        [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 15, 20],
                        index=2,
                        key=f"q_per_c_tb_{tb.get('id', 0)}"
                    )

                # Optional customization per concept
                has_exam_custom = False
                exam_custom_counts = {}
                with st.expander("⚙️ Customize Exam Question Counts per Concept (Optional)", expanded=False):
                    st.caption("Select how many exam questions to generate for each specific concept (overrides general questions-per-concept setting):")
                    use_custom_exam_counts = st.checkbox("Override counts for individual concepts", value=False, key=f"chk_custom_exam_{tb_id}")
                    if use_custom_exam_counts and tb_concepts_list:
                        has_exam_custom = True
                        ex_cols = st.columns(2)
                        for c_idx, c in enumerate(tb_concepts_list, 1):
                            c_name = c.get("concept_name") or c.get("name") or f"Concept {c_idx}"
                            col_target = ex_cols[(c_idx - 1) % 2]
                            with col_target:
                                q_cnt = st.number_input(
                                    f"Concept {c_idx}: {c_name[:30]}{'...' if len(c_name)>30 else ''}",
                                    min_value=0, max_value=20, value=int(q_per_concept_sel), step=1,
                                    key=f"ex_q_cnt_{tb_id}_{c_idx}",
                                    help=f"Full concept name: {c_name}"
                                )
                                exam_custom_counts[c_name] = q_cnt

                total_exam_questions = sum(exam_custom_counts.values()) if (has_exam_custom and exam_custom_counts) else ((len(tb_concepts_list) if tb_concepts_list else 4) * int(q_per_concept_sel))
                st.write(f"📊 **Total Exam Questions to Generate**: `{total_exam_questions}`")

                if st.button("🎯 Generate Aligned End-of-Topic Mastery Exam", key=f"btn_gen_exam_from_tb_{tb.get('id', 0)}", type="primary", use_container_width=True):
                    current_api_key = (st.session_state.get("gemini_api_key") or "").strip()
                    if not current_api_key:
                        st.error("🔑 Personal Gemini API Key required. Please configure your key in the sidebar.")
                    elif total_exam_questions <= 0:
                        st.warning("Please select at least 1 question across your concepts.")
                    else:
                        with st.spinner("Generating 1:1 Concept-Aligned End-of-Topic Mastery Exam via Gemini..."):
                            try:
                                exam_data = ai_engine.generate_topic_mastery_exam(
                                    theory_booklet=tb,
                                    year_level=tb.get("year_level"),
                                    topic=tb.get("topic"),
                                    textbook=tb.get("textbook", "CambridgeMATHS NSW"),
                                    term=tb.get("term"),
                                    week=tb.get("week"),
                                    api_key=current_api_key,
                                    questions_per_concept=int(q_per_concept_sel),
                                    concept_counts=exam_custom_counts if (has_exam_custom and exam_custom_counts) else None
                                )
                                new_ws_id = database.save_worksheet(
                                    title=exam_data["title"],
                                    term=exam_data.get("term"),
                                    week=exam_data.get("week"),
                                    year_level=exam_data["year_level"],
                                    topic=exam_data["topic"],
                                    difficulty="Tiered (Level 1-3)",
                                    questions=exam_data["questions"],
                                    marking_key=exam_data["marking_key"],
                                    set_number=1,
                                    custom_instructions="End-of-Topic Mastery Exam (1:1 Concept Coverage)",
                                    cost=exam_data.get("meta_cost", 0.0),
                                    model=exam_data.get("model_used"),
                                    tokens=exam_data.get("meta_tokens"),
                                    source_theory_id=tb.get("id"),
                                    assessment_type="topic_exam"
                                )
                                st.session_state["latest_worksheet"] = {**exam_data, "id": new_ws_id}
                                st.session_state["latest_exam_created_id"] = new_ws_id
                                ex_cost = exam_data.get('meta_cost', 0.0)
                                ex_tokens = exam_data.get('meta_tokens', 0)
                                st.success(f"🎉 Successfully generated End-of-Topic Mastery Exam #{new_ws_id}! (💰 Cost: ${ex_cost:.4f} AUD • {ex_tokens:,} tokens) — Head to Tab 2 to grade submissions or see linked exam above.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Failed to generate End-of-Topic Exam: {e}")

            # === 5. EXAM PREPARATION BOOKLET TAB ===
            with suite_tab_prep:
                st.info("💡 **HSC Senior Marker Exam Preparation Suite (Dual Booklets)**: Booklet 1 (Theory Summary, Visual Cheat-Sheets & Worked Past Papers) and Booklet 2 (Timed Practice Exam with Student and Teacher Editions).")

                all_pkgs = database.get_exam_packages()
                matching_pkgs = [
                    p for p in all_pkgs
                    if str(p.get("topic", "")).lower() == str(tb.get("topic", "")).lower()
                    and str(p.get("year_level", "")).lower() == str(tb.get("year_level", "")).lower()
                ]
                if matching_pkgs:
                    st.success(f"📋 **{len(matching_pkgs)} Exam Preparation Package(s)** found for this topic.")
                    for mp in matching_pkgs:
                        mp_content = mp.get("content", mp)
                        mp_cost_str = f" • 💰 ${mp_content.get('meta_cost', 0.0):.4f} AUD" if mp_content.get('meta_cost') else ""
                        with st.expander(f"📦 Exam Package #{mp['id']}: {mp.get('title', 'Exam Package')}{mp_cost_str}", expanded=False):
                            mp_cnt_json = json.dumps(mp_content)
                            mp_term = mp.get("term")
                            mp_week = mp.get("week")

                            b1_pdf = get_cached_exam_pkg_pdf(mp['id'], mp_cnt_json, "theory", mp_term, mp_week, "student")
                            b2_pdf = get_cached_exam_pkg_pdf(mp['id'], mp_cnt_json, "practice", mp_term, mp_week, "teacher")

                            b1_name = get_exam_package_download_filename(mp, booklet_type="theory", mode="student")
                            b2_name = get_exam_package_download_filename(mp, booklet_type="practice", mode="teacher")

                            col_p1, col_p2 = st.columns(2)
                            with col_p1:
                                st.download_button("📥 Booklet 1 (Theory & Worked Past Papers)", data=b1_pdf, file_name=b1_name, mime="application/pdf", key=f"dl_c_b1_{mp['id']}", use_container_width=True)
                            with col_p2:
                                st.download_button("📥 Booklet 2 (Practice Exam & Solutions)", data=b2_pdf, file_name=b2_name, mime="application/pdf", key=f"dl_c_b2_{mp['id']}", use_container_width=True)

                            # 1-Click ZIP bundle & Delete
                            col_p_z, col_p_d = st.columns([2, 1])
                            with col_p_z:
                                pkg_zip_bytes = build_exam_pkg_zip_package(mp['id'], json.dumps(mp))
                                clean_pkg_topic = re.sub(r'^(?:Chapter|Unit|Topic\s*)?(?:\d+[\.\:\-]\s*|\d+[A-Za-z][\.\:\-]\s*|\d+\s+)', '', str(mp.get('topic') or tb.get('topic') or 'Exam Package')).strip()
                                zip_pkg_filename = f"{clean_pkg_topic} Exam Package Complete Suite.zip".replace("_", " ")
                                st.download_button("📦 Download All as ZIP (Complete Exam Package Suite)", data=pkg_zip_bytes, file_name=zip_pkg_filename, mime="application/zip", key=f"dl_zip_pkg_{mp['id']}", use_container_width=True)
                            with col_p_d:
                                if st.button("🗑️ Delete Exam Package", key=f"btn_del_pkg_{mp['id']}", use_container_width=True):
                                    database.delete_exam_package(mp['id'])
                                    st.success(f"Deleted Exam Package #{mp['id']}!")
                                    st.rerun()

                st.caption(f"Compiles an authentic examination package covering all concepts of **{tb.get('topic')}** with senior HSC marker feedback & past paper style questions.")

                if st.button("🚀 Generate Aligned Exam Preparation Package", key=f"btn_gen_pkg_from_tb_{tb_id}", type="primary", use_container_width=True):
                    current_api_key = (st.session_state.get("gemini_api_key") or "").strip()
                    if not current_api_key:
                        st.error("🔑 Personal Gemini API Key required. Please configure your key in the sidebar.")
                    else:
                        with st.spinner("Generating Aligned Comprehensive Exam Package via Gemini..."):
                            try:
                                pkg_subtopics = [c.get("concept_name") or c.get("name") for c in tb_concepts_list] if tb_concepts_list else None
                                pkg_data = ai_engine.generate_exam_package(
                                    year_level=tb.get("year_level"),
                                    topic=tb.get("topic"),
                                    subtopics=pkg_subtopics,
                                    term=tb.get("term"),
                                    week=tb.get("week"),
                                    textbook=tb.get("textbook", "CambridgeMATHS NSW"),
                                    api_key=current_api_key
                                )
                                pkg_id = database.save_exam_package(
                                    title=pkg_data.get("title", f"{tb.get('topic')} Exam Package"),
                                    term=tb.get("term"),
                                    week=tb.get("week"),
                                    year_level=tb.get("year_level"),
                                    topic=tb.get("topic"),
                                    content=pkg_data
                                )
                                pkg_data["id"] = pkg_id
                                st.session_state["latest_exam_package"] = pkg_data
                                st.session_state["latest_exam_package_id"] = pkg_id
                                pkg_cost = pkg_data.get('meta_cost', 0.0)
                                pkg_tokens = pkg_data.get('meta_tokens', 0)
                                st.success(f"🎉 Successfully generated Exam Preparation Package #{pkg_id}! (💰 Cost: ${pkg_cost:.4f} AUD • {pkg_tokens:,} tokens)")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Failed to generate Exam Preparation Package: {e}")

            st.markdown("---")
            st.markdown("#### 👁️ PDF Preview")
            st.caption("Pixel-perfect representation of the compiled PDF ready for high-resolution printing.")

            def _render_raw_tb_content():
                for c_idx, c in enumerate(tb.get("concepts", []), 1):
                    st.markdown(f"### Concept {c_idx}: {c.get('name', 'Concept')}")
                    if c.get("theory_text"):
                        st.markdown(f"**Theory & Notes:**\n\n{c.get('theory_text')}")
                    if c.get("key_formulas"):
                        st.markdown("**Key Formulas:**")
                        for f in c.get("key_formulas"):
                            st.markdown(f"- {f}")
                    if c.get("tutor_tips"):
                        st.info(f"💡 **Tutor Tips:** {c.get('tutor_tips')}")

                    st.markdown("#### 👨‍🏫 Teacher Examples:")
                    for e_idx, ex in enumerate(c.get("teacher_examples", []), 1):
                        st.markdown(f"**Example {c_idx}.{e_idx}:** {ex.get('problem_text')}")
                        with st.expander(f"Show Solution for Example {c_idx}.{e_idx}", expanded=False):
                            st.markdown(f"**Worked Solution:**\n\n{ex.get('worked_solution')}")
                            if ex.get("teaching_notes"):
                                st.caption(f"Teaching Notes: {ex.get('teaching_notes')}")

                    st.markdown("#### ✍️ Tiered Practice Questions:")
                    for p_idx, pq in enumerate(c.get("practice_questions", []), 1):
                        diff = pq.get("difficulty", "Medium")
                        marks = pq.get("marks", 2)
                        st.markdown(f"**Practice {c_idx}.{p_idx}** `[{diff} • {marks} Mark{'s' if marks > 1 else ''}]`: {pq.get('text')}")
                        with st.expander(f"Show Solution & Answer for Practice {c_idx}.{p_idx}", expanded=False):
                            st.markdown(f"**Answer:** {pq.get('final_answer')}")
                            st.markdown(f"**Worked Solution:**\n\n{pq.get('worked_solution')}")
                    st.markdown("---")

            tb_editions = {
                "Theory Student Class (Questions Only)": student_class_pdf_bytes,
                "Theory Student Private (Complete Notes)": student_private_pdf_bytes,
                "Theory Teacher (With Solutions)": teacher_pdf_bytes,
            }
            render_authentic_pdf_preview(
                pdf_bytes=student_class_pdf_bytes,
                key_prefix="latest_tb",
                available_editions=tb_editions,
                default_edition="Theory Student Class (Questions Only)",
                raw_content_callback=_render_raw_tb_content,
                raw_content_title="📝 View Raw Questions, Examples & LaTeX Code"
            )

    with sub_tab_worksheet:
        st.markdown("### Generate Exam-Style Worksheet & Auto Marking Key")
        st.caption("Aligned with NSW Syllabus textbooks (CambridgeMATHS & Maths in Focus). Questions are allocated marks according to problem complexity and steps required.")

        # Saved Worksheets & Homework Booklets Library
        saved_worksheets = database.get_worksheets()
        if saved_worksheets:
            with st.expander("📚 Saved Worksheets & Homework Booklets Library (Load Existing Booklet)", expanded=False):
                ws_lib_opts = {}
                for w in saved_worksheets:
                    s_type = w.get("assessment_type") or w.get("sheet_type") or "Worksheet"
                    s_num = w.get("set_number", 1)
                    type_str = f"Homework Set {s_num}" if "homework" in s_type.lower() else s_type.replace("_", " ").title()
                    t_str = f"T{w.get('term')}W{w.get('week')}" if (w.get('term') and w.get('week')) else "General"
                    lbl = f"#{w['id']} — [{t_str}] {type_str} • {w.get('year_level', '')} — {w.get('topic') or w.get('title')} ({w.get('total_questions', 0)} Qs)"
                    ws_lib_opts[lbl] = w['id']
                selected_lib_ws_label = st.selectbox("Select a Saved Worksheet / Homework Booklet:", list(ws_lib_opts.keys()), key="sel_lib_ws")
                sel_lib_ws_id = ws_lib_opts[selected_lib_ws_label]
                if st.session_state.get("pending_delete_ws_id") != sel_lib_ws_id:
                    st.session_state.pop("pending_delete_ws_id", None)
                load_col, delete_col = st.columns(2)
                with load_col:
                    if st.button("📂 Load Selected Worksheet", key=f"btn_load_lib_ws_{sel_lib_ws_id}", type="primary", use_container_width=True):
                        loaded_ws = database.get_worksheet_by_id(sel_lib_ws_id)
                        if loaded_ws:
                            st.session_state["latest_worksheet"] = loaded_ws
                            st.session_state["latest_ws_id"] = loaded_ws["id"]
                            st.session_state.pop("latest_ws_cache_key", None)
                            st.session_state.pop("latest_ws_artifacts", None)
                            st.success(f"Loaded Worksheet #{loaded_ws['id']}: {loaded_ws.get('title')}!")
                            st.rerun()
                with delete_col:
                    if st.button("🗑️ Delete Selected Worksheet", key=f"btn_delete_lib_ws_{sel_lib_ws_id}", use_container_width=True):
                        st.session_state["pending_delete_ws_id"] = sel_lib_ws_id
                        st.rerun()
                if st.session_state.get("pending_delete_ws_id") == sel_lib_ws_id:
                    ws_subs_count = database.get_worksheet_submission_count(sel_lib_ws_id)
                    if ws_subs_count > 0:
                        st.warning(f"⚠️ Delete worksheet #{sel_lib_ws_id}: `{selected_lib_ws_label}`? It currently has **{ws_subs_count} marked student submission(s)** in the database. Deleting it will permanently erase these marks and student reports.")
                        force_cb = st.checkbox(f"Yes, permanently delete worksheet #{sel_lib_ws_id} and all {ws_subs_count} student submission(s).", key=f"force_del_lib_{sel_lib_ws_id}")
                    else:
                        st.warning(f"Delete worksheet #{sel_lib_ws_id}: `{selected_lib_ws_label}`? This cannot be undone.")
                        force_cb = False

                    confirm_col, cancel_col = st.columns(2)
                    with confirm_col:
                        btn_disabled = (ws_subs_count > 0 and not force_cb)
                        if st.button("Confirm Delete", key=f"confirm_delete_ws_{sel_lib_ws_id}", type="primary", disabled=btn_disabled, use_container_width=True):
                            try:
                                if database.delete_worksheet(sel_lib_ws_id, force=force_cb):
                                    if st.session_state.get("latest_ws_id") == sel_lib_ws_id:
                                        for state_key in ("latest_worksheet", "latest_ws_id", "latest_ws_cache_key", "latest_ws_artifacts"):
                                            st.session_state.pop(state_key, None)
                                    if st.session_state.get("preselected_marking_ws_id") == sel_lib_ws_id:
                                        st.session_state.pop("preselected_marking_ws_id", None)
                                    st.session_state.pop("pending_delete_ws_id", None)
                                    st.success(f"Worksheet #{sel_lib_ws_id} deleted successfully.")
                                    st.rerun()
                                else:
                                    st.error("This worksheet no longer exists.")
                            except ValueError as exc:
                                st.error(str(exc))
                    with cancel_col:
                        if st.button("Cancel", key=f"cancel_delete_ws_{sel_lib_ws_id}", use_container_width=True):
                            st.session_state.pop("pending_delete_ws_id", None)
                            st.rerun()

        col_yl, col_tb = st.columns([1.2, 1.8])
        with col_yl:
            default_yl_index = YEAR_LEVEL_OPTIONS.index("Year 11 (Extension)") if "Year 11 (Extension)" in YEAR_LEVEL_OPTIONS else 8
            year_level = st.selectbox(
                "Year Level",
                YEAR_LEVEL_OPTIONS,
                index=default_yl_index,
                key="select_year_level"
            )

        with col_tb:
            available_ws_tbs = ai_engine.get_textbooks_for_year(year_level)
            ws_textbook = st.selectbox(
                "📚 Choose Textbook Curriculum Series",
                available_ws_tbs,
                index=0,
                key=f"ws_tb_{year_level}"
            )

        if ai_engine.is_year_11_advanced(year_level):
            st.info("🔒 **Strict NSW Stage 6 Syllabus Boundary Enforced**: Pure Year 11 Mathematics Advanced & Stage 5.3 prerequisites only. Zero Year 12 calculus (no integration, product/quotient/chain rules), zero Extension 1 (no vectors, induction, combinatorics, polynomials division), and zero tertiary content.")

        col2, col3 = st.columns([2, 1])
        with col2:
            # Pre-filled topics from selected textbook for selected year level
            available_topics = ai_engine.get_topics_for_year(year_level, textbook=ws_textbook)
            topic_options = available_topics + ["Custom Topic..."]
            selected_topic_choice = st.selectbox(
                f"Topic / Chapter (from {ws_textbook})",
                topic_options,
                index=0,
                key=f"topic_choice_{ws_textbook}_{year_level}"
            )
            if selected_topic_choice == "Custom Topic...":
                topic_input = st.text_input("Enter Custom Topic Name", value="Probability", key=f"custom_topic_txt_{ws_textbook}_{year_level}")
            else:
                topic_input = selected_topic_choice

        with col3:
            st.markdown("<div style='height: 4px;'></div>", unsafe_allow_html=True)
            use_mc = st.checkbox("Include Multiple Choice", value=False, key="ws_use_mc", help="Adds NESA-style Section 1 Multiple Choice questions with options (A), (B), (C), (D)")
            if use_mc:
                num_mc = st.number_input("Multiple Choice Quantity", min_value=1, max_value=25, value=5, step=1, key="ws_num_mc")
            else:
                num_mc = 0

        col4, col5 = st.columns([2, 2])
        with col4:
            has_ws_term_week = st.checkbox("📅 Specify Term & Week (Optional)", value=True, key="ws_has_term_week")
            if has_ws_term_week:
                c_term, c_week = st.columns(2)
                with c_term:
                    term_num = st.number_input("Term", min_value=1, max_value=4, value=3, step=1, key="ws_term_input")
                with c_week:
                    week_num = st.number_input("Week", min_value=1, max_value=12, value=8, step=1, key="ws_week_input")
            else:
                term_num = None
                week_num = None
                st.caption("ℹ️ General resource — not assigned to a specific term or week.")
        with col5:
            col_type, col_set = st.columns([1.2, 1])
            with col_type:
                sheet_type = st.radio("Worksheet Type", ["Homework", "In-Class"], horizontal=True, key="ws_sheet_type_radio")
            with col_set:
                if sheet_type == "Homework":
                    ws_set_number = st.number_input("Homework Set", min_value=1, max_value=50, value=1, step=1, key="ws_set_number", help="Designates Set 1, Set 2, etc. on the booklet and file name.")
                else:
                    ws_set_number = 1

        # --- SUBTOPIC ALLOCATION SYSTEM (NSW SYLLABUS PRE-FILLED) ---
        st.markdown("---")
        st.markdown("#### 📋 Allocate Questions by Subtopic")
        st.caption(f"Pre-filled from **{ws_textbook}** for **{year_level} — {topic_input}**. Adjust question counts per subtopic:")

        subtopics_cache_key = f"subs_{ws_textbook}_{year_level}_{topic_input}"
        if subtopics_cache_key not in st.session_state:
            try:
                st.session_state[subtopics_cache_key] = ai_engine.get_curriculum_subtopics(year_level, topic_input, textbook=ws_textbook)
            except Exception:
                st.session_state[subtopics_cache_key] = []

        active_subtopics = st.session_state[subtopics_cache_key]

        col_act_a, col_act_b = st.columns([1, 1])
        with col_act_a:
            if st.button("🤖 AI Suggest More Subtopics", key=f"btn_ai_subs_{subtopics_cache_key}"):
                cur_key = st.session_state.get("gemini_api_key", "")
                with st.spinner(f"Fetching {ws_textbook} subtopics with AI..."):
                    ai_subs = ai_engine.suggest_subtopics_ai(year_level, topic_input, cur_key, textbook=ws_textbook)
                    st.session_state[subtopics_cache_key] = ai_subs
                    st.rerun()

        with col_act_b:
            with st.popover("➕ Add Custom Subtopic"):
                new_sub_name = st.text_input("Subtopic Title", placeholder="e.g. Additional Problem Types")
                if st.button("Add to List") and new_sub_name.strip():
                    if new_sub_name.strip() not in active_subtopics:
                        active_subtopics.append(new_sub_name.strip())
                        st.session_state[subtopics_cache_key] = active_subtopics
                        st.rerun()

        # --- PER-SUBTOPIC DIFFICULTY SELECTION MATRIX ---
        subtopic_counts = {}
        total_allocated_items = 0
        total_easy = 0
        total_med = 0
        total_hard = 0
        total_exhard = 0
        total_pastexam = 0

        st.markdown("---")
        for i, sub in enumerate(active_subtopics):
            key_include = f"sub_inc_{subtopics_cache_key}_{i}"
            key_e = f"diff_e_{subtopics_cache_key}_{i}"
            key_m = f"diff_m_{subtopics_cache_key}_{i}"
            key_h = f"diff_h_{subtopics_cache_key}_{i}"
            key_eh = f"diff_eh_{subtopics_cache_key}_{i}"
            key_pe = f"diff_pe_{subtopics_cache_key}_{i}"

            # Default initial values: Include=True, 1 Easy, 1 Medium, 0 Hard, 0 Extremely Hard, 0 Past Exam
            if key_include not in st.session_state:
                st.session_state[key_include] = True
            if key_e not in st.session_state:
                st.session_state[key_e] = 1
            if key_m not in st.session_state:
                st.session_state[key_m] = 1
            if key_h not in st.session_state:
                st.session_state[key_h] = 0
            if key_eh not in st.session_state:
                st.session_state[key_eh] = 0
            if key_pe not in st.session_state:
                st.session_state[key_pe] = 0

            is_included = st.session_state[key_include]

            cur_e = st.session_state[key_e] if is_included else 0
            cur_m = st.session_state[key_m] if is_included else 0
            cur_h = st.session_state[key_h] if is_included else 0
            cur_eh = st.session_state[key_eh] if is_included else 0
            cur_pe = st.session_state[key_pe] if is_included else 0
            sub_sum = cur_e + cur_m + cur_h + cur_eh + cur_pe

            header_col1, header_col2 = st.columns([0.05, 0.95])
            with header_col1:
                sub_checked = st.checkbox("Include subtopic", value=is_included, key=key_include, label_visibility="collapsed")
            with header_col2:
                if sub_checked:
                    st.markdown(f"**📌 {sub}** &nbsp; <span style='color: #666; font-size: 0.9em;'>(Subtotal: <b>{sub_sum}</b> questions)</span>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<span style='color: #9E9E9E; text-decoration: line-through;'><b>📌 {sub}</b></span> &nbsp; <span style='color: #BDBDBD; font-size: 0.85em;'>(Excluded from booklet)</span>", unsafe_allow_html=True)

            if sub_checked:
                c_e, c_m, c_h, c_eh, c_pe = st.columns(5)
                with c_e:
                    cnt_e = st.number_input("🟢 Easy", min_value=0, max_value=20, step=1, key=key_e, help="Foundational 1-step problems (Commit to Memory)")
                with c_m:
                    cnt_m = st.number_input("🟡 Medium", min_value=0, max_value=20, step=1, key=key_m, help="Standard 2-step textbook applications (Further Practice)")
                with c_h:
                    cnt_h = st.number_input("🟠 Hard", min_value=0, max_value=20, step=1, key=key_h, help="Multi-step non-routine problem solving (Application)")
                with c_eh:
                    cnt_eh = st.number_input("🔴 Extremely Hard", min_value=0, max_value=20, step=1, key=key_eh, help="Challenging extension problems (Thinking Creatively)")
                with c_pe:
                    cnt_pe = st.number_input("🏆 Past Exam", min_value=0, max_value=20, step=1, key=key_pe, help="Authentic selective/independent trial & HSC exam questions (Exam Questions)")

                subtopic_counts[sub] = {
                    "Easy": cnt_e,
                    "Medium": cnt_m,
                    "Hard": cnt_h,
                    "Extremely Hard": cnt_eh,
                    "Past Exam": cnt_pe
                }
                total_allocated_items += (cnt_e + cnt_m + cnt_h + cnt_eh + cnt_pe)
                total_easy += cnt_e
                total_med += cnt_m
                total_hard += cnt_h
                total_exhard += cnt_eh
                total_pastexam += cnt_pe

        st.markdown("---")
        if total_allocated_items > 0:
            st.info(
                f"📊 **Total Questions to Allocate: {total_allocated_items} questions** &nbsp;|&nbsp; "
                f"🟢 **{total_easy} Easy** &nbsp;•&nbsp; "
                f"🟡 **{total_med} Medium** &nbsp;•&nbsp; "
                f"🟠 **{total_hard} Hard** &nbsp;•&nbsp; "
                f"🔴 **{total_exhard} Extremely Hard** &nbsp;•&nbsp; "
                f"🏆 **{total_pastexam} Past Exam**"
            )
        else:
            st.warning("⚠️ **Total Questions Allocated: 0 questions.** Please allocate at least 1 question using the number inputs above.")

        custom_notes = st.text_area(
            "Specific Curriculum Requirements / Instructions (Optional)",
            placeholder="e.g. Focus on examination style questions, include non-monic quadratics, surds, and geometric applications.",
            key="ws_custom_notes"
        )

        use_search = st.checkbox("🌍 Enable Live Google Search Grounding", value=False, key="ws_use_search", help="Grounds problem contexts with current Australian data and real-world statistics")

        latest_tb = st.session_state.get("latest_theory_booklet")
        align_with_tb = False
        if latest_tb and isinstance(latest_tb, dict):
            tb_topic = latest_tb.get("topic", "")
            if not topic_input or topic_input.lower() in tb_topic.lower() or tb_topic.lower() in topic_input.lower():
                align_with_tb = True
                st.info(f"🔗 **Pedagogically Aligned with Theory Booklet**: Questions generated will directly mirror the concepts, examples, and methods from your generated Theory Booklet (*{latest_tb.get('title')}*) so students can solve homework directly using their classroom notes.")

        if st.button("🚀 Generate Exam Worksheet & Auto Marking Key", type="primary"):
            current_api_key = (st.session_state.get("gemini_api_key") or "").strip()
            if not current_api_key:
                st.error("⚠️ Gemini API Key Required: Please enter your personal Google Gemini API key in the left sidebar under '🔑 Personal Gemini API Key' (Get a free key in 30s at https://aistudio.google.com/app/apikey).")
            elif total_allocated_items <= 0 and (not use_mc or num_mc <= 0):
                st.error("Please allocate at least 1 question across your subtopics or Multiple Choice.")
            else:
                total_to_gen = total_allocated_items + (num_mc if use_mc else 0)
                with st.spinner(f"Generating {total_to_gen} Australian curriculum items with LaTeX formulas, worked solutions, and marking key ({ws_textbook})..."):
                    try:
                        diff_parts = []
                        if total_easy: diff_parts.append(f"{total_easy}E")
                        if total_med: diff_parts.append(f"{total_med}M")
                        if total_hard: diff_parts.append(f"{total_hard}H")
                        if total_exhard: diff_parts.append(f"{total_exhard}EH")
                        if total_pastexam: diff_parts.append(f"{total_pastexam}PE")
                        diff_str = f"Mixed ({'/'.join(diff_parts)})" if diff_parts else "Differentiated (Tiered Levels)"

                        generated_data = ai_engine.generate_curriculum_worksheet(
                            topic=topic_input,
                            year_level=year_level,
                            subtopics_dict=subtopic_counts,
                            difficulty=diff_str,
                            sheet_type=sheet_type,
                            term=int(term_num) if term_num is not None else None,
                            week=int(week_num) if week_num is not None else None,
                            custom_instructions=custom_notes,
                            textbook=ws_textbook,
                            api_key=current_api_key,
                            num_mc=num_mc if use_mc else 0,
                            use_search=use_search,
                            theory_reference_data=latest_tb if align_with_tb else None
                        )
                        clean_topic = ai_engine.clean_topic_title(topic_input)
                        set_num_val = ws_set_number if sheet_type == "Homework" else 1
                        custom_title = f"{year_level} - {clean_topic} Homework Set {set_num_val}" if sheet_type == "Homework" else f"{year_level} - {clean_topic} In-Class Worksheet"
                        generated_data["title"] = custom_title
                        generated_data["topic"] = clean_topic
                        generated_data["set_number"] = set_num_val
                        generated_data["sheet_type"] = sheet_type
                        generated_data["source_theory_id"] = latest_tb.get("id") if align_with_tb else None

                        ws_id = database.ensure_generated_worksheet_saved(generated_data)
                        generated_data["id"] = ws_id
                        st.session_state["latest_worksheet"] = generated_data
                        st.session_state["latest_ws_id"] = ws_id
                        st.session_state["preselected_marking_ws_id"] = ws_id
                        ws_cost = generated_data.get('meta_cost', 0.0)
                        ws_tokens = generated_data.get('meta_tokens', 0)
                        st.success(f"🎉 Generated and saved Homework Set {set_num_val} as assignment #{ws_id}! (💰 Cost: ${ws_cost:.4f} AUD • {ws_tokens:,} tokens) — Ready for marking and printing." if sheet_type == "Homework" else f"🎉 Generated and saved worksheet #{ws_id}! (💰 Cost: ${ws_cost:.4f} AUD • {ws_tokens:,} tokens) — Ready for marking and printing.")
                    except Exception as e:
                        st.error(f"Error generating worksheet: {e}")

        # Preview & Download Latest Generated Worksheet
        if "latest_worksheet" in st.session_state:
            ws = st.session_state["latest_worksheet"]
            st.markdown("---")
            st.markdown(f"#### 📄 {ws.get('title')}")

            if ws.get("meta_cost") is not None or ws.get("meta_tokens"):
                st.info(f"💰 **Generation Cost:** **${ws.get('meta_cost', 0.0):.4f} AUD** • **{ws.get('meta_tokens', 0):,} tokens** ({ws.get('model_used', 'Gemini 3.8 Flash')})")

            # Extract question labels and answers (expanded for multi-part questions: 1(a), 1(b), etc.)
            question_labels, ws_answers, ws_expanded_key, ws_items = pdf_generator.extract_worksheet_answer_sheet_data(
                ws.get("questions", []), ws.get("marking_key")
            )
            ws_item_topic = ws.get("topic", topic_input)
            ws_sheet_type = ws.get("sheet_type", sheet_type)
            ws_set_val = ws.get("set_number", ws_set_number if ws_sheet_type == "Homework" else 1)

            ws_cache_key = f"{ws.get('id', 0)}_{ws_set_val}_{ws_sheet_type}_{ws.get('title', '')}"
            if st.session_state.get("latest_ws_cache_key") != ws_cache_key or "latest_ws_artifacts" not in st.session_state:
                with st.spinner("Compiling Practice Worksheet PDFs & Materials (one-time)..."):
                    _ws_pdf = pdf_generator.generate_worksheet_pdf(
                        title=ws.get("title", "Homework Worksheet"),
                        year_level=ws.get("year_level", year_level),
                        topic=ws_item_topic,
                        questions=ws.get("questions", []),
                        include_solutions=True,
                        term=ws.get("term"),
                        week=ws.get("week"),
                        sheet_type=ws_sheet_type,
                        set_number=ws_set_val
                    )
                    _ws_docx = pdf_generator.generate_worksheet_docx(
                        title=ws.get("title", "Homework Worksheet"),
                        year_level=ws.get("year_level", year_level),
                        topic=ws_item_topic,
                        questions=ws.get("questions", []),
                        include_solutions=True,
                        term=ws.get("term"),
                        week=ws.get("week"),
                        sheet_type=ws_sheet_type,
                        set_number=ws_set_val
                    )
                    _ws_s_ans = pdf_generator.generate_blank_answer_sheet_pdf(
                        question_labels=question_labels,
                        num_questions=len(question_labels),
                        term=ws.get("term"),
                        week=ws.get("week"),
                        items=ws_items
                    )
                    _ws_t_ans = pdf_generator.generate_teacher_answer_sheet_pdf(
                        question_labels=question_labels,
                        answers=ws_answers,
                        num_questions=len(question_labels),
                        term=ws.get("term"),
                        week=ws.get("week"),
                        items=ws_items
                    )
                    st.session_state["latest_ws_cache_key"] = ws_cache_key
                    st.session_state["latest_ws_artifacts"] = {
                        "pdf": _ws_pdf,
                        "docx": _ws_docx,
                        "s_ans_pdf": _ws_s_ans,
                        "t_ans_pdf": _ws_t_ans,
                        "expanded_key": ws_expanded_key,
                    }

            _cached_ws = st.session_state["latest_ws_artifacts"]
            worksheet_pdf_bytes = _cached_ws["pdf"]
            worksheet_docx_bytes = _cached_ws["docx"]
            student_ans_pdf_bytes = _cached_ws["s_ans_pdf"]
            teacher_ans_pdf_bytes = _cached_ws["t_ans_pdf"]

            p_col1, p_col2 = st.columns(2)
            with p_col1:
                ws_dl_name = ai_engine.get_worksheet_download_filename(
                    topic=ws_item_topic,
                    sheet_type=ws_sheet_type,
                    set_number=ws_set_val,
                    extension="pdf"
                )
                st.download_button(
                    "📥 Download Exam Worksheet (PDF)",
                    data=worksheet_pdf_bytes,
                    file_name=ws_dl_name,
                    mime="application/pdf",
                    use_container_width=True
                )
                if worksheet_docx_bytes:
                    ws_docx_name = ai_engine.get_worksheet_download_filename(
                        topic=ws_item_topic,
                        sheet_type=ws_sheet_type,
                        set_number=ws_set_val,
                        extension="docx"
                    )
                    st.download_button(
                        "📄 Download Word Doc (.docx)",
                        data=worksheet_docx_bytes,
                        file_name=ws_docx_name,
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        use_container_width=True
                    )
            with p_col2:
                student_ans_name = ai_engine.get_worksheet_download_filename(
                    topic=ws_item_topic,
                    sheet_type=ws_sheet_type,
                    set_number=ws_set_val,
                    suffix="Ans Sheet Student",
                    extension="pdf"
                )
                st.download_button(
                    "📥 Download Student Answer Sheet (PDF)",
                    data=student_ans_pdf_bytes,
                    file_name=student_ans_name,
                    mime="application/pdf",
                    use_container_width=True
                )
                teacher_ans_name = ai_engine.get_worksheet_download_filename(
                    topic=ws_item_topic,
                    sheet_type=ws_sheet_type,
                    set_number=ws_set_val,
                    suffix="Ans Sheet Teacher",
                    extension="pdf"
                )
                st.download_button(
                    "🔑 Download Teacher Answer Sheet (PDF)",
                    data=teacher_ans_pdf_bytes,
                    file_name=teacher_ans_name,
                    mime="application/pdf",
                    use_container_width=True
                )
            col_ws_mark, col_ws_save = st.columns([1, 1])
            with col_ws_mark:
                if st.button("⚡ Mark Student Submissions in Tab 2", key=f"btn_mark_now_ws_{ws.get('id', 0)}", type="primary", use_container_width=True):
                    st.session_state["preselected_marking_ws_id"] = ws.get("id")
                    st.session_state["active_tab_hint"] = "marking"
                    st.info(f"✅ Pre-selected **{ws.get('title', 'Worksheet')}**! Please click **Tab 2 (1-Click AI Homework Marking)** above to grade student submissions.")

            with col_ws_save:
                if cloud_sync.is_cloud_connected():
                    if st.button("☁️ Save Worksheet to DA Cloud Library", key=f"btn_cloud_save_ws_{ws.get('id', 0)}", use_container_width=True):
                        with st.spinner("Saving to DA Cloud Library (Supabase)..."):
                            ok, msg = cloud_sync.save_exam_to_cloud(
                                subject=f"{ws.get('year_level', '')} Maths",
                                year_level=ws.get('year_level', ''),
                                topic=ws_item_topic,
                                teacher_name=current_user.get("display_name", "DA Tutor"),
                                pdf_bytes=worksheet_pdf_bytes,
                                docx_bytes=worksheet_docx_bytes,
                                difficulty=ws.get("difficulty", "Medium"),
                                num_questions=len(ws.get("questions", [])),
                                set_number=ws_set_val,
                                extra_instructions=ws.get("custom_instructions") or custom_notes or "",
                                cost=ws.get("meta_cost", 0.0),
                                model=ws.get("model_used", "gemini-3.8-flash")
                            )
                            if ok:
                                st.success(msg)
                            else:
                                st.error(msg)

            st.markdown("---")
            st.markdown("#### 👁️ PDF Preview")
            st.caption("Pixel-perfect representation of the compiled PDF ready for high-resolution printing.")

            def _render_raw_ws_content():
                for q in ws.get("questions", []):
                    item_lbl = q.get('item_label', q.get('num', ''))
                    marks_val = int(q.get('marks', 1))
                    m_label = f"{marks_val} mark{'s' if marks_val > 1 else ''}"
                    diff_badge = f"{q.get('difficulty')} • " if q.get('difficulty') else ""
                    st.markdown(f"**Question {item_lbl}:** {q.get('text')} &nbsp;&nbsp;`[{diff_badge}{m_label}]` *(Subtopic: {q.get('subtopic', '-')})*")
                    st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;**Answer:** {q.get('correct_answer')}")
                    if q.get('solution_steps'):
                        st.caption(f"&nbsp;&nbsp;&nbsp;&nbsp;*Working:* {q.get('solution_steps')}")
                    st.markdown("---")

            ws_editions = {
                "Exam Worksheet (Student Edition)": worksheet_pdf_bytes,
                "Student Blank Answer Sheet": student_ans_pdf_bytes,
                "Teacher Master Answer Sheet": teacher_ans_pdf_bytes,
            }
            render_authentic_pdf_preview(
                pdf_bytes=worksheet_pdf_bytes,
                key_prefix="latest_ws",
                available_editions=ws_editions,
                default_edition="Exam Worksheet (Student Edition)",
                raw_content_callback=_render_raw_ws_content,
                raw_content_title="📝 View Raw Questions, Solutions & Marking Key"
            )

    # Sub-tab: Generate Review Booklet (Revision & Exam Prep)
    with sub_tab_review:
        st.markdown("### 🔄 Generate Topic Review & Exam Revision Booklet (Teacher & Student Editions)")
        st.caption("Specifically designed for students revising topics previously taught, preparing for yearly/term examinations, or consolidating mastery. Features high-yield concept summaries, vital formula lists, tutor secrets & exam shortcuts, common pitfall traps, worked exam-style mastery examples, and revision practice questions.")

        col_rev_yl, col_rev_tb = st.columns([1.2, 1.8])
        with col_rev_yl:
            default_rev_yl_index = YEAR_LEVEL_OPTIONS.index("Year 10") if "Year 10" in YEAR_LEVEL_OPTIONS else 5
            rev_year_level = st.selectbox(
                "Select Year Level / Stage:",
                YEAR_LEVEL_OPTIONS,
                index=default_rev_yl_index,
                key="rev_year_level_select"
            )

        with col_rev_tb:
            available_rev_textbooks = ai_engine.get_textbooks_for_year(rev_year_level)
            default_rev_tb_idx = 0
            rev_textbook = st.selectbox(
                "Curriculum Series / Textbook Reference:",
                available_rev_textbooks,
                index=default_rev_tb_idx,
                key=f"rev_textbook_select_{rev_year_level}"
            )

        if ai_engine.is_year_11_advanced(rev_year_level):
            st.info("🔒 **Strict NSW Stage 6 Syllabus Boundary Enforced**: Pure Year 11 Mathematics Advanced & Stage 5.3 prerequisites only. Zero Year 12 calculus (no integration, product/quotient/chain rules), zero Extension 1 (no vectors, induction, combinatorics, polynomials division), and zero tertiary content.")

        try:
            rev_topics = ai_engine.get_topics_for_year(rev_year_level, textbook=rev_textbook)
        except Exception:
            rev_topics = []

        rev_custom_topics_key = f"rev_custom_topics_{rev_textbook}_{rev_year_level}"
        if rev_custom_topics_key not in st.session_state:
            st.session_state[rev_custom_topics_key] = []
        rev_all_topic_options = (rev_topics or []) + [t for t in st.session_state[rev_custom_topics_key] if t not in (rev_topics or [])]

        col_rtop_sel, col_rtop_custom = st.columns([3.2, 1.2])
        with col_rtop_sel:
            rev_selected_topics = st.multiselect(
                f"Select Revision Topic(s) / Chapter(s) ({rev_textbook}) — choose 1 or more:",
                rev_all_topic_options,
                default=[rev_all_topic_options[0]] if rev_all_topic_options else [],
                key=f"rev_topics_multi_{rev_year_level}_{rev_textbook}",
                help="Select one or more topics to consolidate into an exam revision booklet."
            )
        with col_rtop_custom:
            st.write("")
            with st.popover("➕ Add Topic"):
                new_rev_top_val = st.text_input("New Topic Name", placeholder="e.g. Vectors & Matrices", key=f"txt_new_rev_topic_{rev_textbook}_{rev_year_level}")
                if st.button("Add Topic", key=f"btn_add_rev_top_{rev_textbook}_{rev_year_level}") and new_rev_top_val.strip():
                    trimmed_rev_top = new_rev_top_val.strip()
                    if trimmed_rev_top not in st.session_state[rev_custom_topics_key]:
                        st.session_state[rev_custom_topics_key].append(trimmed_rev_top)
                        st.rerun()

        rev_combined_default = ai_engine.format_combined_topics(rev_selected_topics) if rev_selected_topics else "General Revision"
        rev_topic = st.text_input(
            "Booklet Topic Title (appears on cover page & headers):",
            value=rev_combined_default,
            key=f"rev_title_input_{rev_textbook}_{rev_year_level}_{'_'.join([str(t)[:8] for t in rev_selected_topics]) if rev_selected_topics else 'none'}",
            help="Custom title displayed on the front cover and headers of the generated revision booklet."
        )

        # Aggregate revision subtopics across all selected topics
        rev_all_subtopics = []
        is_multi_rev = len(rev_selected_topics) > 1
        for top_item in rev_selected_topics:
            try:
                subs = ai_engine.get_curriculum_subtopics(rev_year_level, top_item, textbook=rev_textbook)
            except Exception:
                subs = []
            if not subs:
                subs = [f"{top_item} Core Principles", f"{top_item} Exam Techniques"]

            if is_multi_rev:
                top_tag = ai_engine.clean_topic_title(top_item)
                for s in subs:
                    tagged_s = f"[{top_tag}] {s}"
                    if tagged_s not in rev_all_subtopics:
                        rev_all_subtopics.append(tagged_s)
            else:
                for s in subs:
                    if s not in rev_all_subtopics:
                        rev_all_subtopics.append(s)

        rev_subtopics_cache_key = f"rev_subs_{rev_textbook}_{rev_year_level}_{hash(tuple(rev_selected_topics))}"
        if rev_subtopics_cache_key not in st.session_state:
            st.session_state[rev_subtopics_cache_key] = list(rev_all_subtopics)

        rev_active_subtopics = st.session_state[rev_subtopics_cache_key]

        col_rev_act_a, col_rev_act_b = st.columns([1, 1])
        with col_rev_act_a:
            if st.button("🤖 AI Suggest More Subtopics", key=f"btn_ai_rev_subs_{rev_subtopics_cache_key}"):
                cur_key = st.session_state.get("gemini_api_key", "")
                with st.spinner(f"Fetching {rev_textbook} subtopics with AI..."):
                    ai_subs = ai_engine.suggest_subtopics_ai(rev_year_level, rev_topic, cur_key, textbook=rev_textbook)
                    for s in ai_subs:
                        if s not in rev_active_subtopics:
                            rev_active_subtopics.append(s)
                    st.session_state[rev_subtopics_cache_key] = rev_active_subtopics
                    st.rerun()

        with col_rev_act_b:
            with st.popover("➕ Add Custom Concept / Subtopic"):
                new_sub_name = st.text_input("Concept Title", placeholder="e.g. Exam Curve Sketching Pitfalls", key=f"txt_rev_new_sub_{rev_subtopics_cache_key}")
                if st.button("Add to List", key=f"btn_add_rev_{rev_subtopics_cache_key}") and new_sub_name.strip():
                    if new_sub_name.strip() not in rev_active_subtopics:
                        rev_active_subtopics.append(new_sub_name.strip())
                        st.session_state[rev_subtopics_cache_key] = rev_active_subtopics
                        st.rerun()

        rev_selected_subtopics = st.multiselect(
            "Select Specific Concepts / Subtopics to Review:",
            rev_active_subtopics,
            default=rev_active_subtopics,
            help="Choose the subtopics to synthesize into this revision booklet.",
            key=f"rev_subtopics_select_{rev_subtopics_cache_key}"
        )

        rev_examples_per_concept = st.slider(
            "Mastery Demonstration Examples per Concept:",
            min_value=1,
            max_value=5,
            value=2,
            help="Model exam-standard examples solved with full whiteboard steps and exam commentary (up to 5 per concept).",
            key="rev_num_examples"
        )

        st.markdown("##### 🎯 Revision Question Counts per Level")
        st.caption("Configure question counts for each difficulty level:")
        col_t1, col_t2, col_t3, col_t4, col_t5 = st.columns(5)
        with col_t1:
            rev_q_l1 = st.number_input("Level 1 - Commit to Memory", min_value=0, max_value=20, value=2, step=1, key="rev_q_l1")
        with col_t2:
            rev_q_l2 = st.number_input("Level 2 - Further Practice", min_value=0, max_value=20, value=2, step=1, key="rev_q_l2")
        with col_t3:
            rev_q_l3 = st.number_input("Level 3 - Application", min_value=0, max_value=20, value=1, step=1, key="rev_q_l3")
        with col_t4:
            rev_q_l4 = st.number_input("Level 4 - Thinking Creatively", min_value=0, max_value=20, value=1, step=1, key="rev_q_l4")
        with col_t5:
            rev_q_exam = st.number_input("Level 5 - Exam Questions", min_value=0, max_value=20, value=1, step=1, key="rev_q_exam")

        rev_level_distribution = {
            "Level 1 - Commit to Memory": int(rev_q_l1),
            "Level 2 - Further Practice": int(rev_q_l2),
            "Level 3 - Application": int(rev_q_l3),
            "Level 4 - Thinking Creatively": int(rev_q_l4),
            "Level 5 - Exam Questions": int(rev_q_exam),
        }
        rev_total_practice_default = sum(rev_level_distribution.values())
        if rev_total_practice_default == 0:
            rev_total_practice_default = 1
            rev_level_distribution["Level 1 - Commit to Memory"] = 1

        rev_custom_distribution = {}
        with st.expander("⚙️ Customize Question Counts Per Subtopic (Optional)", expanded=False):
            st.caption("Override question counts for specific individual concepts:")
            for idx, sub in enumerate(rev_selected_subtopics):
                sub_safe_key = f"rev_sub_dist_{hash(sub)}_{idx}"
                sub_override = st.checkbox(f"Custom counts for **{sub}**", value=False, key=f"chk_{sub_safe_key}")
                if sub_override:
                    sc1, sc2, sc3, sc4, sc5 = st.columns(5)
                    with sc1:
                        sq1 = st.number_input("L1 - Commit to Memory", min_value=0, max_value=20, value=int(rev_q_l1), key=f"sq1_{sub_safe_key}")
                    with sc2:
                        sq2 = st.number_input("L2 - Further Practice", min_value=0, max_value=20, value=int(rev_q_l2), key=f"sq2_{sub_safe_key}")
                    with sc3:
                        sq3 = st.number_input("L3 - Application", min_value=0, max_value=20, value=int(rev_q_l3), key=f"sq3_{sub_safe_key}")
                    with sc4:
                        sq4 = st.number_input("L4 - Thinking Creatively", min_value=0, max_value=20, value=int(rev_q_l4), key=f"sq4_{sub_safe_key}")
                    with sc5:
                        sqe = st.number_input("L5 - Exam Questions", min_value=0, max_value=20, value=int(rev_q_exam), key=f"sqe_{sub_safe_key}")
                    rev_custom_distribution[sub] = {
                        "Level 1 - Commit to Memory": int(sq1),
                        "Level 2 - Further Practice": int(sq2),
                        "Level 3 - Application": int(sq3),
                        "Level 4 - Thinking Creatively": int(sq4),
                        "Level 5 - Exam Questions": int(sqe)
                    }
                else:
                    rev_custom_distribution[sub] = dict(rev_level_distribution)

        rev_total_q_sum = sum(sum(t.values()) for t in rev_custom_distribution.values()) if rev_custom_distribution else (len(rev_selected_subtopics) * rev_total_practice_default)
        st.info(f"📊 **Selected Concepts:** **{len(rev_selected_subtopics)} concepts** | Total: {len(rev_selected_subtopics) * int(rev_examples_per_concept)} model examples & {rev_total_q_sum} revision questions")

        col_rev_tw_check, col_rev_tw_inputs = st.columns([1.2, 2.8])
        with col_rev_tw_check:
            rev_use_term_week = st.checkbox("Assign to specific Term & Week?", value=False, key="rev_specify_term_week")
        with col_rev_tw_inputs:
            if rev_use_term_week:
                col_rt, col_rw = st.columns(2)
                with col_rt:
                    rev_term = st.number_input("Term:", min_value=1, max_value=4, value=1, key="rev_term_num")
                with col_rw:
                    rev_week = st.number_input("Week:", min_value=1, max_value=10, value=5, key="rev_week_num")
            else:
                rev_term = None
                rev_week = None
                st.caption("📅 *Independent Revision Resource (no Term/Week constraint)*")

        rev_custom_instructions = st.text_area(
            "Special Revision Instructions / Exam Focus (Optional):",
            placeholder="e.g. Focus heavily on exam pitfalls with algebraic fractions and negative brackets, include tips for graphing without a table of values...",
            key="rev_custom_instructions",
            height=70
        )

        col_gen_rev, _ = st.columns([1.5, 2.5])
        with col_gen_rev:
            generate_rev_clicked = st.button(
                "🚀 Generate Topic Review Booklet (Teacher, Student & Class Editions)",
                type="primary",
                use_container_width=True,
                key="btn_generate_review_booklet"
            )

        if generate_rev_clicked:
            active_tutor_api_key = (st.session_state.get("gemini_api_key") or "").strip()
            if not active_tutor_api_key:
                st.error("⚠️ Gemini API Key Required: Please enter your personal Google Gemini API key in the left sidebar under '🔑 Personal Gemini API Key' (Get a free key in 30s at https://aistudio.google.com/app/apikey).")
            elif not rev_selected_topics:
                st.warning("Please select at least one topic/chapter to review.")
            elif not rev_selected_subtopics:
                st.warning("Please select at least one concept/subtopic to review.")
            else:
                with st.spinner("🧠 Synthesizing Comprehensive Topic Review Booklet with Gemini AI..."):
                    try:
                        rev_data = ai_engine.generate_review_booklet(
                            year_level=rev_year_level,
                            topic=rev_topic,
                            subtopics=rev_selected_subtopics,
                            examples_per_concept=int(rev_examples_per_concept),
                            practice_per_concept=int(rev_total_practice_default),
                            term=int(rev_term) if rev_term is not None else None,
                            week=int(rev_week) if rev_week is not None else None,
                            custom_instructions=rev_custom_instructions,
                            api_key=active_tutor_api_key,
                            textbook=rev_textbook,
                            question_distribution=rev_custom_distribution,
                            level_distribution=rev_level_distribution
                        )
                        rev_data["textbook"] = rev_textbook
                        rev_booklet_id = int(time.time())
                        rev_data["id"] = rev_booklet_id
                        st.session_state["latest_review_booklet"] = rev_data
                        st.session_state["latest_review_booklet_id"] = rev_booklet_id
                        rb_cost = rev_data.get('meta_cost', 0.0)
                        rb_tokens = rev_data.get('meta_tokens', 0)
                        st.success(f"🎉 Successfully created Topic Review Booklet: {rev_data.get('title')}! (💰 Cost: ${rb_cost:.4f} AUD • {rb_tokens:,} tokens)")
                    except Exception as e:
                        st.error(f"Error generating review booklet: {str(e)}")

        # Display latest generated review booklet
        if st.session_state.get("latest_review_booklet"):
            rb = st.session_state["latest_review_booklet"]
            st.markdown("---")
            st.markdown(f"### 📥 Download Generated Review Booklet: **{rb.get('title')}**")

            if rb.get("meta_cost") is not None or rb.get("meta_tokens"):
                st.info(f"💰 **Generation Cost:** **${rb.get('meta_cost', 0.0):.4f} AUD** • **{rb.get('meta_tokens', 0):,} tokens** ({rb.get('model_used', 'Gemini 3.8 Flash')})")

            rb_font_theme = "charter"

            rb_cache_key = f"{rb.get('id', 0)}_{rb.get('title', '')}_{rb_font_theme}"
            if st.session_state.get("latest_rb_cache_key") != rb_cache_key or "latest_rb_artifacts" not in st.session_state:
                with st.spinner("Compiling Review Booklet PDFs & Materials (one-time)..."):
                    _t_pdf = pdf_generator.generate_review_booklet_pdf(
                        booklet_data=rb, mode="teacher", term=rb.get("term"), week=rb.get("week"), font_theme=rb_font_theme
                    )
                    _s_pdf = pdf_generator.generate_review_booklet_pdf(
                        booklet_data=rb, mode="student", term=rb.get("term"), week=rb.get("week"), font_theme=rb_font_theme
                    )
                    _sc_pdf = pdf_generator.generate_review_booklet_pdf(
                        booklet_data=rb, mode="student_class", term=rb.get("term"), week=rb.get("week"), font_theme=rb_font_theme
                    )
                    _t_docx = pdf_generator.generate_review_booklet_docx(
                        booklet_data=rb, mode="teacher", term=rb.get("term"), week=rb.get("week")
                    )
                    _s_docx = pdf_generator.generate_review_booklet_docx(
                        booklet_data=rb, mode="student", term=rb.get("term"), week=rb.get("week")
                    )
                    _sc_docx = pdf_generator.generate_review_booklet_docx(
                        booklet_data=rb, mode="student_class", term=rb.get("term"), week=rb.get("week")
                    )
                    
                    _rev_labels, _rev_answers, _rev_key = pdf_generator.extract_review_booklet_answer_sheet_data(rb)
                    _s_ans_pdf = None
                    _t_ans_pdf = None
                    if _rev_labels:
                        _s_ans_pdf = pdf_generator.generate_prefilled_answer_sheet_pdf(
                            topic=rb.get("topic", "Topic Review"),
                            sheet_type="Review",
                            year_level=rb.get("year_level", ""),
                            questions_data=_rev_labels if isinstance(_rev_labels[0], dict) else [{"item_label": str(lbl), "text": ""} for lbl in _rev_labels],
                            include_answers=False
                        ) if hasattr(pdf_generator, "generate_prefilled_answer_sheet_pdf") else pdf_generator.generate_blank_answer_sheet_pdf(
                            question_labels=_rev_labels, num_questions=len(_rev_labels), term=rb.get("term"), week=rb.get("week")
                        )
                        _t_ans_pdf = pdf_generator.generate_teacher_answer_sheet_pdf(
                            question_labels=_rev_labels, answers=_rev_answers, num_questions=len(_rev_labels), term=rb.get("term"), week=rb.get("week")
                        )

                    st.session_state["latest_rb_cache_key"] = rb_cache_key
                    st.session_state["latest_rb_artifacts"] = {
                        "t_pdf": _t_pdf,
                        "s_pdf": _s_pdf,
                        "sc_pdf": _sc_pdf,
                        "t_docx": _t_docx,
                        "s_docx": _s_docx,
                        "sc_docx": _sc_docx,
                        "rev_labels": _rev_labels,
                        "rev_answers": _rev_answers,
                        "rev_key": _rev_key,
                        "s_ans_pdf": _s_ans_pdf,
                        "t_ans_pdf": _t_ans_pdf
                    }

            _cached_rb = st.session_state["latest_rb_artifacts"]
            teacher_rev_pdf_bytes = _cached_rb["t_pdf"]
            student_rev_pdf_bytes = _cached_rb["s_pdf"]
            student_class_rev_pdf_bytes = _cached_rb["sc_pdf"]
            teacher_rev_docx_bytes = _cached_rb["t_docx"]
            student_rev_docx_bytes = _cached_rb["s_docx"]
            student_class_rev_docx_bytes = _cached_rb["sc_docx"]
            rev_labels = _cached_rb["rev_labels"]
            rev_answers = _cached_rb["rev_answers"]
            rev_key = _cached_rb["rev_key"]
            student_ans_pdf_bytes = _cached_rb["s_ans_pdf"]
            teacher_ans_pdf_bytes = _cached_rb["t_ans_pdf"]

            p_rev_col1, p_rev_col2, p_rev_col3 = st.columns(3)
            with p_rev_col1:
                teacher_rev_dl_name = get_review_booklet_download_filename(rb, mode="teacher")
                st.download_button(
                    "📥 Teacher Master Review (PDF)",
                    data=teacher_rev_pdf_bytes,
                    file_name=teacher_rev_dl_name,
                    mime="application/pdf",
                    key="dl_latest_teacher_review_pdf",
                    use_container_width=True
                )
                if teacher_rev_docx_bytes:
                    teacher_rev_docx_name = get_review_booklet_download_filename(rb, mode="teacher", extension="docx")
                    st.download_button(
                        "📄 Teacher Master (Word .docx)",
                        data=teacher_rev_docx_bytes,
                        file_name=teacher_rev_docx_name,
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        key="dl_latest_teacher_review_docx",
                        use_container_width=True
                    )
                st.caption("✅ Includes high-yield revision notes, tutor tips & exam shortcuts, worked mastery examples with teacher commentary, and tiered revision questions with step-by-step solutions.")

            with p_rev_col2:
                student_rev_dl_name = get_review_booklet_download_filename(rb, mode="student")
                st.download_button(
                    "📥 Student with space Review (PDF)",
                    data=student_rev_pdf_bytes,
                    file_name=student_rev_dl_name,
                    mime="application/pdf",
                    key="dl_latest_student_review_pdf",
                    use_container_width=True
                )
                if student_rev_docx_bytes:
                    student_rev_docx_name = get_review_booklet_download_filename(rb, mode="student", extension="docx")
                    st.download_button(
                        "📄 Student with space Review (Word .docx)",
                        data=student_rev_docx_bytes,
                        file_name=student_rev_docx_name,
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        key="dl_latest_student_review_docx",
                        use_container_width=True
                    )
                st.caption("✅ Includes pre-printed revision summaries, tips & tricks boxes, model demonstrations, clean boxed workspace for revision practice, plus quick answers at the back.")

            with p_rev_col3:
                student_class_rev_dl_name = get_review_booklet_download_filename(rb, mode="student_class")
                st.download_button(
                    "📥 Student no space Review (PDF)",
                    data=student_class_rev_pdf_bytes,
                    file_name=student_class_rev_dl_name,
                    mime="application/pdf",
                    key="dl_latest_student_class_review_pdf",
                    use_container_width=True
                )
                if student_class_rev_docx_bytes:
                    student_class_rev_docx_name = get_review_booklet_download_filename(rb, mode="student_class", extension="docx")
                    st.download_button(
                        "📄 Student no space Review (.docx)",
                        data=student_class_rev_docx_bytes,
                        file_name=student_class_rev_docx_name,
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        key="dl_latest_student_class_review_docx",
                        use_container_width=True
                    )
                st.caption("🌿 **Paper-Saving Edition**: Zero working space boxes; students write working in their own exercise book. Includes quick answers at the back.")

            # Answer sheets and marking key for Review Booklet
            if rev_labels:
                st.markdown("---")
                st.markdown("##### 📝 Review Answer Sheets & Auto-Marking Key")
                col_ras1, col_ras2, col_ras3 = st.columns(3)
                with col_ras1:
                    student_ans_dl_name = get_review_booklet_download_filename(rb, mode="student_answer_sheet", extension="pdf")
                    st.download_button(
                        "📥 Student Answer Sheet (PDF)",
                        data=student_ans_pdf_bytes,
                        file_name=student_ans_dl_name,
                        mime="application/pdf",
                        key="dl_latest_review_student_answer_sheet_pdf",
                        use_container_width=True
                    )
                    st.caption("Prefilled question numbering on standard answer sheet template.")
                with col_ras2:
                    teacher_ans_dl_name = get_review_booklet_download_filename(rb, mode="teacher_answer_sheet", extension="pdf")
                    st.download_button(
                        "🔑 Teacher Answer Sheet (PDF)",
                        data=teacher_ans_pdf_bytes,
                        file_name=teacher_ans_dl_name,
                        mime="application/pdf",
                        key="dl_latest_review_teacher_answer_sheet_pdf",
                        use_container_width=True
                    )
                    st.caption("Master sample answers prefilled for grading & checking.")
                with col_ras3:
                    final_rev_key = rb.get("marking_key") or rev_key
                    rev_key_json_str = json.dumps(final_rev_key, indent=2)
                    rev_key_dl_name = get_review_booklet_download_filename(rb, mode="marking_key", extension="json")
                    st.download_button(
                        "📊 Export Marking Key (JSON)",
                        data=rev_key_json_str,
                        file_name=rev_key_dl_name,
                        mime="application/json",
                        key="dl_latest_review_marking_key_json",
                        use_container_width=True
                    )
                    st.caption("JSON marking key compatible with homework/test grading engine.")

            if cloud_sync.is_cloud_connected():
                if st.button("☁️ Save Review Booklet to DA Cloud Library", key=f"btn_cloud_save_rb_{rb.get('id', 0)}", use_container_width=True):
                    with st.spinner("Saving to DA Cloud Library (Supabase)..."):
                        ok, msg = cloud_sync.save_exam_to_cloud(
                            subject=f"{rb.get('year_level', '')} Maths",
                            year_level=rb.get('year_level', ''),
                            topic=f"{rb.get('topic', '')} Review",
                            teacher_name=current_user.get("display_name", "DA Tutor"),
                            pdf_bytes=teacher_rev_pdf_bytes,
                            docx_bytes=teacher_rev_docx_bytes,
                            difficulty="Revision",
                            num_questions=len(rb.get("concepts", [])),
                            extra_instructions=rb.get("custom_instructions") or rev_custom_instructions or "",
                            cost=rb.get("meta_cost", 0.0),
                            model=rb.get("model_used", "gemini-3.8-flash")
                        )
                        if ok:
                            st.success(msg)
                        else:
                            st.error(msg)

            st.markdown("---")
            st.markdown("#### 👁️ PDF Preview")
            st.caption("Pixel-perfect representation of the compiled PDF ready for high-resolution printing.")

            def _render_raw_rb_content():
                for c_idx, c in enumerate(rb.get("concepts", []), 1):
                    c_title = c.get("name") or c.get("concept_name", f"Concept {c_idx}")
                    st.markdown(f"### Review Part {c_idx}: {c_title}")
                    rev_sum = c.get("revision_summary") or c.get("theory_content", "")
                    if rev_sum:
                        st.markdown(f"**High-Yield Summary:**\n\n{rev_sum}")
                    if c.get("key_formulas"):
                        st.markdown("**Essential Exam Formulas:**")
                        for f in c.get("key_formulas"):
                            st.markdown(f"- {f}")
                    tips = c.get("tips_and_tricks") or c.get("tutor_tips", "")
                    if tips:
                        st.info(f"💡 **Tutor Secrets & Exam Shortcuts:** {tips}")
                    if c.get("common_pitfalls"):
                        st.warning("**⚠️ Common Examination Traps:**\n" + "\n".join([f"- {p}" for p in c.get("common_pitfalls")]))

                    mastery_ex = c.get("mastery_examples") or c.get("teacher_examples", [])
                    if mastery_ex:
                        st.markdown("#### 👨‍🏫 Exam Mastery Demonstrations:")
                        for e_idx, ex in enumerate(mastery_ex, 1):
                            st.markdown(f"**Mastery Example {c_idx}.{e_idx}:** {ex.get('problem_text')}")
                            with st.expander(f"Show Solution for Mastery Example {c_idx}.{e_idx}", expanded=False):
                                st.markdown(f"**Worked Solution:**\n\n{ex.get('worked_solution')}")
                                comm = ex.get("exam_commentary") or ex.get("teaching_notes", "")
                                if comm:
                                    st.caption(f"Tutor Commentary: {comm}")

                    rev_q = c.get("review_questions") or c.get("practice_questions", [])
                    if rev_q:
                        st.markdown("#### ✍️ Revision Practice Questions:")
                        for p_idx, pq in enumerate(rev_q, 1):
                            diff_badge = f"{pq.get('difficulty', 'Standard')} • " if pq.get('difficulty') else ""
                            m_count = pq.get('marks', 2)
                            st.markdown(f"**Revision Q{c_idx}.{p_idx}:** {pq.get('text', '')} &nbsp;&nbsp;`[{diff_badge}{m_count} mark{'s' if m_count > 1 else ''}]`")
                            with st.expander(f"Show Solution for Revision Q{c_idx}.{p_idx}", expanded=False):
                                st.markdown(f"**Solution:**\n\n{pq.get('worked_solution', '')}")
                                if pq.get('final_answer'):
                                    st.markdown(f"**Final Answer:** {pq.get('final_answer')}")
                    st.markdown("---")

            rb_editions = {
                "Student with space (Default)": student_rev_pdf_bytes,
                "Student no space (Paper-Saving)": student_class_rev_pdf_bytes,
                "Teacher Master (With Solutions)": teacher_rev_pdf_bytes,
            }
            render_authentic_pdf_preview(
                pdf_bytes=student_rev_pdf_bytes,
                key_prefix="latest_rb",
                available_editions=rb_editions,
                default_edition="Student with space (Default)",
                raw_content_callback=_render_raw_rb_content,
                raw_content_title="📝 View Raw Questions, Solutions & Revision Notes"
            )

    # =========================================================================
    # SUB-TAB 4: COMPLETE EXAM REVISION & PRACTICE PACKAGE (DUAL BOOKLETS)
    # =========================================================================
    with sub_tab_package:
        st.markdown("### 📦 Generate Complete Exam Revision & Practice Package (Dual Booklets)")
        st.caption("Elite HSC Senior Marker Exam Preparation Suite. Generates two dedicated, publication-quality booklets: **Booklet 1 (Theory, Study Notes & Worked Past Papers)** with rapid visual cheat-sheet notes, glowing Neon UI exam hacks, coloured speech-bubble pitfall traps, and worked past paper demonstrations with official marking guidelines; and **Booklet 2 (Exam Practice & Past Papers)** available in clean **Student Edition** (spacious, unclustered working space boxes) and **Complete Solutions & Marking Guidelines Edition**.")

        col_pkg_yl, col_pkg_tb = st.columns([1.2, 1.8])
        with col_pkg_yl:
            default_pkg_yl_index = YEAR_LEVEL_OPTIONS.index("Year 12 (Extension 1)") if "Year 12 (Extension 1)" in YEAR_LEVEL_OPTIONS else 8
            pkg_year_level = st.selectbox(
                "Select Year Level / Stage:",
                YEAR_LEVEL_OPTIONS,
                index=default_pkg_yl_index,
                key="pkg_year_level_select"
            )

        with col_pkg_tb:
            available_pkg_textbooks = ai_engine.get_textbooks_for_year(pkg_year_level)
            default_pkg_tb_idx = 0
            pkg_textbook = st.selectbox(
                "Curriculum Series / Textbook Reference:",
                available_pkg_textbooks,
                index=default_pkg_tb_idx,
                key=f"pkg_textbook_select_{pkg_year_level}"
            )

        if ai_engine.is_year_11_advanced(pkg_year_level):
            st.info("🔒 **Strict NSW Stage 6 Syllabus Boundary Enforced**: Pure Year 11 Mathematics Advanced & Stage 5.3 prerequisites only. Zero Year 12 calculus (no integration, product/quotient/chain rules), zero Extension 1 (no vectors, induction, combinatorics, polynomials division), and zero tertiary content.")

        try:
            pkg_topics = ai_engine.get_topics_for_year(pkg_year_level, textbook=pkg_textbook)
        except Exception:
            pkg_topics = []

        pkg_custom_topics_key = f"pkg_custom_topics_{pkg_textbook}_{pkg_year_level}"
        if pkg_custom_topics_key not in st.session_state:
            st.session_state[pkg_custom_topics_key] = []
        pkg_all_topic_options = (pkg_topics or []) + [t for t in st.session_state[pkg_custom_topics_key] if t not in (pkg_topics or [])]

        col_ptop_sel, col_ptop_custom = st.columns([3.2, 1.2])
        with col_ptop_sel:
            pkg_selected_topics = st.multiselect(
                f"Select Exam Topic(s) / Chapter(s) ({pkg_textbook}) — choose 1 or more:",
                pkg_all_topic_options,
                default=[pkg_all_topic_options[0]] if pkg_all_topic_options else [],
                key=f"pkg_topics_multi_{pkg_year_level}_{pkg_textbook}",
                help="Select one or more topics to compile into this comprehensive exam revision and practice package."
            )
        with col_ptop_custom:
            st.write("")
            with st.popover("➕ Add Topic"):
                new_pkg_top_val = st.text_input("New Topic Name", placeholder="e.g. Further Vectors & Projectiles", key=f"txt_new_pkg_topic_{pkg_textbook}_{pkg_year_level}")
                if st.button("Add Topic", key=f"btn_add_pkg_top_{pkg_textbook}_{pkg_year_level}") and new_pkg_top_val.strip():
                    trimmed_pkg_top = new_pkg_top_val.strip()
                    if trimmed_pkg_top not in st.session_state[pkg_custom_topics_key]:
                        st.session_state[pkg_custom_topics_key].append(trimmed_pkg_top)
                        st.rerun()

        pkg_combined_default = ai_engine.format_combined_topics(pkg_selected_topics) if pkg_selected_topics else "Exam Package"
        pkg_topic = st.text_input(
            "Package Topic Title (appears on cover page & headers):",
            value=pkg_combined_default,
            key=f"pkg_title_input_{pkg_textbook}_{pkg_year_level}_{'_'.join([str(t)[:8] for t in pkg_selected_topics]) if pkg_selected_topics else 'none'}",
            help="Custom title displayed on the front covers and headers of the generated exam package booklets."
        )

        # Aggregate subtopics across all selected topics
        pkg_all_subtopics = []
        is_multi_pkg = len(pkg_selected_topics) > 1
        for top_item in pkg_selected_topics:
            try:
                subs = ai_engine.get_curriculum_subtopics(pkg_year_level, top_item, textbook=pkg_textbook)
            except Exception:
                subs = []
            if not subs:
                subs = [f"{top_item} Core Principles", f"{top_item} Past Paper Mastery"]

            if is_multi_pkg:
                top_tag = ai_engine.clean_topic_title(top_item)
                for s in subs:
                    tagged_s = f"[{top_tag}] {s}"
                    if tagged_s not in pkg_all_subtopics:
                        pkg_all_subtopics.append(tagged_s)
            else:
                for s in subs:
                    if s not in pkg_all_subtopics:
                        pkg_all_subtopics.append(s)

        pkg_subtopics_cache_key = f"pkg_subs_{pkg_textbook}_{pkg_year_level}_{hash(tuple(pkg_selected_topics))}"
        if pkg_subtopics_cache_key not in st.session_state:
            st.session_state[pkg_subtopics_cache_key] = list(pkg_all_subtopics)

        pkg_active_subtopics = st.session_state[pkg_subtopics_cache_key]

        col_pkg_act_a, col_pkg_act_b = st.columns([1, 1])
        with col_pkg_act_a:
            if st.button("🤖 AI Suggest More Subtopics", key=f"btn_ai_pkg_subs_{pkg_subtopics_cache_key}"):
                cur_key = st.session_state.get("gemini_api_key", "")
                with st.spinner(f"Fetching {pkg_textbook} subtopics with AI..."):
                    ai_subs = ai_engine.suggest_subtopics_ai(pkg_year_level, pkg_topic, cur_key, textbook=pkg_textbook)
                    for s in ai_subs:
                        if s not in pkg_active_subtopics:
                            pkg_active_subtopics.append(s)
                    st.session_state[pkg_subtopics_cache_key] = pkg_active_subtopics
                    st.rerun()

        with col_pkg_act_b:
            with st.popover("➕ Add Custom Concept / Subtopic"):
                new_sub_name = st.text_input("Concept Title", placeholder="e.g. Velocity Vector Projections", key=f"txt_pkg_new_sub_{pkg_subtopics_cache_key}")
                if st.button("Add to List", key=f"btn_add_pkg_{pkg_subtopics_cache_key}") and new_sub_name.strip():
                    if new_sub_name.strip() not in pkg_active_subtopics:
                        pkg_active_subtopics.append(new_sub_name.strip())
                        st.session_state[pkg_subtopics_cache_key] = pkg_active_subtopics
                        st.rerun()

        pkg_selected_subtopics = st.multiselect(
            "Select Concepts / Subtopics to Include in Package:",
            pkg_active_subtopics,
            default=pkg_active_subtopics,
            help="Choose the subtopics to synthesize into this complete exam revision and practice package.",
            key=f"pkg_subtopics_select_{pkg_subtopics_cache_key}"
        )

        col_ex_cnt, col_q_hdr = st.columns([1.5, 2.5])
        with col_ex_cnt:
            pkg_examples_per_concept = st.slider(
                "Worked Past Paper Examples per Concept:",
                min_value=1,
                max_value=5,
                value=2,
                help="Authentic past paper / trial exam model examples with line-by-line whiteboard working and official rubrics.",
                key="pkg_num_examples"
            )

        st.markdown("##### 🎯 Practice Exam Questions per Concept (Tier Distribution)")
        st.caption("Configure the distribution of exam practice questions across pedagogical sections:")
        col_pt1, col_pt2, col_pt3, col_pt4, col_pt5 = st.columns(5)
        with col_pt1:
            pkg_q_l1 = st.number_input("S1 - Commit to Memory", min_value=0, max_value=20, value=1, step=1, key="pkg_q_l1")
        with col_pt2:
            pkg_q_l2 = st.number_input("S2 - Further Practice", min_value=0, max_value=20, value=1, step=1, key="pkg_q_l2")
        with col_pt3:
            pkg_q_l3 = st.number_input("S3 - Application", min_value=0, max_value=20, value=1, step=1, key="pkg_q_l3")
        with col_pt4:
            pkg_q_l4 = st.number_input("S4 - Thinking Creatively", min_value=0, max_value=20, value=1, step=1, key="pkg_q_l4")
        with col_pt5:
            pkg_q_exam = st.number_input("S5 - Exam Questions", min_value=0, max_value=20, value=1, step=1, key="pkg_q_exam")

        pkg_level_distribution = {
            "Section 1 - Commit to Memory": int(pkg_q_l1),
            "Section 2 - Further Practice": int(pkg_q_l2),
            "Section 3 - Application": int(pkg_q_l3),
            "Section 4 - Thinking Creatively": int(pkg_q_l4),
            "Section 5 - Exam Questions": int(pkg_q_exam),
        }
        pkg_total_practice_default = sum(pkg_level_distribution.values())
        if pkg_total_practice_default == 0:
            pkg_total_practice_default = 1
            pkg_level_distribution["Section 1 - Commit to Memory"] = 1

        pkg_custom_distribution = {}
        with st.expander("⚙️ Customize Question Counts Per Subtopic (Different counts for easy vs harder concepts)", expanded=False):
            st.caption("Override question counts for specific individual concepts. For example, easier concepts can have fewer questions (e.g. 1-2 questions), while challenging concepts can have more (e.g. 4-5 questions). Subtopics left uncustomized will automatically inherit the baseline distribution above.")
            
            pkg_cust_all = st.checkbox("Enable custom counts for all subtopics", value=False, key=f"pkg_customize_all_subtopics_{pkg_subtopics_cache_key}")
            
            for idx, sub in enumerate(pkg_selected_subtopics):
                clean_sub_id = re.sub(r'[^a-zA-Z0-9_]', '_', sub)[:25]
                sub_safe_key = f"pkg_sub_dist_{clean_sub_id}_{idx}"
                
                if pkg_cust_all:
                    sub_override = True
                    st.markdown(f"**📌 {sub}**")
                else:
                    sub_override = st.checkbox(f"Custom counts for **{sub}**", value=False, key=f"chk_{sub_safe_key}")
                
                if sub_override:
                    sc1, sc2, sc3, sc4, sc5 = st.columns(5)
                    with sc1:
                        sq1 = st.number_input("S1 - Commit to Memory", min_value=0, max_value=20, value=int(pkg_q_l1), step=1, key=f"sq1_{sub_safe_key}")
                    with sc2:
                        sq2 = st.number_input("S2 - Further Practice", min_value=0, max_value=20, value=int(pkg_q_l2), step=1, key=f"sq2_{sub_safe_key}")
                    with sc3:
                        sq3 = st.number_input("S3 - Application", min_value=0, max_value=20, value=int(pkg_q_l3), step=1, key=f"sq3_{sub_safe_key}")
                    with sc4:
                        sq4 = st.number_input("S4 - Thinking Creatively", min_value=0, max_value=20, value=int(pkg_q_l4), step=1, key=f"sq4_{sub_safe_key}")
                    with sc5:
                        sqe = st.number_input("S5 - Exam Questions", min_value=0, max_value=20, value=int(pkg_q_exam), step=1, key=f"sqe_{sub_safe_key}")
                    sub_tot = int(sq1) + int(sq2) + int(sq3) + int(sq4) + int(sqe)
                    st.caption(f"↳ Total for *{sub}*: **{sub_tot} questions**")
                    pkg_custom_distribution[sub] = {
                        "Section 1 - Commit to Memory": int(sq1),
                        "Section 2 - Further Practice": int(sq2),
                        "Section 3 - Application": int(sq3),
                        "Section 4 - Thinking Creatively": int(sq4),
                        "Section 5 - Exam Questions": int(sqe)
                    }
                else:
                    pkg_custom_distribution[sub] = dict(pkg_level_distribution)

        has_pkg_custom = any(
            st.session_state.get(f"chk_pkg_sub_dist_{re.sub(r'[^a-zA-Z0-9_]', '_', s)[:25]}_{i}", False)
            for i, s in enumerate(pkg_selected_subtopics)
        ) or pkg_cust_all

        pkg_total_q_sum = sum(sum(t.values()) for t in pkg_custom_distribution.values()) if (has_pkg_custom and pkg_custom_distribution) else (len(pkg_selected_subtopics) * pkg_total_practice_default)
        pkg_total_ex_sum = len(pkg_selected_subtopics) * int(pkg_examples_per_concept)
        st.info(f"📊 **Package Contents:** **{len(pkg_selected_subtopics)} concepts** | **{pkg_total_ex_sum} worked past paper demonstrations** | **{pkg_total_q_sum} tiered practice questions**")

        col_pkg_tw_check, col_pkg_tw_inputs = st.columns([1.2, 2.8])
        with col_pkg_tw_check:
            pkg_use_term_week = st.checkbox("Assign to Term & Week?", value=False, key="pkg_specify_term_week")
        with col_pkg_tw_inputs:
            if pkg_use_term_week:
                col_pt, col_pw = st.columns(2)
                with col_pt:
                    pkg_term = st.number_input("Term:", min_value=1, max_value=4, value=1, key="pkg_term_num")
                with col_pw:
                    pkg_week = st.number_input("Week:", min_value=1, max_value=10, value=5, key="pkg_week_num")
            else:
                pkg_term = None
                pkg_week = None
                st.caption("📅 *Independent Exam Resource (no Term/Week constraint)*")

        pkg_custom_instructions = st.text_area(
            "Special Exam Focus / Custom Instructions (Optional):",
            placeholder="e.g. Focus heavily on vector dot product proofs, projectile motion angle deductions, include common marking penalties for unit vectors...",
            key="pkg_custom_instructions",
            height=70
        )

        col_gen_pkg, _ = st.columns([1.8, 2.2])
        with col_gen_pkg:
            generate_pkg_clicked = st.button(
                "🚀 Generate Complete Exam Package (Dual Booklets)",
                type="primary",
                use_container_width=True,
                key="btn_generate_exam_package"
            )

        if generate_pkg_clicked:
            active_tutor_api_key = (st.session_state.get("gemini_api_key") or "").strip()
            if not active_tutor_api_key:
                st.error("⚠️ Gemini API Key Required: Please enter your personal Google Gemini API key in the left sidebar under '🔑 Personal Gemini API Key' (Get a free key in 30s at https://aistudio.google.com/app/apikey).")
            elif not pkg_selected_topics:
                st.warning("Please select at least one topic/chapter to include in the package.")
            elif not pkg_selected_subtopics:
                st.warning("Please select at least one concept/subtopic to include in the package.")
            else:
                with st.spinner("🧠 Synthesizing Complete Exam Revision & Practice Package with Gemini AI..."):
                    try:
                        pkg_data = ai_engine.generate_exam_package(
                            year_level=pkg_year_level,
                            topic=pkg_topic,
                            subtopics=pkg_selected_subtopics,
                            examples_per_concept=int(pkg_examples_per_concept),
                            practice_per_concept=int(pkg_total_practice_default),
                            term=int(pkg_term) if pkg_term is not None else None,
                            week=int(pkg_week) if pkg_week is not None else None,
                            custom_instructions=pkg_custom_instructions,
                            textbook=pkg_textbook,
                            api_key=active_tutor_api_key,
                            question_distribution=pkg_custom_distribution if (has_pkg_custom and pkg_custom_distribution) else None,
                            level_distribution=pkg_level_distribution
                        )
                        pkg_data["textbook"] = pkg_textbook
                        pkg_id = int(time.time())
                        pkg_data["id"] = pkg_id
                        st.session_state["latest_exam_package"] = pkg_data
                        st.session_state["latest_exam_package_id"] = pkg_id
                        pkg_cost = pkg_data.get('meta_cost', 0.0)
                        pkg_tokens = pkg_data.get('meta_tokens', 0)
                        st.success(f"🎉 Successfully created Complete Exam Package: {pkg_data.get('title')}! (💰 Cost: ${pkg_cost:.4f} AUD • {pkg_tokens:,} tokens)")
                    except Exception as e:
                        st.error(f"Error generating exam package: {str(e)}")

        # Display latest generated exam package
        if st.session_state.get("latest_exam_package"):
            ep = st.session_state["latest_exam_package"]
            st.markdown("---")
            st.markdown(f"### 📥 Download Generated Exam Package: **{ep.get('title')}**")

            if ep.get("meta_cost") is not None or ep.get("meta_tokens"):
                st.info(f"💰 **Generation Cost:** **${ep.get('meta_cost', 0.0):.4f} AUD** • **{ep.get('meta_tokens', 0):,} tokens** ({ep.get('model_used', 'Gemini 3.8 Flash')})")

            col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)
            with col_stat1:
                st.metric("Concepts Covered", len(ep.get("concepts", [])))
            with col_stat2:
                st.metric("Worked Past Paper Examples", ep.get("total_examples", 0))
            with col_stat3:
                st.metric("Practice Questions", ep.get("total_questions", 0))
            with col_stat4:
                st.metric("Total Marks Available", f"{ep.get('total_marks', 0)} Marks")

            ep_font_theme = "charter"

            ep_cache_key = f"{ep.get('id', 0)}_{ep.get('title', '')}_{ep_font_theme}"
            if st.session_state.get("latest_ep_cache_key") != ep_cache_key or "latest_ep_artifacts" not in st.session_state:
                with st.spinner("Compiling Complete Exam Package PDFs & ZIP Bundle (one-time)..."):
                    _ep_zip = pdf_generator.generate_exam_package_zip_bundle(ep, font_theme=ep_font_theme)
                    _ep_t_pdf = pdf_generator.generate_exam_package_theory_pdf(
                        package_data=ep,
                        mode="student",
                        term=ep.get("term"),
                        week=ep.get("week"),
                        font_theme=ep_font_theme
                    )
                    _ep_ps_pdf = pdf_generator.generate_exam_package_practice_pdf(
                        package_data=ep,
                        mode="student",
                        term=ep.get("term"),
                        week=ep.get("week"),
                        font_theme=ep_font_theme
                    )
                    _ep_sol_pdf = pdf_generator.generate_exam_package_practice_pdf(
                        package_data=ep,
                        mode="solutions",
                        term=ep.get("term"),
                        week=ep.get("week"),
                        font_theme=ep_font_theme
                    )
                    st.session_state["latest_ep_cache_key"] = ep_cache_key
                    st.session_state["latest_ep_artifacts"] = {
                        "zip": _ep_zip,
                        "t_pdf": _ep_t_pdf,
                        "ps_pdf": _ep_ps_pdf,
                        "sol_pdf": _ep_sol_pdf,
                    }

            _cached_ep = st.session_state["latest_ep_artifacts"]
            zip_bundle_bytes = _cached_ep["zip"]
            theory_pdf_bytes = _cached_ep["t_pdf"]
            practice_stud_pdf_bytes = _cached_ep["ps_pdf"]
            practice_sol_pdf_bytes = _cached_ep["sol_pdf"]

            st.markdown("#### ⚡ 1-Click Complete Package Download")
            clean_top_safe = ai_engine.clean_topic_title(ep.get("topic", "Exam Package")).replace(" ", "_")
            zip_filename = f"{clean_top_safe}_Complete_Exam_Package.zip"
            st.download_button(
                "📦 Download Complete Exam Package Bundle (.ZIP with All 3 PDFs)",
                data=zip_bundle_bytes,
                file_name=zip_filename,
                mime="application/zip",
                key="dl_latest_exam_pkg_zip",
                use_container_width=True,
                type="primary"
            )
            st.caption("✨ Includes Booklet 1 (Theory & Worked Examples), Booklet 2 (Student Practice Edition), and Booklet 2 (Complete Solutions & Marking Guidelines) in high-resolution PDF format.")

            st.markdown("#### 📂 Individual Booklet Downloads")
            p_pkg_col1, p_pkg_col2, p_pkg_col3 = st.columns(3)

            with p_pkg_col1:
                st.markdown("##### 📘 Booklet 1: Theory & Notes")
                theory_dl_name = get_exam_package_download_filename(ep, booklet_type="theory", mode="student", extension="pdf")
                st.download_button(
                    "📥 Theory & Notes (PDF)",
                    data=theory_pdf_bytes,
                    file_name=theory_dl_name,
                    mime="application/pdf",
                    key="dl_latest_ep_theory_pdf",
                    use_container_width=True
                )
                st.caption("✅ Features rapid visual study notes, glowing Neon UI exam hacks, coloured speech-bubble pitfall traps, and worked past paper demonstrations with official marking rubrics.")

            with p_pkg_col2:
                st.markdown("##### 📝 Booklet 2: Student Practice")
                practice_stud_dl_name = get_exam_package_download_filename(ep, booklet_type="practice", mode="student", extension="pdf")
                st.download_button(
                    "📥 Student Practice Booklet (PDF)",
                    data=practice_stud_pdf_bytes,
                    file_name=practice_stud_dl_name,
                    mime="application/pdf",
                    key="dl_latest_ep_prac_stud_pdf",
                    use_container_width=True
                )
                st.caption("✅ Clean exam questions with generous, unclustered student working space boxes and quick self-checking answer key at the back.")

            with p_pkg_col3:
                st.markdown("##### 🎯 Booklet 2: Complete Solutions")
                practice_sol_dl_name = get_exam_package_download_filename(ep, booklet_type="practice", mode="solutions", extension="pdf")
                st.download_button(
                    "📥 Solutions & Rubrics (PDF)",
                    data=practice_sol_pdf_bytes,
                    file_name=practice_sol_dl_name,
                    mime="application/pdf",
                    key="dl_latest_ep_prac_sol_pdf",
                    use_container_width=True
                )
                st.caption("✅ Full line-by-line whiteboard worked solutions, point-by-point marking criteria rubrics, and examiner pitfall warnings under every question.")

            st.markdown("---")
            st.markdown("#### 👁️ PDF Preview")
            st.caption("Pixel-perfect representation of the compiled PDF ready for high-resolution printing.")

            def _render_raw_ep_content():
                p_tab1, p_tab2, p_tab3 = st.tabs([
                    "📘 Booklet 1: Theory, Notes & Worked Examples",
                    "📝 Booklet 2: Student Practice Questions",
                    "🎯 Booklet 2: Complete Solutions & Marking Rubrics"
                ])

                with p_tab1:
                    for c_idx, c in enumerate(ep.get("concepts", []), 1):
                        c_name = c.get("concept_name") or c.get("name", f"Concept {c_idx}")
                        st.markdown(f"### Part {chr(64 + c_idx) if c_idx <= 26 else c_idx}: {c_name}")
                        
                        s_notes = c.get("study_notes", {})
                        if isinstance(s_notes, dict):
                            pts = s_notes.get("summary_points", [])
                            forms = s_notes.get("essential_formulas", [])
                        else:
                            pts = [str(s_notes)] if s_notes else []
                            forms = []

                        if pts:
                            st.markdown("##### 📌 High-Yield Study Notes:")
                            for pt in pts:
                                st.markdown(pt)

                        if forms:
                            st.markdown("##### 📐 Essential Formulae:")
                            for f in forms:
                                if isinstance(f, dict):
                                    st.markdown(f"- **{f.get('name', '')}**: {f.get('formula', '')} *( {f.get('note', '')} )*")
                                else:
                                    st.markdown(f"- {f}")

                        hacks = c.get("exam_hacks", [])
                        if hacks:
                            st.markdown("##### ⚡ Neon UI Exam Hacks:")
                            for h in hacks:
                                if isinstance(h, dict):
                                    st.info(f"**⚡ {h.get('title', 'Exam Hack')}:** {h.get('hack_content', '')}")
                                else:
                                    st.info(f"**⚡ Exam Hack:** {h}")

                        traps = c.get("common_mistakes", [])
                        if traps:
                            st.markdown("##### 💬 Speech-Bubble Pitfalls & Traps:")
                            for t in traps:
                                if isinstance(t, dict):
                                    st.warning(f"**💬 {t.get('trap_title', 'Exam Trap')}:** {t.get('trap_explanation', '')}")
                                else:
                                    st.warning(f"**💬 Exam Trap:** {t}")

                        p_exs = c.get("worked_past_paper_examples") or c.get("mastery_examples", [])
                        if p_exs:
                            st.markdown("##### 🏛️ Worked Past Paper Examples:")
                            for e_idx, ex in enumerate(p_exs, 1):
                                st.markdown(f"**Example {c_idx}.{e_idx}: {ex.get('title', '')}** `[{ex.get('source_tag', 'HSC Standard')} • {ex.get('marks', 3)} marks]`")
                                st.markdown(f"*{ex.get('problem_text', '')}*")
                                with st.expander(f"Show Worked Solution & Rubric for Example {c_idx}.{e_idx}", expanded=False):
                                    st.markdown(f"**Worked Solution:**\n\n{ex.get('worked_solution', '')}")
                                    crits = ex.get("marking_guidelines", [])
                                    if crits:
                                        st.markdown("**Marking Guidelines:**")
                                        for cr in crits:
                                            if isinstance(cr, dict):
                                                st.markdown(f"- **{cr.get('marks', 1)} Mark:** {cr.get('criteria', '')}")
                                            else:
                                                st.markdown(f"- {cr}")
                        st.markdown("---")

                with p_tab2:
                    for c_idx, c in enumerate(ep.get("concepts", []), 1):
                        c_name = c.get("concept_name") or c.get("name", f"Part {c_idx}")
                        p_let = chr(64 + c_idx) if c_idx <= 26 else str(c_idx)
                        st.markdown(f"### Part {p_let}: {c_name} --- Practice Questions")
                        pqs = c.get("practice_questions", [])
                        for q_idx, q in enumerate(pqs, 1):
                            diff_badge = f"{q.get('difficulty', 'Standard')} • " if q.get('difficulty') else ""
                            m_cnt = q.get('marks', 2)
                            src = f" • {q.get('source_tag')}" if q.get('source_tag') else ""
                            st.markdown(f"**Question {p_let}.{q_idx}:** {q.get('text', '')} &nbsp;&nbsp;`[{diff_badge}{m_cnt} mark{'s' if m_cnt > 1 else ''}{src}]`")
                            st.caption(f"✍️ *Student Working Area Allocated: {q.get('working_lines_cm', 4.5)}cm*")
                            st.markdown("")
                        st.markdown("---")

                with p_tab3:
                    for c_idx, c in enumerate(ep.get("concepts", []), 1):
                        c_name = c.get("concept_name") or c.get("name", f"Part {c_idx}")
                        p_let = chr(64 + c_idx) if c_idx <= 26 else str(c_idx)
                        st.markdown(f"### Part {p_let}: {c_name} --- Solutions & Rubrics")
                        pqs = c.get("practice_questions", [])
                        for q_idx, q in enumerate(pqs, 1):
                            st.markdown(f"#### Question {p_let}.{q_idx}: {q.get('text', '')}")
                            st.markdown(f"**Model Solution:**\n\n{q.get('worked_solution', '')}")
                            crits = q.get("marking_guidelines", [])
                            if crits:
                                st.markdown("**Marking Criteria & Rubric:**")
                                for cr in crits:
                                    if isinstance(cr, dict):
                                        st.markdown(f"- **{cr.get('marks', 1)} Mark:** {cr.get('criteria', '')}")
                                    else:
                                        st.markdown(f"- {cr}")
                            if q.get("examiner_pitfall"):
                                st.error(f"⚠️ **Examiner Deduction Warning:** {q.get('examiner_pitfall')}")
                            if q.get("final_answer"):
                                st.success(f"**Final Answer:** {q.get('final_answer')}")
                        st.markdown("---")

            ep_editions = {
                "Booklet 1: Theory, Notes & Worked Examples": theory_pdf_bytes,
                "Booklet 2: Student Practice Questions": practice_stud_pdf_bytes,
                "Booklet 2: Solutions & Marking Rubrics": practice_sol_pdf_bytes,
            }
            render_authentic_pdf_preview(
                pdf_bytes=theory_pdf_bytes,
                key_prefix="latest_ep",
                available_editions=ep_editions,
                default_edition="Booklet 1: Theory, Notes & Worked Examples",
                raw_content_callback=_render_raw_ep_content,
                raw_content_title="📝 View Raw Questions, Rubrics & Past Paper Content"
            )

    # Sub-tab: DA Tuition Cloud Exam Library
    with sub_tab_cloud:
        cloud_sync.render_cloud_exam_library(current_user=current_user, is_admin=is_admin)

def _save_marked_submission_result(
    grade_data: Dict[str, Any],
    file_name: str,
    active_total_marks: float,
    active_ws_id: Optional[int],
    worksheet_title: str,
    term_val: Optional[int],
    week_val: Optional[int],
    selected_class_id: Optional[int],
    q_meta: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[Dict[str, Any], Tuple[str, bytes], str]:
    """Persist one grading result and build its downloadable report."""
    student_name = str(grade_data.get("extracted_name") or os.path.splitext(file_name)[0]).strip()
    score = float(grade_data.get("score", 0.0))
    score = max(0.0, min(score, float(active_total_marks)))
    accuracy_pct = round((score / float(active_total_marks)) * 100.0, 1) if active_total_marks else 0.0
    mistakes = grade_data.get("mistakes", []) or []
    summary_text = grade_data.get("summary_text", "")
    cls_obj = database.get_class_by_id(selected_class_id) if selected_class_id else None
    class_display_name = cls_obj["name"] if cls_obj else ""

    if term_val and week_val:
        tw_header, tw_tag = f"Term {term_val} Week {week_val} Homework Report", f"T{term_val}W{week_val}"
    elif term_val:
        tw_header, tw_tag = f"Term {term_val} Homework Report", f"T{term_val}"
    elif week_val:
        tw_header, tw_tag = f"Week {week_val} Homework Report", f"W{week_val}"
    else:
        tw_header, tw_tag = (f"{worksheet_title} Report" if worksheet_title else "Homework Performance Report"), "Homework"

    report_filename = f"DA_Report_{re.sub(r'[^A-Za-z0-9]+', '_', student_name).strip('_')}_{tw_tag}.pdf"
    sub_id = database.save_submission(
        worksheet_id=active_ws_id,
        student_name=student_name,
        raw_file_name=file_name,
        score=score,
        total_marks=active_total_marks,
        accuracy_pct=accuracy_pct,
        pdf_report_path=report_filename,
        summary_text=summary_text,
        mistakes=mistakes,
        class_id=selected_class_id
    )
    sub_concepts = database.get_submission_concept_breakdown(sub_id) if sub_id else []
    report_bytes = pdf_generator.generate_student_report_pdf(
        student_name=student_name,
        term_week_header=tw_header,
        score=score,
        total_marks=active_total_marks,
        accuracy_pct=accuracy_pct,
        mistakes=mistakes,
        summary_text=summary_text,
        class_name=class_display_name,
        concept_breakdown=sub_concepts
    )
    return (
        {"Student Name": student_name, "Score": f"{score} / {active_total_marks}",
         "Accuracy %": f"{round(accuracy_pct)}%", "Errors": len(mistakes),
         "File": file_name, "Summary": summary_text},
        (report_filename, report_bytes),
        student_name.lower()
    )


# ==========================================
# TAB 2: 1-CLICK AI HOMEWORK MARKING
# ==========================================
if main_section == "🚀 2. 1-Click AI Marking":
    st.markdown("### 1-Click AI Homework Marking")
    st.caption("Upload your students' handwritten PDF scans. The AI matches answers against the marking key and reconciles against your class roll.")

    col_cls, col_ws = st.columns(2)
    all_classes = database.get_classes_for_user(current_user_id, current_user_role)

    with col_cls:
        if all_classes:
            class_options = {f"{c['name']} (Teacher: {c.get('tutor_display_name') or c['teacher_name'] or 'N/A'})": c['id'] for c in all_classes}
            class_options["-- No Specific Class --"] = None
            selected_class_label = st.selectbox("Assign to Class Roll:", list(class_options.keys()))
            selected_class_id = class_options[selected_class_label]
            class_roll = database.get_class_students(selected_class_id) if selected_class_id else []
            if selected_class_id:
                st.info(f"👥 **{len(class_roll)} students** enrolled in this class roll.")
        else:
            selected_class_id = None
            class_roll = []
            if is_admin:
                st.info("💡 No classes created yet. You can set up your class rosters in **Tab 5 (Classes & Rolls)**.")
            else:
                st.info("💡 You currently have no classes assigned to your account. Set up your class in **Tab 5 (Classes & Rolls)** or ask an Admin to assign one to you.")

    with col_ws:
        latest_sess_ws = st.session_state.get("latest_worksheet")
        if latest_sess_ws:
            try:
                saved_ws_id = database.ensure_generated_worksheet_saved(latest_sess_ws)
                if latest_sess_ws.get("id") != saved_ws_id:
                    latest_sess_ws["id"] = saved_ws_id
                    st.session_state["latest_ws_id"] = saved_ws_id
                    st.session_state["preselected_marking_ws_id"] = saved_ws_id
            except Exception as exc:
                st.error(f"Could not save the current worksheet for marking: {exc}")
        worksheets_list = database.get_worksheets()
        marking_mode = st.radio("Marking Key Source:", ["Use a generated Worksheet", "Custom / Ad-hoc Key"], horizontal=True)

    active_key = {}
    active_total_marks = 10.0
    active_ws_id = None
    worksheet_title = "Homework"
    term_val = 1
    week_val = 1

    if marking_mode == "Use a generated Worksheet":
        latest_sess_ws = st.session_state.get("latest_worksheet")
        if not worksheets_list and not latest_sess_ws:
            st.warning("No generated worksheets found. Generate one in Tab 1 or switch to 'Custom / Ad-hoc Key'.")
        elif latest_sess_ws and not worksheets_list:
            _, _, active_key, _ = pdf_generator.extract_worksheet_answer_sheet_data(
                latest_sess_ws.get("questions", []), latest_sess_ws.get("marking_key")
            )
            calculated_marks = sum(int(q.get('marks', 1)) for q in latest_sess_ws.get("questions", []))
            active_total_marks = float(calculated_marks or len(active_key) or latest_sess_ws.get("total_questions", 10))
            active_ws_id = None
            worksheet_title = latest_sess_ws.get("title", "Current Session Worksheet")
            term_val = latest_sess_ws.get("term", 1) or 1
            week_val = latest_sess_ws.get("week", 1) or 1
            st.success(f"Loaded {len(active_key)} question parts from active session worksheet: **{worksheet_title}** (Total Marks: {int(active_total_marks)})")
        else:
            # 1. Determine Class Year Level for smart auto-filtering
            class_year_tag = None
            if selected_class_label and selected_class_id:
                m_yr = re.search(r'\b(?:Yr|Year)\s*(\d{1,2})\b', selected_class_label, re.IGNORECASE)
                if m_yr:
                    class_year_tag = f"Year {m_yr.group(1)}"

            # 2. Extract available years, types, terms across existing worksheets
            all_years = sorted(list({w.get("year_level") for w in worksheets_list if w.get("year_level")}))
            year_filter_options = ["All Years"] + all_years
            default_year_idx = 0
            if class_year_tag:
                for y_idx, y_opt in enumerate(year_filter_options):
                    if class_year_tag.lower() in y_opt.lower():
                        default_year_idx = y_idx
                        break

            # 3. Filter Bar (Year Level, Type, Search)
            f_col1, f_col2, f_col3 = st.columns([1.2, 1.2, 1.6])
            with f_col1:
                sel_year_filter = st.selectbox(
                    "🎓 Filter Year Level",
                    year_filter_options,
                    index=default_year_idx,
                    key="tab2_filter_year"
                )
            with f_col2:
                sel_type_filter = st.selectbox(
                    "📂 Filter Booklet Type",
                    ["All Types", "🏠 Homework", "📝 In-Class", "🎯 Topic Exam", "📖 Theory Practice"],
                    index=0,
                    key="tab2_filter_type"
                )
            with f_col3:
                sel_search = st.text_input(
                    "🔍 Search Topic / Keyword",
                    placeholder="e.g. Permutations, Quadratics...",
                    key="tab2_filter_search"
                )

            # 4. Filter Worksheets
            filtered_ws = []
            for w in worksheets_list:
                # Year filter
                if sel_year_filter != "All Years":
                    w_yr = str(w.get("year_level", "")).lower()
                    if sel_year_filter.lower() not in w_yr:
                        continue

                # Type filter
                atype = w.get("assessment_type", "homework")
                if sel_type_filter == "🏠 Homework" and atype != "homework":
                    continue
                if sel_type_filter == "📝 In-Class" and atype != "in_class":
                    continue
                if sel_type_filter == "🎯 Topic Exam" and atype != "topic_exam":
                    continue
                if sel_type_filter == "📖 Theory Practice" and atype != "theory_practice":
                    continue

                # Search query filter
                if sel_search.strip():
                    q_term = sel_search.strip().lower()
                    combined_searchable = f"{w.get('title', '')} {w.get('topic', '')} {w.get('year_level', '')}".lower()
                    if q_term not in combined_searchable:
                        continue

                filtered_ws.append(w)

            if not filtered_ws:
                st.warning("🔍 No assignments matched your active filters. Try selecting 'All Years' or clearing your search query.")
            else:
                ws_options = {}
                for w in filtered_ws:
                    atype = w.get("assessment_type", "homework")
                    if atype == "theory_practice":
                        type_badge = "📖 Theory"
                    elif atype == "topic_exam":
                        type_badge = "🎯 Exam"
                    elif atype == "in_class":
                        type_badge = "📝 In-Class"
                    else:
                        s_num = w.get("set_number", 1)
                        type_badge = f"Homework Set {s_num}"

                    t_val = w.get("term")
                    w_val = w.get("week")
                    time_badge = f"T{t_val}W{w_val} " if (t_val and w_val) else ""
                    
                    # Clean Topic Name (strips duplicate curriculum prefixes)
                    raw_topic = w.get("topic") or w.get("title") or "Mathematics"
                    clean_top = re.sub(r'^(?:Chapter|Unit|Topic\s*)?(?:\d+[\.\:\-]\s*|\d+[A-Za-z][\.\:\-]\s*|\d+\s+)', '', str(raw_topic)).strip()
                    clean_top = re.sub(r'^(?:Year\s+\d+\s*(?:\([^\)]+\))?\s*(?:Mathematics)?\s*[\-\–\—\:]\s*)', '', clean_top, flags=re.IGNORECASE).strip()
                    clean_top = re.sub(r'\s*(?:Homework|In-Class|Worksheet|Mastery Exam|Theory & Practice Booklet|Theory Booklet)[\s\S]*$', '', clean_top, flags=re.IGNORECASE).strip()
                    if not clean_top:
                        clean_top = w.get("title", "Worksheet")

                    w_yr_short = str(w.get("year_level", "")).replace("Mathematics", "Maths").strip()
                    clean_label = f"{time_badge}{type_badge} • {w_yr_short} — {clean_top} ({w.get('total_questions', 0)} Qs) [ID #{w['id']}]"
                    ws_options[clean_label] = w['id']

                ws_keys = list(ws_options.keys())
                preselected_ws_id = st.session_state.get("preselected_marking_ws_id")
                default_idx = 0
                if preselected_ws_id:
                    for idx, k in enumerate(ws_keys):
                        if ws_options[k] == preselected_ws_id:
                            default_idx = idx
                            break

                selected_label = st.selectbox(
                    f"Select Assignment ({len(filtered_ws)} available):",
                    ws_keys,
                    index=default_idx
                )
                selected_ws_id = ws_options[selected_label]
                full_ws = database.get_worksheet_by_id(selected_ws_id)
                if full_ws:
                    _, _, active_key, _ = pdf_generator.extract_worksheet_answer_sheet_data(
                        full_ws.get("questions", []), full_ws.get("marking_key")
                    )
                    calculated_marks = sum(int(q.get('marks', 1)) for q in full_ws.get("questions", []))
                    active_total_marks = float(calculated_marks or len(active_key) or full_ws.get("total_questions", 10))
                    active_ws_id = full_ws["id"]
                    worksheet_title = full_ws["title"]
                    term_val = full_ws["term"]
                    week_val = full_ws["week"]
                    
                    src_tb_id = full_ws.get("source_theory_id")
                    tb_badge = ""
                    if src_tb_id:
                        src_tb = database.get_theory_booklet_by_id(src_tb_id)
                        if src_tb:
                            tb_badge = f" • Linked to Theory Booklet: **#{src_tb_id} ({src_tb.get('title')})**"
                    
                    st.success(f"Loaded {len(active_key)} question parts from **{worksheet_title}** (Total Marks: {int(active_total_marks)}){tb_badge}")

                    with st.expander("📥 Re-Download Booklet & Answer Sheet Materials", expanded=False):
                        ws_atype = full_ws.get("assessment_type") or full_ws.get("sheet_type") or "homework"
                        ws_set_n = full_ws.get("set_number", 1)
                        ws_q_json = full_ws.get("questions_json") or json.dumps(full_ws.get("questions", []))
                        ws_mk_json = full_ws.get("marking_key_json") or json.dumps(full_ws.get("marking_key", {}))
                        ws_yl = full_ws.get("year_level", "")
                        ws_tp = full_ws.get("topic", full_ws.get("title", ""))

                        tb_ref = src_tb if src_tb_id else None

                        f_stu_pdf = get_cached_worksheet_pdf(full_ws['id'], full_ws['title'], ws_yl, ws_tp, ws_q_json, ws_mk_json, full_ws.get('term'), full_ws.get('week'), ws_atype, "student", ws_set_n)
                        f_tea_pdf = get_cached_worksheet_pdf(full_ws['id'], full_ws['title'], ws_yl, ws_tp, ws_q_json, ws_mk_json, full_ws.get('term'), full_ws.get('week'), ws_atype, "teacher", ws_set_n)
                        f_sans_pdf = get_cached_worksheet_pdf(full_ws['id'], full_ws['title'], ws_yl, ws_tp, ws_q_json, ws_mk_json, full_ws.get('term'), full_ws.get('week'), ws_atype, "answers", ws_set_n)
                        f_tans_pdf = get_cached_worksheet_pdf(full_ws['id'], full_ws['title'], ws_yl, ws_tp, ws_q_json, ws_mk_json, full_ws.get('term'), full_ws.get('week'), ws_atype, "teacher_answers", ws_set_n)

                        f_stu_name = get_worksheet_download_filename(full_ws, sheet_type=ws_atype, mode="student", theory_booklet=tb_ref)
                        f_tea_name = get_worksheet_download_filename(full_ws, sheet_type=ws_atype, mode="teacher", theory_booklet=tb_ref)
                        f_sans_name = get_worksheet_download_filename(full_ws, sheet_type=ws_atype, mode="answers", theory_booklet=tb_ref)
                        f_tans_name = get_worksheet_download_filename(full_ws, sheet_type=ws_atype, mode="teacher_answers", theory_booklet=tb_ref)

                        rd_col1, rd_col2, rd_col3, rd_col4 = st.columns(4)
                        with rd_col1:
                            st.download_button("📥 Student Worksheet", data=f_stu_pdf, file_name=f_stu_name, mime="application/pdf", key=f"t2_dl_stu_{full_ws['id']}", use_container_width=True)
                        with rd_col2:
                            st.download_button("📥 Teacher Solutions", data=f_tea_pdf, file_name=f_tea_name, mime="application/pdf", key=f"t2_dl_tea_{full_ws['id']}", use_container_width=True)
                        with rd_col3:
                            st.download_button("📥 Student Answer Sheet", data=f_sans_pdf, file_name=f_sans_name, mime="application/pdf", key=f"t2_dl_sans_{full_ws['id']}", use_container_width=True)
                        with rd_col4:
                            st.download_button("🔑 Teacher Answer Key", data=f_tans_pdf, file_name=f_tans_name, mime="application/pdf", key=f"t2_dl_tans_{full_ws['id']}", use_container_width=True)

                        rd_z, rd_open, rd_del = st.columns([1.4, 1.0, 1.0])
                        with rd_z:
                            f_zip_bytes = build_worksheet_zip_package(full_ws['id'], json.dumps(full_ws), json.dumps(tb_ref) if tb_ref else None)
                            clean_z_topic = re.sub(r'^(?:Chapter|Unit|Topic\s*)?(?:\d+[\.\:\-]\s*|\d+[A-Za-z][\.\:\-]\s*|\d+\s+)', '', str(ws_tp)).strip()
                            zip_f_name = f"{clean_z_topic} {ws_atype.replace('_', ' ').title()} Complete Package.zip".replace("_", " ")
                            st.download_button("📦 Download All as ZIP (Complete Package)", data=f_zip_bytes, file_name=zip_f_name, mime="application/zip", key=f"t2_dl_zip_{full_ws['id']}", use_container_width=True)
                        with rd_open:
                            if st.button("📂 Load in Tab 1", key=f"t2_open_tab1_{full_ws['id']}", use_container_width=True):
                                st.session_state["latest_worksheet"] = full_ws
                                st.session_state["latest_ws_id"] = full_ws["id"]
                                st.session_state.pop("latest_ws_cache_key", None)
                                st.session_state.pop("latest_ws_artifacts", None)
                                st.session_state["active_tab_hint"] = "generate"
                                st.success("Loaded into Tab 1! Switch to Tab 1 above.")
                        with rd_del:
                            if st.button("🗑️ Delete Booklet", key=f"t2_del_btn_trigger_{full_ws['id']}", use_container_width=True):
                                st.session_state[f"t2_show_del_confirm_{full_ws['id']}"] = not st.session_state.get(f"t2_show_del_confirm_{full_ws['id']}", False)
                                st.rerun()

                    if st.session_state.get(f"t2_show_del_confirm_{selected_ws_id}", False):
                        ws_subs_count = database.get_worksheet_submission_count(selected_ws_id)
                        with st.container():
                            st.warning(f"⚠️ **Confirm Deletion for Worksheet #{selected_ws_id}:** {worksheet_title}")
                            if ws_subs_count > 0:
                                st.error(f"This assignment currently has **{ws_subs_count} marked student submission(s)** in the database. Deleting it will permanently erase these marks and student reports.")
                                force_agree = st.checkbox(f"Yes, permanently delete this worksheet and all {ws_subs_count} student submission(s).", key=f"t2_force_agree_{selected_ws_id}")
                                c_del1, c_del2 = st.columns(2)
                                with c_del1:
                                    if st.button("🚨 Permanently Delete", key=f"t2_do_del_{selected_ws_id}", type="primary", disabled=not force_agree, use_container_width=True):
                                        database.delete_worksheet(selected_ws_id, force=True)
                                        if st.session_state.get("preselected_marking_ws_id") == selected_ws_id:
                                            st.session_state.pop("preselected_marking_ws_id", None)
                                        if st.session_state.get("latest_ws_id") == selected_ws_id:
                                            for k in ("latest_worksheet", "latest_ws_id", "latest_ws_cache_key", "latest_ws_artifacts"):
                                                st.session_state.pop(k, None)
                                        st.session_state.pop(f"t2_show_del_confirm_{selected_ws_id}", None)
                                        st.success(f"Worksheet #{selected_ws_id} and submissions deleted successfully!")
                                        st.rerun()
                                with c_del2:
                                    if st.button("Cancel", key=f"t2_cancel_del_{selected_ws_id}", use_container_width=True):
                                        st.session_state.pop(f"t2_show_del_confirm_{selected_ws_id}", None)
                                        st.rerun()
                            else:
                                st.info("This assignment has no marked submissions. It will be removed from your database immediately.")
                                c_del1, c_del2 = st.columns(2)
                                with c_del1:
                                    if st.button("Confirm Delete", key=f"t2_do_safe_del_{selected_ws_id}", type="primary", use_container_width=True):
                                        database.delete_worksheet(selected_ws_id, force=False)
                                        if st.session_state.get("preselected_marking_ws_id") == selected_ws_id:
                                            st.session_state.pop("preselected_marking_ws_id", None)
                                        if st.session_state.get("latest_ws_id") == selected_ws_id:
                                            for k in ("latest_worksheet", "latest_ws_id", "latest_ws_cache_key", "latest_ws_artifacts"):
                                                st.session_state.pop(k, None)
                                        st.session_state.pop(f"t2_show_del_confirm_{selected_ws_id}", None)
                                        st.success(f"Worksheet #{selected_ws_id} deleted successfully!")
                                        st.rerun()
                                with c_del2:
                                    if st.button("Cancel", key=f"t2_cancel_safe_del_{selected_ws_id}", use_container_width=True):
                                        st.session_state.pop(f"t2_show_del_confirm_{selected_ws_id}", None)
                                        st.rerun()
    else:
        c1, c2, c3 = st.columns(3)
        with c1:
            term_val = st.number_input("Term", 1, 4, 1, key="m_term")
        with c2:
            week_val = st.number_input("Week", 1, 12, 1, key="m_week")
        with c3:
            active_total_marks = st.number_input("Total Marks", 1.0, 300.0, 20.0, key="m_marks")

        custom_key_text = st.text_area(
            "Paste Marking Key (JSON or '1: ans, 2: ans')",
            placeholder='{"1": "12", "2": "x = 5"}'
        )
        if custom_key_text:
            try:
                active_key = json.loads(custom_key_text)
            except Exception:
                parsed = {}
                for item in custom_key_text.replace("\n", ",").split(","):
                    if ":" in item:
                        k, v = item.split(":", 1)
                        parsed[k.strip()] = v.strip()
                active_key = parsed

    # Upload Student Submissions
    st.markdown("#### Upload Student Submissions")
    uploaded_files = st.file_uploader(
        "Drop student handwritten PDF scans here (single or multiple files)",
        type=["pdf"],
        accept_multiple_files=True
    )

    # Detect the organisation from the upload itself. A single PDF is sent to
    # the combined grader (which can return one or many student records),
    # while multiple PDFs are unambiguously one file per student.
    upload_mode = None
    if uploaded_files:
        if len(uploaded_files) == 1:
            upload_mode = "One combined PDF containing multiple students"
            st.info("Automatically detected: one combined PDF. Gemini will identify each student in the scan.")
        else:
            upload_mode = "One PDF per student"
            st.info(f"Automatically detected: {len(uploaded_files)} PDFs, one per student.")

    if uploaded_files and st.button("🚀 Start Automated Batch Marking", type="primary"):
        current_api_key = st.session_state.get("gemini_api_key", "")
        if not current_api_key:
            st.error("Gemini API Key missing in environment.")
        elif not active_key:
            st.error("No marking key available. Please select or enter a marking key.")
        else:
            progress_bar = st.progress(0)
            status_text = st.empty()
            results_list = []
            generated_pdf_reports = []
            submitted_names = set()

            total_files = len(uploaded_files)

            for idx, file in enumerate(uploaded_files):
                status_text.text(f"Grading [{idx+1}/{total_files}]: {file.name}...")
                try:
                    pdf_bytes = file.read()
                    q_meta = full_ws.get("questions", []) if (marking_mode == "Use a generated Worksheet" and full_ws) else None
                    if upload_mode.startswith("One combined"):
                        grade_records = ai_engine.grade_combined_student_submissions(
                            student_pdf_bytes=pdf_bytes, marking_key=active_key,
                            total_marks=active_total_marks, worksheet_title=worksheet_title,
                            term=int(term_val) if term_val is not None else 1,
                            week=int(week_val) if week_val is not None else 1,
                            api_key=current_api_key, questions_metadata=q_meta
                        )
                    else:
                        grade_records = [ai_engine.grade_student_submission(
                            student_pdf_bytes=pdf_bytes, marking_key=active_key,
                            total_marks=active_total_marks, worksheet_title=worksheet_title,
                            term=int(term_val) if term_val is not None else 1,
                            week=int(week_val) if week_val is not None else 1,
                            api_key=current_api_key, questions_metadata=q_meta
                        )]

                    for grade_data in grade_records:
                        result_row, report_item, submitted_name = _save_marked_submission_result(
                            grade_data=grade_data, file_name=file.name,
                            active_total_marks=active_total_marks, active_ws_id=active_ws_id,
                            worksheet_title=worksheet_title, term_val=term_val, week_val=week_val,
                            selected_class_id=selected_class_id, q_meta=q_meta
                        )
                        results_list.append(result_row)
                        generated_pdf_reports.append(report_item)
                        submitted_names.add(submitted_name)

                except Exception as e:
                    st.error(f"Failed to grade {file.name}: {e}")

                progress_bar.progress((idx + 1) / total_files)

            status_text.text("✅ Batch Marking Complete!")
            st.session_state["batch_results"] = results_list
            st.session_state["batch_reports"] = generated_pdf_reports
            st.session_state["submitted_names"] = submitted_names
            st.session_state["last_marked_class_id"] = selected_class_id

    # Display Results & Roll Reconciliation
    if "batch_results" in st.session_state and st.session_state["batch_results"]:
        st.markdown("---")
        st.markdown("### 🏆 Batch Marking Results")

        last_cid = st.session_state.get("last_marked_class_id")
        if last_cid:
            current_roll = database.get_class_students(last_cid)
            submitted = st.session_state.get("submitted_names", set())
            missing_students = [name for name in current_roll if name.lower().strip() not in submitted]

            r_col1, r_col2 = st.columns(2)
            with r_col1:
                st.success(f"✅ **{len(submitted)} of {len(current_roll)} students** submitted homework.")
            with r_col2:
                if missing_students:
                    st.warning(f"⚠️ **Missing Submissions ({len(missing_students)}):** " + ", ".join(missing_students))
                else:
                    st.success("🎉 100% Submission Rate! All students submitted.")

        results_df = pd.DataFrame(st.session_state["batch_results"])
        st.dataframe(results_df, use_container_width=True)

        if "batch_reports" in st.session_state and st.session_state["batch_reports"]:
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w") as zf:
                for fname, fbytes in st.session_state["batch_reports"]:
                    zf.writestr(fname, fbytes)

            col_dl1, col_dl2 = st.columns([1, 1])
            with col_dl1:
                st.download_button(
                    "📥 Download All Generated Student PDF Reports (.ZIP)",
                    data=zip_buffer.getvalue(),
                    file_name=f"DA Homework Reports T{term_val} W{week_val}.zip",
                    mime="application/zip",
                    type="primary"
                )

            with st.expander("📄 View & Download Individual Correction Reports (For Printing)", expanded=True):
                st.caption("Print individual performance breakdown sheets so students know which questions they got wrong and what the correct answer is to complete corrections.")
                for fname, fbytes in st.session_state["batch_reports"]:
                    stu_disp = fname.replace("DA_Report_", "").replace(f"_T{term_val}W{week_val}.pdf", "").replace("_", " ")
                    col_name, col_btn = st.columns([3, 1])
                    with col_name:
                        st.markdown(f"**{stu_disp}** (`{fname}`)")
                    with col_btn:
                        st.download_button(
                            label="🖨️ Download PDF",
                            data=fbytes,
                            file_name=fname,
                            mime="application/pdf",
                            key=f"dl_report_{fname}"
                        )

# ==========================================
# TAB 3: STUDENT TRACKING & ANALYTICS
# ==========================================
if main_section == "📊 3. Student Tracking & Analytics":
    st.markdown("### Student Progress & Class Diagnostics")
    st.caption("Track cohort curriculum coverage, detect systemic teaching gaps across concepts, and inspect weakness heatmaps.")

    tab3_coverage, tab3_overview = st.tabs([
        "🎯 1. Topic Assessment & Teaching Coverage Matrix",
        "📊 2. Overall Class Analytics & Student Timelines"
    ])

    with tab3_coverage:
        st.markdown("#### 🎯 Topic Assessment & Teaching Coverage Matrix")
        st.caption("Audits 100% syllabus concept coverage against teaching, diagnoses cohort-wide mastery vs individual gaps, and generates instant reteach briefs.")

        all_ws = database.get_worksheets()
        if not all_ws:
            st.info("No assessments or worksheets generated yet. Generate a Theory Booklet and its aligned End-of-Topic Exam in **Tab 1**!")
        else:
            col_cov_cls, col_cov_exam = st.columns([1.2, 2.0])
            with col_cov_cls:
                all_cls = database.get_classes_for_user(current_user_id, current_user_role)
                cov_class_opts = {"All My Classes" if not is_admin else "All Classes": None}
                for c in all_cls:
                    cov_class_opts[c['name']] = c['id']
                sel_cov_class_name = st.selectbox("Filter by Class Roll:", list(cov_class_opts.keys()), key="cov_class_sel")
                cov_filter_class_id = cov_class_opts[sel_cov_class_name]

            with col_cov_exam:
                exam_opts = {}
                for w in all_ws:
                    atype = w.get("assessment_type", "homework")
                    if atype == "theory_practice":
                        prefix = "📖 [THEORY PRACTICE] "
                    elif atype == "topic_exam":
                        prefix = "🎯 [TOPIC EXAM] "
                    elif atype == "in_class":
                        prefix = "📝 [IN-CLASS] "
                    else:
                        prefix = "🏠 [HOMEWORK] "
                    
                    t_val = w.get("term")
                    w_val = w.get("week")
                    tw_str = f"Term {t_val} Wk {w_val}" if t_val and w_val else "General Resource"
                    label = f"#{w['id']} - {prefix}{tw_str}: {w['title']} ({w.get('total_questions', 0)} Qs)"
                    exam_opts[label] = w['id']
                
                exam_keys = list(exam_opts.keys())
                preselected_matrix_id = st.session_state.get("preselected_matrix_ws_id")
                cov_default_idx = 0
                if preselected_matrix_id:
                    for idx, k in enumerate(exam_keys):
                        if exam_opts[k] == preselected_matrix_id:
                            cov_default_idx = idx
                            break

                sel_exam_label = st.selectbox("Select Assessment / Exam to Audit:", exam_keys, index=cov_default_idx, key="cov_exam_sel")
                sel_exam_id = exam_opts[sel_exam_label]

            if sel_exam_id:
                if not hasattr(database, "get_topic_assessment_matrix"):
                    import importlib
                    importlib.reload(database)
                matrix = database.get_topic_assessment_matrix(sel_exam_id, class_id=cov_filter_class_id)
                if not matrix or not matrix.get("student_records"):
                    st.info(f"💡 No student submissions recorded yet for **{matrix.get('title', 'this assessment')}** with the selected filter. Grade student papers in **Tab 2 (1-Click AI Marking)** to populate this matrix!")
                else:
                    # Source Theory Booklet link callout banner
                    src_tb_id = matrix.get("source_theory_id")
                    if src_tb_id:
                        src_title = matrix.get("source_theory_title") or f"Theory Booklet #{src_tb_id}"
                        st.success(f"📖 **Audited against Theory Curriculum**: Linked to Theory Booklet **#{src_tb_id}: {src_title}**")

                    # 1. KPI Cards
                    cov_kpi1, cov_kpi2, cov_kpi3, cov_kpi4 = st.columns(4)
                    cov_info = matrix["theory_coverage"]
                    cov_kpi1.metric(
                        "Curriculum Coverage",
                        f"{cov_info['tested_count']} / {cov_info['theory_count']} Concepts",
                        f"{cov_info['coverage_pct']}% Coverage"
                    )
                    cov_kpi2.metric(
                        "Cohort Mastery Average",
                        f"{matrix['class_average_pct']}%",
                        f"{'🟢 Strong' if matrix['class_average_pct'] >= 75 else ('🟡 Moderate' if matrix['class_average_pct'] >= 60 else '🔴 Needs Review')}"
                    )
                    cov_kpi3.metric("Assessed Students", f"{matrix['student_count']}")
                    gap_count = len(matrix["teaching_gaps"])
                    cov_kpi4.metric(
                        "Systemic Teaching Gaps",
                        f"{gap_count} Concept{'s' if gap_count != 1 else ''}",
                        delta="Requires Reteach" if gap_count > 0 else "All Concepts Absorbed",
                        delta_color="inverse" if gap_count > 0 else "normal"
                    )

                    # 2. Teaching Gap Alert Banner
                    if matrix["teaching_gaps"]:
                        st.markdown("---")
                        st.markdown("##### 🚨 Systemic Teaching Gap Diagnosis (< 65% Cohort Mastery)")
                        for gap in matrix["teaching_gaps"]:
                            st.error(
                                f"⚠️ **Concept Gap**: **{gap['concept_name']}** — Cohort Average: **{gap['average_pct']}%**.\n\n"
                                f"More than one-third of the class lost marks on this concept. This indicates a teaching pace or explanation gap rather than individual student error."
                            )
                        with st.expander("⚡ 15-Minute Class Reteach Blueprint (Directly Extracted from Theory Booklet)", expanded=True):
                            st.markdown("**Recommended In-Class Reteach Actions:**")
                            for gap in matrix["teaching_gaps"]:
                                st.markdown(f"#### 🎯 Reteach Focus: **{gap['concept_name']}** (Cohort Average: `{gap['average_pct']}%`)")
                                
                                if gap.get("key_formulas"):
                                    st.markdown("**📐 Key Formulas to Reinforce on Whiteboard:**")
                                    for form in gap["key_formulas"]:
                                        st.markdown(f"- `{form}`")

                                if gap.get("tutor_tips"):
                                    st.info(f"💡 **Whiteboard Teacher Tip / Method:** {gap['tutor_tips']}")

                                teacher_ex = gap.get("teacher_example")
                                if teacher_ex and isinstance(teacher_ex, dict):
                                    st.markdown(f"**👨‍🏫 Recommended Whiteboard Walkthrough Example:**")
                                    st.markdown(f"*{teacher_ex.get('problem_text', '')}*")
                                    if teacher_ex.get('worked_solution'):
                                        with st.expander(f"Show Step-by-Step Whiteboard Solution for {gap['concept_name']}", expanded=False):
                                            st.markdown(teacher_ex['worked_solution'])
                                    if teacher_ex.get('teaching_notes'):
                                        st.caption(f"Teacher Note / Trap: {teacher_ex['teaching_notes']}")

                                st.markdown(f"- **Action Plan**: Spend 10 minutes working through the formula box and demonstration example above at the start of next week's lesson.")
                                st.markdown("---")
                            st.caption("Tip: Use the DA Master Method recipe from the Theory Booklet during the whiteboard demonstration.")

                    # 3. Visual Cohort Concept Heatmap Table
                    st.markdown("---")
                    st.markdown("##### 📊 Cohort Concept Mastery Matrix")
                    st.caption("Green (≥80%): Mastered | Amber (60–79%): Developing | Red (<60%): Critical Gap")

                    table_rows = []
                    for s in matrix["student_records"]:
                        row_data = {
                            "Student": s["student_name"],
                            "Overall Score": f"{s['score']}/{s['total_marks']} ({s['accuracy_pct']}%)",
                        }
                        for c_name in matrix["concepts_tested"]:
                            c_data = s["concepts"].get(c_name, {})
                            pct = c_data.get("pct", 0.0)
                            icon = "🟢" if pct >= 80 else ("🟡" if pct >= 60 else "🔴")
                            row_data[c_name] = f"{icon} {pct}%"
                        table_rows.append(row_data)

                    # Cohort Average Row
                    avg_row = {
                        "Student": "🏫 CLASS COHORT AVERAGE",
                        "Overall Score": f"Average: {matrix['class_average_pct']}%"
                    }
                    for c_name in matrix["concepts_tested"]:
                        c_avg = matrix["cohort_concept_averages"].get(c_name, {}).get("average_pct", 0.0)
                        icon = "🟢" if c_avg >= 80 else ("🟡" if c_avg >= 65 else "🔴")
                        avg_row[c_name] = f"{icon} {c_avg}%"
                    table_rows.append(avg_row)

                    df_matrix = pd.DataFrame(table_rows)
                    st.dataframe(df_matrix, use_container_width=True, hide_index=True)

                    # 4. Remediation Quick Action
                    st.markdown("---")
                    col_rem_info, col_rem_btn = st.columns([3, 1.2])
                    with col_rem_info:
                        st.info("🩺 **Automated Remediation**: Need to generate targeted homework drills for students who scored in the Red zone (<60%)? Jump to Tab 4 with one click.")
                    with col_rem_btn:
                        st.write("")
                        if st.button("👉 Go to Tab 4 Remedial Packs", use_container_width=True, key="btn_goto_tab4_matrix"):
                            st.session_state["active_tab_hint"] = "remedial"
                            st.info("Please switch to Tab 4 above to generate targeted remedial sheets.")

    with tab3_overview:
        all_cls = database.get_classes_for_user(current_user_id, current_user_role)
        filter_col1, filter_col2 = st.columns([1, 2])
        with filter_col1:
            class_filter_opts = {"All My Classes" if not is_admin else "All Classes": None}
            for c in all_cls:
                class_filter_opts[c['name']] = c['id']
            selected_filter_class = st.selectbox("Filter by Class:", list(class_filter_opts.keys()), key="t3_filter_cls")
            filter_class_id = class_filter_opts[selected_filter_class]

        submissions = database.get_submissions_summary(
            class_id=filter_class_id,
            user_id=current_user_id,
            role=current_user_role
        )

        if not submissions:
            st.info("No submissions found for the selected filter. Grade homework in Tab 2 to view analytics!")
        else:
            df_subs = pd.DataFrame(submissions)

            avg_score = df_subs["accuracy_pct"].mean()
            total_graded = len(df_subs)
            pass_rate = (df_subs["accuracy_pct"] >= 70).mean() * 100

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total Papers Graded", f"{total_graded}")
            m2.metric("Class Average Accuracy", f"{avg_score:.1f}%")
            m3.metric("Pass Rate (≥70%)", f"{pass_rate:.1f}%")
            unique_students = df_subs['student_name'].nunique()
            m4.metric("Students Tracked", f"{unique_students}")

            st.markdown("---")

            col_c1, col_c2 = st.columns(2)
            with col_c1:
                st.markdown("#### 🚨 Weakness Heatmap (Mistakes by Topic)")
                topic_weaknesses = database.get_topic_weaknesses(
                    class_id=filter_class_id,
                    user_id=current_user_id,
                    role=current_user_role
                )
                if topic_weaknesses:
                    df_weak = pd.DataFrame(topic_weaknesses)
                    fig_weak = px.bar(
                        df_weak.head(10),
                        x="mistake_count",
                        y="topic",
                        orientation="h",
                        color="total_marks_lost",
                        labels={"mistake_count": "Total Errors Made", "topic": "Math Topic", "total_marks_lost": "Marks Lost"},
                        color_continuous_scale="Reds",
                        title="Top Topics Causing Lost Marks"
                    )
                    fig_weak.update_layout(yaxis=dict(autorange="reversed"))
                    st.plotly_chart(fig_weak, use_container_width=True)
                else:
                    st.write("No mistakes recorded.")

            with col_c2:
                st.markdown("#### 📈 Student Individual Progress Timeline")
                student_list = sorted(list(df_subs['student_name'].unique()))
                if student_list:
                    selected_stu = st.selectbox("Select Student:", student_list, key="t3_stu_sel")
                    history = database.get_student_history(selected_stu)
                    if history:
                        df_hist = pd.DataFrame(history)
                        fig_hist = px.line(
                            df_hist,
                            x="graded_at",
                            y="accuracy_pct",
                            markers=True,
                            labels={"graded_at": "Date Graded", "accuracy_pct": "Accuracy %"},
                            title=f"{selected_stu}'s Trajectory Over Time"
                        )
                        fig_hist.update_yaxes(range=[0, 105])
                        st.plotly_chart(fig_hist, use_container_width=True)

                        # Concept-level Strengths and Weaknesses breakdown
                        concept_matrix = database.get_student_concept_mastery_matrix(selected_stu)
                        if concept_matrix:
                            st.markdown("##### 🎯 Concept-Level Strengths & Weaknesses")
                            st.caption("Aggregated performance per concept mapped to assigned questions and student accuracy.")
                            
                            c_cols = st.columns(min(len(concept_matrix), 3))
                            for c_idx, c_info in enumerate(concept_matrix):
                                col_target = c_cols[c_idx % len(c_cols)]
                                with col_target:
                                    if c_info["status"] == "Strength":
                                        badge = "🟢 Strength"
                                    elif c_info["status"] == "Weakness":
                                        badge = "🔴 Weakness"
                                    else:
                                        badge = "🟡 Review"
                                    st.markdown(f"**{c_info['concept_name']}**")
                                    st.caption(f"{badge} • `{c_info['correct_count']}/{c_info['total_questions']}` correct ({round(c_info['accuracy_pct'])}%)")
                                    st.progress(min(1.0, max(0.0, c_info['accuracy_pct'] / 100.0)))

                        weak_topics = database.get_student_weak_topics(selected_stu)
                        if weak_topics:
                            st.markdown(f"**Identified Weak Areas:** " + " • ".join([f"`{t}`" for t in weak_topics]))
                        else:
                            st.write("🎉 Perfect track record!")

                        with st.expander(f"📄 Past Correction Reports for {selected_stu}", expanded=False):
                            st.caption("Download or reprint performance breakdown sheets with concept diagnostics from previous submissions.")
                            for sub_item in history:
                                sub_id = sub_item.get('id')
                                ws_title = sub_item.get('worksheet_title') or "Homework"
                                t_val = sub_item.get('term')
                                w_val = sub_item.get('week')
                                term_wk_str = f"Term {t_val} Week {w_val}" if t_val and w_val else ws_title
                                sub_score = sub_item.get('score', 0)
                                sub_total = sub_item.get('total_marks', 0)
                                sub_acc = sub_item.get('accuracy_pct', 0)
                                graded_date = str(sub_item.get('graded_at', ''))[:10]

                                row_col1, row_col2, row_col3 = st.columns([3, 1, 0.8])
                                with row_col1:
                                    st.markdown(f"**{term_wk_str}** — Score: `{sub_score}/{sub_total}` ({round(sub_acc)}%) • *{graded_date}*")
                                with row_col2:
                                    sub_mistakes = database.get_submission_mistakes(sub_id)
                                    sub_concepts = database.get_submission_concept_breakdown(sub_id)
                                    rep_bytes = pdf_generator.generate_student_report_pdf(
                                        student_name=selected_stu,
                                        term_week_header=f"{term_wk_str} Homework Report",
                                        score=sub_score,
                                        total_marks=sub_total,
                                        accuracy_pct=sub_acc,
                                        mistakes=sub_mistakes,
                                        summary_text=sub_item.get('summary_text', ''),
                                        class_name=sub_item.get('class_name', ''),
                                        concept_breakdown=sub_concepts
                                    )
                                    fname = f"DA_Report_{selected_stu.replace(' ', '_')}_{term_wk_str.replace(' ', '_')}.pdf"
                                    st.download_button(
                                        label="🖨️ Print Sheet",
                                        data=rep_bytes,
                                        file_name=fname,
                                        mime="application/pdf",
                                        key=f"dl_hist_rep_{sub_id}"
                                    )
                                with row_col3:
                                    if st.button("🗑️ Delete", key=f"delete_hist_sub_{sub_id}", use_container_width=True):
                                        st.session_state["pending_delete_submission_id"] = sub_id
                                        st.rerun()
                                if st.session_state.get("pending_delete_submission_id") == sub_id:
                                    st.warning(f"Delete the test report for {selected_stu}? This removes this submission and its diagnostic mistakes, but keeps the worksheet.")
                                    confirm_col, cancel_col = st.columns(2)
                                    with confirm_col:
                                        if st.button("Confirm Delete Report", key=f"confirm_delete_hist_sub_{sub_id}", type="primary", use_container_width=True):
                                            database.delete_submission(sub_id)
                                            st.session_state.pop("pending_delete_submission_id", None)
                                            st.rerun()
                                    with cancel_col:
                                        if st.button("Cancel", key=f"cancel_delete_hist_sub_{sub_id}", use_container_width=True):
                                            st.session_state.pop("pending_delete_submission_id", None)
                                            st.rerun()

            st.markdown("---")
            st.markdown("#### 📋 Detailed Submissions Log")
            st.dataframe(
                df_subs[["student_name", "class_name", "worksheet_title", "score", "total_marks", "accuracy_pct", "graded_at"]],
                use_container_width=True
            )

# ==========================================
# TAB 4: REMEDIAL REVISION PACKS
# ==========================================
if main_section == "🎯 4. Remedial Revision Packs":
    st.markdown("### Generate Targeted Remedial Revision Pack")
    st.caption("Automatically create personalized revision homework tailored to a student's weak topics.")

    all_students = database.get_students_for_user(current_user_id, current_user_role)
    if not all_students:
        if is_admin:
            st.info("No students registered yet. Mark submissions in Tab 2 or add them in Tab 5.")
        else:
            st.info("No students enrolled in your assigned classes yet. Add students to your class rolls in Tab 5.")
    else:
        col_r1, col_r2, col_r3 = st.columns([1.4, 1.0, 1.6])
        with col_r1:
            target_student = st.selectbox("Select Student:", [s['name'] for s in all_students], key="rem_stu")
            student_weak_topics = database.get_student_weak_topics(target_student, limit=4)
        with col_r2:
            student_year = st.selectbox("Year Level", YEAR_LEVEL_OPTIONS, index=5, key="rem_yr")
        with col_r3:
            rem_focus_type = st.selectbox(
                "Worksheet Focus / Type:",
                [
                    "Remedial Practice Worksheet (Foundational Drills)",
                    "Targeted NESA Practice Worksheet (Exam-Style Questions)"
                ],
                index=0,
                key="rem_focus_type"
            )
        rem_num_qs = st.slider("Number of Practice Questions (1 Mark Each)", 3, 20, 5, key="rem_qs")

        if student_weak_topics:
            st.info(f"💡 **AI Diagnostic Weak Areas for {target_student}:** " + ", ".join([f"**{t}**" for t in student_weak_topics]))
        else:
            st.warning(f"No specific mistakes logged yet for {target_student}. The remedial pack will generate general revision.")

        selected_ws_mode = "Targeted NESA" if "nesa" in rem_focus_type.lower() else "Remedial"
        btn_label = f"🎯 Generate Targeted NESA Practice for {target_student}" if selected_ws_mode == "Targeted NESA" else f"🩺 Generate Remedial Practice for {target_student}"
        if st.button(btn_label, type="primary"):
            current_api_key = (st.session_state.get("gemini_api_key") or "").strip()
            if not current_api_key:
                st.error("⚠️ Gemini API Key Required: Please enter your personal Google Gemini API key in the left sidebar under '🔑 Personal Gemini API Key' (Get a free key in 30s at https://aistudio.google.com/app/apikey).")
            else:
                with st.spinner(f"Generating personalized practice questions for {target_student}..."):
                    try:
                        rem_worksheet = ai_engine.generate_remedial_worksheet(
                            student_name=target_student,
                            year_level=student_year,
                            weak_topics=student_weak_topics if student_weak_topics else ["General Revision"],
                            num_questions=rem_num_qs,
                            worksheet_type=selected_ws_mode,
                            api_key=current_api_key
                        )

                        sheet_saved_title = rem_worksheet.get("title", f"DA Tuition - {target_student} {selected_ws_mode} Practice Worksheet")
                        rem_worksheet["id"] = int(time.time())
                        st.session_state["latest_remedial"] = rem_worksheet
                        rem_cost = rem_worksheet.get('meta_cost', 0.0)
                        rem_tokens = rem_worksheet.get('meta_tokens', 0)
                        st.success(f"🎉 Created personalized worksheet for {target_student}! (💰 Cost: ${rem_cost:.4f} AUD • {rem_tokens:,} tokens) — Ready for printing.")
                    except Exception as e:
                        st.error(f"Error generating revision pack: {e}")

        if "latest_remedial" in st.session_state:
            rws = st.session_state["latest_remedial"]
            st.markdown("---")
            st.markdown(f"#### 📄 {rws.get('title')}")

            if rws.get("meta_cost") is not None or rws.get("meta_tokens"):
                st.info(f"💰 **Generation Cost:** **${rws.get('meta_cost', 0.0):.4f} AUD** • **{rws.get('meta_tokens', 0):,} tokens** ({rws.get('model_used', 'Gemini 3.8 Flash')})")

            rem_cache_key = f"{rws.get('id', 0)}_{rws.get('title', '')}_{target_student}"
            if st.session_state.get("latest_rem_cache_key") != rem_cache_key or "latest_rem_pdf" not in st.session_state:
                with st.spinner("Compiling Remedial Practice Worksheet PDF (one-time)..."):
                    _rem_pdf = pdf_generator.generate_worksheet_pdf(
                        title=rws.get("title", f"DA Tuition - {target_student} Practice Worksheet"),
                        year_level=rws.get("year_level", student_year),
                        topic=rws.get("topic", "Targeted Revision"),
                        questions=rws.get("questions", []),
                        include_solutions=True,
                        term=1,
                        week=1,
                        sheet_type="Homework"
                    )
                    st.session_state["latest_rem_cache_key"] = rem_cache_key
                    st.session_state["latest_rem_pdf"] = _rem_pdf

            rem_pdf_bytes = st.session_state["latest_rem_pdf"]

            rem_dl_filename = f"DA Tuition - {target_student} Remedial Practice Worksheet.pdf"
            nesa_dl_filename = f"DA Tuition - {target_student} Targeted NESA Practice Worksheet.pdf"

            is_current_nesa = "nesa" in str(rws.get("worksheet_type", "")).lower() or "nesa" in str(rws.get("title", "")).lower()

            c_dl1, c_dl2 = st.columns(2)
            with c_dl1:
                st.download_button(
                    "📥 Download Remedial Practice Worksheet (PDF)",
                    data=rem_pdf_bytes,
                    file_name=rem_dl_filename,
                    mime="application/pdf",
                    key="dl_latest_remedial_practice_pdf",
                    use_container_width=True
                )
                st.caption(f"Filename: `{rem_dl_filename}`")
            with c_dl2:
                st.download_button(
                    "🎯 Download Targeted NESA Practice Worksheet (PDF)",
                    data=rem_pdf_bytes,
                    file_name=nesa_dl_filename,
                    mime="application/pdf",
                    key="dl_latest_targeted_nesa_practice_pdf",
                    use_container_width=True
                )
                st.caption(f"Filename: `{nesa_dl_filename}`")

            st.markdown("---")
            st.markdown("#### 👁️ PDF Preview")
            st.caption("Pixel-perfect representation of the compiled PDF ready for high-resolution printing.")

            def _render_raw_rem_content():
                for q in rws.get("questions", []):
                    item_lbl = q.get('item_label', q.get('num', ''))
                    st.markdown(f"**Question {item_lbl}:** {q.get('text')} &nbsp;&nbsp;`[1 mark]` *(Subtopic: {q.get('subtopic', '-')})*")
                    st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;**Answer:** {q.get('correct_answer')}")
                    if q.get('solution_steps'):
                        st.caption(f"&nbsp;&nbsp;&nbsp;&nbsp;*Steps:* {q.get('solution_steps')}")
                    st.markdown("---")

            render_authentic_pdf_preview(
                pdf_bytes=rem_pdf_bytes,
                key_prefix="latest_rem",
                raw_content_callback=_render_raw_rem_content,
                raw_content_title="📝 View Raw Questions, Answers & Solution Steps"
            )

# ==========================================
# TAB 5: CLASSES & STUDENT ROLLS
# ==========================================
if main_section == "👥 5. Classes & Student Rolls":
    st.markdown("### Class Rosters & Student Rolls")
    st.caption("Manage multiple teachers, classes, and student attendance/submission rolls with strict tutor isolation.")

    c_left, c_right = st.columns([1, 1])

    with c_left:
        st.markdown("#### ➕ Create New Class")
        with st.form("create_class_form", clear_on_submit=True):
            new_class_name = st.text_input("Class Name", placeholder="e.g. Year 10 Advanced - Sat 10am")
            new_class_year = st.selectbox("Year Level", YEAR_LEVEL_OPTIONS, index=5)
            
            all_tutors = database.get_all_tutors()
            if is_admin and all_tutors:
                tutor_map = {f"{t['display_name']} (@{t['username']})": t['id'] for t in all_tutors}
                sel_tutor_label = st.selectbox("Assign to Tutor", list(tutor_map.keys()))
                assigned_tutor_id = tutor_map[sel_tutor_label]
                new_class_teacher = sel_tutor_label.split(" (")[0]
            else:
                assigned_tutor_id = current_user_id
                new_class_teacher = current_user['display_name']
                st.text_input("Teacher / Tutor Name", value=new_class_teacher, disabled=True)

            new_class_time = st.text_input("Class Schedule", placeholder="e.g. Saturday 10:00 AM - 12:00 PM")
            submit_class = st.form_submit_button("Create Class", type="primary")

            if submit_class:
                if not new_class_name:
                    st.error("Please provide a Class Name.")
                else:
                    try:
                        cid = database.create_class(new_class_name, new_class_year, new_class_teacher, new_class_time, tutor_id=assigned_tutor_id)
                        st.success(f"🎉 Created class '{new_class_name}' with ID #{cid}!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error creating class: {e}")

    with c_right:
        st.markdown("#### 📋 Manage Student Roll")
        classes = database.get_classes_for_user(current_user_id, current_user_role)
        if not classes:
            if is_admin:
                st.info("No classes found. Create a class on the left first.")
            else:
                st.info("You currently have no classes assigned to your account. Create a class on the left or contact an administrator.")
        else:
            class_dict = {f"{c['name']} (Tutor: {c.get('tutor_display_name') or c['teacher_name'] or 'N/A'})": c['id'] for c in classes}
            sel_class_label = st.selectbox("Select Class to View/Edit Roll:", list(class_dict.keys()), key="roll_class_select")
            sel_class_id = class_dict[sel_class_label]

            # Security verification
            if not database.can_user_access_class(current_user_id, current_user_role, sel_class_id):
                st.error("⛔ Access Denied: You do not have permission to view or edit this class roll.")
            else:
                # View current roll
                students_in_class = database.get_class_students(sel_class_id)
                st.markdown(f"**Current Roll ({len(students_in_class)} students):**")
                if students_in_class:
                    st.write(", ".join([f"`{s}`" for s in students_in_class]))
                else:
                    st.caption("No students enrolled yet.")

                # Bulk add students
                st.markdown("##### 👥 Bulk Add Students to Roll")
                paste_students = st.text_area(
                    "Paste student names (one per line):",
                    placeholder="Ryan Huynh\nEmily Chen\nAlex Smith\nDaniel Kim\nJessica Tran",
                    height=120
                )
                if st.button("Add Students to Roll", type="primary"):
                    names_list = [line.strip() for line in paste_students.split("\n") if line.strip()]
                    if names_list:
                        added = database.add_students_to_class(sel_class_id, names_list)
                        st.success(f"Added {added} students to the roll!")
                        st.rerun()

                # Delete class option
                with st.expander("🗑️ Delete this Class"):
                    if st.button("Confirm Delete Class", type="secondary"):
                        database.delete_class(sel_class_id)
                        st.success("Class deleted.")
                        st.rerun()

    # Admin Only: Staff & Tutor Account Management Section
    if is_admin:
        st.markdown("---")
        st.markdown("### 👨‍🏫 Staff & Tutor Account Management (Admin Oversight)")
        st.caption("Create new tutor logins, inspect staff credentials, and reassign classes across tutors.")

        admin_col1, admin_col2 = st.columns([1, 1])
        with admin_col1:
            st.markdown("#### ➕ Add New Staff Account")
            with st.form("create_tutor_form", clear_on_submit=True):
                new_username = st.text_input("Username (lowercase, no spaces)", placeholder="e.g. tutor_sarah").strip().lower()
                new_display_name = st.text_input("Display Name", placeholder="e.g. Ms. Sarah Jenkins")
                new_password = st.text_input("Temporary Password", type="password", placeholder="••••••••")
                new_api_key = st.text_input("Personal Gemini API Key (Optional)", type="password", placeholder="AIzaSy...")
                new_role = st.selectbox("Role", ["tutor", "admin"], index=0, format_func=lambda x: "👨‍🏫 Tutor (Isolated to assigned classes)" if x == "tutor" else "🛡️ Admin (Full Center Access)")
                submit_tutor = st.form_submit_button("Create Account", type="primary")

                if submit_tutor:
                    if not new_username or not new_password or not new_display_name:
                        st.error("Please fill out all fields.")
                    elif database.get_user_by_username(new_username):
                        st.error(f"Username '{new_username}' already exists.")
                    else:
                        try:
                            uid = database.create_user(new_username, new_password, new_display_name, new_role, new_api_key.strip())
                            st.success(f"🎉 Created staff account for **{new_display_name}** (@{new_username}) with ID #{uid}!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error creating account: {e}")

        with admin_col2:
            st.markdown("#### 👥 Existing Staff Accounts")
            tutors_list = database.get_all_tutors()
            if tutors_list:
                df_tutors = pd.DataFrame(tutors_list)
                df_tutors["role"] = df_tutors["role"].apply(lambda r: "🛡️ Admin" if r == "admin" else "👨‍🏫 Tutor")
                df_tutors["api_key_status"] = df_tutors["api_key"].apply(lambda k: "✅ Configured" if (k and str(k).strip()) else "❌ Missing")
                df_tutors.rename(columns={"display_name": "Name", "username": "Username", "role": "Role", "api_key_status": "Personal API Key", "created_at": "Joined"}, inplace=True)
                st.dataframe(df_tutors[["Name", "Username", "Role", "Personal API Key", "Joined"]], use_container_width=True)

            st.markdown("##### 🔄 Reassign Class Tutor")
            all_classes_admin = database.get_all_classes()
            if all_classes_admin and tutors_list:
                with st.form("reassign_class_form"):
                    cls_select_map = {f"{c['name']} (Current: {c.get('tutor_display_name') or 'Unassigned'})": c['id'] for c in all_classes_admin}
                    sel_cls_reassign = st.selectbox("Select Class:", list(cls_select_map.keys()))
                    tutor_select_map = {f"{t['display_name']} (@{t['username']})": t['id'] for t in tutors_list}
                    sel_tutor_reassign = st.selectbox("Assign to Tutor:", list(tutor_select_map.keys()))
                    btn_reassign = st.form_submit_button("Update Assignment")
                    if btn_reassign:
                        target_cid = cls_select_map[sel_cls_reassign]
                        target_tid = tutor_select_map[sel_tutor_reassign]
                        database.update_class_tutor(target_cid, target_tid)
                        st.success("Successfully updated class tutor assignment!")
                        st.rerun()


# ==========================================
# TAB 6: LESSON COVER SHEETS & PROGRESS
# ==========================================
if main_section == "📋 6. Lesson Cover Sheets & Progress":
    st.markdown("### 📋 High School Lesson Cover Sheets & Progress Tracking")
    st.caption("FD Elite Continuous Learning System: <90s diagnostic tracking, cognitive independence matrix, student reflection pulse, and 15-second Director parent inquiry reporting.")

    lcs_tab_log, lcs_tab_director, lcs_tab_print = st.tabs([
        "⚡ 1. Rapid Lesson Logger (<90s)",
        "📞 2. Director Parent Inquiry Portal",
        "🖨️ 3. Printable A4 Cover Sheets"
    ])

    # -------------------------------------------------------------
    # SUB-TAB 1: RAPID LESSON LOGGER
    # -------------------------------------------------------------
    with lcs_tab_log:
        st.markdown("#### ⚡ Rapid Lesson Logger")
        st.info("💡 **Tutor Guide**: Complete this at the end of each lesson (< 90 seconds). Avoids essay writing by capturing cognitive mastery, root causes, and student sentiment through high-signal indicators.")

        user_classes = database.get_classes_for_user(current_user_id, current_user_role)
        if not user_classes:
            st.warning("No classes found. Please create or enroll in a class in Tab 5 first.")
        else:
            class_map = {f"{c['name']} ({c['year_level']})": c['id'] for c in user_classes}
            sel_class_label = st.selectbox("Select Class:", list(class_map.keys()), key="lcs_sel_class")
            sel_class_id = class_map[sel_class_label]

            # Fetch class students
            class_students = database.get_class_students(sel_class_id)
            if not class_students:
                st.warning("No students currently enrolled in this class roll. Please add students in Tab 5.")
            else:
                sel_student = st.selectbox("Select Student:", class_students, key="lcs_sel_student")

                with st.form("rapid_lesson_cover_form"):
                    # Lesson Metadata
                    meta_c1, meta_c2, meta_c3, meta_c4 = st.columns([1.2, 1, 1, 1])
                    with meta_c1:
                        lesson_date = st.date_input("Lesson Date", value=datetime.now())
                    with meta_c2:
                        term_num = st.selectbox("Term", [1, 2, 3, 4], index=0)
                    with meta_c3:
                        week_num = st.selectbox("Week", list(range(1, 11)), index=0)
                    with meta_c4:
                        subject_choice = st.selectbox("Subject", ["Mathematics", "English"], index=0)

                    st.markdown("---")
                    st.markdown("##### 1. What Was Taught & Focus Syllabus Outcomes")
                    f_c1, f_c2, f_c3 = st.columns([2, 2, 1.2])
                    with f_c1:
                        topic_input = st.text_input("Topic", placeholder="e.g. Vectors in 2D & 3D / Differential Calculus")
                    with f_c2:
                        subtopic_input = st.text_input("Subtopic", placeholder="e.g. Dot Product, Orthogonality & Projections")
                    with f_c3:
                        outcome_input = st.text_input("Syllabus Code", placeholder="e.g. ME-V1 / MA5.2-1WM")

                    materials_opts = ["DA Topic Booklet", "Exam Papers", "School Assessment Prep", "Revision Pack", "Textbook Exercise"]
                    sel_materials = st.multiselect("Materials Used:", materials_opts, default=["DA Topic Booklet"])

                    st.markdown("---")
                    st.markdown("##### 2. Cognitive Mastery & Independence Matrix")
                    st.caption("Categorize student problem-solving autonomy across up to 3 core concepts tested today.")

                    mastery_entries = []
                    level_options = [
                        "Modeled (Tutor Led / Demonstrated)",
                        "Scaffolded (Solved With Hints / Prompts)",
                        "Independent (Unassisted / Band 5/6 Ready)",
                        "Exam Ready (Extension / Unfamiliar Multi-Step)"
                    ]

                    for c_idx in range(1, 4):
                        c_col1, c_col2 = st.columns([2.5, 2])
                        with c_col1:
                            c_name = st.text_input(f"Concept {c_idx}", placeholder=f"e.g. Concept {c_idx} (Leave blank if not applicable)", key=f"c_name_{c_idx}")
                        with c_col2:
                            c_lvl = st.selectbox(f"Independence Level {c_idx}", level_options, index=2, key=f"c_lvl_{c_idx}")
                        if c_name.strip():
                            # Extract short level key
                            short_lvl = "Independent"
                            if "Modeled" in c_lvl:
                                short_lvl = "Modeled"
                            elif "Scaffolded" in c_lvl:
                                short_lvl = "Scaffolded"
                            elif "Exam" in c_lvl:
                                short_lvl = "Exam Ready"
                            mastery_entries.append({"concept": c_name.strip(), "level": short_lvl})

                    st.markdown("---")
                    diag_col1, diag_col2 = st.columns(2)
                    with diag_col1:
                        st.markdown("##### 3. Diagnostic Root-Cause (Why Marks Were Lost)")
                        st.caption("Pinpoint the foundational failure mode:")
                        rc_options = [
                            "Prerequisite Deficit (Prior Years)",
                            "Conceptual / Theory Void",
                            "Reading / Setup Trap",
                            "Careless / Algebraic Slip",
                            "Exam Pacing / Time Pressure",
                            "Formula / Rule Misapplied"
                        ]
                        sel_rc = st.multiselect("Diagnosed Error Types:", rc_options, default=["Careless / Algebraic Slip"])
                        stumble_note = st.text_input("Specific Stumbling Block", placeholder="e.g. Dropped negative sign during dot product expansion")

                    with diag_col2:
                        st.markdown("##### 4. Tutor Intervention & Strategy Applied")
                        st.caption("What did you do to help the student conquer it?")
                        iv_options = [
                            "Stepped Algorithm / Deconstruction",
                            "Visual / Geometric Sketch / Diagram",
                            "Concrete Counter-Example",
                            "Formula Derivation & Cheat-Sheet Mapping",
                            "Targeted Drill on Prerequisite Skill",
                            "Timed Exam Condition Re-test"
                        ]
                        sel_iv = st.multiselect("Pedagogical Interventions:", iv_options, default=["Stepped Algorithm / Deconstruction", "Visual / Geometric Sketch / Diagram"])

                    st.markdown("---")
                    att_col1, att_col2 = st.columns(2)
                    with att_col1:
                        st.markdown("##### 5. Learning Attributes (Scale: 1 Low -> 5 High)")
                        sc_eng = st.select_slider("Engagement & Focus", options=[1, 2, 3, 4, 5], value=4)
                        sc_conf = st.select_slider("Confidence in Answering", options=[1, 2, 3, 4, 5], value=4)
                        sc_ind = st.select_slider("Independent Problem Solving", options=[1, 2, 3, 4, 5], value=4)
                        tutor_obs = st.text_input("Tutor Observations", placeholder="e.g. Sharp work pace, asked perceptive questions.")

                    with att_col2:
                        st.markdown("##### 6. Attention & Escalation Flags (Director Alert)")
                        st.caption("Flag any immediate concerns requiring management attention:")
                        flag_choice = st.selectbox(
                            "Escalation Flag:",
                            [
                                ("all_clear", "🟢 All Clear (On Track)"),
                                ("homework_missing", "🟡 Homework Incomplete / Missing"),
                                ("exam_urgency", "🟠 Upcoming School Exam Urgency"),
                                ("deficit_remedial", "🔴 Foundational Deficit (Remedial Pack Needed)"),
                                ("anxiety_disengagement", "🟣 Low Motivation / Exam Anxiety")
                            ],
                            format_func=lambda x: x[1]
                        )[0]
                        flag_notes = st.text_input("Director Attention Notes (if flagged)", placeholder="e.g. Needs revision pack on index laws before next week.")

                    st.markdown("---")
                    st.markdown("##### 7. What Happens Next (Actionable Follow-through)")
                    nxt_c1, nxt_c2, nxt_c3 = st.columns([2.5, 1, 1])
                    with nxt_c1:
                        hw_assigned = st.text_input("Homework Assigned", placeholder="e.g. Exercise 4B Q1-8 + DA Vector Drill")
                    with nxt_c2:
                        hw_due = st.text_input("Due Date", value=f"Next Lesson ({term_num}W{week_num+1 if week_num < 10 else 1})")
                    with nxt_c3:
                        target_acc = st.text_input("Target Accuracy", value="85%")

                    next_priority = st.text_input("Next Lesson Priority", placeholder="e.g. Vector Projections and 3D Direction Cosines")

                    st.markdown("---")
                    st.markdown("##### 8. The Parent Soundbite (For Director Parent Queries)")
                    st.caption("A 1-sentence synthesis a Director can quote word-for-word over the phone when a parent asks *'How is my child going?'*")
                    default_soundbite = f"Today, {sel_student} demonstrated strong understanding of {topic_input if topic_input else 'key concepts'}; our focus for next week is reinforcing independent problem solving under exam timing."
                    parent_soundbite_val = st.text_area("Parent Soundbite (1 Sentence)", value=default_soundbite, height=70)

                    st.markdown("---")
                    st.markdown("##### 9. Student 45-Second Reflection Pulse")
                    st.caption("To be answered by the student at the end of the lesson (or transcribed by tutor):")
                    st_c1, st_c2 = st.columns(2)
                    with st_c1:
                        s_clarity = st.selectbox("1. My tutor's explanations today were:", ["Crystal Clear", "Mostly Clear", "Cloudy"], index=0)
                        s_support = st.selectbox("2. When I was stuck or made mistakes, I felt:", ["Very Supported", "Okay", "Stressed"], index=0)
                        s_questions = st.selectbox("3. I felt comfortable asking questions:", ["Always (100%)", "Sometimes", "Hesitant"], index=0)
                    with st_c2:
                        s_diff = st.selectbox("4. Today's difficulty level was:", ["Sweet Spot", "Too Easy", "Overwhelming"], index=0)
                        s_conf = st.selectbox("5. Compared to when I arrived, my confidence:", ["Higher", "Same", "Lower"], index=0)
                        s_note = st.text_input("6. Student request/goal for next lesson:", placeholder="e.g. Do 1 hard HSC exam proof together")

                    submit_cover_sheet = st.form_submit_button("💾 Save Lesson Cover Sheet & Generate A4 PDF", type="primary", use_container_width=True)

                    if submit_cover_sheet:
                        if not topic_input.strip():
                            st.error("Please provide at least a Topic name.")
                        else:
                            sheet_payload = {
                                "student_name": sel_student,
                                "class_id": sel_class_id,
                                "tutor_id": current_user_id,
                                "term": term_num,
                                "week": week_num,
                                "lesson_date": lesson_date.strftime("%Y-%m-%d"),
                                "subject": subject_choice,
                                "topic": topic_input,
                                "subtopic": subtopic_input,
                                "syllabus_outcomes": outcome_input,
                                "materials_used": sel_materials,
                                "mastery_data": mastery_entries if mastery_entries else [{"concept": topic_input, "level": "Independent"}],
                                "root_cause_tags": sel_rc,
                                "specific_stumbling_block": stumble_note,
                                "intervention_tags": sel_iv,
                                "score_engagement": sc_eng,
                                "score_confidence": sc_conf,
                                "score_independence": sc_ind,
                                "tutor_observations": tutor_obs,
                                "attention_flag": flag_choice,
                                "attention_notes": flag_notes,
                                "homework_assigned": hw_assigned,
                                "homework_due": hw_due,
                                "target_accuracy": target_acc,
                                "next_lesson_priority": next_priority,
                                "parent_soundbite": parent_soundbite_val,
                                "student_clarity": s_clarity,
                                "student_support": s_support,
                                "student_questions": s_questions,
                                "student_difficulty": s_diff,
                                "student_confidence_shift": s_conf,
                                "student_request_note": s_note
                            }

                            new_id = database.create_lesson_cover_sheet(sheet_payload)
                            sheet_payload["id"] = new_id
                            sheet_payload["class_name"] = sel_class_label
                            sheet_payload["tutor_name"] = current_user["display_name"]

                            pdf_bytes = pdf_generator.generate_lesson_cover_sheet_pdf(sheet_payload, mode="2page")
                            st.session_state["recent_cover_pdf"] = pdf_bytes
                            st.session_state["recent_cover_data"] = sheet_payload
                            st.success(f"🎉 Successfully logged Lesson Cover Sheet #{new_id} for **{sel_student}**!")

                if st.session_state.get("recent_cover_data"):
                    recent_data = st.session_state["recent_cover_data"]
                    st.markdown("##### 📥 Download High School Mathematics Cover Sheet")
                    
                    sel_var = st.radio(
                        "Choose Design Variation:",
                        [
                            "📐 Blueprint Design: Mathematics Years 7–12 (Cobalt & Cyan, Primary Standard)",
                            "🏛️ Variation 1: The Studio Math Journal (Slate Navy & Amber, Warm Editorial)",
                            "⚡ Variation 3: The High-Yield Exam Sprint (Crimson & Coral, Trial Acceleration)"
                        ],
                        index=0,
                        horizontal=False,
                        key="recent_var_choice"
                    )
                    var_code = "blueprint" if "Blueprint" in sel_var else ("journal" if "Journal" in sel_var else "sprint")

                    d_c1, d_c2 = st.columns(2)
                    with d_c1:
                        pdf_2p = pdf_generator.generate_lesson_cover_sheet_pdf(recent_data, mode="2page", variation=var_code)
                        s_name_clean = str(recent_data.get('student_name', 'Student')).replace('_', ' ')
                        st.download_button(
                            label=f"📄 2-Page Double-Sided PDF ({recent_data.get('student_name')})",
                            data=pdf_2p,
                            file_name=f"MathCover {var_code.title()} {s_name_clean} T{recent_data.get('term')}W{recent_data.get('week')} 2Page.pdf",
                            mime="application/pdf",
                            type="primary",
                            use_container_width=True
                        )
                    with d_c2:
                        pdf_1p = pdf_generator.generate_lesson_cover_sheet_pdf(recent_data, mode="1page", variation=var_code)
                        st.download_button(
                            label=f"📄 1-Page Condensed PDF ({recent_data.get('student_name')})",
                            data=pdf_1p,
                            file_name=f"MathCover {var_code.title()} {s_name_clean} T{recent_data.get('term')}W{recent_data.get('week')} 1Page.pdf",
                            mime="application/pdf",
                            type="secondary",
                            use_container_width=True
                        )

    # -------------------------------------------------------------
    # SUB-TAB 2: DIRECTOR PARENT INQUIRY PORTAL
    # -------------------------------------------------------------
    with lcs_tab_director:
        st.markdown("#### 📞 Director Parent Inquiry & Progress Portal")
        st.caption("When a parent calls asking: *“How has my child been going?”* — this portal provides the 15-second soundbite, multi-week trajectories, and verified mastery evidence.")

        # Student selection scoped by role
        eligible_students = database.get_students_for_user(current_user_id, current_user_role)
        if not eligible_students:
            st.info("No students found in your assigned classes.")
        else:
            student_names = sorted(list(set(s["name"] for s in eligible_students)))
            sel_dir_student = st.selectbox("Select Student for Progress Review:", student_names, key="dir_student_sel")

            metrics = database.get_student_longitudinal_metrics(sel_dir_student)

            if metrics["total_lessons"] == 0:
                st.warning(f"No completed lesson cover sheets found for **{sel_dir_student}** yet. Log a lesson in Tab 1 to populate.")
            else:
                # 15-Second Parent Response Card
                st.markdown(f"##### 🎯 15-Second Parent Response Box")
                latest_sb = metrics.get("latest_soundbite") or "Student has shown steady focus and is mastering core syllabus concepts."
                st.markdown(f"""
                <div style="background-color: #FEF3C7; border: 1.5px solid #F59E0B; border-radius: 8px; padding: 16px; margin-bottom: 16px;">
                    <span style="color: #B45309; font-weight: bold; font-size: 0.9rem; text-transform: uppercase;">Direct Parent Soundbite (Quote this over the phone):</span>
                    <p style="color: #1E293B; font-size: 1.1rem; font-style: italic; margin-top: 8px; margin-bottom: 4px;">
                        "{latest_sb}"
                    </p>
                    <span style="color: #64748B; font-size: 0.8rem;">Latest Lesson: <b>{metrics.get('latest_date')}</b> • Topic: <b>{metrics.get('latest_topic')}</b> • Tutor: <b>{metrics.get('latest_tutor')}</b></span>
                </div>
                """, unsafe_allow_html=True)

                # Key Performance Indicators Row
                m_c1, m_c2, m_c3, m_c4 = st.columns(4)
                m_c1.metric("Total Lessons Logged", f"{metrics['total_lessons']}")
                m_c2.metric("Avg Engagement", f"{metrics['avg_engagement']} / 5.0")
                m_c3.metric("Avg Confidence", f"{metrics['avg_confidence']} / 5.0")
                m_c4.metric("Avg Independence", f"{metrics['avg_independence']} / 5.0")

                # Progression Trajectory Chart
                st.markdown("##### 📈 Multi-Week Learning Trajectory")
                if metrics["chronological_scores"]:
                    chart_df = pd.DataFrame(metrics["chronological_scores"])
                    chart_df.rename(columns={
                        "week_label": "Lesson",
                        "engagement": "Engagement",
                        "confidence": "Confidence",
                        "independence": "Independence"
                    }, inplace=True)
                    st.line_chart(chart_df.set_index("Lesson")[["Engagement", "Confidence", "Independence"]])

                # Diagnostic & Sentiment Insights
                ins_c1, ins_c2 = st.columns(2)
                with ins_c1:
                    st.markdown("##### 🔍 Recurring Error Root-Causes")
                    if metrics["root_cause_freq"]:
                        df_rc = pd.DataFrame(list(metrics["root_cause_freq"].items()), columns=["Root Cause", "Occurrences"])
                        df_rc.sort_values(by="Occurrences", ascending=False, inplace=True)
                        st.dataframe(df_rc, use_container_width=True, hide_index=True)
                    else:
                        st.caption("No root-cause error patterns recorded.")

                with ins_c2:
                    st.markdown("##### 😊 Student Sentiment & Pacing")
                    st.write(f"• **Clarity Ratings:** {metrics.get('sentiment_clarity', {})}")
                    st.write(f"• **Difficulty Sweet-Spot:** {metrics.get('sentiment_difficulty', {})}")
                    
                    if metrics["attention_flags"]:
                        st.error(f"⚠️ **{len(metrics['attention_flags'])} Flagged Alert(s)** in lesson history:")
                        for f_item in metrics["attention_flags"]:
                            st.caption(f"• **{f_item['lesson_date']}** [{f_item['flag']}]: {f_item['notes']}")
                    else:
                        st.success("🟢 No escalation flags recorded — all lessons on track.")

                # Historical Log with PDF Download
                st.markdown("---")
                st.markdown("##### 📁 Past Lesson Cover Sheets Archive")
                past_sheets = database.get_lesson_cover_sheets(student_name=sel_dir_student, limit=20)
                for ps in past_sheets:
                    with st.expander(f"📅 {ps.get('lesson_date')} • Term {ps.get('term')} Wk {ps.get('week')} — {ps.get('topic')}"):
                        p_col1, p_col2 = st.columns([3, 1.2])
                        with p_col1:
                            st.write(f"**Tutor:** {ps.get('tutor_name')} | **Class:** {ps.get('class_name')}")
                            st.write(f"**Parent Soundbite:** *\"{ps.get('parent_soundbite')}\"*")
                            st.write(f"**Homework:** {ps.get('homework_assigned')} (Due: {ps.get('homework_due')})")
                            st.write(f"**Student Reflection:** Clarity: `{ps.get('student_clarity')}` | Support: `{ps.get('student_support')}` | Pace: `{ps.get('student_difficulty')}`")
                        with p_col2:
                            pdf_hist_2p = pdf_generator.generate_lesson_cover_sheet_pdf(ps, mode="2page")
                            st.download_button(
                                label="📥 2-Page PDF",
                                data=pdf_hist_2p,
                                file_name=f"CoverSheet 2Page {sel_dir_student.replace('_', ' ')} {ps.get('lesson_date')}.pdf",
                                mime="application/pdf",
                                key=f"dl_ps_2p_{ps.get('id')}",
                                use_container_width=True
                            )
                            pdf_hist_1p = pdf_generator.generate_lesson_cover_sheet_pdf(ps, mode="1page")
                            st.download_button(
                                label="📥 1-Page PDF",
                                data=pdf_hist_1p,
                                file_name=f"CoverSheet 1Page {sel_dir_student.replace('_', ' ')} {ps.get('lesson_date')}.pdf",
                                mime="application/pdf",
                                key=f"dl_ps_1p_{ps.get('id')}",
                                use_container_width=True
                            )

    # -------------------------------------------------------------
    # SUB-TAB 3: PRINTABLE A4 COVER SHEETS
    # -------------------------------------------------------------
    with lcs_tab_print:
        st.markdown("#### 🖨️ Printable A4 Cover Sheets (Blank & Class Batch)")
        st.caption("For tutors who prefer handwriting their notes on paper during the lesson and keeping physical student folders.")

        p_col1, p_col2 = st.columns(2)
        with p_col1:
            st.markdown("##### 📄 Universal Blank Cover Sheet (High School Maths)")
            st.write("Clean, publication-grade High School Mathematics templates with large readable fonts, rating bubbles, and write-in lines.")
            
            blank_var = st.selectbox(
                "Choose Design Variation:",
                [
                    "📐 Blueprint Design: Mathematics Years 7–12 (Cobalt & Cyan, Primary Standard)",
                    "🏛️ Variation 1: The Studio Math Journal (Slate Navy & Amber, Warm Editorial)",
                    "⚡ Variation 3: The High-Yield Exam Sprint (Crimson & Coral, Trial Acceleration)"
                ],
                index=0,
                key="blank_var_choice"
            )
            b_var_code = "blueprint" if "Blueprint" in blank_var else ("journal" if "Journal" in blank_var else "sprint")

            b_dl1, b_dl2 = st.columns(2)
            with b_dl1:
                blank_2p = pdf_generator.generate_lesson_cover_sheet_pdf(mode="2page", variation=b_var_code)
                st.download_button(
                    label="📥 2-Page Double-Sided",
                    data=blank_2p,
                    file_name=f"DA Math Cover {b_var_code.title()} Blank 2Page.pdf",
                    mime="application/pdf",
                    type="primary",
                    use_container_width=True
                )
            with b_dl2:
                blank_1p = pdf_generator.generate_lesson_cover_sheet_pdf(mode="1page", variation=b_var_code)
                st.download_button(
                    label="📥 1-Page Condensed",
                    data=blank_1p,
                    file_name=f"DA Math Cover {b_var_code.title()} Blank 1Page.pdf",
                    mime="application/pdf",
                    type="secondary",
                    use_container_width=True
                )

        with p_col2:
            st.markdown("##### 👥 Batch Class Roll Cover Sheets")
            st.write("Generate a combined PDF with a personalized cover sheet for every student in your class (pre-printed student name, class, and tutor).")

            user_classes_print = database.get_classes_for_user(current_user_id, current_user_role)
            if user_classes_print:
                cls_print_map = {f"{c['name']} ({c['year_level']})": c['id'] for c in user_classes_print}
                sel_p_class = st.selectbox("Select Class to Batch Print:", list(cls_print_map.keys()), key="print_batch_class")
                sel_p_cid = cls_print_map[sel_p_class]
                
                b_c1, b_c2, b_c3 = st.columns(3)
                with b_c1:
                    batch_term = st.selectbox("Term for Batch:", [1, 2, 3, 4], index=0, key="batch_term")
                with b_c2:
                    batch_week = st.selectbox("Week for Batch:", list(range(1, 11)), index=0, key="batch_week")
                with b_c3:
                    batch_mode = st.selectbox("Format:", ["2-Page Double-Sided", "1-Page Condensed"], index=0, key="batch_mode")

                batch_var_sel = st.selectbox(
                    "Design Variation for Batch:",
                    [
                        "📐 Blueprint Design: Mathematics Years 7–12 (Cobalt & Cyan, Primary Standard)",
                        "🏛️ Variation 1: The Studio Math Journal (Slate Navy & Amber, Warm Editorial)",
                        "⚡ Variation 3: The High-Yield Exam Sprint (Crimson & Coral, Trial Acceleration)"
                    ],
                    index=0,
                    key="batch_var_sel"
                )
                b_var_code_batch = "blueprint" if "Blueprint" in batch_var_sel else ("journal" if "Journal" in batch_var_sel else "sprint")

                if st.button("Generate Batch Class Cover Sheets", type="secondary", use_container_width=True):
                    b_students = database.get_class_students(sel_p_cid)
                    if not b_students:
                        st.warning("No students in this class.")
                    else:
                        from pypdf import PdfWriter, PdfReader
                        from io import BytesIO
                        
                        writer = PdfWriter()
                        pdf_mode_code = "2page" if "2-Page" in batch_mode else "1page"
                        for s_name in b_students:
                            single_data = {
                                "student_name": s_name,
                                "class_name": sel_p_class,
                                "tutor_name": current_user["display_name"],
                                "term": batch_term,
                                "week": batch_week,
                                "lesson_date": datetime.now().strftime("%Y-%m-%d"),
                                "subject": "Mathematics"
                            }
                            single_pdf = pdf_generator.generate_lesson_cover_sheet_pdf(single_data, mode=pdf_mode_code, variation=b_var_code_batch)
                            reader = PdfReader(BytesIO(single_pdf))
                            for page in reader.pages:
                                writer.add_page(page)

                        out_batch = BytesIO()
                        writer.write(out_batch)
                        batch_bytes = out_batch.getvalue()

                        total_pages = len(writer.pages)
                        st.success(f"🎉 Generated batch PDF ({total_pages} pages, {len(b_students)} students) in {b_var_code_batch.title()} style!")
                        st.download_button(
                            label=f"📥 Download Class Batch PDF ({total_pages} Pages)",
                            data=batch_bytes,
                            file_name=f"ClassBatch MathCover {b_var_code_batch.title()} {sel_p_class.split(' ')[0]} T{batch_term}W{batch_week} {pdf_mode_code}.pdf",
                            mime="application/pdf",
                            type="primary",
                            use_container_width=True
                        )
