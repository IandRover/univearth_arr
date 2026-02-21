#!/usr/bin/env python3
"""
analysis_0220.py — Analysis script for OSCAR results (UniverEarth rebuttal).

Loads OSCAR memory JSONs from results_2602/oscar/ and baseline results from
results_2511/, computes accuracy / outcome breakdowns, and generates figures
saved to figures_0220/.

Usage:
    python analysis_0220.py                          # auto-detect latest OSCAR run
    python analysis_0220.py --oscar_dir results_2602/oscar/python/gemini-2.5-pro+gemini-2.5-flash__v1
    python analysis_0220.py --baseline_model gemini-2.5-pro
"""

import argparse
import copy
import glob
import json
import math
import os
import re
from collections import Counter, defaultdict

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
import seaborn as sns

# ═══════════════════════════════════════════════════════════════════════════════
# 0. CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

PRED_MEANING_MAP = {
    "A": "Yes",
    "B": "No",
    "C1": "Empty Collection",
    "C2": "No Valid Pixels",
    "C3": "Calculation Failure",
    "D": "Execution Error",
}

OUTCOME_ORDER = [
    "Correct",
    "Wrong Answer",
    "C1 (Empty)",
    "C2 (No Pixels)",
    "C3 (Calc Fail)",
    "D (Syntax Err)",
]

STACK_COLORS = {
    "Correct": "#2E7D32",
    "Wrong Answer": "#F9A825",
    "C1 (Empty)": "#90A4AE",
    "C2 (No Pixels)": "#546E7A",
    "C3 (Calc Fail)": "#37474F",
    "D (Syntax Err)": "#C62828",
}


# ═══════════════════════════════════════════════════════════════════════════════
# 1. HELPERS
# ═══════════════════════════════════════════════════════════════════════════════


def safe_load_json(filepath):
    """Load JSON that may contain bare NaN (not valid JSON but Python-common)."""
    with open(filepath, "r") as f:
        text = f.read()
    text = text.replace("NaN", "null")
    return json.loads(text)


def normalize_gt(raw_gt):
    """Convert raw ground-truth to 'Yes' / 'No'."""
    if raw_gt is None:
        return "Yes"
    if isinstance(raw_gt, float) and math.isnan(raw_gt):
        return "Yes"
    s = str(raw_gt).strip()
    if s in ("NaN", "nan", "null", ""):
        return "Yes"
    if s.lower() == "no":
        return "No"
    return s


def categorize_result(gt, pred):
    """Classify outcome into one of the 6 categories."""
    if (gt == "Yes" and pred == "A") or (gt == "No" and pred == "B"):
        return "Correct"
    if pred in ("A", "B"):
        return "Wrong Answer"
    if pred == "C1":
        return "C1 (Empty)"
    if pred == "C2":
        return "C2 (No Pixels)"
    if pred == "C3":
        return "C3 (Calc Fail)"
    if pred == "D":
        return "D (Syntax Err)"
    return "Unknown"


def _extract_self_answer(exec_msg, exec_returncode):
    """Extract the self-reported answer (A/B/C1/C2/C3/D) from execution output.

    Handles multiple output formats:
      - Bare: "A", "B", "C1", "C2", "C3", "D"
      - Tagged: "<answer>A</answer>"
      - Labeled: "A: Yes", "B: No", "C1: Empty Collection", "C2: No Valid Pixels", etc.
    """
    if exec_returncode != 0:
        return "D"
    if not exec_msg or not exec_msg.strip():
        return "D"

    # First try <answer>X</answer> tags (most reliable)
    tag_match = re.search(r"<answer>\s*(A|B|C1|C2|C3|D)\s*</answer>", exec_msg)
    if tag_match:
        return tag_match.group(1)

    # Scan lines bottom-up for any recognized answer pattern
    for line in reversed(exec_msg.strip().split("\n")):
        line = line.strip()
        # Exact match
        if line in ("A", "B", "C1", "C2", "C3", "D"):
            return line
        # "A: Yes", "B: No", "C1: Empty Collection", etc.
        m = re.match(r"^(A|B|C1|C2|C3|D)\b", line)
        if m:
            return m.group(1)

    assert False, f"Could not parse self-reported answer from:\n{exec_msg}"
    return "D"


def save_fig(fig, save_dir, name):
    """Save a figure as both PDF and PNG."""
    for ext in ("pdf", "png"):
        path = os.path.join(save_dir, f"{name}.{ext}")
        fig.savefig(path, dpi=300, bbox_inches="tight")
    print(f"  Saved: {os.path.join(save_dir, name)}.{{pdf,png}}")


# ═══════════════════════════════════════════════════════════════════════════════
# 2. DATA LOADERS
# ═══════════════════════════════════════════════════════════════════════════════


