from extensions import db

class Subject(db.Model):
    __tablename__ = "subjects"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    topics = db.relationship("Topic", backref="subject", lazy=True)
