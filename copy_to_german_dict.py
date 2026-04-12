import pandas as pd
import os
import re

# --- Configuration ---
AI_FILE = "german_30k_AI_fixed.tsv"
OUTPUT_FILE = "courses/german/data.csv"

# --- 1. Compression Algorithms ---

# Inseparable verb prefixes — these do NOT separate in conjugation
INSEPARABLE_PREFIXES = {'ver', 'be', 'ent', 'er', 'ge', 'zer', 'emp', 'miss', 'hinter'}

# Separable verb prefixes — these split off in main clauses
SEPARABLE_PREFIXES = ['ab', 'an', 'auf', 'aus', 'bei', 'ein', 'mit', 'nach', 'vor', 'zu',
                      'weg', 'her', 'hin', 'los', 'fest', 'frei', 'um', 'durch']

# Fugen-elements for compound word detection
FUGEN_ELEMENTS = ["", "s", "es", "n", "en", "er", "e"]

# POS normalization map for minor/variant POS tags
POS_NORMALIZE = {
    'CONJ/ADV': 'CONJ', 'ADV/CONJ': 'ADV', 'PREP/POSTP': 'PREP',
    'ADVB': 'ADV', 'ADVERB': 'ADV'
}


def apply_dsl_shorthand(lemma, plural):
    """Compress noun plural form into DSL shorthand."""
    plu = plural.replace("die ", "").strip()

    # No plural exists
    if plu == "-":
        return "-"

    # Same as lemma
    if plu == lemma:
        return "-"

    # Check for umlaut shift
    shifts = {'a': 'ä', 'o': 'ö', 'u': 'ü', 'au': 'äu'}
    umlaut_detected = False
    for plain, umlaut in shifts.items():
        if plain in lemma.lower() and umlaut in plu.lower():
            umlaut_detected = True
            break

    if umlaut_detected:
        for end in ["er", "e", "n"]:
            if plu.endswith(end):
                return f'"{end}'
        return '"'

    # Suffix-only addition
    if plu.startswith(lemma):
        return plu.replace(lemma, "")

    return plu


def apply_adj_shorthand(lemma, comp, sup):
    """Compress adjective comparison forms into shorthand."""
    lemma = lemma.lower().strip()
    comp = comp.lower().strip()
    sup = sup.lower().replace("am ", "").strip()

    # Uninflectable adjective — no comparison forms
    if comp == "-" or comp == lemma:
        return lemma

    # Determine expected superlative suffix
    if any(lemma.endswith(e) for e in ["d", "t", "s", "ß", "z", "x"]):
        expected_suffix = "esten"
    else:
        expected_suffix = "sten"

    # Regular comparison: X → Xer → am Xsten
    if comp == lemma + "er" and sup == lemma + expected_suffix:
        return lemma

    # Umlaut comparison: X → Ẍer → am Ẍsten
    shifts = {'a': 'ä', 'o': 'ö', 'u': 'ü', 'au': 'äu'}
    for plain, umlaut in shifts.items():
        if plain in lemma:
            umlaut_stem = lemma.replace(plain, umlaut, 1)
            if comp == umlaut_stem + "er" and sup == umlaut_stem + expected_suffix:
                return f'{lemma}, "'

    # Irregular — show full forms
    return f"{lemma}, {comp}, am {sup}"


def apply_verb_shorthand(lemma, pres, pret, part, aux):
    """Compress verb conjugation into shorthand showing only irregular parts."""
    lemma = lemma.lower().strip()

    # Handle reflexive verbs: strip "sich " prefix
    reflexive = False
    if lemma.startswith("sich "):
        reflexive = True
        lemma = lemma[5:]

    # Determine if verb has an inseparable prefix (do NOT separate these)
    is_inseparable = any(lemma.startswith(p) and len(lemma) > len(p) + 2
                         for p in INSEPARABLE_PREFIXES)

    prefix = ""
    base = lemma

    if not is_inseparable:
        for p in SEPARABLE_PREFIXES:
            if lemma.startswith(p) and len(lemma) > len(p) + 2:
                prefix = p
                base = lemma[len(p):]
                break

    # Build stem
    stem = base[:-2] if base.endswith('en') else base[:-1]
    filler = "e" if stem.endswith(('t', 'd')) else ""

    # Expected weak-verb forms
    if prefix:
        exp_pres = f"{stem}{filler}t {prefix}".strip()
        exp_pret = f"{stem}{filler}te {prefix}".strip()
        exp_part = f"{prefix}ge{stem}{filler}t"
    elif is_inseparable:
        exp_pres = f"{stem}{filler}t"
        exp_pret = f"{stem}{filler}te"
        exp_part = f"{stem}{filler}t"  # inseparable: no "ge-" prefix
    else:
        exp_pres = f"{stem}{filler}t"
        exp_pret = f"{stem}{filler}te"
        if base.endswith("ieren"):
            exp_part = f"{stem}{filler}t"  # -ieren verbs: no "ge-"
        else:
            exp_part = f"ge{stem}{filler}t"

    # Compare actual vs expected, collect differences
    diffs = []
    if pres.lower() != exp_pres:
        diffs.append(pres)
    if pret.lower() != exp_pret or part.lower() != exp_part:
        diffs.append(pret)
        # Reconstruct participle with auxiliary
        if aux == "ist":
            diffs.append(f"ist {part}")
        elif aux == "hat/ist":
            diffs.append(f"hat/ist {part}")
        else:
            diffs.append(part)
    elif aux == "ist":
        diffs.append("ist")
    elif aux == "hat/ist":
        diffs.append("hat/ist")

    # Rebuild output
    out_lemma = f"sich {lemma}" if reflexive else lemma
    if not diffs:
        return out_lemma
    return f"{out_lemma}, {', '.join(diffs)}"


