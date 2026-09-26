import os
import time
import json
import uuid
import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime

_confirmed_missing_columns = set()

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import streamlit as st
except ImportError:
    st = None

try:
    from supabase import create_client, Client
except ImportError:
    Client = None
    create_client = None

def get_supabase_creds() -> Tuple[str, str]:
    """
    Reads Supabase URL and Key from environment or Streamlit secrets.
    Prefers service_role key to bypass RLS for administrative tutor storage.
    """
    sb_url = os.environ.get("SUPABASE_URL", "")
    sb_key = ""

    if st and hasattr(st, "secrets"):
        try:
            sb_url = st.secrets.get("SUPABASE_URL", sb_url) or sb_url
            sb_key = (
                st.secrets.get("SUPABASE_SERVICE_ROLE_KEY", "")
                or st.secrets.get("SUPABASE_SERVICE_KEY", "")
                or st.secrets.get("SUPABASE_KEY", "")
            )
        except Exception:
            pass

    if not sb_key:
        sb_key = (
            os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
            or os.environ.get("SUPABASE_SERVICE_KEY", "")
            or os.environ.get("SUPABASE_KEY", "")
        )

    return sb_url.strip(), sb_key.strip()

_cached_client: Optional[Any] = None

def get_supabase_client() -> Optional[Any]:
    global _cached_client
    if _cached_client is not None:
        return _cached_client
    if create_client is None:
        return None
    url, key = get_supabase_creds()
    if url and key:
        try:
            _cached_client = create_client(url, key)
            return _cached_client
        except Exception as e:
            print(f"[cloud_sync] Supabase initialization error: {e}")
            return None
    return None

def is_cloud_connected() -> bool:
    return get_supabase_client() is not None

def fetch_cloud_exams(search_query: str = "", year_level: str = "", limit: int = 50) -> List[Dict[str, Any]]:
    client = get_supabase_client()
    if not client:
        return []
    try:
        query = client.table("saved_exams").select("*").order("created_at", desc=True)
        if year_level and year_level != "All":
            query = query.ilike("year", f"%{year_level}%")
        res = query.limit(limit).execute()
        rows = res.data or []
        if search_query:
            sq = search_query.lower()
            rows = [
                r for r in rows
                if sq in str(r.get("topic", "")).lower()
                or sq in str(r.get("subject", "")).lower()
                or sq in str(r.get("teacher_name", "")).lower()
            ]
        return rows
    except Exception as e:
        print(f"[cloud_sync] Error fetching cloud exams: {e}")
        return []

def _get_exam_cost_info(exam: Dict[str, Any]) -> Tuple[float, str]:
    """Extract stored cost or compute an accurate estimate using Gemini Flash rates in AUD."""
    if exam.get("cost") is not None:
        try:
            return float(exam["cost"]), str(exam.get("model") or "gemini-2.5-flash")
        except (ValueError, TypeError):
            pass

    num_q = exam.get("num_questions") or 10
    est_in_tokens = 6500
    est_out_tokens = (num_q * 220) + 500
    est_cost_usd = ((est_in_tokens / 1_000_000) * 0.30) + ((est_out_tokens / 1_000_000) * 2.50)
    est_cost_aud = est_cost_usd * 1.55
    return round(est_cost_aud, 5), str(exam.get("model") or "gemini-2.5-flash")

def get_exam_instructions(pdf_url: str, db_instructions: str = "") -> str:
    """Retrieve instructions from db field or storage companion file."""
    if db_instructions and str(db_instructions).strip():
        return str(db_instructions).strip()
    client = get_supabase_client()
    if not pdf_url or not client:
        return ""
    try:
        storage_path = urllib.parse.unquote(pdf_url.split("/exam-files/")[-1].split("?")[0])
        if storage_path.endswith(".pdf"):
            instr_path = storage_path[:-4] + "_instructions.txt"
            res = client.storage.from_("exam-files").download(instr_path)
            if res:
                return res.decode("utf-8").strip()
    except Exception:
        pass
    return ""

