# Company AI Tools - Hiring AI Assistant

A starter project for the Hiring AI Assistant described in the PRD.
It follows the hiring process exactly: **Screening -> M1 round -> M2 round**.

**Only HR / Recruitment uses this platform.** HR contacts HODs, interviewers and candidates
through the usual company channels (Teams, email, phone), and records every step here:
who was contacted, through which channel, and what they decided.

**Tech stack:** Python, LangGraph, LangChain, an open-source LLM (via Ollama), Streamlit, PostgreSQL.

---

## 1. What you need installed first

1. **Python 3.10 or newer**: https://www.python.org/downloads/
2. **PostgreSQL**: https://www.postgresql.org/download/ (remember the password you set for the `postgres` user)
3. **Ollama** (runs the open-source LLM): https://ollama.com/download

The app still works without Ollama. You'll just see "AI is not available" instead of AI answers.

---

## 2. Setup (one time)

Open a terminal **inside the project folder** and run these commands.

**Step 1: Create a virtual environment**

Windows:

```
python -m venv venv
venv\Scripts\activate
```

Mac / Linux:

```
python3 -m venv venv
source venv/bin/activate
```

**Step 2: Install the packages**

```
pip install -r requirements.txt
```

**Step 3: Create your settings file**

Copy `.env.example` to a new file named `.env`:

Windows: `copy .env.example .env`
Mac / Linux: `cp .env.example .env`

Open `.env` and set your PostgreSQL password in `DATABASE_URL`:

```
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/hiring_ai
```

**Step 4: Download the open-source LLM**

```
ollama pull llama3.1
```

(You can use another model, such as `mistral` or `qwen2.5`. Just change `LLM_MODEL` in `.env`.)

**Step 5: Set up the database**

```
python -m database.setup_db
```

This creates the `hiring_ai` database, its 5 tables, demo data and the first recruitment login.
It's safe to run again.

You will see:

```
Demo HR login created: hr@bilal.local / ChangeMe@123
```

**Already set up an earlier version?** Just run `python -m database.setup_db` again.
It moves your existing data into the 5 tables and removes the old tables it no longer needs.

---

## 3. Run the app

```
streamlit run app.py
```

The app opens in your browser at http://localhost:8501

---

## 4. Log in and try the full flow

Open http://localhost:8501 and log in with:

- **Email:** `hr@bilal.local`
- **Password:** `ChangeMe@123`

**Change this password right away:** go to **People** → **My password**.

To give other recruitment team members access, go to **People** → **Recruitment accounts** and create an account for each person.
HODs and interviewers are kept as **records only** (People → HODs & interviewers). They don't log in.

**Walk through one candidate:**

1. **Jobs:** click **Create job** (for example, in Frontend Engineering), then **Open** the job and upload some CVs. The AI ranks them.
2. **My Tasks:** approve the shortlist.
3. Contact the HOD on Teams / email (the "Generate AI message to copy" button can write the message for you), then **record** it.
4. Record which interviewers the HOD assigned.
5. Record the interviewer slots, the candidate's availability, and the M1 schedule.
6. Record that the M1 interview was done, then record the interviewer's feedback (Selected / Unselected).
7. Record the M1 result. Selected candidates move to M2; Unselected candidates are closed.
8. Record the HOD's slots and the M2 schedule, that the interview was done, and the HOD's final feedback.
9. Close the process (Offer or Rejection).

Open **Dashboard** at any time to see every candidate's status, the next step, and the full history
(including which channel was used and which recruiter recorded each step).

**Note:** for security, refreshing the browser page logs you out.

---

## 5. Folder structure

