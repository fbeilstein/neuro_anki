import os
import jinja2
from flask import Flask, render_template, request, redirect, url_for, send_from_directory
from card_manager import CardManager

app = Flask(__name__)
app.config['SECRET_KEY'] = 'neuro_anki_secret'

# --- CONFIGURATION ---
CURRENT_COURSE = "japanese"
COURSE_PATH = os.path.join("courses", CURRENT_COURSE)

# --- CRITICAL: MULTI-FOLDER TEMPLATE LOADING ---
# This tells Flask: "Look for templates in 'templates/' AND 'courses/'"
# This allows 'layout.html' (in courses) to find 'base.html' (in templates)
my_loader = jinja2.ChoiceLoader([
    jinja2.FileSystemLoader(['templates', 'courses']),
])
app.jinja_loader = my_loader

manager = CardManager(CURRENT_COURSE)

@app.route('/study')
def study():
    context = manager.get_next_card()
    if not context:
        return "<h1>No cards due! Good job.</h1>"

    card = context['card']
    
    # UI Stats calculation (same as before)
    drum_items = manager.stm.drum 
    histogram = manager.db.get_workload_histogram(7)
    total_cards = len(manager.db.df)
    seen_cards = len(manager.db.df[manager.db.df['last_review'] > 0])
    progress_pct = int((seen_cards / total_cards) * 100) if total_cards > 0 else 0

    # RENDER
    # We ask for the course-specific layout. 
    # Because of the loader above, we reference it relative to 'courses/'
    # e.g. "japanese_core/layout.html"
    template_name = f"{CURRENT_COURSE}/layout.html"
    
    return render_template(
        template_name,
        card=card,
        source=context['source'],
        drum_items=drum_items,
        histogram=histogram,
        progress_current=seen_cards,
        progress_total=total_cards,
        progress_pct=progress_pct,
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
