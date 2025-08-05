from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import uuid

db = SQLAlchemy()

# Association table for Worker-Task many-to-many relationship
worker_task = db.Table(
    "worker_task",
    db.Column("worker_id", db.String(36), db.ForeignKey("worker.id", ondelete="CASCADE"), primary_key=True),
    db.Column("task_id", db.String(36), db.ForeignKey("task.id", ondelete="CASCADE"), primary_key=True)
)

class User(db.Model):
    __tablename__ = "user"
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = db.Column(db.String(70), unique=True, nullable=False)
    email = db.Column(db.String(70), unique=True, nullable=False)
    password = db.Column(db.String(500), nullable=False)
    role = db.Column(db.String(20), default="user")
    task = db.relationship("Task", backref="user", lazy=True)
    workers = db.relationship("Worker", backref="creator", lazy=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __init__(self, username, email, password, role="user"):
        self.id = str(uuid.uuid4())
        self.username = username
        self.email = email
        self.set_password(password)
        self.role = role

    def set_password(self, password):
        """Validates and hashes the password."""
        if not password:
            raise ValueError("Password is required")
        if len(password) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if not any(c.isupper() for c in password):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in password):
            raise ValueError("Password must contain at least one number")
        self.password = generate_password_hash(password)

    def check_password(self, password):
        """Verifies the provided password against the stored hash."""
        return check_password_hash(self.password, password)

    @staticmethod
    def validate_password(password):
        """Validates password format, returns error message or None."""
        if not password:
            return "Password is required"
        if len(password) < 8:
            return "Password must be at least 8 characters long"
        if not any(c.isupper() for c in password):
            return "Password must contain at least one uppercase letter"
        if not any(c.isdigit() for c in password):
            return "Password must contain at least one number"
        return None

class Task(db.Model):
    __tablename__ = "task"
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String(36), db.ForeignKey("user.id"), nullable=False)
    task_type = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), default="queued", nullable=False)
    data = db.Column(db.JSON, nullable=False)
    result = db.Column(db.JSON, nullable=True)
    queue = db.Column(db.String(50))
    celery_task_id = db.Column(db.String(36), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    workers = db.relationship("Worker", secondary=worker_task, backref=db.backref("tasks", lazy="dynamic"))

class Worker(db.Model):
    __tablename__ = "worker"
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.String(36), db.ForeignKey("user.id"), nullable=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    queue_name = db.Column(db.String(50), unique=True, nullable=False)
    status = db.Column(db.String(20), default="idle")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    
# psql -U brain -h localhost -p 5432 -d task_scheduler