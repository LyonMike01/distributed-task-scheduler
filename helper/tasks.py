from celery import Celery
from helper.config import Config
from helper.models import db, Task, Worker
from flask import current_app as app
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Celery
celery = Celery(
    "tasks",
    broker=Config.CELERY_BROKER_URL,
    backend=Config.CELERY_RESULT_BACKEND
)

celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_ignore_result=False
)

@celery.task(bind=True, max_retries=3)
def process_task(self, task_id):
    """
    Processes a task based on its type and updates its status and result.

    Args:
        task_id (str): The ID of the task to process.

    Returns:
        dict: Task result if successful.

    Raises:
        ValueError: If task is not found or has invalid status/type.
    """
    with app.app_context():
        try:
            task = db.session.get(Task, task_id)
            if not task:
                logger.error(f"Task with ID {task_id} not found")
                raise ValueError(f"Task with ID {task_id} not found")

            if task.status != "Assigned and Pending":
                logger.warning(f"Task {task_id} is not in 'Assigned and Pending' state, current status:{task.status}")
                raise ValueError(f"Task {task_id} is not in 'Assigned and Pending' state")

            worker = Worker.query.filter_by(queue_name=self.request.queue).first()
            if worker:
                worker.status = "active"
                task.status = "processing"
                db.session.commit()
                logger.debug(f"Task {task_id} set to 'processing', worker {worker.name} set to 'active'")

            valid_task_types = {"send_email", "generate_report", "process_image"}
            if task.task_type not in valid_task_types:
                raise ValueError(f"Unsupported task type: {task.task_type}")

            result = None
            if task.task_type == "send_email":
                result = {"success": True, "message": f"Email sent with params: {task.data}"}
            elif task.task_type == "generate_report":
                result = {"success": True, "message": f"Report generated with params: {task.data}"}
            elif task.task_type == "process_image":
                result = {"success": True, "message": f"Image processed with params: {task.data}"}

            task.status = "completed"
            task.result = result
            task.updated_at = datetime.utcnow()
            if worker:
                worker.status = "idle"
                worker.updated_at = datetime.utcnow()
            db.session.commit()
            logger.info(f"Task {task_id} completed successfully with result: {result}")

            return result

        except Exception as e:
            logger.error(f"Task {task_id} failed: {str(e)}")
            task = db.session.get(Task, task_id)
            if task:
                task.status = "failed"
                task.result = {"error": str(e)}
                task.updated_at = datetime.utcnow()
                if worker:
                    worker.status = "idle"
                    worker.updated_at = datetime.utcnow()
                db.session.commit()
                logger.debug(f"Task {task_id} marked as 'failed' with error: {str(e)}")
            if self.request.retries < self.max_retries:
                logger.info(f"Retrying task {task_id}, attempt {self.request.retries + 1}/{self.max_retries}")
                raise self.retry(countdown=10, exc=e)
            raise