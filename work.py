import sys
import logging
from flask import Flask
from sqlalchemy.sql import text
from helper.config import Config
from helper.tasks import celery as celery_app
from helper.models import db, Worker

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app for database access
app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

def get_default_queue():
    """
    Retrieves a default queue_name from the worker table, preferring idle workers.

    Returns:
        str: The selected queue_name, or None if no workers exist.
    """
    try:
        with app.app_context():
            # Prefer an idle worker
            worker = Worker.query.filter_by(status="idle").first()
            if worker:
                logger.debug(f"Selected idle worker: id={worker.id}, name={worker.name}, queue_name={worker.queue_name}")
                return worker.queue_name
            # Fallback to any worker
            worker = Worker.query.first()
            if worker:
                logger.debug(f"No idle workers, selected worker: id={worker.id}, name={worker.name}, queue_name={worker.queue_name}")
                return worker.queue_name
            # No workers found
            logger.warning("No workers found in the worker table")
            return None
    except Exception as e:
        logger.error(f"Error retrieving default queue: {str(e)}")
        return None

def validate_queue(queue_name):
    """
    Validates if the queue_name exists in the worker table.

    Args:
        queue_name (str): The queue name to validate.

    Returns:
        bool: True if queue exists, False otherwise.
    """
    try:
        with app.app_context():
            worker = Worker.query.filter_by(queue_name=queue_name).first()
            if worker:
                logger.debug(f"Queue {queue_name} found for worker id={worker.id}, name={worker.name}")
                return True
            logger.warning(f"Queue {queue_name} not found in worker table")
            available_queues = [w.queue_name for w in Worker.query.all()]
            logger.info(f"Available queues in worker table: {available_queues}")
            return False
    except Exception as e:
        logger.error(f"Error validating queue {queue_name}: {str(e)}")
        return False

if __name__ == "__main__":
    # Get queue_name from command-line argument or default to an available worker
    queue_name = sys.argv[1] if len(sys.argv) > 1 else get_default_queue()
    if not queue_name:
        logger.error(
            "Cannot start worker: No valid queue_name provided and no workers found in the database."
            "Create a worker using the /create_worker endpoint to generate a valid queue_name (e.g., worker_<uuid>)."
            "Check the 'worker' table with: SELECT queue_name FROM worker;"
        )
        sys.exit(1)

    logger.info(f"Starting Celery worker for queue: {queue_name}")

    # Check Redis connectivity
    try:
        celery_app.control.ping()
        logger.info("Successfully connected to Redis broker")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {str(e)}")
        sys.exit(1)

    # Check database connectivity
    try:
        with app.app_context():
            db.session.execute(text("SELECT 1"))
            logger.info("Successfully connected to PostgreSQL database")
    except Exception as e:
        logger.error(f"Failed to connect to PostgreSQL: {str(e)}")
        sys.exit(1)

    if not validate_queue(queue_name):
        logger.error(
            f"Cannot start worker: Queue '{queue_name}'"
            "Create a worker using the /create_worker endpoint to generate a valid queue_name (e.g., worker_<uuid>). "
            "Check the 'worke' table with: SELECT queue_name FROM worker;"
        )
        sys.exit(1)

    try:
        logger.debug(f"Starting Celery worker with args: worker --loglevel=info -Q {queue_name} --concurrency=3")
        celery_app.worker_main(
            ["worker", "--loglevel=info", "-Q", queue_name, "--concurrency=3"]
        )
        logger.info(f"Celery worker started successfully for queue: {queue_name}")
    except Exception as e:
        logger.error(f"Failed to start Celery worker for queue {queue_name}: {str(e)}")
        sys.exit(1)