# --- 2. The Grammar Parser Engine ---

def generate_compressed_de(row):
    """Routes the grammar info to the correct compressor based on POS."""
    lemma = str(row['Lemma']).strip()
    pos = str(row['POS']).strip()
    gi = str(row['Grammar_Info']).strip()

    # Normalize minor POS tags
    pos = POS_NORMALIZE.get(pos, pos)

    try:
        parts = [p.strip() for p in gi.split(',')]

        if pos == "NOUN":
            # Plurale tantum or headless noun entries (Ferien, Leute, Eltern)
            if len(parts) == 1:
                return f"die {lemma}"

            if len(parts) != 3:
                return f"[REVIEW] {gi}"

            art_lemma, gen, plu = parts

            art = art_lemma.split(' ')[0] if ' ' in art_lemma else ''
            noun_lemma = art_lemma.split(' ')[1] if ' ' in art_lemma else art_lemma

            plu_short = apply_dsl_shorthand(noun_lemma, plu)

            if art == "die":
                return f"{art_lemma}, {plu_short}"
            else:
                # Robust genitive article stripping
                clean_gen = re.sub(r'^(des|der|die|das)\s+', '', gen.strip())
                gen_end = clean_gen.replace(noun_lemma, "") if clean_gen.startswith(noun_lemma) else clean_gen

                if not gen_end or gen_end == "-":
                    gen_end = "-"

                # Standard masculine/neuter -s/-es are suppressed
                if gen_end in ["s", "es"]:
                    return f"{art_lemma}, {plu_short}"
                else:
                    return f"{art_lemma}, {gen_end}, {plu_short}"

        elif pos == "VERB":
            if len(parts) != 4:
                return f"[REVIEW] {gi}"
            pres, pret, perf_str = parts[1], parts[2], parts[3]

            # Parse auxiliary from perfect form
            if perf_str.startswith("hat/ist "):
                aux, part = "hat/ist", perf_str[8:]
            elif perf_str.startswith("ist "):
                aux, part = "ist", perf_str[4:]
            elif perf_str.startswith("hat "):
                aux, part = "hat", perf_str[4:]
            else:
                aux, part = "hat", perf_str

            return apply_verb_shorthand(lemma, pres, pret, part, aux)

        elif pos == "ADJ":
            if len(parts) == 1:
                return apply_adj_shorthand(lemma, "-", "-")
            if len(parts) == 3:
                return apply_adj_shorthand(lemma, parts[1], parts[2])
            return f"[REVIEW] {gi}"

        elif pos == "PREP":
            if "+" in gi:
                cases_part = gi.split("+")[1].upper()
                cases = []
                if "N" in cases_part: cases.append("N")
                if "G" in cases_part: cases.append("G")
                if "D" in cases_part: cases.append("D")
                if "A" in cases_part: cases.append("A")
                if cases:
                    return f"{lemma}, {''.join(cases)}"
            return f"{lemma}, {gi}"

        else:
            # ADV, CONJ, DET, PRON — Verb position encoding
            formatted_gi = gi.replace("->", ",")
            formatted_gi = formatted_gi.replace("Hauptsatz", "2")
            formatted_gi = formatted_gi.replace("Nebensatz", "-1")
            formatted_gi = formatted_gi.replace(" ,", ",").replace(",  ", ", ")
            return formatted_gi

    except Exception as e:
        return f"[REVIEW] {gi}"


# --- 3. Compound Word Detection ---

