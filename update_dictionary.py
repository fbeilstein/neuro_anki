import sys
import subprocess
import os
import pandas as pd
import daff
import streamlit as st
from streamlit.runtime import exists
from st_aggrid import AgGrid, GridOptionsBuilder, JsCode, DataReturnMode, GridUpdateMode

# --- The Terminal Course Chooser & Launcher ---
if __name__ == "__main__":
    if not exists():
        # 1. We are in the terminal. Scan the courses directory.
        courses_dir = "courses"
        if not os.path.exists(courses_dir):
            print(f"❌ Error: Could not find the '{courses_dir}' directory.")
            sys.exit(1)
            
        # Get all subdirectories in 'courses/'
        available_courses = [d for d in os.listdir(courses_dir) if os.path.isdir(os.path.join(courses_dir, d))]
        
        if not available_courses:
            print(f"❌ No course folders found inside '{courses_dir}'.")
            sys.exit(1)
            
        # 2. Render the terminal menu
        print("\n📚 Available Courses:")
        for i, course in enumerate(available_courses):
            print(f"  {i + 1}. {course.capitalize()}")
            
        # 3. Wait for user selection
        while True:
            try:
                choice = int(input(f"\nSelect a course to sync (1-{len(available_courses)}): "))
                if 1 <= choice <= len(available_courses):
                    selected_course = available_courses[choice - 1]
                    break
                else:
                    print("⚠️ Invalid selection. Try again.")
            except ValueError:
                print("⚠️ Please enter a number.")
                
        print(f"\n🚀 Booting up the Sync UI for: {selected_course.capitalize()}...")
        
        # 4. Inject the selection into the environment and launch Streamlit
        env = os.environ.copy()
        env["SYNC_COURSE_NAME"] = selected_course
        subprocess.run([sys.executable, "-m", "streamlit", "run", sys.argv[0]], env=env)
        
        # 5. Exit the terminal script gracefully when you close the browser/server
        sys.exit(0)

# --- Configuration (Streamlit is now running) ---
st.set_page_config(page_title="Course Data Sync", layout="wide")

# Fetch the course name that the terminal injected
COURSE_NAME = os.environ.get("SYNC_COURSE_NAME")

# Fallback: Just in case you run `streamlit run sync_ui.py` directly bypassing the terminal menu
if not COURSE_NAME:
    st.error("⚠️ No course selected. Please start the app by running `python sync_ui.py` in your terminal.")
    st.stop()

# Dynamically construct the file paths!
GIT_FILE = f"courses/{COURSE_NAME}/{COURSE_NAME}.csv"
APP_FILE = f"courses/{COURSE_NAME}/data.csv"
PRIMARY_KEY = "id"  
PROG_COLS = ["due", "last_review", "history_result", "history_intervals"]

st.title(f"🔄 Course Sync: {COURSE_NAME.capitalize()}")

# --- 1. Robust File Loading ---
@st.cache_data
def load_data():
    if not os.path.exists(GIT_FILE):
        st.error(f"Git file missing: {GIT_FILE}. You must have a master dictionary.")
        st.stop()
        
    df_git = pd.read_csv(GIT_FILE, dtype=str).fillna("")
    
    app_exists = os.path.exists(APP_FILE)
    if app_exists:
        df_app = pd.read_csv(APP_FILE, dtype=str).fillna("")
    else:
        st.info("App data.csv not found. Initializing a fresh course state...")
        empty_cols = list(df_git.columns) + PROG_COLS
        df_app = pd.DataFrame(columns=empty_cols)

    return df_git, df_app, app_exists

df_git, df_app, app_exists = load_data()

if app_exists:
    existing_progress = df_app[[PRIMARY_KEY] + [c for c in PROG_COLS if c in df_app.columns]].copy()
else:
    existing_progress = pd.DataFrame(columns=[PRIMARY_KEY] + PROG_COLS)

df_app_bare = df_app.drop(columns=PROG_COLS, errors='ignore')

# --- 2. Daff Diff Engine ---
def generate_daff_diff(df_local, df_remote):
    t_local = daff.PythonTableView([df_local.columns.tolist()] + df_local.values.tolist())
    t_remote = daff.PythonTableView([df_remote.columns.tolist()] + df_remote.values.tolist())
    
    alignment = daff.compareTables(t_local, t_remote).align()
    flags = daff.CompareFlags()
    flags.show_unchanged = False
    flags.show_unchanged_columns = True
    flags.addPrimaryKey(PRIMARY_KEY)
    
    data_diff = []
    t_diff = daff.PythonTableView(data_diff)
    highlighter = daff.TableDiff(alignment, flags)
    highlighter.hilite(t_diff)
    
    if len(data_diff) > 1:
        return pd.DataFrame(data_diff[1:], columns=data_diff[0])
    return pd.DataFrame()

