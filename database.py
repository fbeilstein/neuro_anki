import pandas as pd
import time
import os
import ast

class Database:
    def __init__(self, course_name):
        self.course_name = course_name
        self.filename = os.path.join("courses", course_name, "data.csv")
        self.df = self._load_db()

    def _load_db(self):
        if not os.path.exists(self.filename):
            raise FileNotFoundError(f"Course {self.course_name} not found.")
        
        # 1. Read CSV
        df = pd.read_csv(self.filename)
        
        # 2. Ensure columns exist
        if 'due' not in df.columns: df['due'] = 0
        if 'last_review' not in df.columns: df['last_review'] = 0
        if 'history_result' not in df.columns: df['history_result'] = "[]"
        if 'history_intervals' not in df.columns: df['history_intervals'] = "[]"

        # 3. CRITICAL FIX: Force History Columns to be Text (Object)
        # This prevents the "Invalid value for dtype float64" crash
        df['history_result'] = df['history_result'].astype(object)
        df['history_intervals'] = df['history_intervals'].astype(object)

        # 4. Fill Empty Cells (NaN) with defaults
        df['due'] = df['due'].fillna(0)
        df['last_review'] = df['last_review'].fillna(0)
        df['history_result'] = df['history_result'].fillna("[]")
        df['history_intervals'] = df['history_intervals'].fillna("[]")
        
        return df

    def _save(self):
        self.df.to_csv(self.filename, index=False)

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
        
        # Save to disk
        self.df.to_csv(self.filename, index=False)

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
        
        # 6. Save
        self.df.to_csv(self.filename, index=False)
        return new_id