def detect_noun_compounds(df):
    """
    Detects true compound nouns by ensuring BOTH the prefix and suffix are valid nouns.
    """
    nouns_list = df[df['POS'] == 'NOUN']['Lemma'].str.strip().tolist()
    nouns_lower = set(n.lower() for n in nouns_list)
    
    fugen_elements = ["", "s", "es", "n", "en", "er", "e"]
    compounds = set()

    for word in nouns_list:
        word_lower = word.lower()
        if len(word_lower) < 6:
            continue

        found_compound = False
        
        # FIX: len(word_lower) - 2 allows it to catch 3-letter suffixes (like 'tür' or 'weg')
        for i in range(3, len(word_lower) - 2):
            prefix = word_lower[:i]
            suffix = word_lower[i:]

            if suffix in nouns_lower:
                for f in fugen_elements:
                    if f == "":
                        candidate_base = prefix
                    elif prefix.endswith(f):
                        candidate_base = prefix[:-len(f)]
                    else:
                        continue

                    if candidate_base in nouns_lower:
                        compounds.add(word)
                        found_compound = True
                        break
            if found_compound:
                break

    # --- SANITY CHECK PRINTS ---
    print(f"   -> Found {len(compounds)} true compounds.")
    if compounds:
        sample = list(compounds)[:5]
        print(f"   -> Pushing to bottom, examples: {sample}")

    return compounds


def compound_aware_sort_key(row, compounds, freq_map):
    """
    Sort key: (is_compound_group, cluster_rank, own_freq_rank)
    - Group 0: Simple words (sorted by their own frequency)
    - Group 1: Compound words (clustered by base word frequency, then sorted by own frequency)
    """
    lemma = str(row['Lemma']).strip()
    own_rank = freq_map.get(lemma, 99999)

    if lemma in compounds:
        base = compounds[lemma]
        base_rank = freq_map.get(base, 99999)
        # '1' pushes to bottom. 'base_rank' groups siblings. 'own_rank' sorts within the group.
        return (1, base_rank, own_rank) 
    else:
        # '0' keeps at top. 'own_rank' sorts by frequency. The final '0' is a dummy value for shape matching.
        return (0, own_rank, 0)


# --- 4. Execution Logic ---

print("🚀 Starting German Dictionary Build Process...")

# 1. Load the AI Generated TSV
df = pd.read_csv(AI_FILE, sep='\t', dtype=str, on_bad_lines='warn').fillna("")
print(f"📥 Loaded {len(df)} words from {AI_FILE}.")

# 2. Assign frequency rank (1 = most frequent = first line of TSV)
df['freq_rank'] = range(1, len(df) + 1)

# 3. Normalize POS tags in the DataFrame
df['POS'] = df['POS'].map(lambda p: POS_NORMALIZE.get(p.strip(), p.strip()))

# 4. Generate the compressed 'DE' column
print("⚙️  Generating compressed grammar (DE column)...")
df['DE'] = df.apply(generate_compressed_de, axis=1)

# ==========================================
# 5. COMPOUND DETECTION & SORTING
# ==========================================

print("🔗 Detecting compound words...")
compounds = detect_noun_compounds(df)
print(f"   Found {len(compounds)} compound word relationships.")

# id = original TSV line number (frequency rank), assigned BEFORE sorting
df['id'] = df['freq_rank']

# Sort: non-compounds first (by freq_rank), then compounds (by freq_rank)
df['_is_compound'] = df['Lemma'].str.strip().map(lambda l: 1 if l in compounds else 0)
df = df.sort_values(by=['_is_compound', 'freq_rank']).reset_index(drop=True)

# ==========================================
# 6. FINALIZE & SAVE
# ==========================================

df = df.rename(columns={'Grammar_Info': 'DE_full'})

final_cols = ['id', 'Lemma', 'POS', 'DE_full', 'DE', 'English_Translation',
              'German_Sentence', 'English_Sentence']

df = df[final_cols]

# Save to output
os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
df.to_csv(OUTPUT_FILE, index=False)

# Print Summary
review_count = df['DE'].str.contains(r'\[REVIEW\]', regex=True).sum()
non_compound = len(df[df['id'].astype(int) == df.index + 1])  # approximate
print(f"\n✅ Successfully created {OUTPUT_FILE} with {len(df)} records.")
print(f"   Columns: {', '.join(final_cols)}")
print(f"   Compounds pushed to bottom: {len(compounds)} words")
if review_count > 0:
    print(f"⚠️  {review_count} entries flagged with [REVIEW] in the DE column.")
else:
    print("🎉 No [REVIEW] flags — all entries compressed successfully!")
