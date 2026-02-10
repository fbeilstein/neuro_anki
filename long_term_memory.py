import time
import numpy as np
import scipy.optimize

class LongTermMemory:
    def __init__(self):
        self.history_limit = 5 
        self.reset_interval = 300  # 5 minutes

    def review_card(self, card, grade, now_ts):
        intervals = list(card.get('history_intervals', []))
        results = list(card.get('history_result', []))
        last_review = card.get('last_review', 0)

        if last_review > 0:
            # We have seen this card before, so the time passed is meaningful
            actual_interval = int(now_ts - last_review)
            
            intervals.append(actual_interval)
            results.append(int(grade))
            
            # Truncate to limit
            intervals = intervals[-self.history_limit:]
            results = results[-self.history_limit:]

        next_interval = self.predict_halftime(intervals, results)        
        return {
            'last_review': now_ts,
            'due': now_ts + next_interval,
            'history_intervals': str(intervals),
            'history_result': str(results)
        }

    def reset_card(self, card, now_ts):
        return {
            'last_review': now_ts,
            'due': now_ts + self.reset_interval,
            'history_intervals': "[]",
            'history_result': "[]"
        }

    def predict_halftime(self, delta_t, result):
        if len(result) == 0:
            return 5 * 60 # initial value
        KOEF = 3600
        data = [(int(dt) / KOEF, int(r)) for dt,r in zip(delta_t, result)]
        success = [dt for dt,r in data if r]
        failure = [dt for dt,r in data if not r]
        if len(failure) == 0:
            return int(2 * np.max(success) * KOEF) # double waiting time until a failure occurs
        if len(success) == 0:
            return int(0.5 * np.min(failure) * KOEF) # halve waiting time until a success occurs

        koef = np.log(np.sum(failure) / np.sum(success) + 1.0)
        alpha_min = koef / np.max(failure)
        alpha_max = koef / np.min(failure)
        if alpha_max - alpha_min < 1e-25:
            return int(np.log(2) / alpha_max * KOEF)

        f     = lambda x:     0.0 if x > 1e2 else (1.0 - x/2.0 if x < 1e-3 else x / (np.exp(x) - 1.0))
        func  = lambda alpha: np.sum(list(map(f, np.multiply(alpha, failure)))) / alpha - np.sum(success)
        alpha = scipy.optimize.bisect(func, alpha_min, alpha_max)
        return int(np.log(2) / alpha * KOEF)
