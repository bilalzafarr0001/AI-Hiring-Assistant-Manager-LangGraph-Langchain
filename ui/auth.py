"""
Login for HR / Recruitment (the only users of this platform).
Every page calls require_login() first. Nothing is shown until you log in.
"""
import streamlit as st

from config.settings import APP_NAME
from services import repository as repo
from services.security import verify_password


def require_login():
    user_id = st.session_state.get("user_id")
    user = repo.get_user(user_id) if user_id else None

    if not user or user["role"] != "HR":
        st.session_state.pop("user_id", None)
        _login_form()
        st.stop()

    st.sidebar.write(f"Logged in as **{user['full_name']}**")
    st.sidebar.caption(user["email"])
    if st.sidebar.button("Log out"):
        st.session_state.clear()
        st.rerun()
    return user


def _login_form():
    st.title(APP_NAME)
    st.subheader("Recruitment login")
    with st.form("login"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        if st.form_submit_button("Log in"):
            user = repo.get_login_user(email)
            if user and verify_password(password, user["password_hash"]):
                st.session_state["user_id"] = user["id"]
                st.rerun()
            else:
                st.error("Wrong email or password.")
