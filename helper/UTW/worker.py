from flask import request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from helper.models import db, User, Worker, Task, worker_task
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.sql import func
import logging
import uuid

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

@jwt_required()
def create_worker():
    """
    Creates a new worker. Restricted to admin users.

    Returns:
        JSON response with worker details or error message.
    """
    try:
        user_id = get_jwt_identity()
        logger.debug(f"Creating worker for user_id: {user_id}")

        user = db.session.get(User, user_id)
        if not user:
            logger.error(f"User not found for user_id: {user_id}")
            return jsonify({"msg": "User not found"}), 404

        if user.role != "admin":
            logger.warning(f"Non-admin user {user_id} attempted to create worker")
            return jsonify({"msg": "Admin access required"}), 403

        data = request.get_json()
        if not data or not data.get("name"):
            logger.warning(f"Invalid worker data provided by user_id: {user_id}")
            return jsonify({"msg": "Worker name is required"}), 400

        name = data.get("name").lower()
        status = data.get("status", "idle").lower()
        valid_statuses = {"idle", "active"}
        if status not in valid_statuses:
            logger.warning(f"Invalid status: {status}")
            return jsonify({"msg": f"Invalid status, must be one of: {", ".join(valid_statuses)}"}), 400

        worker = Worker(
            user_id=user_id,
            name=name,
            queue_name=f"worker_{uuid.uuid4().hex}",
            status=status
        )

        try:
            db.session.add(worker)
            db.session.commit()
            logger.info(f"Worker created successfully: id={worker.id}, name={name}, queue_name={worker.queue_name}, user_id={user_id}")
        except IntegrityError:
            db.session.rollback()
            logger.error(f"Failed to create worker due to name or queue_name conflict: {name}")
            return jsonify({"msg": "Worker name or queue name already exists"}), 400
        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"Database error during worker creation: {str(e)}")
            return jsonify({"msg": "Failed to create worker", "error": str(e)}), 500

        response = {
            "msg": "Worker created successfully",
            "worker": {
                "worker_id": worker.id,
                "name": worker.name,
                "queue_name": worker.queue_name,
                "status": worker.status,
                "created_at": worker.created_at.isoformat(),
                "updated_at": worker.updated_at.isoformat() if worker.updated_at else None,
                "user_id": worker.user_id
            }
        }

        logger.debug(f"Returning worker id={worker.id} for user_id: {user_id}")
        return jsonify(response), 201
    except Exception as e:
        logger.error(f"Unexpected error in create_worker: {str(e)}")
        return jsonify({"msg": "Unexpected error occurred", "error": str(e)}), 500

@jwt_required()
def list_workers():
    """
    Lists all workers with their task counts. Restricted to admin users.

    Returns:
        JSON response with list of workers or error message.
    """
    try:
        user_id = get_jwt_identity()
        logger.debug(f"Listing workers for user_id: {user_id}")

        user = db.session.get(User, user_id)
        if not user:
            logger.error(f"User not found for user_id: {user_id}")
            return jsonify({"msg": "User not found"}), 404

        if user.role != "admin":
            logger.warning(f"Non-admin user {user_id} attempted to list workers")
            return jsonify({"msg": "Admin access required"}), 403

        workers = Worker.query.all()
        response = {
            "msg": "Workers retrieved successfully",
            "workers": [
                {
                    "worker_id": worker.id,
                    "name": worker.name,
                    "queue_name": worker.queue_name,
                    "status": worker.status,
                    "task_count": 0 if worker.status == "idle" else len(worker.tasks.all()),
                    "created_at": worker.created_at.isoformat(),
                    "updated_at": worker.updated_at.isoformat() if worker.updated_at else None,
                    "user_id": worker.user_id
                }
                for worker in workers
            ]
        }

        # Clear stale task associations for idle workers
        for worker in workers:
            if worker.status == "idle" and worker.tasks.all():
                db.session.execute(
                    worker_task.delete().where(worker_task.c.worker_id == worker.id)
                )
                logger.info(f"Cleared stale task associations for idle worker: id={worker.id}, name={worker.name}")

        try:
            db.session.commit()
            logger.info(f"Retrieved {len(workers)} workers for user_id: {user_id}")
            return jsonify(response), 200
        except Exception as e:
            db.session.rollback()
            logger.error(f"Database error during commit: {str(e)}")
            return jsonify({"msg": "Failed to retrieve workers", "error": str(e)}), 500
    except Exception as e:
        logger.error(f"Unexpected error while listing workers: {str(e)}")
        return jsonify({"msg": "Failed to retrieve workers", "error": str(e)}), 500

@jwt_required()
def worker_status(worker_id):
    """
    Retrieves the status of a worker and its assigned tasks.

    Args:
        worker_id (str): The ID of the worker.

    Returns:
        JSON response with worker details and tasks.
    """
    try:
        current_user = User.query.get(get_jwt_identity())
        if current_user.role != "admin":
            logger.warning(f"Unauthorized worker_status attempt by user_id={current_user.id}")
            return jsonify({"msg": "Unauthorized: Admin access required"}), 403

        worker = Worker.query.get(worker_id)
        if not worker:
            logger.warning(f"Worker not found: id={worker_id}")
            return jsonify({"msg": "Worker not found"}), 404

        tasks = worker.tasks.all()
        # Update status to 'idle' if no tasks are assigned
        if not tasks and worker.status != "idle":
            worker.status = "idle"
            db.session.commit()
            logger.info(f"Updated worker status to idle: id={worker_id}, name={worker.name}")

        response = {
            "msg": "Worker status retrieved successfully",
            "worker": {
                "worker_id": worker.id,
                "name": worker.name,
                "queue_name": worker.queue_name,
                "status": worker.status,
                "task_count": len(tasks),
                "tasks": [{
                    "task_id": task.id,
                    "task_type": task.task_type,
                    "status": task.status,
                    "created_at": task.created_at.isoformat(),
                    "updated_at": task.updated_at.isoformat()
                } for task in tasks]
            }
        }
        logger.info(f"Worker status retrieved: id={worker_id}, name={worker.name}")
        return jsonify(response), 200
    except Exception as e:
        logger.error(f"Database error while retrieving worker status: {str(e)}")
        return jsonify({"msg": "Failed to retrieve worker status", "error": str(e)}), 500