def load_oscar_results(oscar_dir):
    """Load all OSCAR memory JSONs from a single run directory.

    For each question, extracts:
      - round_answers: list of self-reported answers at each execution round
        round_answers[0] = first exec (round 0), [1] = after 1st replan, etc.
      - final answer from the summary (post-verify)
    """
    records = []
    for fname in sorted(os.listdir(oscar_dir)):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(oscar_dir, fname)
        data = safe_load_json(fpath)
        meta = data.get("metadata", {})
        summary = data.get("summary", {})
        trajectory = data.get("trajectory", [])

        gt_norm = normalize_gt(meta.get("answer"))
        final_answer = summary.get("final_answer", "D")

        replan_count = summary.get("replan_attempts", 0)
        confidence = summary.get("confidence", "unknown")
        answer_source = summary.get("answer_source", "unknown")

        # Extract per-round self-reported answers from trajectory
        round_answers = []
        for t in trajectory:
            if t["state"] in ("execute_run", "replan_execute"):
                msg = t["data"].get("exec_msg", "")
                rc = t["data"].get("exec_returncode", -1)
                ans = _extract_self_answer(msg, rc)
                round_answers.append(ans)

        first_exec_answer = round_answers[0] if round_answers else None

        record = {
            "unique_id": meta.get("unique_id"),
            "filename": fname,
            "language": meta.get("language", "python"),
            "strategy": "oscar",
            "code_llm": meta.get("code_llm"),
            "answer_llm": meta.get("answer_llm"),
            "gt_raw": meta.get("answer"),
            "gt_answer": gt_norm,
            "pred_code": final_answer,
            "pred_meaning": PRED_MEANING_MAP.get(final_answer, "Unknown"),
            "question": meta.get("question"),
            "url": meta.get("url"),
            # OSCAR-specific fields
            "replan_attempts": replan_count,
            "confidence": confidence,
            "answer_source": answer_source,
            "first_exec_answer": first_exec_answer,
            "round_answers": round_answers,  # [round0, round1, round2, ...]
            "total_states": summary.get("total_states", 0),
        }
        records.append(record)
    return records


def load_baseline_results(
    root_dir, strategies=("zero_shot",), language="python", code_llm_filter=None
):
    """Load baseline results from results_2511.
    Returns a list of record dicts, one per (unique_id, strategy, stage).
    """
    records = []
    for strategy in strategies:
        strategy_dir = os.path.join(root_dir, strategy, language)
        if not os.path.isdir(strategy_dir):
            continue
        for model_folder in sorted(os.listdir(strategy_dir)):
            model_path = os.path.join(strategy_dir, model_folder)
            if not os.path.isdir(model_path):
                continue

            if "+" in model_folder:
                parts = model_folder.split("__")[0].split("+")
                folder_code_llm = parts[0]
                folder_answer_llm = parts[1] if len(parts) > 1 else "unknown"
            else:
                folder_code_llm = model_folder
                folder_answer_llm = "unknown"

            if code_llm_filter and folder_code_llm != code_llm_filter:
                continue

            for fname in sorted(os.listdir(model_path)):
                if not fname.endswith(".json"):
                    continue

                fpath = os.path.join(model_path, fname)
                data = safe_load_json(fpath)
                meta = data.get("metadata", {})
                gt_norm = normalize_gt(meta.get("answer"))

                data_list = data.get("data", [])
                if not data_list:
                    continue
                zs_answer = data_list[0].get("answer", "D")

                record = {
                    "unique_id": meta.get("unique_id"),
                    "filename": fname,
                    "language": meta.get("language", language),
                    "strategy": strategy,
                    "code_llm": meta.get("code_llm", folder_code_llm),
                    "answer_llm": meta.get("answer_llm", folder_answer_llm),
                    "gt_raw": meta.get("answer"),
                    "gt_answer": gt_norm,
                    "pred_code": zs_answer,
                    "pred_meaning": PRED_MEANING_MAP.get(zs_answer, "Unknown"),
                    "question": meta.get("question"),
                    "stage": "zero_shot",
                }
                records.append(record)

                # reflexion_1 stage (cumulative: keep zs_answer if reflexion didn't run)
                rfx1 = data.get("reflexion_1", [])
                rfx1_answer = rfx1[0]["answer"] if rfx1 else zs_answer
                rfx1_record = copy.deepcopy(record)
                rfx1_record.update(
                    {
                        "pred_code": rfx1_answer,
                        "pred_meaning": PRED_MEANING_MAP.get(rfx1_answer, "Unknown"),
                        "stage": "reflexion_1",
                    }
                )
                records.append(rfx1_record)

                # reflexion_2 stage
                rfx2 = data.get("reflexion_2", [])
                rfx2_answer = rfx2[0]["answer"] if rfx2 else rfx1_answer
                rfx2_record = copy.deepcopy(record)
                rfx2_record.update(
                    {
                        "pred_code": rfx2_answer,
                        "pred_meaning": PRED_MEANING_MAP.get(rfx2_answer, "Unknown"),
                        "stage": "reflexion_2",
                    }
                )
                records.append(rfx2_record)

    return records


# ═══════════════════════════════════════════════════════════════════════════════
# 3. CUMULATIVE ROUND BUILDER
# ═══════════════════════════════════════════════════════════════════════════════