def save_exam_instructions(exam_id: Any, pdf_url: str, instructions_text: str) -> bool:
    """Persist instructions to storage file and database."""
    client = get_supabase_client()
    if not client:
        return False
    clean_text = instructions_text.strip()
    if pdf_url:
        try:
            storage_path = urllib.parse.unquote(pdf_url.split("/exam-files/")[-1].split("?")[0])
            if storage_path.endswith(".pdf"):
                instr_path = storage_path[:-4] + "_instructions.txt"
                client.storage.from_("exam-files").upload(
                    instr_path,
                    clean_text.encode("utf-8"),
                    {"content-type": "text/plain; charset=utf-8", "upsert": "true"},
                )
        except Exception as e:
            print(f"[cloud_sync] save_exam_instructions storage error: {e}")

    for col_name in ("extra_instructions", "instructions"):
        try:
            client.table("saved_exams").update({col_name: clean_text}).eq("id", exam_id).execute()
            break
        except Exception:
            pass

    return True

def save_exam_to_cloud(
    subject: str,
    year_level: str,
    topic: str,
    teacher_name: str,
    pdf_bytes: Optional[bytes] = None,
    docx_bytes: Optional[bytes] = None,
    difficulty: str = "Medium",
    num_questions: int = 10,
    set_number: int = 1,
    content_text: str = "",
    answers_text: str = "",
    solutions_text: str = "",
    extra_instructions: str = "",
    cost: Optional[float] = None,
    model: Optional[str] = None
) -> Tuple[bool, str]:
    """
    Uploads generated PDF and DOCX to Supabase Storage ('exam-files')
    and creates a record in the 'saved_exams' table.
    """
    client = get_supabase_client()
    if not client:
        return False, "Supabase is not connected. Add SUPABASE_URL and SUPABASE_KEY to your settings."

    try:
        clean_topic = urllib.parse.quote(topic.replace(" ", "_").replace("/", "-")[:40])
        clean_year = urllib.parse.quote(year_level.replace(" ", "_")[:20])
        clean_subj = urllib.parse.quote(subject.replace(" ", "_")[:20])
        timestamp = int(time.time())
        file_base = f"{clean_topic}_Set{set_number}_{timestamp}"

        pdf_url = ""
        docx_url = ""

        # Upload files sequentially with retry for bulletproof reliability under macOS / Supabase client
        if pdf_bytes:
            pdf_storage_path = f"{clean_subj}/{clean_year}/{file_base}.pdf"
            for attempt in range(3):
                try:
                    client.storage.from_("exam-files").upload(
                        pdf_storage_path,
                        pdf_bytes,
                        {"content-type": "application/pdf", "upsert": "true"}
                    )
                    break
                except Exception as up_err:
                    if attempt < 2 and ("35" in str(up_err) or "temporary" in str(up_err).lower() or "resource" in str(up_err).lower()):
                        time.sleep(0.5 * (attempt + 1))
                        continue
                    raise up_err
            base_pdf_url = client.storage.from_("exam-files").get_public_url(pdf_storage_path)
            pdf_url = f"{base_pdf_url}?t={timestamp}"

        if docx_bytes:
            docx_storage_path = f"{clean_subj}/{clean_year}/{file_base}.docx"
            try:
                client.storage.from_("exam-files").upload(
                    docx_storage_path,
                    docx_bytes,
                    {"content-type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "upsert": "true"}
                )
                base_docx_url = client.storage.from_("exam-files").get_public_url(docx_storage_path)
                docx_url = f"{base_docx_url}?t={timestamp}"
            except Exception as d_err:
                print(f"[cloud_sync] Companion DOCX upload notice: {d_err}")

        if extra_instructions and extra_instructions.strip():
            try:
                instr_storage_path = f"{clean_subj}/{clean_year}/{file_base}_instructions.txt"
                client.storage.from_("exam-files").upload(
                    instr_storage_path,
                    extra_instructions.strip().encode("utf-8"),
                    {"content-type": "text/plain; charset=utf-8", "upsert": "true"}
                )
            except Exception as ex_err:
                print(f"[cloud_sync] Companion instructions upload notice: {ex_err}")

        payload = {
            "subject": subject,
            "year": year_level,
            "topic": topic,
            "teacher_name": teacher_name or "DA Tutor",
            "num_questions": num_questions,
            "difficulty": difficulty,
            "set_number": set_number,
            "pdf_url": pdf_url,
            "docx_url": docx_url,
            "created_at": datetime.utcnow().isoformat()
        }

        # Only add optional fields when non-empty to avoid triggering missing column errors unnecessarily
        if content_text and content_text.strip():
            payload["content"] = content_text[:10000].strip()
        if answers_text and answers_text.strip():
            payload["answers"] = answers_text[:5000].strip()
        if solutions_text and solutions_text.strip():
            payload["solutions"] = solutions_text[:10000].strip()
        if extra_instructions and extra_instructions.strip():
            payload["extra_instructions"] = extra_instructions[:10000].strip()
            payload["instructions"] = extra_instructions[:10000].strip()
        if cost is not None:
            payload["cost"] = float(cost)
        if model:
            payload["model"] = str(model)

        # Preemptively strip confirmed missing columns to avoid round-trip rejection delays
        for col in list(payload.keys()):
            if col in _confirmed_missing_columns:
                payload.pop(col, None)

        # Resilient insertion: dynamically drop unrecognized columns if remote schema cache lacks them
        max_retries = 10
        for attempt in range(max_retries):
            try:
                client.table("saved_exams").insert(payload).execute()
                break
            except Exception as e:
                err_str = str(e)
                # 1. PostgREST PGRST204: Could not find the '<col>' column of 'saved_exams' in the schema cache
                col_match = re.search(r"Could not find the '([^']+)' column", err_str, re.IGNORECASE)
                if col_match:
                    missing_col = col_match.group(1)
                    _confirmed_missing_columns.add(missing_col)
                    if missing_col in payload:
                        print(f"[cloud_sync] Column '{missing_col}' not in saved_exams schema cache; dropping and retrying...")
                        payload.pop(missing_col, None)
                        continue

                # 2. Check for explicit column mentions in Postgres / PostgREST error messages
                dropped_col = None
                for col in ["answers", "solutions", "content", "docx_url", "extra_instructions", "instructions", "cost", "model", "difficulty", "set_number", "num_questions"]:
                    if col in payload and col in err_str.lower():
                        dropped_col = col
                        _confirmed_missing_columns.add(dropped_col)
                        break
                if dropped_col:
                    print(f"[cloud_sync] Dropping column '{dropped_col}' due to remote schema mismatch and retrying...")
                    payload.pop(dropped_col, None)
                    continue

                # If no unrecognized column could be determined, re-raise the exception
                raise e

        return True, "Successfully saved to DA Tuition Cloud Library!"
    except Exception as e:
        print(f"[cloud_sync] Error saving exam to cloud: {e}")
        return False, f"Cloud upload failed: {str(e)}"

def delete_cloud_exam(exam_id: Any, pdf_url: str = "", docx_url: str = "") -> bool:
    client = get_supabase_client()
    if not client:
        return False
    try:
        paths_to_delete = []
        for u in [pdf_url, docx_url]:
            if u and "/exam-files/" in u:
                raw_path = u.split("/exam-files/")[-1].split("?")[0]
                p_path = urllib.parse.unquote(raw_path)
                paths_to_delete.append(p_path)
                if p_path.endswith(".pdf"):
                    paths_to_delete.append(p_path[:-4] + "_instructions.txt")
        if paths_to_delete:
            try:
                client.storage.from_("exam-files").remove(paths_to_delete)
            except Exception:
                pass
        client.table("saved_exams").delete().eq("id", exam_id).execute()
        return True
    except Exception as e:
        print(f"[cloud_sync] Error deleting cloud exam: {e}")
        return False

def render_cloud_exam_library(current_user: Optional[Dict[str, Any]] = None, is_admin: bool = False):
    """
    Renders the interactive Cloud Exam Library in Streamlit.
    Allows tutors to search, filter, preview, and download exams shared across branches.
    """
    import streamlit as st

    st.markdown("### ☁️ DA Tuition Cloud Exam Library")
    st.caption("Browse, search, and download curriculum-aligned exams and practice worksheets shared by DA Tuition tutors across all branches. Stored securely in Supabase Cloud with both print-ready PDF and editable Microsoft Word (.docx) copies.")

    if not is_cloud_connected():
        st.warning("⚠️ **DA Cloud Sync is currently offline.** All worksheets and theory booklets are currently being saved locally on your computer.")
        st.info(
            "💡 **Why connect Supabase Cloud?**\n\n"
            "- **Cross-Branch Sharing**: Worksheets and theory booklets generated at Burwood, Parramatta, Chatswood, etc., can be shared across all DA tutors.\n"
            "- **Dual Formats**: Automatically archives both vector PDFs (for printing) and Microsoft Word .docx files (for custom editing).\n"
            "- **Centralized Search**: Instant search by syllabus topic, year level, difficulty, or author tutor."
        )

        if is_admin:
            with st.expander("🔑 Connect to Supabase Cloud", expanded=True):
                st.caption("Paste your Supabase Project URL and Service / Anon Key below to activate cloud syncing across tutors.")
                cur_url, cur_key = get_supabase_creds()
                in_url = st.text_input("Supabase Project URL", value=cur_url, placeholder="https://xyz.supabase.co", key="cloud_tab_url_in")
                in_key = st.text_input("Supabase Key (Service Role or Anon)", value=cur_key, type="password", placeholder="eyJ...", key="cloud_tab_key_in")
                if st.button("Connect & Save Credentials", key="btn_connect_sb_cloud_tab", use_container_width=True):
                    if in_url.strip() and in_key.strip():
                        global _cached_client
                        os.environ["SUPABASE_URL"] = in_url.strip()
                        os.environ["SUPABASE_SERVICE_ROLE_KEY"] = in_key.strip()
                        _cached_client = None
                        try:
                            env_path = os.path.join(os.path.dirname(__file__), ".env")
                            with open(env_path, "a", encoding="utf-8") as f:
                                f.write(f"\nSUPABASE_URL={in_url.strip()}\nSUPABASE_SERVICE_ROLE_KEY={in_key.strip()}\n")
                        except Exception:
                            pass
                        st.success("Credentials saved! Reconnecting to DA Cloud Library...")
                        st.rerun()
                    else:
                        st.error("Please enter both the Supabase URL and Key.")

        with st.expander("🛠️ Supabase Database & Storage Setup Instructions", expanded=False):
            st.markdown(
                """
                If you are setting up a new Supabase project for DA Tuition, run this SQL in your Supabase SQL Editor:
                ```sql
                create table if not exists saved_exams (
                    id bigint generated by default as identity primary key,
                    subject text not null,
                    year text not null,
                    topic text not null,
                    teacher_name text default 'DA Tutor',
                    num_questions int default 10,
                    difficulty text default 'Medium',
                    set_number int default 1,
                    pdf_url text,
                    docx_url text,
                    content text,
                    answers text,
                    solutions text,
                    extra_instructions text,
                    cost numeric,
                    model text,
                    created_at timestamp with time zone default timezone('utc'::text, now()) not null
                );
                ```

                **Existing Table Migration (Fix missing column warnings):**
                ```sql
                alter table saved_exams add column if not exists answers text;
                alter table saved_exams add column if not exists solutions text;
                alter table saved_exams add column if not exists content text;
                alter table saved_exams add column if not exists docx_url text;
                alter table saved_exams add column if not exists extra_instructions text;
                alter table saved_exams add column if not exists instructions text;
                alter table saved_exams add column if not exists cost numeric;
                alter table saved_exams add column if not exists model text;
                ```
                And in **Supabase Storage**, ensure you have a public bucket named `exam-files`.
                """
            )
        return

    # Connected state
    c_status, c_refresh = st.columns([4, 1])
    with c_status:
        st.success("🟢 **Connected to Supabase Cloud Storage** (`exam-files` bucket & `saved_exams` table)")
    with c_refresh:
        if st.button("🔄 Refresh Library", key="btn_refresh_cloud_exams", use_container_width=True):
            st.rerun()

    # Search & filters
    col_q, col_yr, col_lim = st.columns([2.5, 1.5, 1])
    with col_q:
        search_q = st.text_input(
            "Search Cloud Library",
            placeholder="Search by topic, subject, or tutor name...",
            label_visibility="collapsed",
            key="input_cloud_search"
        )
    with col_yr:
        year_filter_options = [
            "All", "Year 7", "Year 8", "Year 9", "Year 10",
            "Year 11 Advanced", "Year 11 Standard", "Year 11 Extension",
            "Year 12 Advanced", "Year 12 Standard", "Year 12 Extension 1", "Year 12 Extension 2"
        ]
        chosen_year = st.selectbox("Year Level", year_filter_options, index=0, key="select_cloud_year")
    with col_lim:
        chosen_limit = st.selectbox("Show", [10, 25, 50, 100], index=2, key="select_cloud_limit")

    exams = fetch_cloud_exams(search_query=search_q, year_level=chosen_year, limit=chosen_limit)

    if not exams:
        st.info("🔍 No exams match your search query in the DA Cloud Library. When tutors generate worksheets and click **'Save to DA Cloud Library'**, they will appear here.")
        return

    st.markdown(f"**Found {len(exams)} exam(s) in Cloud Library:**")

    for ex in exams:
        exam_id = ex.get("id")
        topic = ex.get("topic", "Worksheet")
        subject = ex.get("subject", "Maths")
        year = ex.get("year", "Year 10")
        tutor = ex.get("teacher_name", "DA Tutor")
        set_num = ex.get("set_number") or 1
        num_q = ex.get("num_questions", 0)
        created = str(ex.get("created_at", ""))[:10]
        pdf_url = ex.get("pdf_url", "")
        docx_url = ex.get("docx_url", "")
        diff = ex.get("difficulty", "Medium")

        cost_val, model_val = _get_exam_cost_info(ex)
        cost_badge = f"${cost_val:.4f} AUD"

        with st.expander(f"📄 {topic} (Set {set_num}) — {year} • by {tutor} • 💸 {cost_badge}", expanded=False):
            st.caption(f"📅 **Uploaded:** {created} &nbsp;|&nbsp; 👤 **Tutor:** {tutor} &nbsp;|&nbsp; 💸 **Cost:** `{cost_badge}` &nbsp;|&nbsp; 🤖 **Engine:** `{model_val}`")
            m_col1, m_col2, m_col3 = st.columns(3)
            with m_col1:
                st.markdown(f"**Subject:** {subject}")
                st.markdown(f"**Year Level:** {year}")
            with m_col2:
                st.markdown(f"**Difficulty:** {diff}")
                st.markdown(f"**Questions:** {num_q}")
            with m_col3:
                st.markdown(f"**Author Tutor:** {tutor}")
                st.markdown(f"**Uploaded:** {created}")

            st.markdown("---")
            d_col1, d_col2, d_col3 = st.columns([1.5, 1.5, 1])
            with d_col1:
                if pdf_url:
                    st.link_button("📥 Open / Download PDF", pdf_url, use_container_width=True)
                else:
                    st.caption("No PDF link available")
            with d_col2:
                if docx_url:
                    st.link_button("📄 Open / Download Word (.docx)", docx_url, use_container_width=True)
                else:
                    st.caption("No Word docx link available")
            with d_col3:
                can_delete = is_admin or (current_user and current_user.get("display_name") == tutor)
                if can_delete:
                    if st.button("🗑️ Remove", key=f"btn_del_cloud_{exam_id}", type="secondary", use_container_width=True):
                        ok = delete_cloud_exam(exam_id, pdf_url, docx_url)
                        if ok:
                            st.success(f"Removed '{topic}' from Cloud Library.")
                            st.rerun()
                        else:
                            st.error("Failed to delete exam from Cloud Library.")

            # --- EXTRA INSTRUCTIONS SECTION ---
            instr_text = get_exam_instructions(
                pdf_url,
                ex.get("extra_instructions") or ex.get("instructions") or ""
            )

            if instr_text:
                st.markdown("---")
                st.markdown("##### 💬 Extra Instructions Used")
                st.code(instr_text, language="text")
                c_reuse, _ = st.columns([2, 3])
                with c_reuse:
                    if st.button("✨ Load Instructions into Generator", key=f"reuse_cloud_instr_{exam_id}", type="primary", use_container_width=True):
                        st.session_state["extra_instructions_input"] = instr_text
                        st.session_state["active_tab_index"] = 0
                        st.rerun()

            with st.expander("✏️ Edit Instructions" if instr_text else "➕ Add Instructions / Notes"):
                edit_box = st.text_area("Instructions / Notes", value=instr_text, key=f"edit_box_cloud_{exam_id}", placeholder="e.g. Focus on finding vertex, quadratic formula, word problems...")
                if st.button("💾 Save Instructions", key=f"save_btn_cloud_{exam_id}"):
                    with st.spinner("Saving instructions..."):
                        save_exam_instructions(exam_id, pdf_url, edit_box)
                        st.success("Instructions updated!")
                        st.rerun()

            if ex.get("content"):
                with st.expander("👁️ Preview Exam Content / Questions", expanded=False):
                    st.markdown(ex["content"])
            if ex.get("solutions"):
                with st.expander("💡 Preview Worked Solutions", expanded=False):
                    st.markdown(ex["solutions"])

