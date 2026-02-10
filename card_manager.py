import time
import ast
from database import Database
from long_term_memory import LongTermMemory
from short_term_memory import ShortTermMemory

class CardManager:
    def __init__(self, course_name):
        self.db = Database(course_name)
        self.ltm = LongTermMemory()
        self.stm = ShortTermMemory()
        
    def get_next_card(self):
        """
        Retrieval Logic:
        1. Check Drum (Short Term)
        2. Check DB Overdue (Long Term)
        3. Check DB New (Long Term)
        """
        # 1. Check Short Term Memory (The Drum)
        card = self.stm.get_ready_card()
        if card:
            return {
                'card': card,
                'source': 'short_term',
                'due_in_drum': True
            }
            
        # 2. Check DB for Overdue
        due_cards = self.db.get_due_cards(limit=1)
        if due_cards:
            return {
                'card': due_cards[0],
                'source': 'long_term',
                'due_in_drum': False
            }
            
        # 3. Check DB for New
        new_cards = self.db.get_new_cards(limit=1)
        if new_cards:
            return {
                'card': new_cards[0],
                'source': 'long_term',
                'due_in_drum': False
            }
        
        return None

    def submit_answer(self, card_id, grade, source_was_drum):
        # 1. Tick the Drum (Time passes for everyone)
        self.stm.tick()
        
        now_ts = time.time()
        
        if grade == 1: # --- CORRECT ---
            if source_was_drum:
                # A. STM Promotion
                self.stm.promote(card_id)
                
                # B. Check Graduates
                graduates = self.stm.get_graduates()
                
                # C. Handle Graduation
                for card in graduates:
                    print(f"Card {card['id']} graduated to LTM.")
                    # Reset in LTM (Treat as freshly learned)
                    updates = self.ltm.reset_card(card, now_ts)
                    self.db.update_card(card['id'], updates)
            else:
                # Standard LTM Update
                card = self.db.get_card(card_id)
                updates = self.ltm.review_card(card, 1, now_ts)
                self.db.update_card(card_id, updates)
                
        else: # --- WRONG ---
            if source_was_drum:
                # STM Demotion
                self.stm.demote(card_id)
            else:
                # LTM Failure
                card = self.db.get_card(card_id)
                updates = self.ltm.review_card(card, 0, now_ts)
                
                # --- YOUR LOGIC FIX ---
                # Check if the card effectively has NO success record.
                # This covers:
                # 1. Fresh cards (History is []) -> sum is 0
                # 2. Panic cards (History is [0,0,0,0,0]) -> sum is 0
                try:
                    # Parse the history string back to a list to check it
                    new_history = ast.literal_eval(updates['history_result'])
                    
                    if sum(new_history) == 0:
                        print(f"Card {card_id} has no success on record. Adding to Drum.")
                        self.stm.add_card(card)
                        
                except Exception as e:
                    print(f"Error checking history for drum: {e}")

                # Save the "bad" history to DB
                self.db.update_card(card_id, updates)