def build_oscar_cumulative_rounds(df_oscar, max_rounds=4):
    """Build cumulative outcome per round for OSCAR.

    Logic: Once a question produces A or B at round k, its answer is "locked in"
    for all subsequent rounds. Only non-A/B questions get re-planned.

    Returns a DataFrame with columns: [unique_id, round, pred_code, gt_answer, outcome]
    """
    rows = []
    for _, row in df_oscar.iterrows():
        uid = row["unique_id"]
        gt = row["gt_answer"]
        round_answers = (
            row["round_answers"] if isinstance(row["round_answers"], list) else []
        )

        locked_answer = None
        for r in range(max_rounds):
            if locked_answer is not None:
                # Already got A/B — carry forward
                ans = locked_answer
            elif r < len(round_answers):
                ans = round_answers[r]
                if ans in ("A", "B"):
                    locked_answer = ans
            else:
                # No more rounds executed — carry forward last known answer
                ans = round_answers[-1] if round_answers else "D"
                if locked_answer is None and ans in ("A", "B"):
                    locked_answer = ans

            rows.append(
                {
                    "unique_id": uid,
                    "round": r,
                    "pred_code": ans,
                    "gt_answer": gt,
                    "outcome": categorize_result(gt, ans),
                }
            )

    return pd.DataFrame(rows)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. STATISTICS PRINTER
# ═══════════════════════════════════════════════════════════════════════════════


