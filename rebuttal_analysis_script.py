#!/usr/bin/env python3
"""Rebuttal analysis: process-level error breakdown + capability taxonomy."""

import os, json, re, math
import pandas as pd
from collections import Counter

ROOT = '/Users/chiahsiang1/Documents/univearth_arr'
OSCAR_DIR = os.path.join(ROOT, 'results_2602/oscar/python/gemini-2.5-pro+gemini-2.5-flash__v2')
BASELINE_DIR = os.path.join(ROOT, 'results_2511/zero_shot/python/gemini-2.5-pro+gemini-2.5-flash__v1')
DATASET_PATH = os.path.join(ROOT, 'dataset/2026_acl_univearth_1123.csv')

def safe_load_json(fpath):
    with open(fpath) as f:
        text = f.read()
    text = text.replace('NaN', 'null')
    return json.loads(text)

def normalize_gt(raw_gt):
    if raw_gt is None or (isinstance(raw_gt, float) and math.isnan(raw_gt)):
        return 'Yes'
    s = str(raw_gt).strip()
    if s in ('NaN', 'nan', 'null', ''):
        return 'Yes'
    if s.lower() == 'no':
        return 'No'
    return s

# ============================================================
# PART 1: Process-Level Error Analysis
# ============================================================

def classify_oscar_error(data):
    summary = data.get('summary', {})
    trajectory = data.get('trajectory', [])
    metadata = data.get('metadata', {})
    final_answer = summary.get('final_answer', 'D')
    gt = normalize_gt(metadata.get('answer'))
    correct = (gt == 'Yes' and final_answer == 'A') or (gt == 'No' and final_answer == 'B')
    if correct:
        return 'Correct', 'correct'
    if final_answer == 'D':
        error_detail = 'syntax/runtime'
        for t in trajectory:
            stderr = t.get('data', {}).get('exec_stderr', '')
            exec_msg = t.get('data', {}).get('exec_msg', '')
            combined = stderr + ' ' + exec_msg
            if 'did not match any bands' in combined or ('band' in combined.lower() and 'error' in combined.lower()):
                error_detail = 'wrong_band'
                break
            elif 'not found' in combined.lower() or 'Asset' in combined:
                error_detail = 'wrong_dataset'
                break
            elif 'timeout' in combined.lower() or 'timed out' in combined.lower():
                error_detail = 'timeout'
                break
        return 'Execution Error (D)', error_detail
    if final_answer == 'C1':
        return 'Empty Collection (C1)', 'temporal_spatial_mismatch'
    if final_answer == 'C2':
        return 'No Valid Pixels (C2)', 'masking_preprocessing'
    if final_answer == 'C3':
        return 'Calculation Failure (C3)', 'numerical_issue'
    if final_answer in ('A', 'B'):
        return 'Wrong Answer', 'reasoning_threshold'
    return 'Unknown', 'unknown'

# Process OSCAR results
oscar_records = []
for fname in sorted(os.listdir(OSCAR_DIR)):
    if not fname.endswith('.json'):
        continue
    data = safe_load_json(os.path.join(OSCAR_DIR, fname))
    category, detail = classify_oscar_error(data)
    oscar_records.append({
        'filename': fname,
        'category': category,
        'detail': detail,
        'replan_attempts': data.get('summary', {}).get('replan_attempts', 0),
        'final_answer': data.get('summary', {}).get('final_answer', 'D'),
        'question': data.get('metadata', {}).get('question', ''),
    })

df_oscar = pd.DataFrame(oscar_records)