```
hiring_ai_assistant/
|-- app.py                     Home page (start here: streamlit run app.py)
|-- requirements.txt           Python packages to install
|-- .env.example               Settings template (copy to .env)
|
|-- pages/                     Streamlit screens
|   |-- 1_Jobs.py              HR: jobs list, create job, open a job to upload CVs + AI ranking
|   |-- 2_My_Tasks.py          Every candidate waiting for the next step
|   |-- 3_Dashboard.py         Status of all candidates + history
|   |-- 4_People.py            Departments, HODs, interviewers, recruitment accounts, password
|
|-- config/
|   |-- settings.py            Reads the .env file
|   |-- steps.py               All process steps and their owner role (from the PRD)
|
|-- database/
|   |-- schema.sql             The 5 database tables
|   |-- seed.sql               Demo departments and users
|   |-- migrate_old_tables.sql Moves data from older versions into the 5 tables (used by setup_db)
|   |-- db.py                  PostgreSQL connection helpers
|   |-- setup_db.py            Database setup (safe to run again)
|
|-- graph/                     LangGraph workflow
|   |-- state.py               The data the workflow works with for one candidate
|   |-- nodes.py               Each step (saves what HR recorded, or waits for HR)
|   |-- workflow.py            The order of steps: Screening -> M1 -> M2
|
|-- services/
|   |-- repository.py          All database reads and writes
|   |-- permissions.py         Only HR / Recruitment can complete steps
|   |-- security.py            Safe password storage
|   |-- workflow_service.py    Starts / continues each candidate's workflow
|   |-- llm.py                 Connection to the open-source LLM (Ollama)
|   |-- ai_helpers.py          AI features: rank CVs, drafts, questions, summary
|   |-- cv_parser.py           Reads PDF / DOCX / TXT CVs
|
|-- ui/
|   |-- auth.py                Login screen and logout
|   |-- step_forms.py          The form HR fills to record each step
|
|-- uploads/                   Uploaded CVs are saved here
```

---

## 6. How it works (simple version)

- **LangGraph** defines the process: the order of the steps and the branches
  (not shortlisted -> close, M1 unselected -> close, M1 selected -> M2).
- Each candidate's place in the process is **saved in their row of the `candidates` table**
  (`current_step` + the decisions), so it can wait for days (for example, for the HOD)
  and continue later, even after a restart.
- When HR completes a step, the workflow saves it, follows the arrows, and stops at the next step that needs HR.
- When CVs are uploaded, the AI scores each one against the job. A score at or above the job's
  **shortlist threshold** (70 by default) is shortlisted automatically; HR can still "Shortlist anyway".
- Only logged-in **HR / Recruitment** users can see the platform or complete steps.
- For HOD and interviewer steps, HR records **who** gave the decision; the app also saves **which recruiter** entered it.
- Every action is saved in the **activity log** (what happened, through which channel, when, and recorded by whom).
- The **AI only helps**: it ranks CVs, drafts messages, suggests questions, and summarizes feedback.
  It never makes a decision.

---

## 7. The database (5 tables)

| Table          | What it keeps                                                                                                                                        |
| -------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| `departments`  | Company departments                                                                                                                                  |
| `users`        | HR / Recruitment logins, and HODs and interviewers (records only, they don't log in)                                                                 |
| `jobs`         | Open positions: title, description, department, AI shortlist threshold                                                                               |
| `candidates`   | One row per CV: AI score and reason, where the process is now, the shortlist decision, assigned interviewers, M1 / M2 schedule, and M1 / M2 feedback |
| `activity_log` | The history: every step, when, which recruiter recorded it, and the details (channel, notes...)                                                      |

---

## 8. Common problems

| Problem                          | Fix                                                                                |
| -------------------------------- | ---------------------------------------------------------------------------------- |
| `password authentication failed` | Check the password in `DATABASE_URL` in your `.env` file                           |
| `connection refused` (port 5432) | PostgreSQL isn't running. Start the PostgreSQL service                             |
| "AI is not available"            | Start Ollama and run `ollama pull llama3.1`                                        |
| `No module named ...`            | Activate the virtual environment, then run `pip install -r requirements.txt` again |
| "Wrong email or password"        | Use `hr@bilal.local` / `ChangeMe@123` (or the password you changed it to)          |
| Login page keeps appearing       | Run `python -m database.setup_db` again to create the demo login                   |

---

## 9. Next steps (not in this starter)

- Optional: company login (Microsoft / Google) instead of email + password
- Reminders when a candidate has been waiting on a step for too long
- Decide the rule when two M1 interviewers give different feedback
  (right now, one M1 feedback is recorded and it moves the process forward)