def print_rebuttal_stats(df_oscar, df_baseline):
    """Print comprehensive statistics useful for rebuttal."""
    sep = "=" * 70

    print(f"\n{sep}")
    print("  OSCAR REBUTTAL STATISTICS")
    print(f"{sep}\n")

    n_oscar = len(df_oscar)
    print(f"OSCAR samples evaluated: {n_oscar}")
    print(f"  Code LLM: {df_oscar['code_llm'].iloc[0] if n_oscar > 0 else 'N/A'}")
    print(f"  Answer LLM: {df_oscar['answer_llm'].iloc[0] if n_oscar > 0 else 'N/A'}")

    # --- OSCAR Outcome Distribution ---
    print(f"\n{'─' * 50}")
    print("1. OSCAR OUTCOME DISTRIBUTION (Final)")
    print(f"{'─' * 50}")
    oscar_outcomes = df_oscar["outcome"].value_counts()
    for outcome in OUTCOME_ORDER:
        count = oscar_outcomes.get(outcome, 0)
        pct = count / n_oscar * 100 if n_oscar > 0 else 0
        print(f"  {outcome:20s}: {count:4d}  ({pct:5.1f}%)")

    oscar_accuracy = (
        oscar_outcomes.get("Correct", 0) / n_oscar * 100 if n_oscar > 0 else 0
    )
    oscar_d_rate = (
        oscar_outcomes.get("D (Syntax Err)", 0) / n_oscar * 100 if n_oscar > 0 else 0
    )
    oscar_c_rate = (
        sum(
            oscar_outcomes.get(c, 0)
            for c in ["C1 (Empty)", "C2 (No Pixels)", "C3 (Calc Fail)"]
        )
        / n_oscar
        * 100
        if n_oscar > 0
        else 0
    )

    print(f"\n  Accuracy:          {oscar_accuracy:.1f}%")
    print(f"  D-rate:            {oscar_d_rate:.1f}%")
    print(f"  C-rate (C1+C2+C3): {oscar_c_rate:.1f}%")

    # --- Cumulative Round-by-Round ---
    print(f"\n{'─' * 50}")
    print("2. CUMULATIVE ROUND-BY-ROUND ACCURACY (OSCAR)")
    print(f"{'─' * 50}")
    print("  (Once A/B is produced, that answer is locked in for later rounds)")

    max_rounds = int(df_oscar["replan_attempts"].max()) + 1 if n_oscar > 0 else 1
    max_rounds = min(max_rounds, 4)
    df_rounds = build_oscar_cumulative_rounds(df_oscar, max_rounds=max_rounds)

    for r in range(max_rounds):
        dr = df_rounds[df_rounds["round"] == r]
        n_r = len(dr)
        if n_r == 0:
            continue
        correct_r = (dr["outcome"] == "Correct").sum()
        d_r = (dr["outcome"] == "D (Syntax Err)").sum()
        c_r = (
            dr["outcome"].isin(["C1 (Empty)", "C2 (No Pixels)", "C3 (Calc Fail)"]).sum()
        )
        ab_r = dr["pred_code"].isin(["A", "B"]).sum()
        non_ab_r = n_r - ab_r
        label = "Initial exec" if r == 0 else f"After replan {r}"
        print(
            f"  Round {r} ({label:16s}): "
            f"Acc={correct_r/n_r*100:5.1f}%  "
            f"A/B={ab_r}/{n_r}  "
            f"D={d_r}  C={c_r}  "
            f"(still non-A/B: {non_ab_r})"
        )

    # --- Re-Plan Statistics ---
    print(f"\n{'─' * 50}")
    print("3. RE-PLAN STATISTICS")
    print(f"{'─' * 50}")
    replan_counts = df_oscar["replan_attempts"].value_counts().sort_index()
    for cnt, num in replan_counts.items():
        print(f"  {cnt} re-plan attempts: {num:4d}  ({num / n_oscar * 100:.1f}%)")

    had_replan = df_oscar[df_oscar["replan_attempts"] > 0]
    n_replan = len(had_replan)
    print(
        f"\n  Questions that needed re-plan: {n_replan} / {n_oscar}  ({n_replan / n_oscar * 100:.1f}%)"
    )

    if n_replan > 0:
        replan_success = had_replan[had_replan["outcome"] == "Correct"]
        print(
            f"  Re-plan → Correct answer:     {len(replan_success)} / {n_replan}  ({len(replan_success) / n_replan * 100:.1f}%)"
        )
        replan_still_bad = had_replan[
            had_replan["outcome"].isin(
                [
                    "D (Syntax Err)",
                    "C1 (Empty)",
                    "C2 (No Pixels)",
                    "C3 (Calc Fail)",
                ]
            )
        ]
        print(
            f"  Re-plan → Still error:        {len(replan_still_bad)} / {n_replan}  ({len(replan_still_bad) / n_replan * 100:.1f}%)"
        )

    # --- Confidence Distribution ---
    print(f"\n{'─' * 50}")
    print("4. VERIFICATION CONFIDENCE")
    print(f"{'─' * 50}")
    conf_counts = df_oscar["confidence"].value_counts()
    for conf, num in conf_counts.items():
        print(f"  {str(conf):10s}: {num:4d}  ({num / n_oscar * 100:.1f}%)")

    # --- Answer Source ---
    print(f"\n{'─' * 50}")
    print("5. ANSWER SOURCE (Verify Override Rate)")
    print(f"{'─' * 50}")
    src_counts = df_oscar["answer_source"].value_counts()
    for src, num in src_counts.items():
        print(f"  {str(src):20s}: {num:4d}  ({num / n_oscar * 100:.1f}%)")

    # --- First-Exec vs Final (shows replan benefit) ---
    if "first_exec_answer" in df_oscar.columns:
        print(f"\n{'─' * 50}")
        print("6. RE-PLAN RECOVERY ANALYSIS")
        print(f"{'─' * 50}")
        has_first = df_oscar.dropna(subset=["first_exec_answer"])
        if len(has_first) > 0:
            first_correct = has_first.apply(
                lambda r: categorize_result(r["gt_answer"], r["first_exec_answer"])
                == "Correct",
                axis=1,
            ).sum()
            final_correct = has_first[has_first["outcome"] == "Correct"].shape[0]
            print(
                f"  First-exec accuracy:  {first_correct}/{len(has_first)} ({first_correct / len(has_first) * 100:.1f}%)"
            )
            print(
                f"  Final accuracy:       {final_correct}/{len(has_first)} ({final_correct / len(has_first) * 100:.1f}%)"
            )
            print(f"  Δ (re-plan gain):     +{final_correct - first_correct}")

            recovered = has_first[
                has_first.apply(
                    lambda r: categorize_result(r["gt_answer"], r["first_exec_answer"])
                    != "Correct",
                    axis=1,
                )
                & (has_first["outcome"] == "Correct")
            ]
            degraded = has_first[
                has_first.apply(
                    lambda r: categorize_result(r["gt_answer"], r["first_exec_answer"])
                    == "Correct",
                    axis=1,
                )
                & (has_first["outcome"] != "Correct")
            ]
            print(f"  Recovered (error → correct): {len(recovered)}")
            print(f"  Degraded  (correct → error): {len(degraded)}")

    # --- Comparison with Baseline ---
    if df_baseline is not None and len(df_baseline) > 0:
        print(f"\n{'─' * 50}")
        print("7. COMPARISON WITH BASELINE (same questions)")
        print(f"{'─' * 50}")

        oscar_ids = set(df_oscar["unique_id"].unique())

        for stage_name in ["zero_shot", "reflexion_1", "reflexion_2"]:
            df_bl_stage = df_baseline[
                (df_baseline["stage"] == stage_name)
                & (df_baseline["unique_id"].isin(oscar_ids))
            ]
            if len(df_bl_stage) == 0:
                continue

            df_bl_stage = df_bl_stage.copy()
            df_bl_stage["outcome"] = df_bl_stage.apply(
                lambda r: categorize_result(r["gt_answer"], r["pred_code"]), axis=1
            )

            n_bl = len(df_bl_stage)
            bl_correct = (df_bl_stage["outcome"] == "Correct").sum()
            bl_d = (df_bl_stage["outcome"] == "D (Syntax Err)").sum()
            bl_c = (
                df_bl_stage["outcome"]
                .isin(["C1 (Empty)", "C2 (No Pixels)", "C3 (Calc Fail)"])
                .sum()
            )

            df_oscar_matched = df_oscar[
                df_oscar["unique_id"].isin(df_bl_stage["unique_id"].unique())
            ]
            n_matched = len(df_oscar_matched)
            oscar_correct_m = (df_oscar_matched["outcome"] == "Correct").sum()
            oscar_d_m = (df_oscar_matched["outcome"] == "D (Syntax Err)").sum()
            oscar_c_m = (
                df_oscar_matched["outcome"]
                .isin(["C1 (Empty)", "C2 (No Pixels)", "C3 (Calc Fail)"])
                .sum()
            )

            print(f"\n  vs {stage_name} (n={n_matched} matched questions):")
            print(f"    {'Metric':25s} {'Baseline':>10s} {'OSCAR':>10s} {'Δ':>10s}")
            print(f"    {'─' * 55}")

            bl_acc = bl_correct / n_bl * 100 if n_bl > 0 else 0
            os_acc = oscar_correct_m / n_matched * 100 if n_matched > 0 else 0
            print(
                f"    {'Accuracy':25s} {bl_acc:9.1f}% {os_acc:9.1f}% {os_acc - bl_acc:+9.1f}%"
            )

            bl_dr = bl_d / n_bl * 100 if n_bl > 0 else 0
            os_dr = oscar_d_m / n_matched * 100 if n_matched > 0 else 0
            print(
                f"    {'D-rate':25s} {bl_dr:9.1f}% {os_dr:9.1f}% {os_dr - bl_dr:+9.1f}%"
            )

            bl_cr = bl_c / n_bl * 100 if n_bl > 0 else 0
            os_cr = oscar_c_m / n_matched * 100 if n_matched > 0 else 0
            print(
                f"    {'C-rate (C1+C2+C3)':25s} {bl_cr:9.1f}% {os_cr:9.1f}% {os_cr - bl_cr:+9.1f}%"
            )

            merged = pd.merge(
                df_bl_stage[["unique_id", "outcome"]].rename(
                    columns={"outcome": "bl_outcome"}
                ),
                df_oscar_matched[["unique_id", "outcome"]].rename(
                    columns={"outcome": "os_outcome"}
                ),
                on="unique_id",
                how="inner",
            )
            transitions = merged.groupby(["bl_outcome", "os_outcome"]).size()
            if len(transitions) > 0:
                print(f"\n    Transition matrix (Baseline → OSCAR):")
                for (bl_o, os_o), cnt in transitions.items():
                    if bl_o != os_o:
                        print(f"      {bl_o:20s} → {os_o:20s}: {cnt}")

    print(f"\n{sep}\n")


