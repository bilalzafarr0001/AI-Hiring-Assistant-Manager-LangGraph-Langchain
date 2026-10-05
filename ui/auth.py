"""
Login for HR / Recruitment (the only users of this platform).
Every page calls require_login() first. Nothing is shown until you log in.

How you stay logged in (login token):
1. When HR logs in, the app makes a random token and saves it in the login_tokens table
   (only a hash of it, see services/security.py). It is valid for 7 days.
2. The token is also saved in the browser as a cookie, so refreshing the page or
   opening a new tab does not show the login form again.
3. On every page, the token is checked in the database. Unknown or expired -> login form.
4. "Log out" deletes the token from the database and from the browser.
"""
import streamlit as st

from config.settings import APP_NAME
from services import repository as repo
from services.security import TOKEN_DAYS, hash_token, new_token, verify_password

COOKIE_NAME = "hiring_ai_token"


def require_login():
    user = _current_user()
    if not user:
        _login_form()
        st.stop()

    # Just logged in: also save the token in the browser.
    if st.session_state.pop("save_cookie", False):
        _set_cookie(st.session_state["token"], max_age_seconds=TOKEN_DAYS * 24 * 60 * 60)

    st.sidebar.write(f"Logged in as **{user['full_name']}**")
    st.sidebar.caption(user["email"])
    if st.sidebar.button("Log out"):
        _log_out()
    return user


def _current_user():
    """
    The logged-in HR user, or None.
    The token comes from this browser session, or (after a refresh / in a new tab) from the cookie.
    """
    token = st.session_state.get("token") or st.context.cookies.get(COOKIE_NAME)
    if not token:
        return None
    user = repo.get_user_by_token(hash_token(token))
    if user:
        st.session_state["token"] = token
    return user


def _login_form():
    # Just logged out: remove the token from the browser too.
    if st.session_state.pop("clear_cookie", False):
        _set_cookie("", max_age_seconds=0)

    st.title(APP_NAME)
    st.subheader("Recruitment login")
    with st.form("login"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        if st.form_submit_button("Log in"):
            user = repo.get_login_user(email)
            if user and verify_password(password, user["password_hash"]):
                token = new_token()
                repo.save_login_token(user["id"], hash_token(token), TOKEN_DAYS)
                st.session_state["token"] = token
                st.session_state["save_cookie"] = True   # done on the next run, see require_login()
                st.rerun()
            else:
                st.error("Wrong email or password.")


def _log_out():
    repo.delete_login_token(hash_token(st.session_state["token"]))
    st.session_state.clear()
    st.session_state["clear_cookie"] = True   # done on the next run, see _login_form()
    st.rerun()


def _set_cookie(value, max_age_seconds):
    """
    Saves the token in the browser (or removes it, with max_age_seconds=0).
    Streamlit can read cookies but cannot write them, so a small script does it.
    """
    secure = "; Secure" if (st.context.url or "").startswith("https") else ""   # once the app is live on HTTPS
    st.html(
        f'<script>document.cookie = "{COOKIE_NAME}={value}; Max-Age={max_age_seconds}; '
        f'Path=/; SameSite=Strict{secure}";</script>',
        unsafe_allow_javascript=True,
    )
