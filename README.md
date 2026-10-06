# Hiring AI Assistant

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

Then make a secret key for the sign-in tokens and put it after `JWT_SECRET=` in `.env`:

```
python -c "import secrets; print(secrets.token_urlsafe(48))"
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
It moves your existing data into the tables and removes the old tables it no longer needs.

---

## 3. Run the app

```
streamlit run app.py
```

The app opens in your browser at http://localhost:8501

---

## 4. Sign in and try the full flow

Open http://localhost:8501 and sign in with the demo account:

- **Email:** `hr@bilal.local`
- **Password:** `ChangeMe@123`

**Change this password right away:** go to **People** → **My password**.

New recruitment team members can create their own account on the **Sign up** tab of the sign-in page,
or you can create one for them in **People** → **Recruitment accounts**.
HODs and interviewers are kept as **records only** (People → HODs & interviewers). They don't sign in.

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

**Staying signed in:** after you sign in, the app gives your browser two signed tokens (JSON Web Tokens):
an **access token** (15 minutes) and a **refresh token** (7 days). When the access token expires, the refresh
token quietly gets a new one, so you stay signed in for 7 days, also after refreshing the page.
Click **Log out** in the sidebar to end it: this signs you out on every device.

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
|   |-- word_lists.py          Other ways skills and degrees are written on CVs (data only)
|
|-- database/
|   |-- schema.sql             The 6 database tables
|   |-- seed.sql               Demo departments and users
|   |-- migrate_old_tables.sql Moves data from older versions into the tables (used by setup_db)
|   |-- db.py                  PostgreSQL connection helpers
|   |-- setup_db.py            Database setup (safe to run again)
|
|-- graph/
|   |-- workflow.py            The LangGraph graph: the steps, and the arrows Screening -> M1 -> M2
|
|-- services/
|   |-- scoring.py             The CV score (0-100): rank_cv()
|   |-- job_requirements.py    What a job asks for: required skills, minimum years, degree fields
|   |-- cv_checks.py           What the app finds in a CV by itself: skills, stated years, degree
|   |-- prompts.py             Every text sent to the AI
|   |-- llm.py                 Connection to the open-source LLM (Ollama) and reading its answers
|   |-- ai_helpers.py          Small AI helpers: messages to copy, interview questions, feedback summary
|   |-- cv_parser.py           Reads PDF / DOCX / TXT CVs
|   |-- workflow_service.py    Starts / continues each candidate's process, and who may do it
|   |-- repository.py          All database reads and writes
|   |-- security.py            Safe password storage, and the sign-in tokens (JWT: access + refresh)
|
|-- ui/
|   |-- auth.py                Sign in, sign up, staying signed in, and log out
|   |-- cv_upload.py           Uploading CVs: read, score (with a live timer), save, shortlist
|   |-- step_forms.py          The form HR fills to record each step (one function per step)
|   |-- process_view.py        Progress of a candidate, "Go back", and success messages
|
|-- uploads/                   Uploaded CVs are saved here
```

### Where to change things

| I want to change...                                   | Open                                                                    |
| ----------------------------------------------------- | ----------------------------------------------------------------------- |
| How a CV is scored (the 4 parts and their points)     | `services/scoring.py`                                                   |
| What the AI is asked                                  | `services/prompts.py`                                                   |
| A skill the app does not recognise ("node" = Node.js) | `config/word_lists.py`                                                  |
| How the job's required skills are read                | `services/job_requirements.py`                                          |
| What happens when CVs are uploaded                    | `ui/cv_upload.py`                                                       |
| The steps of the process, their names and order       | `config/steps.py` (names) and `graph/workflow.py` (order and branches)  |
| The form of one step                                  | `ui/step_forms.py` (the function named after the step)                  |
| A database query                                      | `services/repository.py`                                                |
| Sign in / sign up pages                               | `ui/auth.py`                                                            |
| How long tokens are valid (15 minutes / 7 days)       | `services/security.py`                                                  |

**How a CV gets its score:** `ui/cv_upload.py` reads the file (`services/cv_parser.py`) and calls
`rank_cv()` in `services/scoring.py`. It checks the skills in the CV (`services/cv_checks.py`), asks the AI
once (`services/prompts.py` + `services/llm.py`), checks the AI's numbers and adds up the four parts.

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
| `users`        | HR / Recruitment accounts (they sign in), and HODs and interviewers (records only). `token_version` goes up by 1 on every log out                    |
| `jobs`         | Open positions: title, description, department, AI shortlist threshold                                                                               |
| `candidates`   | One row per CV: AI score and reason, where the process is now, the shortlist decision, assigned interviewers, M1 / M2 schedule, and M1 / M2 feedback |
| `activity_log` | The history: every step, when, which recruiter recorded it, and the details (channel, notes...)                                                      |

Sign-in tokens are **not** stored in the database: they are signed with `JWT_SECRET` from `.env`, so the app can
check them without a table. Running `python -m database.setup_db` removes the `login_tokens` table of older versions.

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
| "JWT_SECRET is missing"          | Add `JWT_SECRET=...` to `.env` (see Step 3), then restart the app                  |

---

## 9. Next steps (not in this starter)

- Optional: company login (Microsoft / Google) instead of email + password
- Reminders when a candidate has been waiting on a step for too long
- Decide the rule when two M1 interviewers give different feedback
  (right now, one M1 feedback is recorded and it moves the process forward)
