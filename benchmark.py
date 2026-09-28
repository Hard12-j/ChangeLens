"""
benchmark.py
------------
Run all three analysis modes on a list of commits and save results.

Usage:
    python benchmark.py --repo /path/to/repo --n 5
    python benchmark.py --repo /path/to/repo --commits sha1,sha2,sha3
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime

import git_utils
import llm
import rules.spring as spring_rules

try:
    import rag as rag_module
    RAG_AVAILABLE = True
except ImportError:
    RAG_AVAILABLE = False

MODES = ["A", "B", "C"]


def run_single(repo_path, commit_sha, mode):
    diff_result = git_utils.get_diff(repo_path, commit_sha)
    commit_info_text = llm.format_commit_info(diff_result.commits)

    rule_findings_text = ""
    if mode in ("B", "C"):
        findings = spring_rules.analyse(diff_result.diff_text)
        rule_findings_text = llm.format_rule_findings(findings)

    rag_context = ""
    if mode == "C" and RAG_AVAILABLE:
        try:
            rag_context = rag_module.build_rag_context(
                diff_result.diff_text, diff_result.changed_files
            )
        except Exception as e:
            rag_context = f"[RAG unavailable: {e}]"

    report = llm.analyse(
        diff_text=diff_result.diff_text,
        commit_info_text=commit_info_text,
        mode=mode,
        rule_findings_text=rule_findings_text,
        rag_context=rag_context,
    )
    return {
        "mode": mode,
        "commit": commit_sha[:7],
        "risk_level": report.get("risk_level", "?"),
        "response_time_s": report.get("_elapsed_s", 0),
        "summary_preview": report.get("summary", "")[:120],
        "notes_correct_breakage": "",
        "notes_missed": "",
        "notes_false_alarm": "",
        "notes_hallucination": "",
        "_full": report,
    }


def run_benchmark(repo_path, commit_shas, output_dir="."):
    all_results = []
    total = len(commit_shas) * len(MODES)
    done = 0
    for sha in commit_shas:
        for mode in MODES:
            done += 1
            print(f"[{done}/{total}] commit={sha[:7]} mode={mode} ...", end=" ", flush=True)
            try:
                r = run_single(repo_path, sha, mode)
                print(f"risk={r['risk_level']} time={r['response_time_s']}s")
            except Exception as e:
                print(f"ERROR: {e}")
                r = {"mode": mode, "commit": sha[:7], "risk_level": "ERROR",
                     "response_time_s": 0, "summary_preview": "",
                     "notes_correct_breakage": str(e), "notes_missed": "",
                     "notes_false_alarm": "", "notes_hallucination": "", "_full": {}}
            all_results.append(r)
            time.sleep(0.3)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = os.path.join(output_dir, f"benchmark_{ts}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nSaved to {json_path}")
    print("\n## Benchmark Results\n")
    print(_to_markdown(all_results))
    return all_results


def _to_markdown(results):
    headers = ["Mode", "Commit", "Risk", "Time(s)", "Correct Breakage", "Missed", "False Alarm", "Hallucination"]
    rows = [headers, ["---"] * len(headers)]
    for r in results:
        rows.append([
            r.get("mode", ""), r.get("commit", ""), r.get("risk_level", ""),
            str(r.get("response_time_s", "")), r.get("notes_correct_breakage", ""),
            r.get("notes_missed", ""), r.get("notes_false_alarm", ""), r.get("notes_hallucination", ""),
        ])
    return "\n".join("| " + " | ".join(row) + " |" for row in rows)


if __name__ == "__main__":
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    parser = argparse.ArgumentParser(description="ChangeLens Benchmark")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--commits", help="Comma-separated SHAs")
    parser.add_argument("--n", type=int, default=5)
    parser.add_argument("--output-dir", default=".")
    args = parser.parse_args()

    if args.commits:
        shas = [s.strip() for s in args.commits.split(",") if s.strip()]
    else:
        commits = git_utils.list_recent_commits(args.repo, args.n)
        shas = [c.sha for c in commits]
        if not shas:
            print("No commits found.", file=sys.stderr)
            sys.exit(1)
        print(f"Auto-selected {len(shas)} commits: {[s[:7] for s in shas]}")

    run_benchmark(args.repo, shas, output_dir=args.output_dir)
