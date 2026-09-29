# DA Tuition — Integrated Tutor Hub

A unified, tutor-friendly platform that solves all 5 major workflow bottlenecks for DA Tuition tutors:
1. **Zero-friction workflow**: Eliminates tedious Google Drive link pasting, manual row tracking, and Apps Script editing.
2. **Auto Marking Key Generation**: Automatically creates the definitive answer key when generating worksheets—no manual handwriting required.
3. **Student Tracking System**: Automatically records all student marks and submissions over time in a persistent database.
4. **Diagnostic Weakness Heatmaps**: Tags student errors by mathematical topic (e.g. *Algebra*, *Fractions*, *Geometry*) and displays class-wide and student-level gap analytics.
5. **Integrated Remedial Generator**: One-click generation of personalized revision worksheets tailored to each student's specific weak areas.

---

## Quick Start

### Work on features at the same time

This is still one app. Each feature folder is an isolated working copy of its code, with a separate branch and local database. The main app remains in this folder.

```bash
./feature-workspaces.sh new attendance
./feature-workspaces.sh new report-layout
./feature-workspaces.sh list
./feature-workspaces.sh run attendance
```

Open `feature-workspaces/attendance` or `feature-workspaces/report-layout` as a separate project in your coding tool. Use a different feature name for each new task. The run command starts each feature on its own port, beginning at 8502; the main app uses 8501. Ask Codex to merge a finished feature into `main` when ready. Feature folders contain local copies of `.env` and the database, so keep them private and avoid entering real student data during tests.

### 1. Launch the Application
Run the launcher script in Terminal:
```bash
./start.sh
```
Or run directly:
```bash
.venv/bin/streamlit run app.py
```

The application will open automatically in your browser at `http://localhost:8501`.

---

## Features Overview

### Tab 1: 📝 Worksheet & Key Generator
- Generate curriculum-aligned math homework sheets for **Year 5 to Year 12 (HSC)**.
- Full step-by-step solutions and answers are generated automatically.
- **Auto-saved Marking Key**: The key is stored in the database, ready for 1-click grading.
- Download **Printable Worksheet PDF**, matching **DA Tuition Blank Answer Sheet (PDF)**, and **JSON Marking Key**.

### Tab 2: 🚀 1-Click AI Homework Marking
- Select the week's worksheet from the dropdown (or paste a custom key).
- Drop student handwritten PDFs (supports batch uploads).
- **Gemini 3.7 Flash** reads handwriting with DA Tuition's benefit-of-the-doubt heuristics, checks answers, calculates deductive marks, and classifies mistakes into diagnostic topics.
- Generates **DA Tuition Performance Breakdown PDF Reports** per student with 1-click ZIP download.

### Tab 3: 📊 Student Tracking & Weakness Analytics
- **Class KPI Dashboard**: Class average accuracy %, pass rates, and submission volume.
- **Mistake Heatmap**: Visual breakdown of which math topics and subtopics caused the most lost marks.
- **Individual Student Progress Timelines**: Track student trajectory over weeks and inspect individual weak areas.

### Tab 4: 🎯 Remedial Revision Packs
- Select a student.
- The system automatically extracts their recent weak topics from their homework history.
- Click **Generate Personalized Revision Pack** to produce a targeted practice worksheet addressing their exact learning gaps.
