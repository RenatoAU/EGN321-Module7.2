"""Persistent threshold with hysteresis; caller saves state transactionally."""
def update(state, count, value):
    if value is None:
        return state, 0
    if state == 'ALERT':
        return ('NORMAL', 0) if value <= 28.5 else (state, 0)
    count = count + 1 if value >= 30 else 0
    return ('ALERT' if count >= 3 else 'NORMAL'), count