# ═══════════════════════════════════════════════════════════════════════════════
# 5. PLOTTING FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════


def _plot_stacked_bar(ax, x_pos, outcome_series, n_total, bar_width, label_first):
    """Helper: draw a single stacked bar and annotate percentages."""
    outcome_counts = outcome_series.value_counts()
    bottom = 0
    for oi, outcome in enumerate(OUTCOME_ORDER):
        count = outcome_counts.get(outcome, 0)
        pct = count / n_total * 100 if n_total > 0 else 0
        ax.bar(
            x_pos,
            pct,
            bottom=bottom,
            width=bar_width,
            color=STACK_COLORS[outcome],
            edgecolor="white",
            linewidth=0.5,
            alpha=0.95,
            label=outcome if label_first else "",
        )
        if pct > 6:
            y_center = bottom + pct / 2
            text_color = (
                "white"
                if outcome
                in ["Correct", "D (Syntax Err)", "C2 (No Pixels)", "C3 (Calc Fail)"]
                else "#333333"
            )
            ax.text(
                x_pos,
                y_center,
                f"{pct:.0f}%",
                ha="center",
                va="center",
                color=text_color,
                fontsize=9,
                weight="bold",
            )
        bottom += pct


def plot_oscar_vs_baseline(df_oscar, df_baseline, oscar_ids, save_dir):
    """Stacked bar chart: Zero-Shot vs Reflexion-1 vs Reflexion-2 vs OSCAR (final)."""
    sns.set_style("whitegrid", {"axes.grid": False})

    stages = ["zero_shot", "reflexion_1", "reflexion_2", "oscar"]
    stage_labels = {
        "zero_shot": "Zero-Shot",
        "reflexion_1": "Refl-1",
        "reflexion_2": "Refl-2",
        "oscar": "OSCAR",
    }

    # Build combined data (only matched IDs)
    rows = []
    for stage in ["zero_shot", "reflexion_1", "reflexion_2"]:
        df_s = df_baseline[
            (df_baseline["stage"] == stage) & (df_baseline["unique_id"].isin(oscar_ids))
        ].copy()
        df_s["method"] = stage
        df_s["outcome"] = df_s.apply(
            lambda r: categorize_result(r["gt_answer"], r["pred_code"]), axis=1
        )
        rows.append(df_s[["unique_id", "method", "outcome"]])

    df_os = df_oscar[df_oscar["unique_id"].isin(oscar_ids)].copy()
    df_os["method"] = "oscar"
    rows.append(df_os[["unique_id", "method", "outcome"]])

    df_all = pd.concat(rows, ignore_index=True)
    df_all["method"] = pd.Categorical(df_all["method"], categories=stages, ordered=True)

    # Percentages
    stack_data = df_all.groupby(["method", "outcome"]).size().unstack(fill_value=0)
    stack_pct = stack_data.div(stack_data.sum(axis=1), axis=0) * 100
    for col in OUTCOME_ORDER:
        if col not in stack_pct.columns:
            stack_pct[col] = 0
    stack_pct = stack_pct[OUTCOME_ORDER]

    # Plot
    fig, ax = plt.subplots(figsize=(6, 6), dpi=300)

    n_stages = len(stages)
    bar_width = 0.18
    gap = 0.03
    total_width = n_stages * bar_width + (n_stages - 1) * gap
    x_center = 0
    offsets = [
        x_center - total_width / 2 + i * (bar_width + gap) + bar_width / 2
        for i in range(n_stages)
    ]

    for si, stage in enumerate(stages):
        try:
            subset = stack_pct.loc[stage]
        except KeyError:
            continue
        bottom = 0
        for outcome in OUTCOME_ORDER:
            val = subset[outcome]
            ax.bar(
                offsets[si],
                val,
                bottom=bottom,
                width=bar_width,
                color=STACK_COLORS[outcome],
                edgecolor="white",
                linewidth=0.5,
                alpha=0.95,
                label=outcome if si == 0 else "",
            )
            if val > 6:
                y_center = bottom + val / 2
                text_color = (
                    "white"
                    if outcome
                    in [
                        "Correct",
                        "D (Syntax Err)",
                        "C2 (No Pixels)",
                        "C3 (Calc Fail)",
                    ]
                    else "#333333"
                )
                ax.text(
                    offsets[si],
                    y_center,
                    f"{val:.0f}%",
                    ha="center",
                    va="center",
                    color=text_color,
                    fontsize=9,
                    weight="bold",
                )
            bottom += val

    ax.set_ylabel("Percentage", fontsize=13)
    ax.set_ylim(0, 105)
    ax.set_xlim(offsets[0] - bar_width, offsets[-1] + bar_width)
    ax.set_xticks(offsets)
    ax.set_xticklabels([stage_labels[s] for s in stages], fontsize=10, weight="bold")
    ax.grid(axis="y", linestyle="--", alpha=0.3, color="grey", zorder=0)

    n_matched = len(df_oscar[df_oscar["unique_id"].isin(oscar_ids)])
    code_llm = df_oscar["code_llm"].iloc[0] if len(df_oscar) > 0 else "?"
    ax.set_title(
        f"OSCAR vs Baselines\n({code_llm}, n={n_matched})", fontsize=14, pad=10
    )

    handles, labels = ax.get_legend_handles_labels()
    by_label = dict(zip(labels, handles))
    ax.legend(
        [by_label[k] for k in OUTCOME_ORDER if k in by_label],
        [k for k in OUTCOME_ORDER if k in by_label],
        loc="upper center",
        bbox_to_anchor=(0.5, -0.08),
        ncol=3,
        frameon=False,
        fontsize=9,
    )
    sns.despine(left=True)
    plt.tight_layout()
    save_fig(fig, save_dir, "oscar_vs_baselines")
    plt.close()


