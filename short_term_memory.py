class ShortTermMemory:
    def __init__(self):
        # The Drum: List of dicts 
        # [{'card': {...}, 'max_index': 0, 'index': 0}, ...]
        self.drum = []
        
        # Kandel-Schwartz limit: Recalling probability drops significantly after ~14 items
        self.graduation_threshold = 14  
        
    def add_card(self, card):
        """
        Accepts a new card. Initializes at 0 (Immediate review).
        """
        # Prevent duplicates
        if any(item['card']['id'] == card['id'] for item in self.drum):
            return

        self.drum.append({
            'card': card,
            'max_index': 0, # Depth in memory
            'index': 0      # Countdown
        })

    def get_ready_card(self):
        """
        Returns the most urgent card (index <= 0).
        Sorts by index ascending (most negative = most overdue).
        """
        ready = [item for item in self.drum if item['index'] <= 0]
        
        if not ready:
            return None
            
        ready.sort(key=lambda x: x['index'])
        return ready[0]['card']

    def tick(self):
        """
        The Clock: Decrements countdown for EVERYONE in the drum.
        """
        for item in self.drum:
            item['index'] -= 1

    def promote(self, card_id):
        """
        Success: Push deeper into memory.
        Pure Logic: max_index += 2, index = max_index.
        NO graduation checking here.
        """
        for item in self.drum:
            if item['card']['id'] == card_id:
                item['max_index'] += 2
                item['index'] = item['max_index']
                return # Done

    def demote(self, card_id):
        """
        Failure: Pull back to surface.
        Pure Logic: max_index -= 1, index = max_index.
        """
        for item in self.drum:
            if item['card']['id'] == card_id:
                item['max_index'] -= 1
                
                # Floor at 0
                if item['max_index'] < 0: 
                    item['max_index'] = 0
                    
                item['index'] = item['max_index']
                return

    def get_graduates(self):
        """
        Checks ALL cards for graduation.
        Returns a list of card objects that have crossed the threshold.
        Removes them from the drum.
        """
        graduated = []
        
        # Iterate backwards to safely pop items while looping
        for i in range(len(self.drum) - 1, -1, -1):
            item = self.drum[i]
            if item['max_index'] >= self.graduation_threshold:
                # Remove from drum and add to list
                graduated.append(self.drum.pop(i)['card'])
                
        return graduated

    def has_card(self, card_id):
        return any(item['card']['id'] == card_id for item in self.drum)
        
    def get_stats(self):
        return len(self.drum)
