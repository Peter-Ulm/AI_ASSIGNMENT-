"""
Streamlit frontend for the University Student Support Assistant.

Talks to the FastAPI backend (/ask, /health, /feedback). Handles the error
situations required by the assignment (Task 7):
  - backend not running   -> clear connection error
  - empty question        -> prompt the user to type one
  - slow response         -> loading spinner
and offers a Good/Average/Poor rating (Bonus Option E).

Run:  streamlit run app.py        (from the frontend/ folder)
"""

from __future__ import annotations

import os

import requests
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
REQUEST_TIMEOUT = int(os.getenv("FRONTEND_TIMEOUT_SECONDS", "180"))

st.set_page_config(page_title="University Student Support Assistant", page_icon="🎓")


def get_health() -> dict | None:
    try:
        resp = requests.get(f"{API_BASE_URL}/health", timeout=5)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException:
        return None


def submit_question(question: str, temperature: float) -> dict:
    """Call the backend /ask endpoint. Raises requests exceptions on failure."""
    resp = requests.post(
        f"{API_BASE_URL}/ask",
        json={"question": question, "temperature": temperature},
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code >= 400:
        # Surface the backend's clear error message (model down, etc.).
        try:
            detail = resp.json().get("detail", resp.text)
        except ValueError:
            detail = resp.text
        raise RuntimeError(detail)
    return resp.json()


def send_feedback(question: str, answer: str, rating: str) -> bool:
    try:
        resp = requests.post(
            f"{API_BASE_URL}/feedback",
            json={"question": question, "answer": answer, "rating": rating},
            timeout=10,
        )
        return resp.ok
    except requests.RequestException:
        return False


# ── Header ──────────────────────────────────────────────────────────────────
st.title("🎓 University Student Support Assistant")
st.caption(
    "Ask about course registration, exams, library, ICT, hostels, fees, the "
    "academic calendar, and student conduct."
)

# ── Sidebar: status + settings ──────────────────────────────────────────────
with st.sidebar:
    st.header("Status")
    health = get_health()
    if health is None:
        st.error("Backend not reachable. Start it with `uvicorn main:app` in backend/.")
    elif health.get("status") == "ok":
        st.success(f"Online - model: {health.get('model')}")
    else:
        st.warning(
            f"Backend up, but the model '{health.get('model')}' is not ready. "
            "Is Ollama running and the model pulled?"
        )
    st.header("Settings")
    temperature = st.slider("Creativity (temperature)", 0.0, 1.0, 0.7, 0.1)

# ── Conversation state ──────────────────────────────────────────────────────
if "history" not in st.session_state:
    st.session_state.history = []  # list of dicts: {question, answer, meta}

with st.form("ask_form", clear_on_submit=False):
    question_input = st.text_area("Your question", placeholder="e.g. How do I register for courses?")
    submitted = st.form_submit_button("Ask")

if submitted:
    if not question_input or not question_input.strip():
        st.warning("Please enter a question first.")
    else:
        with st.spinner("Thinking... contacting the local model"):
            try:
                result = submit_question(question_input.strip(), temperature)
                st.session_state.history.append({
                    "question": question_input.strip(),
                    "answer": result["answer"],
                    "meta": result,
                })
            except requests.ConnectionError:
                st.error(
                    "Could not connect to the backend. Make sure it is running "
                    f"at {API_BASE_URL} (run `uvicorn main:app` in backend/)."
                )
            except requests.Timeout:
                st.error("The request timed out. The model may be busy - try again.")
            except RuntimeError as exc:
                st.error(f"The assistant could not answer: {exc}")

# ── Render the latest answer with rating, then older history ────────────────
for i, turn in enumerate(reversed(st.session_state.history)):
    is_latest = i == 0
    st.markdown(f"**You:** {turn['question']}")
    st.markdown(f"**Assistant:** {turn['answer']}")
    meta = turn["meta"]
    caption = (
        f"model: {meta.get('model')} · {meta.get('tokens_used')} tokens · "
        f"{meta.get('generation_time')}s"
    )
    if meta.get("faq_section"):
        caption += f" · grounded in FAQ: {meta['faq_section']}"
    st.caption(caption)

    if is_latest:
        st.write("Was this answer helpful?")
        c1, c2, c3 = st.columns(3)
        for col, label in ((c1, "Good"), (c2, "Average"), (c3, "Poor")):
            if col.button(label, key=f"rate-{label}-{len(st.session_state.history)}"):
                ok = send_feedback(turn["question"], turn["answer"], label)
                st.toast("Thanks for the feedback!" if ok else "Could not save feedback.")
    st.divider()