@jwt_required()
def update_worker(worker_id):
    """
    Updates a worker"s name or status. Restricted to admin users.

    Args:
        worker_id (str): The ID of the worker to update.

    Returns:
        JSON response with updated worker details or error message.
    """
    try:
        user_id = get_jwt_identity()
        logger.debug(f"Updating worker {worker_id} for user_id: {user_id}")

        user = db.session.get(User, user_id)
        if not user:
            logger.error(f"User not found for user_id: {user_id}")
            return jsonify({"msg": "User not found"}), 404

        if user.role != "admin":
            logger.warning(f"Non-admin user {user_id} attempted to update worker")
            return jsonify({"msg": "Admin access required"}), 403

        worker = db.session.get(Worker, worker_id)
        if not worker:
            logger.warning(f"Worker not found for worker_id: {worker_id}")
            return jsonify({"msg": "Worker not found"}), 404

        data = request.get_json()
        if not data:
            logger.warning(f"No data provided to update worker {worker_id}")
            return jsonify({"msg": "No data provided"}), 400

        name = data.get("name", worker.name).lower()
        status = data.get("status", worker.status).lower()
        valid_statuses = {"idle", "active"}
        if status not in valid_statuses:
            logger.warning(f"Invalid status: {status}")
            return jsonify({"msg": f"Invalid status, must be one of: {", ".join(valid_statuses)}"}), 400

        worker.name = name
        worker.status = status
        worker.updated_at = func.now()

        try:
            db.session.commit()
            logger.info(f"Worker updated successfully: id={worker.id}, name={name}, status={status}")
        except IntegrityError:
            db.session.rollback()
            logger.error(f"Failed to update worker due to name or queue_name conflict: {name}")
            return jsonify({"msg": "Worker name or queue name already exists"}), 400
        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"Database error during worker update: {str(e)}")
            return jsonify({"msg": "Failed to update worker", "error": str(e)}), 500

        response = {
            "msg": "Worker updated successfully",
            "worker": {
                "worker_id": worker.id,
                "name": worker.name,
                "queue_name": worker.queue_name,
                "status": worker.status,
                "created_at": worker.created_at.isoformat(),
                "updated_at": worker.updated_at.isoformat() if worker.updated_at else None,
                "user_id": worker.user_id
            }
        }

        logger.debug(f"Returning updated worker id={worker.id} for user_id: {user_id}")
        return jsonify(response), 200
    except Exception as e:
        logger.error(f"Unexpected error in update_worker: {str(e)}")
        return jsonify({"msg": "Unexpected error occurred", "error": str(e)}), 500


@jwt_required()
def delete_worker(worker_id):
    """
    Deletes a worker and reassigns its tasks to another worker.

    Args:
        worker_id (str): The ID of the worker to delete.

    Returns:
        JSON response indicating success or error.
    """
    try:
        current_user_id = get_jwt_identity()
        worker = Worker.query.get(worker_id)
        if not worker:
            logger.warning(f"Worker not found: id={worker_id}")
            return jsonify({"msg": "Worker not found"}), 404

        # Check authorization: admin or worker"s creator
        if current_user_id != worker.user_id and User.query.get(current_user_id).role != "admin":
            logger.warning(f"Unauthorized delete_worker attempt by user_id={current_user_id} for worker_id={worker_id}")
            return jsonify({"msg": "Unauthorized: Admin or creator access required"}), 403

        # Reassign tasks to another idle worker
        tasks = worker.tasks.all()
        if tasks:
            idle_worker = Worker.query.filter(Worker.id != worker_id, Worker.status == "idle").first()
            if idle_worker:
                for task in tasks:
                    task.queue = idle_worker.queue_name
                    db.session.execute(
                        worker_task.delete().where(worker_task.c.task_id == task.id, worker_task.c.worker_id == worker_id)
                    )
                    db.session.execute(
                        worker_task.insert().values(worker_id=idle_worker.id, task_id=task.id)
                    )
                    logger.info(f"Reassigned task id={task.id} from worker_id={worker_id} to worker_id={idle_worker.id}")
            else:
                logger.warning(f"No idle workers available to reassign tasks from worker_id={worker_id}")
                return jsonify({"msg": "Cannot delete worker: No idle workers available to reassign tasks"}), 400

        try:
            db.session.delete(worker)
            db.session.commit()
            logger.info(f"Worker deleted successfully: id={worker_id}, name={worker.name}")
            return jsonify({"msg": "Worker deleted successfully"}), 200
        except Exception as e:
            db.session.rollback()
            logger.error(f"Database error during worker deletion: id={worker_id}, error={str(e)}")
            return jsonify({"msg": "Failed to delete worker", "error": str(e)}), 500
    except Exception as e:
        logger.error(f"Unexpected error in delete_worker: {str(e)}")
        return jsonify({"msg": "Unexpected error occurred", "error": str(e)}), 500
    