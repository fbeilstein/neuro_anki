import pandas as pd
import datetime
import os
import ast
import time

# --- CONFIGURATION ---
COURSE_NAME = "japanese"
# Adjust this path if your folder structure is different
DB_PATH = os.path.join("courses", COURSE_NAME, "data.csv")

# Timezone Offset for Kyiv (Standard is UTC+2, DST is UTC+3)
# Simple approach: Use system local time if server is in Kyiv, 
# or explicit offset. Let's use system local for simplicity.
def get_kyiv_time_str(timestamp):
    if timestamp == 0 or pd.isna(timestamp):
        return "Never"
    
    # Create datetime object (assuming system is configured, or use UTC)
    dt = datetime.datetime.fromtimestamp(timestamp)
    return dt.strftime('%Y-%m-%d %H:%M:%S')

def format_duration(seconds):
    if seconds == 0:
        return "0s"
    
    intervals = (
        ('d', 86400),    # 60 * 60 * 24
        ('h', 3600),     # 60 * 60
        ('m', 60),
        ('s', 1),
    )
    
    result = []
    for name, count in intervals:
        value = seconds // count
        if value:
            seconds -= value * count
            result.append(f"{int(value)}{name}")
            
    return " ".join(result[:2]) # Only show top 2 units (e.g., "5d 2h")

def print_debug_report():
    from database import Database
    
    print(f"--- LOADING DATABASE: {COURSE_NAME} ---")
    try:
        db = Database(COURSE_NAME)
    except Exception as e:
        print(f"Error loading database: {e}")
        return

    df = db.df
    
    # Filter: Only show cards that have been reviewed (last_review > 0)
    # or have a due date set.
    if 'last_review' in df.columns:
        active_cards = df[df['last_review'] > 0].copy()
    else:
        print("No 'last_review' column found. Is the DB initialized?")
        return

    if len(active_cards) == 0:
        print("No active cards found (History is empty).")
        return

    # Sort by 'due' date (most urgent first)
    active_cards = active_cards.sort_values(by='due')

    print(f"{'ID':<5} | {'Word (EN)':<20} | {'Last Review (Kyiv)':<20} | {'Next Due (Kyiv)':<20} | {'Interval':<10} | {'History (Result)':<15} | {'History (Intervals)'}")
    print("-" * 130)

    now = time.time()

    for _, row in active_cards.iterrows():
        # 1. Basic Info
        card_id = row['id']
        word = row['EN'][:18] + ".." if len(row['EN']) > 18 else row['EN']
        
        # 2. Timestamps
        last_rev = get_kyiv_time_str(row['last_review'])
        due_date = get_kyiv_time_str(row['due'])
        
        # 3. Calculated Status
        is_overdue = row['due'] < now
        status_icon = "[!]" if is_overdue else "   "
        
        # 4. History Parsing
        try:
            # Parse string lists "[1, 0, 1]" -> List
            hist_res = ast.literal_eval(str(row['history_result']))
            hist_int = ast.literal_eval(str(row['history_intervals']))
            
            # Format History: 1=OK, 0=Fail
            # e.g. [OK, FAIL, OK]
            res_str = str(hist_res).replace("1", "OK").replace("0", "FAIL")
            
            # Format Intervals: Convert seconds to human readable
            # e.g. [300, 86400] -> [5m, 1d]
            int_str = "[" + ", ".join([format_duration(i) for i in hist_int]) + "]"
            
        except:
            res_str = "Error"
            int_str = "Error"

        # 5. Current Interval (Estimated from last history or due - last)
        # Just showing the time until due (or time overdue)
        delta = row['due'] - now
        if delta < 0:
            time_str = f"Overdue {format_duration(abs(delta))}"
        else:
            time_str = f"Due in {format_duration(delta)}"

        print(f"{card_id:<5} | {word:<20} | {last_rev:<20} | {status_icon} {due_date:<16} | {time_str:<10} | {res_str:<15} | {int_str}")

if __name__ == "__main__":
    print_debug_report()
