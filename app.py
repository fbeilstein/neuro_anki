from flask import Flask, render_template, request, redirect, url_for, send_from_directory
from card_manager import CardManager
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'neuro_anki_secret'

# --- CONFIGURATION ---
CURRENT_COURSE = "japanese"
COURSE_PATH = os.path.join("courses", CURRENT_COURSE)

# Initialize Manager (Loads DB, LTM, STM)
manager = CardManager(CURRENT_COURSE)

@app.route('/')
def index():
    return redirect(url_for('study'))

@app.route('/study')
def study():
    # 1. Get Next Card
    # This returns: {'card': {...}, 'source': 'drum'/'db', 'due_in_drum': True/False}
    context = manager.get_next_card()
    
    if not context:
        return "<h1>No cards due! Good job.</h1>"

    card = context['card']
    
    # 2. Get UI Stats
    # A. Drum State (Show 'EN' to avoid spoilers)
    # We grab the whole drum list to visualize it
    drum_items = manager.stm.drum # Access raw list for UI
    
    # B. Histogram (Next 7 days)
    histogram = manager.db.get_workload_histogram(7)
    
    # C. Progress (LTM vs Total)
    # We estimate "LTM" as cards that have > 0 reviews
    # Total cards is len(df)
    total_cards = len(manager.db.df)
    seen_cards = len(manager.db.df[manager.db.df['last_review'] > 0])
    progress_pct = int((seen_cards / total_cards) * 100) if total_cards > 0 else 0

    # 3. Render
    # We assume the HTML is inside the course folder
    return render_template(
        'layout.html', 
        
        # Card Data
        card=card,
        source=context['source'],
        
        # UI Stats
        drum_items=drum_items,
        histogram=histogram,
        progress_current=seen_cards,
        progress_total=total_cards,
        progress_pct=progress_pct,
        
        # System
        course=CURRENT_COURSE
    )

@app.route('/answer', methods=['POST'])
def answer():
    card_id = int(request.form['card_id'])
    grade = int(request.form['grade']) # 1 or 0
    source = request.form['source']    # 'short_term' or 'long_term'
    
    # Determine if it came from the drum (for your Promotion logic)
    was_in_drum = (source == 'short_term')
    
    # Submit to Manager
    manager.submit_answer(card_id, grade, was_in_drum)
    
    return redirect(url_for('study'))

# --- MEDIA SERVER ---
@app.route('/media/<path:filename>')
def serve_media(filename):
    # Serves audio files from courses/japanese_core/media/
    media_dir = os.path.join(COURSE_PATH, "media")
    return send_from_directory(media_dir, filename)

if __name__ == '__main__':
    # Add the course folder to template path so Flask finds layout.html
    app.template_folder = COURSE_PATH
    app.run(debug=True, port=5000)