# Process baseline results
baseline_records = []
for fname in sorted(os.listdir(BASELINE_DIR)):
    if not fname.endswith('.json'):
        continue
    data = safe_load_json(os.path.join(BASELINE_DIR, fname))
    metadata = data.get('metadata', {})
    data_list = data.get('data', [])
    if not data_list:
        continue
    zs_answer = data_list[0].get('answer', 'D')
    gt = normalize_gt(metadata.get('answer'))
    correct = (gt == 'Yes' and zs_answer == 'A') or (gt == 'No' and zs_answer == 'B')
    if correct:
        category, detail = 'Correct', 'correct'
    elif zs_answer == 'D':
        detail = 'syntax/runtime'
        exec_msg = str(data_list[0].get('exec_msg', ''))
        exec_stderr = str(data_list[0].get('exec_stderr', ''))
        combined = exec_stderr + ' ' + exec_msg
        if 'did not match any bands' in combined or ('band' in combined.lower() and 'error' in combined.lower()):
            detail = 'wrong_band'
        elif 'not found' in combined.lower() or 'Asset' in combined:
            detail = 'wrong_dataset'
        category = 'Execution Error (D)'
    elif zs_answer == 'C1':
        category, detail = 'Empty Collection (C1)', 'temporal_spatial_mismatch'
    elif zs_answer == 'C2':
        category, detail = 'No Valid Pixels (C2)', 'masking_preprocessing'
    elif zs_answer == 'C3':
        category, detail = 'Calculation Failure (C3)', 'numerical_issue'
    elif zs_answer in ('A', 'B'):
        category, detail = 'Wrong Answer', 'reasoning_threshold'
    else:
        category, detail = 'Unknown', 'unknown'
    baseline_records.append({
        'filename': fname,
        'category': category,
        'detail': detail,
        'final_answer': zs_answer,
        'question': metadata.get('question', ''),
    })

df_baseline = pd.DataFrame(baseline_records)

# Print results
print('=' * 70)
print('PART 1: PROCESS-LEVEL ERROR BREAKDOWN')
print('=' * 70)

cat_counts = df_oscar['category'].value_counts()
cat_counts_b = df_baseline['category'].value_counts()

all_cats = ['Correct', 'Wrong Answer', 'Empty Collection (C1)', 'No Valid Pixels (C2)', 'Calculation Failure (C3)', 'Execution Error (D)']
print(f'\n{"Category":30s} | {"Baseline (ZS)":>14s} | {"OSCAR":>14s} | {"Delta":>10s}')
print('-' * 75)
for cat in all_cats:
    b_cnt = cat_counts_b.get(cat, 0)
    o_cnt = cat_counts.get(cat, 0)
    b_pct = b_cnt / len(df_baseline) * 100 if len(df_baseline) > 0 else 0
    o_pct = o_cnt / len(df_oscar) * 100 if len(df_oscar) > 0 else 0
    delta = o_pct - b_pct
    print(f'  {cat:28s} | {b_cnt:4d} ({b_pct:5.1f}%) | {o_cnt:4d} ({o_pct:5.1f}%) | {delta:+6.1f}%')
print(f'\n  {"TOTAL":28s} | {len(df_baseline):4d}          | {len(df_oscar):4d}          |')

print(f'\n--- OSCAR Detailed Error Subtypes ---')
detail_counts = df_oscar['detail'].value_counts()
for det, cnt in detail_counts.items():
    print(f'  {det:30s}: {cnt:4d} ({cnt/len(df_oscar)*100:.1f}%)')

print(f'\n--- Baseline Detailed Error Subtypes ---')
detail_counts_b = df_baseline['detail'].value_counts()
for det, cnt in detail_counts_b.items():
    print(f'  {det:30s}: {cnt:4d} ({cnt/len(df_baseline)*100:.1f}%)')

# ============================================================
# PART 2: Capability Taxonomy
# ============================================================

df_data = pd.read_csv(DATASET_PATH)