def plot_oscar_cumulative_rounds(df_oscar, save_dir):
    """Cumulative stacked bar chart showing OSCAR results across rounds.

    Key idea: once a question gets A/B at round k, it is "locked in" for
    all subsequent rounds. Only non-A/B questions are re-planned. So each
    round's bar shows the CUMULATIVE state of all questions.
    """
    sns.set_style("whitegrid", {"axes.grid": False})

    max_rounds = int(df_oscar["replan_attempts"].max()) + 1 if len(df_oscar) > 0 else 1
    max_rounds = min(max_rounds, 4)
    df_rounds = build_oscar_cumulative_rounds(df_oscar, max_rounds=max_rounds)

    n_total = df_oscar["unique_id"].nunique()

    round_labels = {
        0: "Round 0\n(Initial)",
        1: "Round 1\n(Replan 1)",
        2: "Round 2\n(Replan 2)",
        3: "Round 3\n(Replan 3)",
    }

    fig, ax = plt.subplots(figsize=(7, 6), dpi=300)
    bar_width = 0.6

    for r in range(max_rounds):
        dr = df_rounds[df_rounds["round"] == r]
        _plot_stacked_bar(
            ax, r, dr["outcome"], n_total, bar_width, label_first=(r == 0)
        )

        # Annotate how many were still "active" (non-A/B going into this round)
        if r > 0:
            # Count questions whose answer at round r-1 was NOT A/B
            dr_prev = df_rounds[df_rounds["round"] == r - 1]
            non_ab_prev = (~dr_prev["pred_code"].isin(["A", "B"])).sum()
            ax.text(
                r,
                103,
                f"retried: {non_ab_prev}",
                ha="center",
                va="bottom",
                fontsize=7,
                color="#555",
                style="italic",
            )

    ax.set_xticks(range(max_rounds))
    ax.set_xticklabels(
        [round_labels.get(r, f"Round {r}") for r in range(max_rounds)],
        fontsize=10,
    )
    ax.set_ylabel("Percentage", fontsize=12)
    ax.set_ylim(0, 112)
    ax.set_title(
        f"OSCAR Cumulative Outcomes Across Rounds (n={n_total})",
        fontsize=13,
        pad=10,
    )
    ax.grid(axis="y", linestyle="--", alpha=0.3, color="grey", zorder=0)

    handles, labels = ax.get_legend_handles_labels()
    by_label = dict(zip(labels, handles))
    ax.legend(
        [by_label[k] for k in OUTCOME_ORDER if k in by_label],
        [k for k in OUTCOME_ORDER if k in by_label],
        loc="upper center",
        bbox_to_anchor=(0.5, -0.10),
        ncol=3,
        frameon=False,
        fontsize=9,
    )

    sns.despine(left=True)
    plt.tight_layout()
    save_fig(fig, save_dir, "oscar_cumulative_rounds")
    plt.close()