df_diff = generate_daff_diff(df_app_bare, df_git)

if df_diff.empty or len(df_diff) <= 1:
    st.success("🎉 Everything is perfectly synced! No changes detected.")
    st.stop()

# --- 3. Split the Diff ---
df_add = df_diff[df_diff['@@'] == '+++'].reset_index(drop=True)
df_del = df_diff[df_diff['@@'] == '---'].reset_index(drop=True)
df_mod = df_diff[df_diff['@@'] == '->'].reset_index(drop=True)

st.markdown("""
* **Accept changes:** Leave rows/text as they are.
* **Reject additions/deletions:** Select the row and click the `Trash` icon in the table.
""")
st.divider()

# --- 4. Additions & Deletions UI ---
st.header(f"🆕 Additions to App ({len(df_add)})")
edited_add = st.data_editor(df_add, num_rows="dynamic", use_container_width=True, key="add")

st.header(f"🗑️ Deletions from App ({len(df_del)})")
edited_del = st.data_editor(df_del, num_rows="dynamic", use_container_width=True, key="del")

st.divider()

# --- 5. Modifications UI (AG-Grid Implementation) ---
st.header(f"🔀 Cell-Level Modifications ({len(df_mod)})")

# JavaScript to ensure only the Merged Result row is editable
editable_jscode = JsCode("""
function(params) {
    return params.data.Source === '✨ Merged Result';
}
""")

for index, row in df_mod.iterrows():
    card_id = str(row[PRIMARY_KEY])
    st.subheader(f"Card ID: `{card_id}`")
    
    app_context = df_app_bare[df_app_bare[PRIMARY_KEY] == card_id]
    git_context = df_git[df_git[PRIMARY_KEY] == card_id]
    
    if app_context.empty or git_context.empty:
        st.warning("Missing context for this card.")
        continue
        
    changed_cols = [c for c in df_diff.columns if c not in ['@@', PRIMARY_KEY] and '->' in str(row[c])]
    
    state_key = f"df_{card_id}"
    if state_key not in st.session_state:
        df_3 = pd.concat([app_context.iloc[[0]], git_context.iloc[[0]], git_context.iloc[[0]].copy()])
        df_3.index = ["📱 App Data", "🐙 Git Data", "✨ Merged Result"]
        st.session_state[state_key] = df_3
        
    # --- A. Whole-Row Copy Buttons ---
    c1, c2 = st.columns(2)
    with c1:
        if st.button(f"📱 Take Entire App Row", key=f"row_app_{card_id}", use_container_width=True):
            st.session_state[state_key].loc["✨ Merged Result"] = st.session_state[state_key].loc["📱 App Data"]
            st.rerun()
    with c2:
        if st.button(f"🐙 Take Entire Git Row", key=f"row_git_{card_id}", use_container_width=True):
            st.session_state[state_key].loc["✨ Merged Result"] = st.session_state[state_key].loc["🐙 Git Data"]
            st.rerun()

    # --- B. Granular Cell Copy Buttons ---
    if len(changed_cols) > 1:
        st.caption("Or merge specific cells individually:")
        cell_cols = st.columns(len(changed_cols))
        for i, col in enumerate(changed_cols):
            with cell_cols[i]:
                col_app, col_git = st.columns(2)
                with col_app:
                    if st.button(f"📱 {col}", key=f"cell_app_{card_id}_{col}"):
                        st.session_state[state_key].loc["✨ Merged Result", col] = st.session_state[state_key].loc["📱 App Data", col]
                        st.rerun()
                with col_git:
                    if st.button(f"🐙 {col}", key=f"cell_git_{card_id}_{col}"):
                        st.session_state[state_key].loc["✨ Merged Result", col] = st.session_state[state_key].loc["🐙 Git Data", col]
                        st.rerun()
                        
    # --- C. The AG-Grid Unified Editor ---
    # Prep the dataframe so the index becomes a static 'Source' column
    df_ag = st.session_state[state_key].copy()
    df_ag.insert(0, 'Source', df_ag.index)
    
    gb = GridOptionsBuilder.from_dataframe(df_ag)
    
    for col in df_ag.columns:
        if col == 'Source':
            # Pin the label column to the left so it doesn't scroll away
            gb.configure_column(col, pinned='left', editable=False, width=150)
        elif col in changed_cols:
            # Highlight conflicts and apply our JS edit lock!
            gb.configure_column(
                col, 
                editable=editable_jscode, 
                cellStyle={'backgroundColor': 'rgba(255, 193, 7, 0.3)', 'fontWeight': 'bold'}
            )
        else:
            # Normal columns, but still enforce the JS edit lock
            gb.configure_column(col, editable=editable_jscode)
            
    gridOptions = gb.build()
    
    st.caption("Double-click cells in the ✨ Merged Result row to edit them manually.")
    
    # Render the mighty AG-Grid
    grid_response = AgGrid(
        df_ag,
        gridOptions=gridOptions,
        update_mode=GridUpdateMode.MODEL_CHANGED,
        data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
        allow_unsafe_jscode=True,  # Crucial for our edit lock JS to work
        theme='streamlit',         # You can change to 'alpine' or 'balham' for different looks
        key=f"grid_{card_id}",
        height=150                 # Perfect height for 3 rows
    )
    
    # Capture manual edits and sync them back to Streamlit session state
    edited_df = pd.DataFrame(grid_response['data'])
    if not edited_df.empty:
        edited_df.set_index('Source', inplace=True)
        edited_df.index.name = None
        # Only update if the user actually typed something new into the grid
        if not st.session_state[state_key].equals(edited_df):
            st.session_state[state_key] = edited_df

    st.divider()

