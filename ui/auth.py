"""
Sign in and sign up for HR / Recruitment (the only users of this platform).
Every page calls require_login() first. Nothing is shown until you sign in.

How you stay signed in (the tokens are made in services/security.py):
1. Sign in (or sign up) gives you two tokens. They are kept in this browser session and saved as browser cookies:
     access token    15 minutes   checked on every page
     refresh token   7 days       gives a new access token when the old one has expired
2. On every page:
     access token valid           -> you are in
     access token expired         -> the refresh token makes a new access token (you notice nothing)
     refresh token expired too    -> the sign-in page (after 7 days you sign in again)
3. "Log out" adds 1 to your token_version in the database, so every token made before stops working
   (on every device), and removes the cookies from this browser.
"""
import re

import psycopg
import streamlit as st

from config.settings import APP_NAME, JWT_SECRET
from config.steps import ROLE_HR
from services import repository as repo
from services.security import (ACCESS_TOKEN_MINUTES, REFRESH_TOKEN_DAYS, create_token, hash_password, read_token,
                               verify_password)

ACCESS_COOKIE = "hiring_ai_access"
REFRESH_COOKIE = "hiring_ai_refresh"
MIN_PASSWORD_LENGTH = 8
EMAIL_FORMAT = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")     # something@something.something


def require_login():
    """Returns the signed-in HR user. If nobody is signed in, shows the sign-in page and stops the page."""
    if not JWT_SECRET:
        st.error("**JWT_SECRET is missing in the .env file.** Add a line `JWT_SECRET=...` with a long random text "
                 "(see .env.example), then restart the app.", icon=":material/key:")
        st.stop()

    user = current_user()
    if not user:
        sign_in_page()
        st.stop()

    save_new_cookies()

    st.sidebar.write(f"Logged in as **{user['full_name']}**")
    st.sidebar.caption(user["email"])
    if st.sidebar.button("Log out", icon=":material/logout:"):
        log_out(user)
    return user


def current_user():
    """
    The signed-in HR user, or None.
    The tokens come from this browser session, or (after a refresh / in a new tab) from the cookies.
    """
    # 1. The access token.
    access_token = st.session_state.get("access_token") or st.context.cookies.get(ACCESS_COOKIE)
    user = user_from_token(access_token, "access")
    if user:
        st.session_state["access_token"] = access_token
        return user

    # 2. No valid access token (expired after 15 minutes, or none yet): the refresh token makes a new one.
    refresh_token = st.session_state.get("refresh_token") or st.context.cookies.get(REFRESH_COOKIE)
    user = user_from_token(refresh_token, "refresh")
    if user:
        new_access_token = create_token(user, "access")
        st.session_state["access_token"] = new_access_token
        st.session_state["refresh_token"] = refresh_token
        st.session_state["cookies_to_save"] = [(ACCESS_COOKIE, new_access_token, ACCESS_TOKEN_MINUTES * 60)]
        return user

    # 3. Both missing or expired: not signed in.
    return None


def user_from_token(token, token_type):
    """The HR user this token belongs to, or None (no token, fake, expired, or made before the user's last log out)."""
    data = read_token(token, token_type)
    if not data:
        return None
    user = repo.get_signed_in_user(int(data["sub"]))
    if not user or user["token_version"] != data["ver"]:
        return None
    return user


# ---------------------------------------------------------------- the sign-in page

def sign_in_page():
    # Just logged out: remove the tokens from the browser too.
    if st.session_state.pop("clear_cookies", False):
        set_cookie(ACCESS_COOKIE, "", max_age_seconds=0)
        set_cookie(REFRESH_COOKIE, "", max_age_seconds=0)

    st.title(APP_NAME, icon=":material/person_search:")
    st.subheader("Recruitment login")
    sign_in_tab, sign_up_tab = st.tabs(["Sign in", "Sign up"])
    with sign_in_tab:
        sign_in_form()
    with sign_up_tab:
        sign_up_form()


def sign_in_form():
    with st.form("sign-in"):
        email = st.text_input("Email", key="sign-in-email")
        password = st.text_input("Password", type="password", key="sign-in-password")
        if st.form_submit_button("Sign in", type="primary"):
            user = repo.get_login_user(email)
            if user and verify_password(password, user["password_hash"]):
                start_session(user)
            else:
                st.error("Wrong email or password.")


def sign_up_form():
    """A new HR / Recruitment account. After sign up, you are signed in straight away."""
    with st.form("sign-up"):
        full_name = st.text_input("Full name", key="sign-up-name")
        email = st.text_input("Work email", key="sign-up-email")
        password = st.text_input(f"Password (at least {MIN_PASSWORD_LENGTH} characters)", type="password",
                                 key="sign-up-password")
        confirm = st.text_input("Confirm password", type="password", key="sign-up-confirm")
        if st.form_submit_button("Create account", type="primary"):
            email = email.strip().lower()
            if not full_name.strip():
                st.error("Please enter your full name.")
            elif not EMAIL_FORMAT.match(email):
                st.error("Please enter a valid email address.")
            elif len(password) < MIN_PASSWORD_LENGTH:
                st.error(f"The password must be at least {MIN_PASSWORD_LENGTH} characters.")
            elif password != confirm:
                st.error("The passwords do not match.")
            else:
                try:
                    repo.create_user(full_name, email, ROLE_HR, None, hash_password(password))
                except psycopg.errors.UniqueViolation:
                    st.error("An account with this email already exists. Please sign in instead.")
                    return
                start_session(repo.get_login_user(email))


def start_session(user):
    """Signed in: make the two tokens, keep them for this browser session, and save them as cookies on the next run."""
    access_token = create_token(user, "access")
    refresh_token = create_token(user, "refresh")
    st.session_state["access_token"] = access_token
    st.session_state["refresh_token"] = refresh_token
    st.session_state["cookies_to_save"] = [
        (ACCESS_COOKIE, access_token, ACCESS_TOKEN_MINUTES * 60),
        (REFRESH_COOKIE, refresh_token, REFRESH_TOKEN_DAYS * 24 * 60 * 60),
    ]
    st.rerun()


def log_out(user):
    repo.bump_token_version(user["id"])        # every token made before (on every device) stops working
    st.session_state.clear()
    st.session_state["clear_cookies"] = True   # done on the next run, see sign_in_page()
    st.rerun()


# ---------------------------------------------------------------- cookies

def save_new_cookies():
    """Saves the tokens made on this run or the run before (after sign in, or after a refresh) in the browser."""
    for name, value, max_age_seconds in st.session_state.pop("cookies_to_save", []):
        set_cookie(name, value, max_age_seconds)


def set_cookie(name, value, max_age_seconds):
    """
    Saves a token in the browser (or removes it, with max_age_seconds=0).
    Streamlit can read cookies but cannot write them, so a small script does it.
    """
    if (st.context.url or "").startswith("https"):
        secure = "; Secure"            # once the app is live on HTTPS, the cookie is only sent over HTTPS
    else:
        secure = ""
    st.html(
        f'<script>document.cookie = "{name}={value}; Max-Age={max_age_seconds}; '
        f'Path=/; SameSite=Strict{secure}";</script>',
        unsafe_allow_javascript=True,
    )