def plot_replan_effectiveness(df_oscar, save_dir):
    """Bar chart showing outcomes grouped by number of re-plan attempts used."""
    sns.set_style("whitegrid", {"axes.grid": False})

    max_rp = int(df_oscar["replan_attempts"].max()) if len(df_oscar) > 0 else 0
    rp_bins = list(range(max_rp + 1))

    fig, ax = plt.subplots(figsize=(6, 5), dpi=300)
    bar_width = 0.6

    for ri, rp in enumerate(rp_bins):
        subset = df_oscar[df_oscar["replan_attempts"] == rp]
        n = len(subset)
        if n == 0:
            continue
        _plot_stacked_bar(
            ax, ri, subset["outcome"], n, bar_width, label_first=(ri == 0)
        )
        ax.text(ri, 102, f"n={n}", ha="center", va="bottom", fontsize=8, color="#555")

    ax.set_xticks(range(len(rp_bins)))
    ax.set_xticklabels([str(r) for r in rp_bins], fontsize=11)
    ax.set_xlabel("Number of Re-Plan Attempts", fontsize=12)
    ax.set_ylabel("Percentage", fontsize=12)
    ax.set_ylim(0, 110)
    ax.set_title("Outcome by Re-Plan Attempt Count", fontsize=14, pad=10)
    ax.grid(axis="y", linestyle="--", alpha=0.3, color="grey", zorder=0)

    handles, labels = ax.get_legend_handles_labels()
    by_label = dict(zip(labels, handles))
    ax.legend(
        [by_label[k] for k in OUTCOME_ORDER if k in by_label],
        [k for k in OUTCOME_ORDER if k in by_label],
        loc="upper center",
        bbox_to_anchor=(0.5, -0.12),
        ncol=3,
        frameon=False,
        fontsize=9,
    )

    sns.despine(left=True)
    plt.tight_layout()
    save_fig(fig, save_dir, "replan_effectiveness")
    plt.close()


def plot_confidence_vs_accuracy(df_oscar, save_dir):
    """Grouped bar chart: accuracy by confidence level."""
    sns.set_style("whitegrid", {"axes.grid": False})

    conf_levels = ["high", "medium", "low"]
    existing = [c for c in conf_levels if c in df_oscar["confidence"].values]

    fig, ax = plt.subplots(figsize=(5, 4), dpi=300)

    accs = []
    counts = []
    for conf in existing:
        subset = df_oscar[df_oscar["confidence"] == conf]
        n = len(subset)
        correct = (subset["outcome"] == "Correct").sum()
        acc = correct / n * 100 if n > 0 else 0
        accs.append(acc)
        counts.append(n)

    bars = ax.bar(
        range(len(existing)),
        accs,
        color=["#2E7D32", "#F9A825", "#C62828"][: len(existing)],
        edgecolor="white",
        linewidth=0.5,
        width=0.5,
    )

    for i, (bar, acc, n) in enumerate(zip(bars, accs, counts)):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 1,
            f"{acc:.0f}%\n(n={n})",
            ha="center",
            va="bottom",
            fontsize=10,
            weight="bold",
        )

    ax.set_xticks(range(len(existing)))
    ax.set_xticklabels([c.capitalize() for c in existing], fontsize=11, weight="medium")
    ax.set_ylabel("Accuracy (%)", fontsize=12)
    ax.set_ylim(0, 110)
    ax.set_title("Accuracy by Verification Confidence", fontsize=14, pad=10)
    ax.grid(axis="y", linestyle="--", alpha=0.3, color="grey", zorder=0)

    sns.despine(left=True)
    plt.tight_layout()
    save_fig(fig, save_dir, "confidence_vs_accuracy")
    plt.close()


def plot_transition_heatmap(df_oscar, df_baseline, oscar_ids, save_dir):
    """Heatmap showing answer transitions from baseline zero_shot → OSCAR."""
    df_bl_zs = df_baseline[
        (df_baseline["stage"] == "zero_shot")
        & (df_baseline["unique_id"].isin(oscar_ids))
    ].copy()
    df_bl_zs["bl_outcome"] = df_bl_zs.apply(
        lambda r: categorize_result(r["gt_answer"], r["pred_code"]), axis=1
    )

    df_os_m = df_oscar[df_oscar["unique_id"].isin(oscar_ids)].copy()

    merged = pd.merge(
        df_bl_zs[["unique_id", "bl_outcome"]],
        df_os_m[["unique_id", "outcome"]].rename(columns={"outcome": "os_outcome"}),
        on="unique_id",
        how="inner",
    )

    if len(merged) == 0:
        return

    cats = OUTCOME_ORDER
    trans_matrix = pd.DataFrame(0, index=cats, columns=cats)
    for _, row in merged.iterrows():
        bl = row["bl_outcome"]
        os_ = row["os_outcome"]
        if bl in cats and os_ in cats:
            trans_matrix.loc[bl, os_] += 1

    trans_matrix = trans_matrix.loc[
        trans_matrix.sum(axis=1) > 0, trans_matrix.sum(axis=0) > 0
    ]

    if trans_matrix.empty:
        return

    fig, ax = plt.subplots(figsize=(7, 5), dpi=300)
    sns.heatmap(
        trans_matrix,
        annot=True,
        fmt="d",
        cmap="YlOrRd",
        ax=ax,
        linewidths=0.5,
        linecolor="white",
        cbar_kws={"label": "Count"},
    )
    ax.set_xlabel("OSCAR Outcome", fontsize=12)
    ax.set_ylabel("Zero-Shot Outcome", fontsize=12)
    ax.set_title(f"Zero-Shot → OSCAR Transition (n={len(merged)})", fontsize=14, pad=10)
    plt.tight_layout()
    save_fig(fig, save_dir, "transition_heatmap")
    plt.close()


