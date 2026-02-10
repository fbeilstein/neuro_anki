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

    def get_due_cards(self, limit=1):
        now = time.time()
        # Filter: due > 0 AND due <= now
        mask = (self.df['due'] > 0) & (self.df['due'] <= now)
        
        df_res = self.df[mask].sort_values(by='due', ascending=True).head(limit)
        return [self._process_card(row) for _, row in df_res.iterrows()]
    
    def get_new_cards(self, limit=1):
        # Filter: last_review == 0
        mask = (self.df['last_review'] == 0)
        df_res = self.df[mask].head(limit)
        return [self._process_card(row) for _, row in df_res.iterrows()]

    # --- WRITE METHODS ---
    def update_card(self, cid, updates):
        idx = self.df.index[self.df['id'] == cid].tolist()
        if not idx: return
        idx = idx[0]
        
        for key, val in updates.items():
            self.df.at[idx, key] = val
                
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
