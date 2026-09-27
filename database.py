import sqlite3
import json
import os
import hashlib
import secrets
import threading
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

DB_FILE = os.path.join(os.path.dirname(__file__), "da_tuition.db")
_db_init_lock = threading.Lock()
_initialized_dbs = set()

def get_connection():
    conn = sqlite3.connect(DB_FILE, timeout=30.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=30000;")
    except Exception:
        pass
    return conn

# --- Cryptographic Password Security ---
def hash_password(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
    """Hashes a password using PBKDF2-HMAC-SHA256 with 100,000 iterations and a random salt."""
    if salt is None:
        salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    )
    return key.hex(), salt

def verify_password(password: str, password_hash: str, salt: str) -> bool:
    """Verifies a password against a stored PBKDF2 hash using constant-time comparison."""
    computed_hash, _ = hash_password(password, salt)
    return secrets.compare_digest(computed_hash, password_hash)

def init_db(force: bool = False):
    global _initialized_dbs
    abs_path = os.path.abspath(DB_FILE)
    if not force and abs_path in _initialized_dbs and os.path.exists(abs_path):
        return

    with _db_init_lock:
        if not force and abs_path in _initialized_dbs and os.path.exists(abs_path):
            return
        conn = get_connection()
        cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        salt TEXT NOT NULL,
        display_name TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'tutor', -- 'admin' or 'tutor'
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS classes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        year_level TEXT,
        teacher_name TEXT,
        schedule_time TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS class_students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        class_id INTEGER NOT NULL,
        student_name TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(class_id) REFERENCES classes(id),
        UNIQUE(class_id, student_name)
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS worksheets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        term INTEGER,
        week INTEGER,
        year_level TEXT,
        topic TEXT,
        difficulty TEXT,
        total_questions INTEGER,
        questions_json TEXT,
        marking_key_json TEXT,
        set_number INTEGER,
        source_theory_id INTEGER,
        assessment_type TEXT DEFAULT 'homework',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    try:
        cursor.execute("ALTER TABLE worksheets ADD COLUMN set_number INTEGER")
    except sqlite3.OperationalError:
        pass

    for col, col_type in [
        ("custom_instructions", "TEXT"), ("cost", "REAL"), ("model", "TEXT"), ("tokens", "INTEGER"),
        ("source_theory_id", "INTEGER"), ("assessment_type", "TEXT DEFAULT 'homework'")
    ]:
        try:
            cursor.execute(f"ALTER TABLE worksheets ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError:
            pass

    try:
        cursor.execute("ALTER TABLE users ADD COLUMN api_key TEXT")
    except sqlite3.OperationalError:
        pass

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS theory_booklets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        term INTEGER,
        week INTEGER,
        year_level TEXT,
        topic TEXT,
        content_json TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS review_booklets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        term INTEGER,
        week INTEGER,
        year_level TEXT,
        topic TEXT,
        content_json TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS exam_packages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        term INTEGER,
        week INTEGER,
        year_level TEXT,
        topic TEXT,
        content_json TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        year_level TEXT,
        class_name TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS submissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        worksheet_id INTEGER,
        student_id INTEGER,
        class_id INTEGER,
        student_name TEXT NOT NULL,
        raw_file_name TEXT,
        score REAL,
        total_marks REAL,
        accuracy_pct REAL,
        pdf_report_path TEXT,
        summary_text TEXT,
        graded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(worksheet_id) REFERENCES worksheets(id),
        FOREIGN KEY(student_id) REFERENCES students(id),
        FOREIGN KEY(class_id) REFERENCES classes(id)
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS mistakes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        submission_id INTEGER,
        student_name TEXT NOT NULL,
        worksheet_id INTEGER,
        class_id INTEGER,
        question_num TEXT,
        topic TEXT,
        subtopic TEXT,
        status TEXT, -- 'Incorrect', 'Partial', 'Missing'
        marks_lost REAL DEFAULT 1.0,
        student_answer TEXT,
        correct_answer TEXT,
        error_type TEXT,
        details TEXT,
        concept_name TEXT,
        cognitive_level TEXT,
        FOREIGN KEY(submission_id) REFERENCES submissions(id),
        FOREIGN KEY(worksheet_id) REFERENCES worksheets(id),
        FOREIGN KEY(class_id) REFERENCES classes(id)
    );
    """)

    for col, col_type in [("concept_name", "TEXT"), ("cognitive_level", "TEXT")]:
        try:
            cursor.execute(f"ALTER TABLE mistakes ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError:
            pass

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS lesson_cover_sheets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_name TEXT NOT NULL,
        class_id INTEGER,
        tutor_id INTEGER,
        term INTEGER DEFAULT 1,
        week INTEGER DEFAULT 1,
        lesson_date TEXT,
        subject TEXT DEFAULT 'Maths',
        topic TEXT NOT NULL,
        subtopic TEXT,
        syllabus_outcomes TEXT,
        materials_used TEXT,
        mastery_data TEXT,
        root_cause_tags TEXT,
        specific_stumbling_block TEXT,
        intervention_tags TEXT,
        score_engagement INTEGER DEFAULT 4,
        score_confidence INTEGER DEFAULT 4,
        score_independence INTEGER DEFAULT 4,
        tutor_observations TEXT,
        attention_flag TEXT DEFAULT 'all_clear',
        attention_notes TEXT,
        homework_assigned TEXT,
        homework_due TEXT,
        target_accuracy TEXT,
        next_lesson_priority TEXT,
        parent_soundbite TEXT,
        student_clarity TEXT DEFAULT 'Crystal Clear',
        student_support TEXT DEFAULT 'Very Supported',
        student_questions TEXT DEFAULT 'Always (100%)',
        student_difficulty TEXT DEFAULT 'Sweet Spot',
        student_confidence_shift TEXT DEFAULT 'Higher',
        student_request_note TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(class_id) REFERENCES classes(id),
        FOREIGN KEY(tutor_id) REFERENCES users(id)
    );
    """)

    # Safe column migrations if database already existed
    try:
        cursor.execute("ALTER TABLE submissions ADD COLUMN class_id INTEGER;")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE mistakes ADD COLUMN class_id INTEGER;")
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE classes ADD COLUMN tutor_id INTEGER REFERENCES users(id);")
    except Exception:
        pass

    # Default User Seeding & Class Linkage (idempotent and race-condition proof)
    admin_id = None
    admin_hash, admin_salt = hash_password("password123")
    tutor_hash, tutor_salt = hash_password("password123")

    cursor.execute("""
        INSERT OR IGNORE INTO users (username, password_hash, salt, display_name, role)
        VALUES (?, ?, ?, ?, ?)
    """, ("bunsea", admin_hash, admin_salt, "Mr. Bunsea", "admin"))

    cursor.execute("""
        INSERT OR IGNORE INTO users (username, password_hash, salt, display_name, role)
        VALUES (?, ?, ?, ?, ?)
    """, ("tutor_david", tutor_hash, tutor_salt, "Mr. David", "tutor"))

    cursor.execute("SELECT id FROM users WHERE username = 'bunsea' LIMIT 1")
    adm_row = cursor.fetchone()
    if adm_row:
        admin_id = adm_row['id']
    else:
        cursor.execute("SELECT id FROM users WHERE role = 'admin' ORDER BY id ASC LIMIT 1")
        fallback_adm = cursor.fetchone()
        if fallback_adm:
            admin_id = fallback_adm['id']

    # Link any unlinked classes to the primary admin account
    if admin_id is not None:
        cursor.execute("UPDATE classes SET tutor_id = ? WHERE tutor_id IS NULL", (admin_id,))

    # Performance Indexes for Instant Tab & Analytics Queries
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_submissions_student ON submissions(student_name);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_submissions_class ON submissions(class_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_mistakes_student ON mistakes(student_name);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_mistakes_submission ON mistakes(submission_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_class_students_class ON class_students(class_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cover_sheets_student ON lesson_cover_sheets(student_name);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cover_sheets_class ON lesson_cover_sheets(class_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_worksheets_created ON worksheets(created_at);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_theory_booklets_created ON theory_booklets(created_at);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_review_booklets_created ON review_booklets(created_at);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_exam_packages_created ON exam_packages(created_at);")

    conn.commit()
    conn.close()
    _initialized_dbs.add(abs_path)

# --- User & Authentication Operations ---
def authenticate_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    """Authenticates a user against PBKDF2 hash. Returns user profile dict or None."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE LOWER(username) = LOWER(?)", (username.strip(),))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    user = dict(row)
    if verify_password(password, user["password_hash"], user["salt"]):
        del user["password_hash"]
        del user["salt"]
        return user
    return None

def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    """Retrieves a user profile by username (case-insensitive, without password hash)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, display_name, role, api_key, created_at FROM users WHERE LOWER(username) = LOWER(?)", (username.strip(),))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def create_user(username: str, password: str, display_name: str, role: str = "tutor", api_key: str = "") -> int:
    """Creates a new tutor or admin user, optionally storing their personal Gemini API key."""
    conn = get_connection()
    cursor = conn.cursor()
    pwd_hash, salt = hash_password(password)
    cursor.execute("""
        INSERT INTO users (username, password_hash, salt, display_name, role, api_key)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (username.strip().lower(), pwd_hash, salt, display_name.strip(), role.strip().lower(), api_key.strip()))
    user_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return user_id

def get_all_tutors() -> List[Dict[str, Any]]:
    """Retrieves all registered tutors and admins."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, display_name, role, api_key, created_at FROM users ORDER BY display_name ASC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    """Retrieves a user profile by ID (without password hash)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, display_name, role, api_key, created_at FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def update_user_api_key(user_id: int, api_key: str) -> bool:
    """Updates personal Gemini API key for a tutor."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET api_key = ? WHERE id = ?", (api_key.strip(), user_id))
    conn.commit()
    conn.close()
    return True

def update_user_password(user_id: int, new_password: str):
    """Updates password with fresh salt and PBKDF2 hash."""
    conn = get_connection()
    cursor = conn.cursor()
    pwd_hash, salt = hash_password(new_password)
    cursor.execute("""
        UPDATE users SET password_hash = ?, salt = ? WHERE id = ?
    """, (pwd_hash, salt, user_id))
    conn.commit()
    conn.close()

# --- Class & Roll Operations ---
def create_class(name: str, year_level: str = "", teacher_name: str = "", schedule_time: str = "", tutor_id: Optional[int] = None) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO classes (name, year_level, teacher_name, schedule_time, tutor_id)
        VALUES (?, ?, ?, ?, ?)
    """, (name.strip(), year_level.strip(), teacher_name.strip(), schedule_time.strip(), tutor_id))
    class_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return class_id

def update_class_tutor(class_id: int, tutor_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE classes SET tutor_id = ? WHERE id = ?", (tutor_id, class_id))
    conn.commit()
    conn.close()

def get_classes_for_user(user_id: int, role: str = "tutor") -> List[Dict[str, Any]]:
    """Returns classes visible to user: all classes for admins, or only assigned classes for tutors."""
    conn = get_connection()
    cursor = conn.cursor()
    if role and role.lower() == "admin":
        cursor.execute("""
            SELECT c.*, u.display_name as tutor_display_name 
            FROM classes c 
            LEFT JOIN users u ON c.tutor_id = u.id 
            ORDER BY c.name ASC
        """)
    else:
        cursor.execute("""
            SELECT c.*, u.display_name as tutor_display_name 
            FROM classes c 
            LEFT JOIN users u ON c.tutor_id = u.id 
            WHERE c.tutor_id = ? 
            ORDER BY c.name ASC
        """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def can_user_access_class(user_id: int, role: str, class_id: int) -> bool:
    """Security check ensuring a tutor can only access or modify their own class."""
    if role and role.lower() == "admin":
        return True
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM classes WHERE id = ? AND tutor_id = ?", (class_id, user_id))
    row = cursor.fetchone()
    conn.close()
    return row is not None

def get_all_classes() -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.*, u.display_name as tutor_display_name 
        FROM classes c 
        LEFT JOIN users u ON c.tutor_id = u.id 
        ORDER BY c.name ASC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_class_by_id(class_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM classes WHERE id = ?", (class_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def delete_class(class_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM class_students WHERE class_id = ?", (class_id,))
    cursor.execute("DELETE FROM classes WHERE id = ?", (class_id,))
    conn.commit()
    conn.close()

def add_students_to_class(class_id: int, student_names: List[str]) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    added_count = 0
    for name in student_names:
        clean = name.strip()
        if clean:
            try:
                cursor.execute("""
                    INSERT OR IGNORE INTO class_students (class_id, student_name)
                    VALUES (?, ?)
                """, (class_id, clean))
                if cursor.rowcount > 0:
                    added_count += 1
                # Also ensure in global students table
                cursor.execute("INSERT OR IGNORE INTO students (name) VALUES (?)", (clean,))
            except Exception:
                pass
    conn.commit()
    conn.close()
    return added_count

def get_class_students(class_id: int) -> List[str]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT student_name FROM class_students 
        WHERE class_id = ? 
        ORDER BY student_name ASC
    """, (class_id,))
    rows = cursor.fetchall()
    conn.close()
    return [r['student_name'] for r in rows]

def remove_student_from_class(class_id: int, student_name: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM class_students WHERE class_id = ? AND student_name = ?", (class_id, student_name.strip()))
    conn.commit()
    conn.close()

# --- Worksheet Operations ---
def save_worksheet(title: str, term: Optional[int], week: Optional[int], year_level: str, topic: str,
                   difficulty: str, questions: List[Dict[str, Any]], marking_key: Dict[str, Any],
                   set_number: Optional[int] = 1, custom_instructions: Optional[str] = "",
                   cost: Optional[float] = None, model: Optional[str] = None, tokens: Optional[int] = None,
                   source_theory_id: Optional[int] = None, assessment_type: str = "homework") -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO worksheets (title, term, week, year_level, topic, difficulty, total_questions, questions_json, marking_key_json, set_number, custom_instructions, cost, model, tokens, source_theory_id, assessment_type)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        title, term, week, year_level, topic, difficulty, len(questions),
        json.dumps(questions), json.dumps(marking_key), set_number,
        custom_instructions or "", cost, model, tokens,
        source_theory_id, assessment_type or "homework"
    ))
    worksheet_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return worksheet_id

def update_worksheet_instructions(worksheet_id: int, instructions_text: str) -> bool:
    """Updates the custom instructions / notes for a saved worksheet."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE worksheets SET custom_instructions = ? WHERE id = ?", (instructions_text.strip(), worksheet_id))
    conn.commit()
    conn.close()
    return True

def get_worksheets() -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM worksheets ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_worksheet_by_id(worksheet_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM worksheets WHERE id = ?", (worksheet_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        d = dict(row)
        d['questions'] = json.loads(d['questions_json']) if d['questions_json'] else []
        d['marking_key'] = json.loads(d['marking_key_json']) if d['marking_key_json'] else {}
        return d
    return None

def delete_worksheet(worksheet_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM mistakes WHERE worksheet_id = ?", (worksheet_id,))
    cursor.execute("DELETE FROM submissions WHERE worksheet_id = ?", (worksheet_id,))
    cursor.execute("DELETE FROM worksheets WHERE id = ?", (worksheet_id,))
    conn.commit()
    conn.close()

# --- Theory Booklet Operations ---
def save_theory_booklet(title: str, term: Optional[int], week: Optional[int], year_level: str, topic: str, content: Dict[str, Any]) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO theory_booklets (title, term, week, year_level, topic, content_json)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        title, term, week, year_level, topic, json.dumps(content)
    ))
    booklet_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return booklet_id

def get_theory_booklets() -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM theory_booklets ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    results = []
    for r in rows:
        d = dict(r)
        d['content'] = json.loads(d['content_json']) if d.get('content_json') else {}
        results.append(d)
    return results

def get_theory_booklet_by_id(booklet_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM theory_booklets WHERE id = ?", (booklet_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        d = dict(row)
        d['content'] = json.loads(d['content_json']) if d.get('content_json') else {}
        return d
    return None

def delete_theory_booklet(booklet_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM theory_booklets WHERE id = ?", (booklet_id,))
    conn.commit()
    conn.close()

def update_theory_booklet_instructions(booklet_id: int, instructions_text: str) -> bool:
    """Updates custom instructions in a saved theory booklet's content JSON."""
    b = get_theory_booklet_by_id(booklet_id)
    if not b:
        return False
    content = b.get("content", {})
    clean_instr = instructions_text.strip()
    content["custom_instructions"] = clean_instr
    content["custom_notes"] = clean_instr
    content["extra_instructions"] = clean_instr
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE theory_booklets SET content_json = ? WHERE id = ?", (json.dumps(content), booklet_id))
    conn.commit()
    conn.close()
    return True

def register_theory_practice_worksheet(theory_id: int, booklet_data: Dict[str, Any]) -> int:
    """
    Registers or updates the tiered practice questions from a Theory Booklet
    as an assessable worksheet in the worksheets table (assessment_type='theory_practice').
    This seamlessly connects Theory Booklet practice questions to:
    1. Tab 2 (1-Click AI Homework & Practice Marking)
    2. Tab 3 (Student Tracking & Topic Mastery Analytics Matrix)
    3. Tab 4 (Targeted Remedial Revision Packs)
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    # Check if worksheet already exists for this theory booklet practice set
    cursor.execute("""
        SELECT id FROM worksheets 
        WHERE source_theory_id = ? AND assessment_type = 'theory_practice'
        LIMIT 1
    """, (theory_id,))
    existing = cursor.fetchone()
    
    # Extract questions and construct marking key from Theory Booklet concepts
    concepts = booklet_data.get("concepts", [])
    if not concepts and isinstance(booklet_data.get("content"), dict):
        concepts = booklet_data["content"].get("concepts", [])
        
    extracted_questions: List[Dict[str, Any]] = []
    marking_key: Dict[str, Any] = {}
    
    q_counter = 1
    for c_idx, c in enumerate(concepts, 1):
        c_name = c.get("concept_name") or c.get("name") or f"Concept {c_idx}"
        practice_qs = c.get("practice_questions", [])
        for p_idx, pq in enumerate(practice_qs, 1):
            q_label = str(q_counter)
            marks = int(pq.get("marks", 2))
            correct_ans = str(pq.get("final_answer") or pq.get("answer") or "")
            sol = pq.get("worked_solution") or ""
            diff = pq.get("difficulty") or "Medium"
            q_text = pq.get("text") or pq.get("problem_text") or ""
            
            extracted_questions.append({
                "item_label": q_label,
                "num": q_counter,
                "question": q_text,
                "marks": marks,
                "difficulty": diff,
                "subtopic": c_name,
                "concept_name": c_name,
                "concept_index": c_idx,
                "practice_index": p_idx,
                "correct_answer": correct_ans,
                "solution": sol,
                "marking_criteria": f"Correct mathematical working and answer: {marks} Mark{'s' if marks > 1 else ''}"
            })
            
            marking_key[q_label] = correct_ans
            q_counter += 1

    title = f"{booklet_data.get('title', 'Theory Booklet')} — Tiered Practice Questions"
    term = booklet_data.get("term")
    week = booklet_data.get("week")
    year_level = booklet_data.get("year_level", "")
    topic = booklet_data.get("topic", "")
    diff_label = "Tiered (Levels 1–5)"
    total_q = len(extracted_questions)
    
    if existing:
        ws_id = existing["id"]
        cursor.execute("""
            UPDATE worksheets SET
                title = ?,
                term = ?,
                week = ?,
                year_level = ?,
                topic = ?,
                difficulty = ?,
                total_questions = ?,
                questions_json = ?,
                marking_key_json = ?,
                custom_instructions = ?
            WHERE id = ?
        """, (
            title, term, week, year_level, topic, diff_label, total_q,
            json.dumps(extracted_questions), json.dumps(marking_key),
            f"Theory Booklet Practice Questions (Linked to Theory #{theory_id})",
            ws_id
        ))
        conn.commit()
        conn.close()
        return ws_id
    else:
        conn.close()
        return save_worksheet(
            title=title,
            term=term,
            week=week,
            year_level=year_level,
            topic=topic,
            difficulty=diff_label,
            questions=extracted_questions,
            marking_key=marking_key,
            set_number=1,
            custom_instructions=f"Theory Booklet Practice Questions (Linked to Theory #{theory_id})",
            cost=booklet_data.get("meta_cost", 0.0),
            model=booklet_data.get("model_used"),
            tokens=booklet_data.get("meta_tokens"),
            source_theory_id=theory_id,
            assessment_type="theory_practice"
        )


# --- Review Booklet Operations (Revision & Exam Prep) ---
def save_review_booklet(title: str, term: Optional[int], week: Optional[int], year_level: str, topic: str, content: Dict[str, Any]) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    content_str = json.dumps(content)
    cursor.execute("""
        INSERT INTO review_booklets (title, term, week, year_level, topic, content_json)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (title, term, week, year_level, topic, content_str))
    booklet_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return booklet_id

def get_review_booklets() -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM review_booklets ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    results = []
    for r in rows:
        d = dict(r)
        d['content'] = json.loads(d['content_json']) if d.get('content_json') else {}
        results.append(d)
    return results

def get_review_booklet_by_id(booklet_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM review_booklets WHERE id = ?", (booklet_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        d = dict(row)
        d['content'] = json.loads(d['content_json']) if d.get('content_json') else {}
        return d
    return None

def delete_review_booklet(booklet_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM review_booklets WHERE id = ?", (booklet_id,))
    conn.commit()
    conn.close()

def update_review_booklet_instructions(booklet_id: int, instructions_text: str) -> bool:
    """Updates custom instructions in a saved review booklet's content JSON."""
    b = get_review_booklet_by_id(booklet_id)
    if not b:
        return False
    content = b.get("content", {})
    clean_instr = instructions_text.strip()
    content["custom_instructions"] = clean_instr
    content["extra_instructions"] = clean_instr
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE review_booklets SET content_json = ? WHERE id = ?", (json.dumps(content), booklet_id))
    conn.commit()
    conn.close()
    return True


# --- Exam Package Operations (Complete Revision & Practice) ---
def save_exam_package(title: str, term: Optional[int], week: Optional[int], year_level: str, topic: str, content: Dict[str, Any]) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    content_str = json.dumps(content)
    cursor.execute("""
        INSERT INTO exam_packages (title, term, week, year_level, topic, content_json)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (title, term, week, year_level, topic, content_str))
    package_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return package_id

def get_exam_packages() -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM exam_packages ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    results = []
    for r in rows:
        d = dict(r)
        d['content'] = json.loads(d['content_json']) if d.get('content_json') else {}
        results.append(d)
    return results

def get_exam_package_by_id(package_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM exam_packages WHERE id = ?", (package_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        d = dict(row)
        d['content'] = json.loads(d['content_json']) if d.get('content_json') else {}
        return d
    return None

def delete_exam_package(package_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM exam_packages WHERE id = ?", (package_id,))
    conn.commit()
    conn.close()

def update_exam_package_instructions(package_id: int, instructions_text: str) -> bool:
    """Updates custom instructions in a saved exam package's content JSON."""
    pkg = get_exam_package_by_id(package_id)
    if not pkg:
        return False
    content = pkg.get("content", {})
    clean_instr = instructions_text.strip()
    content["custom_instructions"] = clean_instr
    content["custom_notes"] = clean_instr
    content["extra_instructions"] = clean_instr
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE exam_packages SET content_json = ? WHERE id = ?", (json.dumps(content), package_id))
    conn.commit()
    conn.close()
    return True



# --- Student & Submission Operations ---
def get_or_create_student(name: str, year_level: str = "", class_name: str = "") -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cleaned_name = name.strip()
    cursor.execute("SELECT id FROM students WHERE LOWER(name) = LOWER(?)", (cleaned_name,))
    row = cursor.fetchone()
    if row:
        student_id = row['id']
    else:
        cursor.execute("INSERT INTO students (name, year_level, class_name) VALUES (?, ?, ?)",
                       (cleaned_name, year_level, class_name))
        student_id = cursor.lastrowid
        conn.commit()
    conn.close()
    return student_id

def get_all_students() -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM students ORDER BY name ASC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_students_for_user(user_id: int, role: str = "tutor") -> List[Dict[str, Any]]:
    """Returns all students for admin, or only students enrolled in the tutor's classes."""
    conn = get_connection()
    cursor = conn.cursor()
    if role and role.lower() == "admin":
        cursor.execute("SELECT * FROM students ORDER BY name ASC")
    else:
        cursor.execute("""
            SELECT DISTINCT s.*
            FROM students s
            JOIN class_students cs ON LOWER(s.name) = LOWER(cs.student_name)
            JOIN classes c ON cs.class_id = c.id
            WHERE c.tutor_id = ?
            ORDER BY s.name ASC
        """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def save_submission(worksheet_id: Optional[int], student_name: str, raw_file_name: str,
                    score: float, total_marks: float, accuracy_pct: float,
                    pdf_report_path: str, summary_text: str = "",
                    mistakes: List[Dict[str, Any]] = None,
                    class_id: Optional[int] = None) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    student_id = get_or_create_student(student_name)

    cursor.execute("""
        INSERT INTO submissions (worksheet_id, student_id, class_id, student_name, raw_file_name, score, total_marks, accuracy_pct, pdf_report_path, summary_text)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        worksheet_id, student_id, class_id, student_name, raw_file_name, score, total_marks, accuracy_pct, pdf_report_path, summary_text
    ))
    submission_id = cursor.lastrowid

    if mistakes:
        for m in mistakes:
            cursor.execute("""
                INSERT INTO mistakes (submission_id, student_name, worksheet_id, class_id, question_num, topic, subtopic, status, marks_lost, student_answer, correct_answer, error_type, details, concept_name, cognitive_level)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                submission_id, student_name, worksheet_id, class_id,
                str(m.get('question_num', '')),
                m.get('topic', 'General Math'),
                m.get('subtopic', ''),
                m.get('status', 'Incorrect'),
                float(m.get('marks_lost', 1.0)),
                str(m.get('student_answer', '')),
                str(m.get('correct_answer', '')),
                m.get('error_type', 'Conceptual'),
                m.get('details', ''),
                m.get('concept_name', ''),
                m.get('cognitive_level', '')
            ))

    conn.commit()
    conn.close()
    return submission_id

def get_submission_by_id(submission_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.*, w.title as worksheet_title, w.term, w.week, w.topic as worksheet_topic, c.name as class_name
        FROM submissions s
        LEFT JOIN worksheets w ON s.worksheet_id = w.id
        LEFT JOIN classes c ON s.class_id = c.id
        WHERE s.id = ?
    """, (submission_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_submission_mistakes(submission_id: int) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM mistakes
        WHERE submission_id = ?
        ORDER BY id ASC
    """, (submission_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

# --- Analytics Operations ---
def get_submissions_summary(worksheet_id: Optional[int] = None, class_id: Optional[int] = None,
                            user_id: Optional[int] = None, role: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    query = """
        SELECT s.*, w.title as worksheet_title, w.term, w.week, c.name as class_name, c.teacher_name, c.tutor_id
        FROM submissions s
        LEFT JOIN worksheets w ON s.worksheet_id = w.id
        LEFT JOIN classes c ON s.class_id = c.id
        WHERE 1=1
    """
    params = []
    if worksheet_id:
        query += " AND s.worksheet_id = ?"
        params.append(worksheet_id)
    if class_id:
        query += " AND s.class_id = ?"
        params.append(class_id)
    if role and role.lower() != "admin" and user_id is not None:
        query += " AND c.tutor_id = ?"
        params.append(user_id)
        
    query += " ORDER BY s.graded_at DESC"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_student_history(student_name: str) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.*, w.title as worksheet_title, w.term, w.week, w.topic as worksheet_topic, c.name as class_name
        FROM submissions s
        LEFT JOIN worksheets w ON s.worksheet_id = w.id
        LEFT JOIN classes c ON s.class_id = c.id
        WHERE LOWER(s.student_name) = LOWER(?)
        ORDER BY s.graded_at ASC
    """, (student_name.strip(),))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_topic_weaknesses(student_name: Optional[str] = None, class_id: Optional[int] = None,
                         user_id: Optional[int] = None, role: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    query = """
        SELECT m.topic, m.subtopic, COUNT(*) as mistake_count, SUM(m.marks_lost) as total_marks_lost
        FROM mistakes m
        LEFT JOIN classes c ON m.class_id = c.id
        WHERE 1=1
    """
    params = []
    if student_name:
        query += " AND LOWER(m.student_name) = LOWER(?)"
        params.append(student_name.strip())
    if class_id:
        query += " AND m.class_id = ?"
        params.append(class_id)
    if role and role.lower() != "admin" and user_id is not None:
        query += " AND c.tutor_id = ?"
        params.append(user_id)

    query += """
        GROUP BY m.topic, m.subtopic
        ORDER BY mistake_count DESC, total_marks_lost DESC
    """
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_student_weak_topics(student_name: str, limit: int = 5) -> List[str]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT topic, COUNT(*) as count
        FROM mistakes
        WHERE LOWER(student_name) = LOWER(?) AND topic != ''
        GROUP BY topic
        ORDER BY count DESC
        LIMIT ?
    """, (student_name.strip(), limit))
    rows = cursor.fetchall()
    conn.close()
    return [r['topic'] for r in rows]

def get_submission_concept_breakdown(submission_id: int) -> List[Dict[str, Any]]:
    """
    Computes concept-by-concept performance for a given submission:
    Links designated questions from the assigned worksheet with the student's mistakes,
    determining total questions, right/wrong count, accuracy %, and Strength/Weakness status.
    """
    sub = get_submission_by_id(submission_id)
    if not sub:
        return []
    
    ws_id = sub.get("worksheet_id")
    ws = get_worksheet_by_id(ws_id) if ws_id else None
    mistakes = get_submission_mistakes(submission_id)
    
    questions = []
    if ws and ws.get("questions_json"):
        try:
            questions = json.loads(ws["questions_json"])
        except Exception:
            questions = []
            
    mistake_map = {}
    for m in mistakes:
        q_raw = str(m.get("question_num", "")).strip().lower()
        clean_k = q_raw.replace("qn", "").replace("q", "").strip()
        mistake_map[q_raw] = m
        if clean_k:
            mistake_map[clean_k] = m

    concept_map = {}
    for idx, q in enumerate(questions, 1):
        q_label = str(q.get("item_label") or idx).strip()
        c_name = q.get("concept_name") or q.get("subtopic") or (ws.get("topic") if ws else "General")
        c_name = c_name.strip() if c_name else "General"
        
        if c_name not in concept_map:
            concept_map[c_name] = {
                "concept_name": c_name,
                "topic": ws.get("topic", "") if ws else "",
                "questions": [],
                "correct_questions": [],
                "incorrect_questions": [],
                "mistakes": []
            }
        
        concept_map[c_name]["questions"].append(q_label)
        
        q_lower = q_label.lower()
        matched = mistake_map.get(q_lower) or mistake_map.get(f"qn {q_lower}")
        if not matched:
            for k, m in mistake_map.items():
                if k == q_lower or k.endswith(f" {q_lower}") or k.endswith(f".{q_lower}"):
                    matched = m
                    break
                    
        if matched:
            concept_map[c_name]["incorrect_questions"].append(q_label)
            concept_map[c_name]["mistakes"].append(matched)
        else:
            concept_map[c_name]["correct_questions"].append(q_label)
            
    if not concept_map and mistakes:
        for m in mistakes:
            c_name = m.get("concept_name") or m.get("subtopic") or m.get("topic") or "General"
            q_num = str(m.get("question_num", "?"))
            if c_name not in concept_map:
                concept_map[c_name] = {
                    "concept_name": c_name,
                    "topic": m.get("topic", ""),
                    "questions": [],
                    "correct_questions": [],
                    "incorrect_questions": [],
                    "mistakes": []
                }
            concept_map[c_name]["questions"].append(q_num)
            concept_map[c_name]["incorrect_questions"].append(q_num)
            concept_map[c_name]["mistakes"].append(m)

    results = []
    for c_name, data in concept_map.items():
        tot = len(data["questions"])
        corr = len(data["correct_questions"])
        inc = len(data["incorrect_questions"])
        acc = round((corr / tot) * 100, 1) if tot > 0 else 0.0
        
        if acc >= 80.0:
            status = "Strength"
        elif acc >= 60.0:
            status = "Moderate"
        else:
            status = "Weakness"
            
        results.append({
            "concept_name": c_name,
            "topic": data["topic"],
            "questions_designated": data["questions"],
            "total_questions": tot,
            "correct_count": corr,
            "incorrect_count": inc,
            "accuracy_pct": acc,
            "status": status,
            "mistakes": data["mistakes"]
        })
    return results

def get_student_concept_mastery_matrix(student_name: str, topic: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Aggregates performance across all historical submissions for a student by concept.
    Returns concept performance with total questions attempted, total correct, total incorrect,
    cumulative accuracy, and overall classification (Strength vs Weakness).
    """
    history = get_student_history(student_name)
    if not history:
        return []

    agg_map = {}
    for sub in history:
        sub_id = sub.get("id")
        if not sub_id:
            continue
        breakdown = get_submission_concept_breakdown(sub_id)
        for item in breakdown:
            c_topic = item.get("topic", "")
            if topic and c_topic.lower() != topic.lower():
                continue
            c_name = item.get("concept_name", "General")
            if c_name not in agg_map:
                agg_map[c_name] = {
                    "concept_name": c_name,
                    "topic": c_topic,
                    "total_questions": 0,
                    "correct_count": 0,
                    "incorrect_count": 0,
                    "submissions_count": 0,
                    "worksheet_titles": set(),
                    "recent_status": item.get("status")
                }
            agg_map[c_name]["total_questions"] += item.get("total_questions", 0)
            agg_map[c_name]["correct_count"] += item.get("correct_count", 0)
            agg_map[c_name]["incorrect_count"] += item.get("incorrect_count", 0)
            agg_map[c_name]["submissions_count"] += 1
            if sub.get("worksheet_title"):
                agg_map[c_name]["worksheet_titles"].add(sub.get("worksheet_title"))

    results = []
    for c_name, d in agg_map.items():
        tot = d["total_questions"]
        corr = d["correct_count"]
        inc = d["incorrect_count"]
        acc = round((corr / tot) * 100, 1) if tot > 0 else 0.0
        if acc >= 80.0:
            status = "Strength"
        elif acc >= 60.0:
            status = "Moderate"
        else:
            status = "Weakness"
        results.append({
            "concept_name": c_name,
            "topic": d["topic"],
            "total_questions": tot,
            "correct_count": corr,
            "incorrect_count": inc,
            "accuracy_pct": acc,
            "status": status,
            "submissions_count": d["submissions_count"],
            "worksheets": list(d["worksheet_titles"])
        })
    results.sort(key=lambda x: (x["status"] != "Weakness", x["accuracy_pct"]))
    return results

# --- Lesson Cover Sheet & Longitudinal Tracking Operations ---

def create_lesson_cover_sheet(data: Dict[str, Any]) -> int:
    """Inserts a completed lesson cover sheet into the database."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Serialize JSON fields if they are lists/dicts
    mastery_data = data.get("mastery_data")
    if isinstance(mastery_data, (list, dict)):
        mastery_data = json.dumps(mastery_data)
        
    root_cause_tags = data.get("root_cause_tags")
    if isinstance(root_cause_tags, (list, dict)):
        root_cause_tags = json.dumps(root_cause_tags)
        
    materials_used = data.get("materials_used")
    if isinstance(materials_used, (list, dict)):
        materials_used = json.dumps(materials_used)
        
    intervention_tags = data.get("intervention_tags")
    if isinstance(intervention_tags, (list, dict)):
        intervention_tags = json.dumps(intervention_tags)

    cursor.execute("""
        INSERT INTO lesson_cover_sheets (
            student_name, class_id, tutor_id, term, week, lesson_date,
            subject, topic, subtopic, syllabus_outcomes, materials_used,
            mastery_data, root_cause_tags, specific_stumbling_block, intervention_tags,
            score_engagement, score_confidence, score_independence, tutor_observations,
            attention_flag, attention_notes, homework_assigned, homework_due, target_accuracy,
            next_lesson_priority, parent_soundbite, student_clarity, student_support,
            student_questions, student_difficulty, student_confidence_shift, student_request_note
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get("student_name", "").strip(),
        data.get("class_id"),
        data.get("tutor_id"),
        data.get("term", 1),
        data.get("week", 1),
        data.get("lesson_date", datetime.now().strftime("%Y-%m-%d")),
        data.get("subject", "Maths"),
        data.get("topic", "").strip(),
        data.get("subtopic", "").strip(),
        data.get("syllabus_outcomes", "").strip(),
        materials_used,
        mastery_data,
        root_cause_tags,
        data.get("specific_stumbling_block", "").strip(),
        intervention_tags,
        int(data.get("score_engagement", 4)),
        int(data.get("score_confidence", 4)),
        int(data.get("score_independence", 4)),
        data.get("tutor_observations", "").strip(),
        data.get("attention_flag", "all_clear"),
        data.get("attention_notes", "").strip(),
        data.get("homework_assigned", "").strip(),
        data.get("homework_due", "").strip(),
        data.get("target_accuracy", "").strip(),
        data.get("next_lesson_priority", "").strip(),
        data.get("parent_soundbite", "").strip(),
        data.get("student_clarity", "Crystal Clear"),
        data.get("student_support", "Very Supported"),
        data.get("student_questions", "Always (100%)"),
        data.get("student_difficulty", "Sweet Spot"),
        data.get("student_confidence_shift", "Higher"),
        data.get("student_request_note", "").strip()
    ))
    sheet_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return sheet_id

def get_lesson_cover_sheet_by_id(sheet_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT lcs.*, c.name as class_name, u.display_name as tutor_name
        FROM lesson_cover_sheets lcs
        LEFT JOIN classes c ON lcs.class_id = c.id
        LEFT JOIN users u ON lcs.tutor_id = u.id
        WHERE lcs.id = ?
    """, (sheet_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    for field in ["mastery_data", "root_cause_tags", "materials_used", "intervention_tags"]:
        if d.get(field):
            try:
                d[field] = json.loads(d[field])
            except Exception:
                pass
    return d

def get_lesson_cover_sheets(user_id: Optional[int] = None, role: Optional[str] = None,
                            class_id: Optional[int] = None, student_name: Optional[str] = None,
                            limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieves lesson cover sheets scoped by user permissions and optional filters."""
    conn = get_connection()
    cursor = conn.cursor()
    query = """
        SELECT lcs.*, c.name as class_name, u.display_name as tutor_name
        FROM lesson_cover_sheets lcs
        LEFT JOIN classes c ON lcs.class_id = c.id
        LEFT JOIN users u ON lcs.tutor_id = u.id
        WHERE 1=1
    """
    params = []
    if role and role.lower() != "admin" and user_id is not None:
        query += " AND (lcs.tutor_id = ? OR c.tutor_id = ?)"
        params.extend([user_id, user_id])
    if class_id:
        query += " AND lcs.class_id = ?"
        params.append(class_id)
    if student_name:
        query += " AND LOWER(lcs.student_name) = LOWER(?)"
        params.append(student_name.strip())
        
    query += " ORDER BY lcs.lesson_date DESC, lcs.id DESC LIMIT ?"
    params.append(limit)
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    result = []
    for r in rows:
        d = dict(r)
        for field in ["mastery_data", "root_cause_tags", "materials_used", "intervention_tags"]:
            if d.get(field):
                try:
                    d[field] = json.loads(d[field])
                except Exception:
                    pass
        result.append(d)
    return result

def get_student_longitudinal_metrics(student_name: str) -> Dict[str, Any]:
    """
    Aggregates multi-week trends for a student across all completed cover sheets:
    - Average engagement, confidence, independence
    - Cognitive independence evolution
    - Recurring diagnostic root-causes
    - Attention flag counts
    - Recent parent soundbites
    """
    sheets = get_lesson_cover_sheets(student_name=student_name, limit=100)
    if not sheets:
        return {
            "total_lessons": 0,
            "avg_engagement": 0.0,
            "avg_confidence": 0.0,
            "avg_independence": 0.0,
            "latest_soundbite": None,
            "attention_flags": [],
            "root_cause_freq": {},
            "student_sentiment": {},
            "chronological_scores": []
        }

    # Reverse to chronological order (oldest to newest)
    chronological = list(reversed(sheets))
    
    total = len(sheets)
    avg_eng = sum(s.get("score_engagement", 4) for s in sheets) / total
    avg_conf = sum(s.get("score_confidence", 4) for s in sheets) / total
    avg_ind = sum(s.get("score_independence", 4) for s in sheets) / total
    
    root_cause_freq: Dict[str, int] = {}
    for s in sheets:
        causes = s.get("root_cause_tags", [])
        if isinstance(causes, list):
            for c in causes:
                root_cause_freq[c] = root_cause_freq.get(c, 0) + 1

    sentiment_clarity: Dict[str, int] = {}
    sentiment_difficulty: Dict[str, int] = {}
    flags = []
    for s in sheets:
        clarity = s.get("student_clarity")
        if clarity:
            sentiment_clarity[clarity] = sentiment_clarity.get(clarity, 0) + 1
        diff = s.get("student_difficulty")
        if diff:
            sentiment_difficulty[diff] = sentiment_difficulty.get(diff, 0) + 1
        flag = s.get("attention_flag")
        if flag and flag != "all_clear":
            flags.append({
                "lesson_date": s.get("lesson_date"),
                "flag": flag,
                "notes": s.get("attention_notes") or s.get("topic")
            })

    chronological_scores = [
        {
            "week_label": f"T{s.get('term', 1)}W{s.get('week', 1)} ({s.get('lesson_date', '')})",
            "engagement": s.get("score_engagement", 4),
            "confidence": s.get("score_confidence", 4),
            "independence": s.get("score_independence", 4),
            "topic": s.get("topic", "")
        }
        for s in chronological
    ]

    latest_sheet = sheets[0] # most recent
    return {
        "total_lessons": total,
        "avg_engagement": round(avg_eng, 2),
        "avg_confidence": round(avg_conf, 2),
        "avg_independence": round(avg_ind, 2),
        "latest_soundbite": latest_sheet.get("parent_soundbite"),
        "latest_topic": latest_sheet.get("topic"),
        "latest_date": latest_sheet.get("lesson_date"),
        "latest_tutor": latest_sheet.get("tutor_name"),
        "attention_flags": flags,
        "root_cause_freq": root_cause_freq,
        "sentiment_clarity": sentiment_clarity,
        "sentiment_difficulty": sentiment_difficulty,
        "chronological_scores": chronological_scores
    }

def delete_lesson_cover_sheet(sheet_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM lesson_cover_sheets WHERE id = ?", (sheet_id,))
    conn.commit()
    conn.close()


def get_theory_linked_worksheets(theory_id: int, assessment_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """Returns all worksheets linked to a specific theory booklet, optionally filtered by assessment_type ('in_class', 'homework', 'topic_exam')."""
    conn = get_connection()
    cursor = conn.cursor()
    if assessment_type:
        cursor.execute("""
            SELECT * FROM worksheets
            WHERE source_theory_id = ? AND assessment_type = ?
            ORDER BY created_at DESC
        """, (theory_id, assessment_type))
    else:
        cursor.execute("""
            SELECT * FROM worksheets
            WHERE source_theory_id = ?
            ORDER BY created_at DESC
        """, (theory_id,))
    rows = cursor.fetchall()
    conn.close()
    results = []
    for r in rows:
        d = dict(r)
        d['questions'] = json.loads(d['questions_json']) if d.get('questions_json') else []
        d['marking_key'] = json.loads(d['marking_key_json']) if d.get('marking_key_json') else {}
        results.append(d)
    return results


def get_theory_linked_exams(theory_id: int) -> List[Dict[str, Any]]:
    """Returns all worksheets / exams linked to a specific theory booklet."""
    return get_theory_linked_worksheets(theory_id)


def get_topic_assessment_matrix(worksheet_id: int, class_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Computes a comprehensive Topic Assessment & Teaching Coverage Matrix for an exam:
    - Lists all concepts tested and total marks per concept.
    - Audits curriculum coverage against the source theory booklet (if linked).
    - Computes per-student scores and percentages across each concept.
    - Computes cohort concept averages to identify systemic teaching gaps (<65%).
    """
    ws = get_worksheet_by_id(worksheet_id)
    if not ws:
        return {}

    questions = ws.get("questions", [])
    # Build question-to-concept map and concept total marks
    concept_totals: Dict[str, float] = {}
    q_to_concept: Dict[str, str] = {}
    q_to_marks: Dict[str, float] = {}

    for q in questions:
        lbl = str(q.get("item_label") or q.get("num") or "").strip()
        c_name = q.get("concept_name") or q.get("subtopic") or "General Knowledge"
        m = float(q.get("marks", 1))
        q_to_concept[lbl] = c_name
        q_to_marks[lbl] = m
        concept_totals[c_name] = concept_totals.get(c_name, 0.0) + m

    ordered_concepts = list(concept_totals.keys())

    # Check source theory booklet coverage and pedagogical assets
    source_theory_id = ws.get("source_theory_id")
    theory_concepts_count = len(ordered_concepts)
    source_tb = None
    theory_concept_map: Dict[str, Dict[str, Any]] = {}
    
    if source_theory_id:
        source_tb = get_theory_booklet_by_id(source_theory_id)
        if source_tb and source_tb.get("content") and source_tb["content"].get("concepts"):
            tb_cs = [c.get("concept_name") or c.get("name") for c in source_tb["content"]["concepts"] if c.get("concept_name") or c.get("name")]
            if tb_cs:
                theory_concepts_count = len(tb_cs)
            for c in source_tb["content"]["concepts"]:
                c_name = c.get("concept_name") or c.get("name")
                if c_name:
                    theory_concept_map[c_name.lower().strip()] = c

    # Fetch submissions
    conn = get_connection()
    cursor = conn.cursor()
    if class_id:
        cursor.execute("SELECT * FROM submissions WHERE worksheet_id = ? AND class_id = ? ORDER BY accuracy_pct DESC", (worksheet_id, class_id))
    else:
        cursor.execute("SELECT * FROM submissions WHERE worksheet_id = ? ORDER BY accuracy_pct DESC", (worksheet_id,))
    subs_rows = cursor.fetchall()

    student_records = []
    cohort_concept_earned: Dict[str, float] = {c: 0.0 for c in ordered_concepts}
    cohort_concept_possible: Dict[str, float] = {c: 0.0 for c in ordered_concepts}

    for sr in subs_rows:
        s_id = sr["id"]
        s_name = sr["student_name"]
        s_score = float(sr["score"])
        s_total = float(sr["total_marks"])
        s_pct = float(sr["accuracy_pct"])

        cursor.execute("SELECT * FROM mistakes WHERE submission_id = ?", (s_id,))
        m_rows = cursor.fetchall()

        marks_lost_per_concept: Dict[str, float] = {}
        for mr in m_rows:
            q_num = str(mr["question_num"]).strip()
            c_name = mr["concept_name"] or q_to_concept.get(q_num) or mr["subtopic"] or "General Knowledge"
            lost = float(mr["marks_lost"] or 1.0)
            marks_lost_per_concept[c_name] = marks_lost_per_concept.get(c_name, 0.0) + lost

        student_concept_breakdown: Dict[str, Dict[str, Any]] = {}
        for c_name in ordered_concepts:
            c_max = concept_totals[c_name]
            c_lost = marks_lost_per_concept.get(c_name, 0.0)
            c_earned = max(0.0, c_max - c_lost)
            c_pct = round((c_earned / c_max) * 100, 1) if c_max > 0 else 100.0

            cohort_concept_earned[c_name] += c_earned
            cohort_concept_possible[c_name] += c_max

            student_concept_breakdown[c_name] = {
                "earned": round(c_earned, 1),
                "total": round(c_max, 1),
                "pct": c_pct,
                "status": "Mastered" if c_pct >= 80 else ("Developing" if c_pct >= 60 else "Critical Gap")
            }

        student_records.append({
            "submission_id": s_id,
            "student_name": s_name,
            "score": s_score,
            "total_marks": s_total,
            "accuracy_pct": s_pct,
            "concepts": student_concept_breakdown
        })

    conn.close()

    cohort_concept_averages: Dict[str, Dict[str, Any]] = {}
    teaching_gaps = []
    for c_name in ordered_concepts:
        poss = cohort_concept_possible[c_name]
        earnd = cohort_concept_earned[c_name]
        avg_pct = round((earnd / poss) * 100, 1) if poss > 0 else 0.0
        is_gap = (avg_pct < 65.0) and (len(student_records) > 0)
        
        # Link pedagogical assets from source Theory Booklet
        matched_theory = theory_concept_map.get(c_name.lower().strip())
        if not matched_theory:
            for k, v in theory_concept_map.items():
                if k in c_name.lower() or c_name.lower() in k:
                    matched_theory = v
                    break
        
        theory_notes = ""
        key_formulas = []
        tutor_tips = ""
        teacher_ex = {}
        if matched_theory:
            theory_notes = matched_theory.get("theory_text", "")
            key_formulas = matched_theory.get("key_formulas", [])
            tutor_tips = matched_theory.get("tutor_tips", "")
            exs = matched_theory.get("teacher_examples", [])
            if exs:
                teacher_ex = exs[0]

        if is_gap:
            teaching_gaps.append({
                "concept_name": c_name,
                "average_pct": avg_pct,
                "alert": f"Class average is {avg_pct}%. Systemic teaching gap detected.",
                "theory_notes": theory_notes,
                "key_formulas": key_formulas,
                "tutor_tips": tutor_tips,
                "teacher_example": teacher_ex,
                "has_theory_link": bool(matched_theory)
            })
        cohort_concept_averages[c_name] = {
            "average_pct": avg_pct,
            "status": "Mastered" if avg_pct >= 80 else ("Developing" if avg_pct >= 65 else "Teaching Gap"),
            "is_gap": is_gap
        }

    overall_class_avg = round(sum(s["accuracy_pct"] for s in student_records) / len(student_records), 1) if student_records else 0.0
    coverage_pct = round((len(ordered_concepts) / max(1, theory_concepts_count)) * 100, 1)

    return {
        "worksheet_id": worksheet_id,
        "title": ws["title"],
        "topic": ws["topic"],
        "year_level": ws["year_level"],
        "term": ws.get("term"),
        "week": ws.get("week"),
        "assessment_type": ws.get("assessment_type", "homework"),
        "source_theory_id": source_theory_id,
        "source_theory_title": source_tb.get("title") if source_tb else None,
        "total_marks": ws.get("total_questions", sum(concept_totals.values())),
        "concepts_tested": ordered_concepts,
        "concept_totals": concept_totals,
        "theory_coverage": {
            "tested_count": len(ordered_concepts),
            "theory_count": theory_concepts_count,
            "coverage_pct": min(100.0, coverage_pct),
            "is_complete": len(ordered_concepts) >= theory_concepts_count
        },
        "student_count": len(student_records),
        "class_average_pct": overall_class_avg,
        "cohort_concept_averages": cohort_concept_averages,
        "teaching_gaps": teaching_gaps,
        "student_records": student_records
    }