# ═══════════════════════════════════════════════════════════════════════════════
# 6. MAIN
# ═══════════════════════════════════════════════════════════════════════════════


def auto_detect_oscar_dir(base="results_2602/oscar/python"):
    """Find the most recent (or largest) OSCAR results directory."""
    if not os.path.isdir(base):
        return None
    candidates = []
    for d in os.listdir(base):
        dp = os.path.join(base, d)
        if os.path.isdir(dp) and "devmate" not in d:
            n_files = len([f for f in os.listdir(dp) if f.endswith(".json")])
            candidates.append((n_files, dp))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def main():
    parser = argparse.ArgumentParser(description="Analyze OSCAR results")
    parser.add_argument(
        "--oscar_dir",
        type=str,
        default=None,
        help="Path to OSCAR results directory",
    )
    parser.add_argument(
        "--baseline_dir",
        type=str,
        default="results_2511",
        help="Path to baseline results root",
    )
    parser.add_argument(
        "--baseline_model",
        type=str,
        default=None,
        help="Filter baseline to this code_llm (e.g. gemini-2.5-pro)",
    )
    parser.add_argument(
        "--save_dir",
        type=str,
        default="figures_0220",
        help="Directory to save figures",
    )
    args = parser.parse_args()

    oscar_dir = args.oscar_dir or auto_detect_oscar_dir()
    if oscar_dir is None or not os.path.isdir(oscar_dir):
        print("ERROR: No OSCAR results directory found. Use --oscar_dir to specify.")
        return

    os.makedirs(args.save_dir, exist_ok=True)

    print(f"Loading OSCAR results from: {oscar_dir}")
    oscar_records = load_oscar_results(oscar_dir)
    df_oscar = pd.DataFrame(oscar_records)
    print(f"  Loaded {len(df_oscar)} OSCAR records")

    if len(df_oscar) == 0:
        print("No OSCAR records found. Exiting.")
        return

    df_oscar["outcome"] = df_oscar.apply(
        lambda r: categorize_result(r["gt_answer"], r["pred_code"]), axis=1
    )

    # Auto-detect baseline model from OSCAR code_llm
    baseline_model = args.baseline_model or df_oscar["code_llm"].iloc[0]
    print(f"\nLoading baseline results from: {args.baseline_dir}")
    print(f"  Filtering for code_llm={baseline_model}")

    # Load from the deepest available strategy dir (contains all stages)
    load_strategy = None
    for s in ("reflexion_2", "reflexion_1", "zero_shot"):
        check_dir = os.path.join(args.baseline_dir, s, "python")
        if os.path.isdir(check_dir):
            for d in os.listdir(check_dir):
                if d.startswith(baseline_model + "+"):
                    load_strategy = s
                    break
        if load_strategy:
            break

    baseline_records = []
    if load_strategy:
        baseline_records = load_baseline_results(
            args.baseline_dir,
            strategies=(load_strategy,),
            language="python",
            code_llm_filter=baseline_model,
        )

    df_baseline = pd.DataFrame(baseline_records) if baseline_records else pd.DataFrame()
    print(f"  Loaded {len(df_baseline)} baseline records")

    if len(df_baseline) > 0:
        df_baseline = df_baseline.drop_duplicates(
            subset=["unique_id", "stage"], keep="last"
        )
        print(f"  After dedup: {len(df_baseline)} baseline records")

    # --- Print Stats ---
    print_rebuttal_stats(df_oscar, df_baseline)

    # --- Generate Figures ---
    oscar_ids = set(df_oscar["unique_id"].unique())
    print("Generating figures...")

    # Fig 1: OSCAR vs Baselines stacked bar
    if len(df_baseline) > 0:
        plot_oscar_vs_baseline(df_oscar, df_baseline, oscar_ids, args.save_dir)
    else:
        print("  Skipping oscar_vs_baselines (no baseline data)")

    # Fig 2: Cumulative rounds (the key cumulative chart)
    plot_oscar_cumulative_rounds(df_oscar, args.save_dir)

    # Fig 3: Re-plan effectiveness (by attempt count)
    plot_replan_effectiveness(df_oscar, args.save_dir)

    # Fig 4: Confidence vs Accuracy
    plot_confidence_vs_accuracy(df_oscar, args.save_dir)

    # Fig 5: Transition heatmap
    if len(df_baseline) > 0:
        plot_transition_heatmap(df_oscar, df_baseline, oscar_ids, args.save_dir)
    else:
        print("  Skipping transition_heatmap (no baseline data)")

    print("\nDone! All figures saved to:", args.save_dir)


if __name__ == "__main__":
    main()
