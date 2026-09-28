"""
app.py  --  ChangeLens Streamlit UI
Run with:   streamlit run app.py
"""

import traceback
import streamlit as st

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import git_utils
import llm
import rules.spring as spring_rules

try:
    import rag as rag_module
    RAG_AVAILABLE = True
except ImportError:
    RAG_AVAILABLE = False

# ── page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ChangeLens",
    page_icon="\U0001f50d",
    layout="wide",
)

st.markdown("""
<style>
.risk-high   { background:#e53935;color:#fff;padding:3px 14px;border-radius:18px;font-weight:700; }
.risk-medium { background:#fb8c00;color:#fff;padding:3px 14px;border-radius:18px;font-weight:700; }
.risk-low    { background:#43a047;color:#fff;padding:3px 14px;border-radius:18px;font-weight:700; }
.risk-unknown{ background:#757575;color:#fff;padding:3px 14px;border-radius:18px;font-weight:700; }
</style>
""", unsafe_allow_html=True)

# ════════════════ Sidebar ════════════════════════════════════════════════════
st.sidebar.title("\U0001f50d ChangeLens")
st.sidebar.caption("Spring Boot Change-Impact Analyzer")
st.sidebar.markdown("---")

repo_input = st.sidebar.text_input(
    "Repository path or GitHub URL",
    placeholder="C:/projects/my-app   or   https://github.com/org/repo",
)
commit_input = st.sidebar.text_input(
    "Commit range or single commit",
    value="HEAD~1..HEAD",
    help="Examples:  HEAD~1..HEAD  |  abc123..def456  |  HEAD",
)

mode_labels = {
    "A - Diff only (fastest)": "A",
    "B - Diff + Spring rules": "B",
    "C - Diff + Rules + RAG (deepest)": "C",
}
mode_choice = st.sidebar.radio("Analysis mode", list(mode_labels.keys()), index=1)
mode = mode_labels[mode_choice]

if mode == "C":
    if not RAG_AVAILABLE:
        st.sidebar.warning("chromadb not installed -- RAG unavailable.")
    else:
        if st.sidebar.button("Index repo for RAG (one-time)", use_container_width=True):
            if repo_input.strip():
                with st.spinner("Indexing Java files..."):
                    try:
                        n = rag_module.index_repo(repo_input.strip(), force=True)
                        st.sidebar.success(f"Indexed {n} chunks.")
                    except Exception as e:
                        st.sidebar.error(f"Indexing failed: {e}")
            else:
                st.sidebar.warning("Enter a repo path first.")

st.sidebar.markdown("---")
analyze_btn = st.sidebar.button("Analyze", use_container_width=True, type="primary")

with st.sidebar.expander("Recent commits helper"):
    if st.button("Load recent commits", use_container_width=True):
        if repo_input.strip():
            with st.spinner("Loading..."):
                try:
                    recent = git_utils.list_recent_commits(repo_input.strip(), n=10)
                    for c in recent:
                        st.code(f"{c.short_sha}  {c.date[:10]}  {c.author}\n{c.message[:60]}", language=None)
                except Exception as e:
                    st.error(str(e))
        else:
            st.warning("Enter a repo path first.")

# ════════════════ Main area ══════════════════════════════════════════════════
st.title("ChangeLens")
st.subheader("Spring Boot Change-Impact Analyzer")

if not analyze_btn:
    st.info("Enter a repository path and commit range in the sidebar, then click **Analyze**.")
    st.stop()

if not repo_input.strip():
    st.error("Please enter a repository path or GitHub URL.")
    st.stop()
if not commit_input.strip():
    st.error("Please enter a commit range.")
    st.stop()

# ── 1. Git diff ───────────────────────────────────────────────────────────────
with st.spinner("Fetching git diff..."):
    try:
        diff_result = git_utils.get_diff(repo_input.strip(), commit_input.strip())
    except Exception as e:
        st.error(f"Git error: {e}")
        with st.expander("Traceback"):
            st.code(traceback.format_exc())
        st.stop()

