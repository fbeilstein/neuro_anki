import pandas as pd
import time
import os
import ast

# Columns that belong to progress.csv (SRS state), not the dictionary
PROGRESS_COLS = ['due', 'last_review', 'history_result', 'history_intervals']

class Database:
    def __init__(self, course_name):
        self.course_name = course_name
        self.course_dir = os.path.join("courses", course_name)
        self.dict_file = os.path.join(self.course_dir, "data.csv")
        self.progress_file = os.path.join(self.course_dir, "progress.csv")
        self.df = self._load_db()

    def _load_db(self):
        if not os.path.exists(self.dict_file):
            raise FileNotFoundError(f"Course {self.course_name} not found at {self.dict_file}")

        # 1. Read Dictionary
        df_dict = pd.read_csv(self.dict_file)
        if 'media' in df_dict.columns:
            df_dict['media'] = df_dict['media'].fillna("")

        # 2. Load or create progress file
        if os.path.exists(self.progress_file):
            df_prog = pd.read_csv(self.progress_file)
        else:
            # Brand new course — create empty progress
            df_prog = pd.DataFrame({'id': df_dict['id']})

        # 3. Ensure progress columns exist with defaults
        for col in PROGRESS_COLS:
            if col not in df_prog.columns:
                default = "[]" if 'history' in col else 0
                df_prog[col] = default

        # 4. Fix types and fill NaN
        df_prog['history_result'] = df_prog['history_result'].astype(object).fillna("[]")
        df_prog['history_intervals'] = df_prog['history_intervals'].astype(object).fillna("[]")
        df_prog['due'] = df_prog['due'].fillna(0)
        df_prog['last_review'] = df_prog['last_review'].fillna(0)

        # 5. Merge dictionary + progress on 'id'
        df = pd.merge(df_dict, df_prog, on='id', how='left')

        # Fill any cards missing from progress (e.g. newly added to dict)
        df['due'] = df['due'].fillna(0)
        df['last_review'] = df['last_review'].fillna(0)
        df['history_result'] = df['history_result'].fillna("[]").astype(object)
        df['history_intervals'] = df['history_intervals'].fillna("[]").astype(object)

        return df

    def _save(self):
        """Split self.df back into dictionary + progress and save both."""
        # Dictionary: everything except progress columns
        dict_cols = [c for c in self.df.columns if c not in PROGRESS_COLS]
        self.df[dict_cols].to_csv(self.dict_file, index=False)

        # Progress: id + progress columns only
        prog_cols = ['id'] + [c for c in PROGRESS_COLS if c in self.df.columns]
        self.df[prog_cols].to_csv(self.progress_file, index=False)

    def _parse_list(self, val):
        """Safely parses string '[1, 2]' into list [1, 2]"""
        try:
            if pd.isna(val) or val == "": return []
            return ast.literal_eval(str(val)) if "[" in str(val) else []
        except:
            return []

    def _process_card(self, row):
        """
        Converts raw CSV row to usable Dict.
        Calculates 'current_interval' (Time since last review) on the fly.
        """
        c = row.to_dict()
        
        # Parse Lists
        c['history_result'] = self._parse_list(c.get('history_result'))
        c['history_intervals'] = self._parse_list(c.get('history_intervals'))
        
        # Calculate LIVE Interval (Crucial for your math)
        if c.get('last_review', 0) > 0:
            c['current_interval'] = time.time() - c['last_review']
        else:
            c['current_interval'] = 0 
            
        return c

    # --- READ METHODS ---
    def get_card(self, cid):
        try:
            row = self.df.loc[self.df['id'] == cid].iloc[0]
            return self._process_card(row)
        except IndexError:
            return None

    def get_due_cards(self, limit=1, exclude_ids=None):
        now = time.time()
        # Filter: due > 0 AND due <= now
        mask = (self.df['due'] > 0) & (self.df['due'] <= now)
        
        # These cards are currently in the short-term memory
        if exclude_ids:
            mask = mask & (~self.df['id'].isin(exclude_ids))
        
        df_res = self.df[mask].sort_values(by='due', ascending=True).head(limit)
        return [self._process_card(row) for _, row in df_res.iterrows()]
    
    def get_new_cards(self, limit=1, exclude_ids=None):
        # Filter: last_review == 0
        mask = (self.df['last_review'] == 0)
        
        # These cards are currently in the short-term memory
        if exclude_ids:
            mask = mask & (~self.df['id'].isin(exclude_ids))
        
        df_res = self.df[mask].head(limit)
        return [self._process_card(row) for _, row in df_res.iterrows()]

    # --- WRITE METHODS ---
    def update_card(self, card_id, updates):
        # Find the row index
        rows = self.df.index[self.df['id'] == card_id].tolist()
        if not rows:
            print(f"Card {card_id} not found!")
            return
        idx = rows[0]
        
        for key, val in updates.items():
            if key in self.df.columns:
                # --- TYPE SAFETY FIX ---
                # Check what type of data the column expects
                col_dtype = self.df[key].dtype
                
                try:
                    # If column is Integer, try to convert string "1" -> 1
                    if pd.api.types.is_integer_dtype(col_dtype):
                        val = int(val)
                    # If column is Float, try to convert string "1.5" -> 1.5
                    elif pd.api.types.is_float_dtype(col_dtype):
                        val = float(val)
                except ValueError:
                    # If conversion fails (e.g. user typed "Two" for a number),
                    # we pass the raw string and let Pandas decide (it might crash, which is good for debugging)
                    pass
                
                # Apply the update
                self.df.at[idx, key] = val
        
        # Save to disk (split into two files)
        self._save()

    # --- ANALYTICS ---
    def get_workload_histogram(self, days=7):
        now = time.time()
        one_day = 86400
        histogram = [0] * days
        
        valid_dues = self.df[self.df['due'] > 0]['due'].values
        
        for due in valid_dues:
            diff = due - now
            day_offset = int(diff // one_day)
            
            if day_offset < 0:
                histogram[0] += 1
            elif day_offset < days:
                histogram[day_offset] += 1
                
        return histogram
        
    def add_new_card(self, form_data):
        # 1. Generate Auto-ID
        if self.df.empty:
            new_id = 1
        else:
            new_id = int(self.df['id'].max()) + 1
            
        # 2. Prepare the new row
        new_row = {'id': new_id}
        
        # 3. Fill Content Fields from Form
        # We only take fields that actually exist in the DB columns
        for col in self.df.columns:
            if col in form_data:
                new_row[col] = form_data[col]
            elif col not in new_row: 
                # If not in form and not ID, it's a technical field or missing
                new_row[col] = None

        # 4. Auto-Fill Technical Fields (The Magic)
        new_row['due'] = 0              # Due immediately (or use time.time())
        new_row['last_review'] = 0      # Never reviewed
        new_row['history_intervals'] = "[]" # Empty list as string
        new_row['history_result'] = "[]"    # Empty list as string
        
        # 5. Append to DataFrame
        # We create a single-row DataFrame and concat it (modern Pandas way)
        new_df = pd.DataFrame([new_row])
        self.df = pd.concat([self.df, new_df], ignore_index=True)
        
        # 6. Save (split into two files)
        self._save()
        return new_id

    def delete_card(self, card_id):
        """Permanently removes a card from the database."""
        mask = self.df['id'] == card_id
        if not mask.any():
            print(f"Card {card_id} not found for deletion.")
            return False
        self.df = self.df[~mask]
        self._save()
        print(f"Card {card_id} deleted.")
        return True

    def search_cards(self, query, limit=50):
        """Case-insensitive search with fuzzy relevance scoring."""
        from thefuzz import fuzz
        
        if not query or not query.strip():
            return []
        
        q = query.strip().lower()
        text_cols = [c for c in self.df.columns if c not in ['id'] + PROGRESS_COLS]
        
        results_with_scores = []
        for idx, row in self.df.iterrows():
            # Initialize max score for the row
            max_row_score = 0
            
            for col in text_cols:
                val = str(row[col]).lower()
                
                # 1. fuzz.ratio: Standard Levenshtein (100 only if identical)
                # 2. fuzz.partial_ratio: Best substring match (100 if query is inside string)
                
                # We combine them: 
                # A perfect string match gets 100.
                # A perfect substring match gets a base high score, 
                # but is penalized by the 'full' ratio to prefer shorter strings.
                
                full_match = fuzz.ratio(q, val)
                partial_match = fuzz.partial_ratio(q, val)
                
                # Weighted Score: 
                # This ensures '鳥' (100) > '小鳥' (~80) > '鳥は飛ぶ' (~60)
                # while still allowing 'tori' to match 'torii' very highly.
                current_cell_score = (partial_match * 0.7) + (full_match * 0.3)
                
                if current_cell_score > max_row_score:
                    max_row_score = current_cell_score
            
            if max_row_score > 45:  # Threshold to filter out garbage noise
                results_with_scores.append((max_row_score, row))
        
        # Sort by the best cell score found in each row
        results_with_scores.sort(key=lambda x: x[0], reverse=True)
        
        return [self._process_card(row) for score, row in results_with_scores[:limit]]
