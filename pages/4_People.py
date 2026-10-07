"""Departments, HODs, interviewers, recruitment accounts and password change."""
import streamlit as st

from config.steps import ROLE_HOD, ROLE_INTERVIEWER, ROLE_LABELS, ROLE_RECRUITER
from services import repository as repo
from services.security import hash_password, verify_password
from ui.auth import require_login

st.set_page_config(page_title="People", page_icon=":material/group:", layout="wide")
user = require_login()
st.title("People", icon=":material/group:")
st.caption("HODs and interviewers are kept here as records only. They do not log in. "
           "Only recruiter accounts (the hiring department) can log in.")

departments = repo.list_departments()
dept_names = {d["id"]: d["name"] for d in departments}

departments_tab, people_tab, accounts_tab, password_tab = st.tabs(
    ["Departments", "HODs & interviewers", "Recruitment accounts", "My password"])

# ---------------------------------------------------------------- departments
with departments_tab:
    with st.form("add-dept", clear_on_submit=True):
        name = st.text_input("New department name")
        if st.form_submit_button("Add department"):
            if not name.strip():
                st.error("Please enter a name.")
            elif repo.create_department(name):
                st.success("Department added.")
                st.rerun()
            else:
                st.error(f"The department '{name.strip()}' already exists.")
    st.dataframe([{"Department": d["name"]} for d in departments], hide_index=True, width="stretch")

# ---------------------------------------------------------------- HODs and interviewers (records only, no login)
with people_tab:
    if not departments:
        st.info("Add a department first.")
    else:
        with st.form("add-person", clear_on_submit=True):
            full_name = st.text_input("Full name")
            email = st.text_input("Email")
            role = st.selectbox("Role", [ROLE_HOD, ROLE_INTERVIEWER], format_func=ROLE_LABELS.get)
            dept_id = st.selectbox("Department", list(dept_names), format_func=dept_names.get, key="new-person-department")
            if st.form_submit_button("Add person"):
                if not full_name.strip() or not email.strip():
                    st.error("Please enter a name and an email.")
                else:
                    try:
                        repo.create_user(full_name, email, role, dept_id)
                        st.success("Person added.")
                        st.rerun()
                    except Exception:
                        st.error("This email already exists.")
    people = [p for p in repo.list_users() if p["role"] in (ROLE_HOD, ROLE_INTERVIEWER)]
    st.dataframe([{"Name": p["full_name"], "Email": p["email"], "Role": ROLE_LABELS[p["role"]],
                   "Department": p["department"]} for p in people], hide_index=True, width="stretch")

# ---------------------------------------------------------------- recruiter accounts (they log in)
with accounts_tab:
    with st.form("add-hr", clear_on_submit=True):
        full_name = st.text_input("Full name")
        email = st.text_input("Email (used to log in)")
        password = st.text_input("Password (min 8 characters)", type="password")
        if st.form_submit_button("Create recruitment account"):
            if not full_name.strip() or not email.strip():
                st.error("Please enter a name and an email.")
            elif len(password) < 8:
                st.error("Password must be at least 8 characters.")
            else:
                try:
                    repo.create_user(full_name, email, ROLE_RECRUITER, None, hash_password(password))
                    st.success("Account created. They can now log in.")
                    st.rerun()
                except Exception:
                    st.error("This email already exists.")
    recruiters = repo.list_users(role=ROLE_RECRUITER)
    st.dataframe([{"Name": u["full_name"], "Email": u["email"],
                   "Can log in": "Yes" if u["password_hash"] else "No"} for u in recruiters],
                 hide_index=True, width="stretch")

# ---------------------------------------------------------------- change my own password
with password_tab:
    with st.form("change-pw", clear_on_submit=True):
        current = st.text_input("Current password", type="password")
        new = st.text_input("New password (min 8 characters)", type="password")
        confirm = st.text_input("Confirm new password", type="password")
        if st.form_submit_button("Change password"):
            if not verify_password(current, user["password_hash"]):
                st.error("Current password is wrong.")
            elif len(new) < 8:
                st.error("New password must be at least 8 characters.")
            elif new != confirm:
                st.error("The new passwords do not match.")
            else:
                repo.set_password(user["id"], hash_password(new))
                st.success("Password changed.")