if not diff_result.diff_text.strip():
    st.warning("No diff found -- the commits may be identical or the range is invalid.")
    st.stop()

# ── 2. Rules ──────────────────────────────────────────────────────────────────
findings = spring_rules.analyse(diff_result.diff_text)
rule_findings_text = llm.format_rule_findings(findings)

# ── 3. RAG ───────────────────────────────────────────────────────────────────
rag_context = ""
if mode == "C" and RAG_AVAILABLE:
    with st.spinner("Retrieving RAG context..."):
        try:
            rag_context = rag_module.build_rag_context(
                diff_result.diff_text, diff_result.changed_files
            )
        except Exception as e:
            st.warning(f"RAG retrieval failed (continuing without it): {e}")

# ── 4. LLM ───────────────────────────────────────────────────────────────────
commit_info_text = llm.format_commit_info(diff_result.commits)
with st.spinner(f"Running LLM analysis (mode {mode})..."):
    try:
        report = llm.analyse(
            diff_text=diff_result.diff_text,
            commit_info_text=commit_info_text,
            mode=mode,
            rule_findings_text=rule_findings_text if mode in ("B", "C") else "",
            rag_context=rag_context,
        )
    except Exception as e:
        st.error(f"LLM error: {e}")
        with st.expander("Traceback"):
            st.code(traceback.format_exc())
        st.stop()

# ════════════════ Report ═════════════════════════════════════════════════════

# Metrics bar
c1, c2, c3, c4 = st.columns(4)
c1.metric("Files changed", diff_result.stats.get("files", 0))
c2.metric("Lines added", f"+{diff_result.stats.get('insertions', 0)}")
c3.metric("Lines removed", f"-{diff_result.stats.get('deletions', 0)}")
c4.metric("Mode", f"Mode {report.get('_mode', mode)}")

st.divider()

# 1. Summary
st.markdown("### What changed (plain English)")
st.markdown(report.get("summary", "No summary generated."))

# 2. Risk badge
st.markdown("### Risk Level")
risk = report.get("risk_level", "Unknown").strip()
reason = report.get("risk_reason", "")
css_class = f"risk-{risk.lower()}" if risk.lower() in ("high", "medium", "low") else "risk-unknown"
st.markdown(f'<span class="{css_class}">{risk}</span>&nbsp;&nbsp;{reason}', unsafe_allow_html=True)

# 3. Changes table
st.markdown("### Change details")
changes = report.get("changes", [])
if changes:
    import pandas as pd
    df = pd.DataFrame(changes)
    rename = {"what": "What changed", "who": "Who", "when": "When",
               "why": "Why (inferred)", "what_could_break": "What could break"}
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    st.dataframe(df, use_container_width=True, hide_index=True)
else:
    st.info("No individual changes returned by the LLM.")

# 4. Technical details
st.markdown("### Technical details")

with st.expander("Raw git diff", expanded=False):
    st.code(diff_result.diff_text or "(empty)", language="diff")

label = f"Rule-based findings ({len(findings)} detected)"
with st.expander(label, expanded=(mode != "A" and len(findings) > 0)):
    if findings:
        for f in findings:
            icon = {"high": "\U0001f534", "medium": "\U0001f7e1", "low": "\U0001f7e2"}.get(f.severity, "\u26aa")
            st.markdown(f"{icon} **[{f.category.upper()}]** {f.description}")
            if f.detail:
                st.code(f.detail, language="java")
    else:
        st.info("No Spring Boot-specific patterns detected in this diff.")

if mode == "C" and rag_context:
    with st.expander("RAG context used", expanded=False):
        st.code(rag_context, language=None)

llm_tech = report.get("technical_findings", [])
if llm_tech:
    with st.expander("LLM technical findings", expanded=False):
        for item in llm_tech:
            st.markdown(f"- {item}")

st.divider()
st.caption(
    f"Model: {report.get('_model', '?')} | "
    f"Time: {report.get('_elapsed_s', '?')}s | "
    f"Mode: {mode} | ChangeLens"
)
