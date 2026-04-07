import os
import jinja2
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, session

from card_manager import CardManager
from database import PROGRESS_COLS

app = Flask(__name__)
app.config['SECRET_KEY'] = 'neuro_anki_secret'

# --- TEMPLATE LOADING ---
# Look for templates in 'templates/' AND 'courses/' so course layout.html can extend base.html
app.jinja_loader = jinja2.ChoiceLoader([
    jinja2.FileSystemLoader(['templates', 'courses']),
])

# --- COURSE MANAGEMENT ---
manager = None  # Initialized on first request or course switch

def get_available_courses():
    """Scan courses/ for ready courses (must have data.csv + layout.html)."""
    courses_dir = "courses"
    ready = []
    if os.path.exists(courses_dir):
        for name in sorted(os.listdir(courses_dir)):
            course_path = os.path.join(courses_dir, name)
            if os.path.isdir(course_path):
                has_data = os.path.exists(os.path.join(course_path, "data.csv"))
                has_layout = os.path.exists(os.path.join(course_path, "layout.html"))
                if has_data and has_layout:
                    ready.append(name)
    return ready

def get_active_course():
    """Return active course name from session, or None."""
    return session.get('active_course')

def ensure_manager():
    """Ensure manager is loaded for the active course. Returns True if ready."""
    global manager
    course = get_active_course()
    if not course:
        return False
    # Re-init if manager is None or course changed
    if manager is None or manager.db.course_name != course:
        manager = CardManager(course)
    return True


# --- ROUTES ---

@app.route('/engine.js')
def serve_engine_js():
    return send_from_directory('templates', 'engine.js')

@app.route('/')
def index():
    if not get_active_course():
        return redirect(url_for('courses'))
    return redirect(url_for('study'))

@app.route('/courses')
def courses():
    available = get_available_courses()
    active = get_active_course()
    return render_template('courses.html', courses=available, active=active)

@app.route('/switch/<course_name>')
def switch_course(course_name):
    available = get_available_courses()
    if course_name not in available:
        return f"Course '{course_name}' not found or not ready.", 404
    session['active_course'] = course_name
    global manager
    manager = CardManager(course_name)
    return redirect(url_for('study'))

@app.route('/study')
def study():
    if not ensure_manager():
        return redirect(url_for('courses'))

    course = get_active_course()
    context = manager.get_next_card()
    if not context:
        return render_template('no_cards.html',
                               course=course,
                               courses=get_available_courses())

    card = context['card']
    
    # UI Stats
    drum_items = manager.stm.drum 
    histogram = manager.db.get_workload_histogram(7)
    total_cards = len(manager.db.df)
    seen_cards = len(manager.db.df[manager.db.df['last_review'] > 0])
    progress_pct = int((seen_cards / total_cards) * 100) if total_cards > 0 else 0

    template_name = f"{course}/layout.html"
    
    return render_template(
        template_name,
        card=card,
        source=context['source'],
        drum_items=drum_items,
        histogram=histogram,
        progress_current=seen_cards,
        progress_total=total_cards,
        progress_pct=progress_pct,
        course=course,
        courses=get_available_courses()
    )

@app.route('/answer', methods=['POST'])
def answer():
    card_id = int(request.form['card_id'])
    grade = int(request.form['grade'])
    source = request.form['source']
    
    was_in_drum = (source == 'short_term')
    manager.submit_answer(card_id, grade, was_in_drum)
    
    return redirect(url_for('study'))

# --- MEDIA SERVER ---
@app.route('/media/<path:filename>')
def serve_media(filename):
    course = get_active_course()
    media_dir = os.path.join("courses", course, "media")
    return send_from_directory(media_dir, filename)


# ---- EDIT CARD ---
@app.route('/edit/<int:card_id>')
def edit_card(card_id):
    card = manager.db.get_card(card_id)
    if not card:
        return "Card not found", 404
        
    system_cols = ['id', 'due', 'last_review', 'history_intervals', 'history_result', 'current_interval']
    editable_fields = {k: v for k, v in card.items() if k not in system_cols}
    
    next_url = request.args.get('next', url_for('study'))
    
    return render_template('edit_card.html', card=card, fields=editable_fields, next_url=next_url)

@app.route('/save_card', methods=['POST'])
def save_card():
    card_id = int(request.form['card_id'])
    
    updates = {}
    for key, value in request.form.items():
        if key != 'card_id':
            updates[key] = value
            
    manager.db.update_card(card_id, updates)
    next_url = request.form.get('next_url', url_for('study'))
    return redirect(next_url)
    
@app.route('/add')
def add_card_page():
    system_cols = ['id', 'Unnamed: 0'] + PROGRESS_COLS
    
    all_cols = manager.db.df.columns.tolist()
    content_fields = [c for c in all_cols if c not in system_cols]
    
    return render_template('add_card.html', fields=content_fields)

@app.route('/create_card', methods=['POST'])
def create_card():
    new_id = manager.db.add_new_card(request.form)
    print(f"Created new card #{new_id}")
    return redirect(url_for('study'))


# ---- DELETE CARD ---
@app.route('/delete_card', methods=['POST'])
def delete_card():
    card_id = int(request.form['card_id'])
    manager.delete_card(card_id)
    return redirect(url_for('study'))


# ---- SEARCH ---
@app.route('/search')
def search():
    if not ensure_manager():
        return redirect(url_for('courses'))
    query = request.args.get('q', '').strip()
    results = manager.db.search_cards(query) if query else []
    display_cols = [c for c in manager.db.df.columns
                    if c not in ['id'] + PROGRESS_COLS]
    return render_template('search.html',
                           query=query,
                           results=results,
                           display_cols=display_cols,
                           course=get_active_course(),
                           courses=get_available_courses())


if __name__ == '__main__':
    app.run(debug=True, port=5000)
