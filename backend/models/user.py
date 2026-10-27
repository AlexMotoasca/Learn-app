from extensions import db
import json

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    total_score = db.Column(db.Integer, default=0)
    current_streak = db.Column(db.Integer, default=0)
    last_quiz_date = db.Column(db.Date, nullable=True)
    longest_streak = db.Column(db.Integer, default=0)

    # store module progress as JSON text to avoid immediate migrations complexity
    modules_in_progress = db.Column(db.Text, nullable=True, default='[]')
    completed_modules = db.Column(db.Text, nullable=True, default='[]')

    # helper for convenience
    def to_dict(self):
        def _safe_load(s):
            try:
                v = json.loads(s) if s else []
                return v if isinstance(v, list) else []
            except Exception:
                return []

        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "total_score": self.total_score,
            "current_streak": self.current_streak,
            "longest_streak": self.longest_streak,
            "last_quiz_date": self.last_quiz_date.isoformat() if self.last_quiz_date else None,
            "modules_in_progress": _safe_load(self.modules_in_progress),
            "completed_modules": _safe_load(self.completed_modules)
        }
