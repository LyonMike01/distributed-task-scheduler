from helper.models import Worker, Task, worker_task, db
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql import func, select
from datetime import datetime
import logging
from uuid import UUID

logger = logging.getLogger(__name__)

def distribute_task(task_id):
    """
    Distributes a queued task to an idle worker with fewer than 3 tasks.

    Args:
        task_id (str): UUID of the task to distribute.

    Returns:
        tuple: (success (bool), message (str), worker_id (str or None))
    """
    try:
        # Validate task_id UUID
        try:
            UUID(task_id)
        except ValueError:
            logger.error(f"Invalid task_id format: {task_id}")
            return False, "Invalid task_id format, must be a valid UUID", None

        # Fetch task
        task = db.session.get(Task, task_id)
        if not task:
            logger.error(f"Task not found for task_id: {task_id}")
            return False, "Task not found", None

        # Check if task is queued
        if task.status != "queued":
            logger.warning(f"Task {task_id} is not queued, current status: {task.status}")
            return False, f"Task is not queued, current status: {task.status}", None

        # Check if task is already assigned
        existing_worker = db.session.execute(
            select(worker_task.c.worker_id).where(worker_task.c.task_id == task_id)
        ).scalar()
        if existing_worker:
            logger.warning(f"Task {task_id} is already assigned to worker {existing_worker}")
            return False, f"Task is already assigned to worker {existing_worker}", existing_worker

        # Subquery to count tasks per worker
        task_count_subquery = db.session.query(
            worker_task.c.worker_id,
            func.count(worker_task.c.task_id).label("task_count")
        ).group_by(worker_task.c.worker_id).subquery()

        # Find an idle worker with fewer than 3 tasks
        worker = db.session.query(Worker).outerjoin(
            task_count_subquery,
            Worker.id == task_count_subquery.c.worker_id
        ).filter(
            Worker.status == "idle",
            (task_count_subquery.c.task_count < 3) | (task_count_subquery.c.task_count.is_(None))
        ).first()

        if not worker:
            logger.warning(f"No idle workers with fewer than 3 tasks available for task_id: {task_id}")
            return False, "No idle workers available", None

        # Assign task to worker
        try:
            db.session.execute(
                worker_task.insert().values(worker_id=worker.id, task_id=task_id)
            )
            worker.status = "active"
            worker.updated_at = datetime.utcnow()
            task.status = "Assigned and Pending"
            task.updated_at = datetime.utcnow()
            db.session.commit()
            logger.info(f"Task {task_id} (type: {task.task_type}) assigned to worker {worker.id} (name: {worker.name}) successfully")
            return True, "Task assigned successfully", worker.id
        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"Failed to assign task {task_id} to worker {worker.id}: {str(e)}")
            return False, "Failed to assign task due to database error", None

    except Exception as e:
        logger.error(f"Unexpected error in distribute_task for task_id {task_id}: {str(e)}")
        return False, f"Unexpected error: {str(e)}", None