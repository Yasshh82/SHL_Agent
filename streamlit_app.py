"""
streamlit_app.py — SHL Assessment Advisor Chat UI
Run with: streamlit run streamlit_app.py
Make sure your FastAPI server is running at http://localhost:8000
"""

import requests
import streamlit as st

# ── Config ────────────────────────────────────────────────────────────────────

API_BASE = "http://localhost:8000"

st.set_page_config(
    page_title="SHL Assessment Advisor",
    page_icon="🎯",
    layout="centered",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────

st.markdown("""
<style>
    /* ── Page background ── */
    .stApp {
        background-color: #f5f6fa;
    }

    /* ── Hide default streamlit chrome ── */
    #MainMenu, footer { visibility: hidden; }
    header { visibility: visible !important; }

    /* ── Top header bar ── */
    .top-header {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 60%, #0f3460 100%);
        border-radius: 16px;
        padding: 28px 32px 24px;
        margin-bottom: 24px;
        display: flex;
        align-items: center;
        gap: 16px;
        box-shadow: 0 4px 24px rgba(15,52,96,0.18);
    }
    .top-header .icon { font-size: 2.4rem; }
    .top-header h1 {
        color: #ffffff;
        font-size: 1.55rem;
        font-weight: 700;
        margin: 0;
        letter-spacing: -0.3px;
    }
    .top-header p {
        color: #a8b9d0;
        font-size: 0.85rem;
        margin: 4px 0 0;
    }

    /* ── Chat bubbles ── */
    .bubble-wrap { margin-bottom: 6px; }

    .bubble-user {
        background: linear-gradient(135deg, #0f3460, #1a5276);
        color: #ffffff;
        border-radius: 18px 18px 4px 18px;
        padding: 12px 18px;
        max-width: 78%;
        margin-left: auto;
        margin-right: 0;
        font-size: 0.93rem;
        line-height: 1.55;
        box-shadow: 0 2px 8px rgba(15,52,96,0.15);
        word-wrap: break-word;
    }

    .bubble-agent {
        background: #ffffff;
        color: #1a1a2e;
        border-radius: 18px 18px 18px 4px;
        padding: 12px 18px;
        max-width: 82%;
        margin-left: 0;
        margin-right: auto;
        font-size: 0.93rem;
        line-height: 1.55;
        box-shadow: 0 2px 8px rgba(0,0,0,0.07);
        border: 1px solid #e8ecf0;
        word-wrap: break-word;
    }

    .label-user {
        text-align: right;
        font-size: 0.72rem;
        color: #7f8c9a;
        margin-bottom: 4px;
        padding-right: 4px;
    }
    .label-agent {
        text-align: left;
        font-size: 0.72rem;
        color: #7f8c9a;
        margin-bottom: 4px;
        padding-left: 4px;
    }

    /* ── Recommendation cards ── */
    .rec-section {
        margin-top: 14px;
        padding-top: 12px;
        border-top: 1px solid #eaecf0;
    }
    .rec-section-title {
        font-size: 0.75rem;
        font-weight: 600;
        color: #7f8c9a;
        text-transform: uppercase;
        letter-spacing: 0.6px;
        margin-bottom: 10px;
    }
    .rec-card {
        background: #f0f4ff;
        border: 1px solid #d0dbf5;
        border-left: 4px solid #0f3460;
        border-radius: 10px;
        padding: 10px 14px;
        margin-bottom: 8px;
    }
    .rec-card-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
    }
    .rec-name {
        font-weight: 600;
        font-size: 0.88rem;
        color: #1a1a2e;
    }
    .rec-badge {
        font-size: 0.7rem;
        font-weight: 700;
        padding: 2px 8px;
        border-radius: 20px;
        background: #0f3460;
        color: #ffffff;
        white-space: nowrap;
        flex-shrink: 0;
    }
    .rec-url {
        font-size: 0.75rem;
        color: #2471a3;
        margin-top: 4px;
        word-break: break-all;
    }
    .rec-url a { color: #2471a3; text-decoration: none; }
    .rec-url a:hover { text-decoration: underline; }

    /* ── Type badge colour map ── */
    .badge-A { background: #1a6b3a; }
    .badge-K { background: #7d3c98; }
    .badge-P { background: #b7500a; }
    .badge-B { background: #1a5276; }
    .badge-M { background: #a93226; }
    .badge-S { background: #0e6655; }
    .badge-C { background: #616a6b; }
    .badge-D { background: #784212; }
    .badge-E { background: #1f618d; }

    /* ── Status pills ── */
    .status-pill {
        display: inline-flex;
        align-items: center;
        gap: 5px;
        font-size: 0.75rem;
        padding: 3px 10px;
        border-radius: 20px;
        margin-bottom: 16px;
    }
    .pill-ok   { background:#e9f7ef; color:#1a6b3a; border:1px solid #a9dfbf; }
    .pill-fail { background:#fdecea; color:#a93226; border:1px solid #f1948a; }
    .pill-dot  { width:7px; height:7px; border-radius:50%; }
    .dot-ok    { background:#1a6b3a; }
    .dot-fail  { background:#a93226; }

    /* ── End-of-conversation banner ── */
    .eoc-banner {
        background: #eafaf1;
        border: 1px solid #a9dfbf;
        border-radius: 10px;
        padding: 10px 16px;
        font-size: 0.85rem;
        color: #1a6b3a;
        margin-top: 8px;
        text-align: center;
    }

    /* ── Input area ── */
    .stTextArea textarea {
        border-radius: 12px !important;
        border: 1.5px solid #d0d7df !important;
        font-size: 0.93rem !important;
        resize: none !important;
        background: #ffffff !important;
        color: #1a1a2e !important;
        caret-color: #0f3460 !important;
    }
    .stTextArea textarea:placeholder {
        color: #7f8c9a !important;
    }
    .stTextArea textarea:focus {
        border-color: #0f3460 !important;
        box-shadow: 0 0 0 3px rgba(15,52,96,0.1) !important;
    }
    .stButton > button {
        background: linear-gradient(135deg, #0f3460, #1a5276) !important;
        color: #ffffff !important;
        border: none !important;
        border-radius: 10px !important;
        font-weight: 600 !important;
        font-size: 0.92rem !important;
        padding: 10px 28px !important;
        transition: opacity 0.15s !important;
    }
    .stButton > button:hover { opacity: 0.88 !important; }

    .stButton.secondary > button {
        background: #f0f2f5 !important;
        color: #1a1a2e !important;
        border: 1.5px solid #d0d7df !important;
    }
        
    /* ── Sidebar toggle button ── */
    button[kind="header"] {
        background: #0f3460 !important;
        color: #ffffff !important;
        border-radius: 8px !important;
    }

    button[kind="header"]:hover {
        background: #1a5276 !important;
    }
</style>
""", unsafe_allow_html=True)

# ── Type label map ──────────────────

TYPE_LABELS = {
    "A": "Ability & Aptitude",
    "K": "Knowledge & Skills",
    "P": "Personality & Behavior",
    "B": "Biodata / SJT",
    "M": "Motivation",
    "S": "Simulation",
    "E": "Exercise",
    "C": "Competencies",
    "D": "Development & 360",
}

# ── Session state init ─────────────────────────────────────────────────────────

if "messages" not in st.session_state:
    st.session_state.messages = []       # [{role, content}]
if "recs_history" not in st.session_state:
    st.session_state.recs_history = {}   # turn_index → [rec, ...]
if "eoc" not in st.session_state:
    st.session_state.eoc = False
if "api_ok" not in st.session_state:
    st.session_state.api_ok = None


# ── Helpers ────────────────────────────────────────────────────────────────────

def check_health() -> bool:
    try:
        r = requests.get(f"{API_BASE}/health", timeout=5)
        return r.status_code == 200 and r.json().get("status") == "ok"
    except Exception:
        return False


def send_message(messages: list) -> dict | None:
    try:
        r = requests.post(f"{API_BASE}/chat", json={"messages": messages}, timeout=35)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.Timeout:
        return {"error": "Request timed out (>35s). The server may be busy."}
    except requests.exceptions.ConnectionError:
        return {"error": f"Cannot connect to the API at {API_BASE}. Is the server running?"}
    except Exception as e:
        return {"error": str(e)}


def render_recommendations(recs: list):
    if not recs:
        return
    st.markdown('<div class="rec-section">', unsafe_allow_html=True)
    st.markdown(f'<div class="rec-section-title">📋 {len(recs)} Assessment{"s" if len(recs) != 1 else ""} Recommended</div>', unsafe_allow_html=True)
    for rec in recs:
        t = rec.get("test_type", "A")
        label = TYPE_LABELS.get(t, t)
        badge_class = f"badge-{t}"
        st.markdown(f"""
        <div class="rec-card">
            <div class="rec-card-header">
                <span class="rec-name">{rec['name']}</span>
                <span class="rec-badge {badge_class}">{t} — {label}</span>
            </div>
            <div class="rec-url"><a href="{rec['url']}" target="_blank">🔗 {rec['url']}</a></div>
        </div>
        """, unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)


# ── Header ─────────────────────────────────────────────────────────────────────

st.markdown("""
<div class="top-header">
    <div class="icon">🎯</div>
    <div>
        <h1>SHL Assessment Advisor</h1>
        <p>Describe a role and I'll recommend the right SHL Individual Test Solutions for you.</p>
    </div>
</div>
""", unsafe_allow_html=True)

# ── API health status ──────────────────────────────────────────────────────────

col_status, col_refresh = st.columns([5, 1])
with col_refresh:
    if st.button("⟳ Check", key="health_check"):
        st.session_state.api_ok = check_health()

if st.session_state.api_ok is None:
    st.session_state.api_ok = check_health()

if st.session_state.api_ok:
    st.markdown('<div class="status-pill pill-ok"><div class="pill-dot dot-ok"></div>API connected — ready</div>', unsafe_allow_html=True)
else:
    st.markdown(f'<div class="status-pill pill-fail"><div class="pill-dot dot-fail"></div>API offline — start your server at {API_BASE}</div>', unsafe_allow_html=True)

# ── Chat history ───────────────────────────────────────────────────────────────

for i, msg in enumerate(st.session_state.messages):
    if msg["role"] == "user":
        st.markdown('<div class="label-user">You</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="bubble-user">{msg["content"]}</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="label-agent">🎯 Advisor</div>', unsafe_allow_html=True)
        recs = st.session_state.recs_history.get(i, [])
        # Build agent bubble with optional recs inside
        rec_html = ""
        if recs:
            rec_items = ""
            for rec in recs:
                t = rec.get("test_type", "A")
                label = TYPE_LABELS.get(t, t)
                rec_items += f"""
                <div class="rec-card">
                    <div class="rec-card-header">
                        <span class="rec-name">{rec['name']}</span>
                        <span class="rec-badge badge-{t}">{t} — {label}</span>
                    </div>
                    <div class="rec-url"><a href="{rec['url']}" target="_blank">🔗 {rec['url']}</a></div>
                </div>"""
            rec_html = f"""
            <div class="rec-section">
                <div class="rec-section-title">📋 {len(recs)} Assessment{"s" if len(recs) != 1 else ""} Recommended</div>
                {rec_items}
            </div>"""

        st.markdown(f'<div class="bubble-agent">{msg["content"]}{rec_html}</div>', unsafe_allow_html=True)

# ── End-of-conversation banner ─────────────────────────────────────────────────

if st.session_state.eoc:
    st.markdown('<div class="eoc-banner">✅ The advisor has completed your assessment selection. Click <b>New Conversation</b> to start over.</div>', unsafe_allow_html=True)

# ── Input area ─────────────────────────────────────────────────────────────────

st.markdown("<br>", unsafe_allow_html=True)

if not st.session_state.eoc:
    user_input = st.text_area(
        label="Your message",
        placeholder='e.g. "I\'m hiring a mid-level Java developer who collaborates with stakeholders"',
        height=90,
        label_visibility="collapsed",
        key="user_input",
    )

    col_send, col_clear = st.columns([3, 1])
    with col_send:
        send_clicked = st.button("Send →", use_container_width=True)
    with col_clear:
        clear_clicked = st.button("New Conversation", use_container_width=True)

    if send_clicked and user_input.strip():
        if not st.session_state.api_ok:
            st.error(f"Cannot reach the API at {API_BASE}. Please start your FastAPI server first.")
        else:
            # Append user message
            st.session_state.messages.append({"role": "user", "content": user_input.strip()})

            with st.spinner("Thinking..."):
                response = send_message(st.session_state.messages)

            if response and "error" in response:
                st.error(response["error"])
                st.session_state.messages.pop()  # remove failed user message
            elif response:
                reply = response.get("reply", "")
                recs  = response.get("recommendations", [])
                eoc   = response.get("end_of_conversation", False)

                # Store assistant message and its recommendations
                assistant_idx = len(st.session_state.messages)
                st.session_state.messages.append({"role": "assistant", "content": reply})
                if recs:
                    st.session_state.recs_history[assistant_idx] = recs
                if eoc:
                    st.session_state.eoc = True

            st.rerun()

    if clear_clicked:
        st.session_state.messages = []
        st.session_state.recs_history = {}
        st.session_state.eoc = False
        st.rerun()

else:
    if st.button("New Conversation", use_container_width=True):
        st.session_state.messages = []
        st.session_state.recs_history = {}
        st.session_state.eoc = False
        st.rerun()

# ── Sidebar ────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("### 💡 Example prompts")
    examples = [
        "I'm hiring a mid-level Java developer who works with stakeholders",
        "We need assessments for a senior leadership / CXO role",
        "Hiring 500 entry-level customer service agents for inbound calls",
        "Looking for a personality and safety instrument for plant operators",
        "Graduate trainee programme — need cognitive, personality and SJT",
        "What is the difference between OPQ32r and the Motivation Questionnaire?",
    ]
    for ex in examples:
        if st.button(ex, key=f"ex_{ex[:30]}", use_container_width=True):
            if not st.session_state.eoc:
                st.session_state.messages.append({"role": "user", "content": ex})
                with st.spinner("Thinking..."):
                    response = send_message(st.session_state.messages)
                if response and "error" not in response:
                    reply = response.get("reply", "")
                    recs  = response.get("recommendations", [])
                    eoc   = response.get("end_of_conversation", False)
                    assistant_idx = len(st.session_state.messages)
                    st.session_state.messages.append({"role": "assistant", "content": reply})
                    if recs:
                        st.session_state.recs_history[assistant_idx] = recs
                    if eoc:
                        st.session_state.eoc = True
                elif response:
                    st.error(response.get("error", "Unknown error"))
                    st.session_state.messages.pop()
                st.rerun()

    st.markdown("---")
    st.markdown("### 🔖 Test type legend")
    for code, label in TYPE_LABELS.items():
        st.markdown(f"**`{code}`** — {label}")

    st.markdown("---")
    st.markdown(f"**API:** `{API_BASE}`")
    st.markdown("**Model:** Gemini 2.5 Flash")