# --- 6. Execution Block ---
st.header("💾 Finalize Sync")
if st.button("🚀 Execute Sync & Patch Files", type="primary", use_container_width=True):
    
    df_final = df_app_bare.copy()
    df_final[PRIMARY_KEY] = df_final[PRIMARY_KEY].astype(str)
    df_final = df_final.set_index(PRIMARY_KEY)
    
    # Additions
    if not edited_add.empty:
        add_df = edited_add.drop(columns=['@@']).copy()
        add_df[PRIMARY_KEY] = add_df[PRIMARY_KEY].astype(str)
        df_final = pd.concat([df_final, add_df.set_index(PRIMARY_KEY)])
        
    # Deletions
    if not edited_del.empty:
        del_ids = edited_del[PRIMARY_KEY].astype(str).tolist()
        df_final = df_final.drop(index=del_ids, errors='ignore')
        
    # Modifications (Extract ONLY the "✨ Merged Result" row from state)
    for index, row in df_mod.iterrows():
        card_id = str(row[PRIMARY_KEY])
        state_key = f"df_{card_id}"
        if state_key in st.session_state and card_id in df_final.index:
            merged_row = st.session_state[state_key].loc["✨ Merged Result"]
            for col in df_final.columns:
                if col in merged_row.index:
                    df_final.at[card_id, col] = merged_row[col]
            
    df_final = df_final.reset_index()
    
    # Reattach Progress
    existing_progress[PRIMARY_KEY] = existing_progress[PRIMARY_KEY].astype(str)
    final_app = pd.merge(df_final, existing_progress, on=PRIMARY_KEY, how='left')
    
    for col in PROG_COLS:
        if col not in final_app.columns:
            final_app[col] = ""
        final_app[col] = final_app[col].fillna("")
        
    # Save files
    final_git = final_app.drop(columns=PROG_COLS, errors='ignore')
    
    try:
        final_app = final_app.sort_values(by=PRIMARY_KEY, key=lambda x: pd.to_numeric(x))
        final_git = final_git.sort_values(by=PRIMARY_KEY, key=lambda x: pd.to_numeric(x))
    except:
        final_app = final_app.sort_values(by=PRIMARY_KEY)
        final_git = final_git.sort_values(by=PRIMARY_KEY)
    
    final_git.to_csv(GIT_FILE, sep=',', index=False)
    final_app.to_csv(APP_FILE, sep=',', index=False)
    
    st.success("✅ Sync successful! Git and App are patched and perfectly aligned.")
    st.balloons()
    
    st.cache_data.clear()
    for key in list(st.session_state.keys()):
        if key.startswith("df_"):
            del st.session_state[key]
            
            
#try:
#    subprocess.run(["streamlit", "run", "sync_ui.py"])
#except KeyboardInterrupt:
#    print("Sync UI closed.")
