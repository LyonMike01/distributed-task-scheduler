import os

class Config:
    # Flask settings
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "1234567890qwertyuiopasdfghjklzxcvbnm!!@@##")
    
    # PostgreSQL settings
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "SQLALCHEMY_DATABASE_URI",
        "postgresql+psycopg2://brain:Perfectgen2mic@localhost:5432/task_scheduler"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Redis settings
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    # Celery settings
    CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")