def classify_capabilities(question):
    q = question.lower()
    caps = []
    if any(re.search(p, q) for p in [
        r'\b(between|from)\s+\w+\s+\d{4}\s+(and|to)',
        r'\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{4}',
        r'\b\d{4}[-/]\d{2}',
        r'\b(before|after|during|since|prior to)\b',
        r'\b(increase|decrease|change|trend|compared to|higher than|lower than|more than|less than)\b',
    ]):
        caps.append('Temporal Reasoning')
    if any(re.search(p, q) for p in [
        r'\b(region|area|boundary|country|city|state|province|basin|coast|ocean|lake|river|island)\b',
        r'\b(north|south|east|west|central|northern|southern|eastern|western)\b',
    ]):
        caps.append('Spatial Reasoning')
    if any(re.search(p, q) for p in [
        r'\b(ndvi|ndwi|mndwi|ndsi|evi|savi|nbr|bsi|lst|nir|swir)\b',
        r'\b(band ratio|spectral|reflectance|radiance|emissivity)\b',
        r'\b(surface temperature|land surface|sea surface)\b',
    ]):
        caps.append('Spectral Index Computation')
    if any(re.search(p, q) for p in [
        r'\b(higher|lower|greater|less|more|exceed|above|below|larger|smaller)\b',
        r'\b(compare|comparison|differ|difference|ratio)\b',
        r'\b(increase|decrease|decline|rise|drop|fall|grow)\b',
    ]):
        caps.append('Quantitative Comparison')
    if any(re.search(p, q) for p in [
        r'\b(anomal|unusual|extreme|outbreak|event|disaster|flood|drought|storm|eruption|earthquake)\b',
        r'\b(hotspot|burn|wildfire|blaze|fire)\b',
    ]):
        caps.append('Anomaly/Event Detection')
    if any(re.search(p, q) for p in [
        r'\b(average|mean|total|sum|median|aggregate|overall)\b',
        r'\b(concentration|density|amount|volume|depth|thickness|rainfall|precipitation)\b',
    ]):
        caps.append('Spatial Aggregation')
    if any(re.search(p, q) for p in [
        r'\b(threshold|classify|classification|detect|detection|mask|filter)\b',
        r'\b(above|below|exceed|greater than|less than)\s+\d',
    ]):
        caps.append('Threshold Classification')
    if not caps:
        caps.append('General EO Query')
    return caps

df_data['capabilities'] = df_data['Question'].apply(classify_capabilities)
df_data['n_capabilities'] = df_data['capabilities'].apply(len)

print('\n' + '=' * 70)
print('PART 2: CAPABILITY TAXONOMY')
print('=' * 70)

cap_counter = Counter()
for caps in df_data['capabilities']:
    for c in caps:
        cap_counter[c] += 1

print(f'\n--- Capability Distribution ({len(df_data)} questions) ---')
for cap, cnt in cap_counter.most_common():
    print(f'  {cap:35s}: {cnt:4d} ({cnt/len(df_data)*100:.1f}%)')

print(f'\n--- Multi-hop Complexity ---')
print(f'  Questions requiring 2+ capabilities: {(df_data["n_capabilities"] >= 2).sum()} ({(df_data["n_capabilities"] >= 2).sum()/len(df_data)*100:.1f}%)')
print(f'  Questions requiring 3+ capabilities: {(df_data["n_capabilities"] >= 3).sum()} ({(df_data["n_capabilities"] >= 3).sum()/len(df_data)*100:.1f}%)')
print(f'  Questions requiring 4+ capabilities: {(df_data["n_capabilities"] >= 4).sum()} ({(df_data["n_capabilities"] >= 4).sum()/len(df_data)*100:.1f}%)')
print(f'  Mean capabilities per question:      {df_data["n_capabilities"].mean():.2f}')

# Topic × Capability cross-tab
print(f'\n--- Topic × Capability Matrix ---')
topics = sorted(df_data['Tag'].dropna().unique())
caps_list = [c for c, _ in cap_counter.most_common()]

rows = []
for topic in topics:
    subset = df_data[df_data['Tag'] == topic]
    row = {'Topic': topic, 'N': len(subset)}
    for cap in caps_list:
        count = sum(1 for caps in subset['capabilities'] if cap in caps)
        row[cap] = count
    rows.append(row)

cross_df = pd.DataFrame(rows).set_index('Topic')
print(cross_df.to_string())
