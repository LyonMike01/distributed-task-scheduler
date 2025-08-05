from flask import jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from helper.models import db, Task, User, Worker, worker_task
from helper.tasks import process_task
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.sql import select, func
from datetime import datetime, timedelta
from uuid import UUID
import logging
import uuid

logger = logging.getLogger(__name__)

@jwt_required()
def create_task():
    """
    Creates a new task and queues it via Celery, assigning it to an idle/active worker or admin-specified queue.

    Returns:
        JSON response with task details or error.
    """
    try:
        # Get JWT identity and user
        user_id = get_jwt_identity()
        logger.debug(f"Authenticated user_id: {user_id}")
        user = db.session.get(User, user_id)
        if not user:
            logger.error(f"User not found for user_id: {user_id}")
            return jsonify({"error": "User not found"}), 404

        # Parse and validate input
        data = request.get_json()
        if not isinstance(data, dict):
            logger.error("Invalid JSON payload received")
            return jsonify({"error": "Invalid JSON payload"}), 400

        logger.debug(f"Received data: {data}")
        task_type = data.get("task_type")
        task_data = data.get("data")
        queue = data.get("queue")

        # Enhanced validation
        if not task_type or not isinstance(task_type, str):
            logger.error("task_type is missing or not a string")
            return jsonify({"error": "task_type is required and must be a string"}), 400
        if not task_data or not isinstance(task_data, dict):
            logger.error("data is missing or not a JSON object")
            return jsonify({"error": "data is required and must be a JSON object"}), 400

        # Convert task_type to lowercase and validate
        task_type = task_type.lower()
        allowed_task_types = {"send_email", "process_data"}
        if task_type not in allowed_task_types:
            logger.error(f"Invalid task_type: {task_type}. Must be one of {allowed_task_types}")
            return jsonify({"error": f"Invalid task_type. Must be one of {allowed_task_types}"}), 400

        # Convert queue to lowercase if provided (admin only)
        if user.role != "admin" and queue:
            logger.warning(f"Non-admin user_id {user_id} attempted to specify queue")
            return jsonify({"error": "Only admins can specify queue"}), 403

        # Select queue: admin-specified or from idle/active worker
        if queue:
            queue = queue.lower()
            worker = Worker.query.filter_by(queue_name=queue).first()
            if not worker:
                logger.warning(f"Queue {queue} does not correspond to any worker")
                return jsonify({"error": f"Queue {queue} does not exist"}), 400
        else:
            worker = Worker.query.filter(Worker.status.in_(["idle", "active"])).first()
            if not worker:
                logger.warning("No idle or active workers available")
                return jsonify({"error": "No idle or active workers available"}), 503
            queue = worker.queue_name

        # Convert fields in task_data to lowercase
        task_data = task_data.copy()
        if "subject" in task_data:
            task_data["subject"] = task_data["subject"].lower() if isinstance(task_data["subject"], str) else task_data["subject"]
            logger.debug(f"Converted data.subject to: {task_data['subject']}")
        if "to" in task_data:
            task_data["to"] = task_data["to"].lower() if isinstance(task_data["to"], str) else task_data["to"]
            logger.debug(f"Converted data.to to: {task_data['to']}")

        # Generate unique task_id
        task_id = str(uuid.uuid4())
        logger.debug(f"Generated task_id: {task_id}")

        # Create and save task
        task = Task(
            id=task_id,
            user_id=user.id,
            task_type=task_type,
            data=task_data,
            status="pending",
            queue=queue,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        try:
            db.session.add(task)
            db.session.commit()
            # Assign task to worker in worker_task table
            db.session.execute(
                worker_task.insert().values(worker_id=worker.id, task_id=task.id)
            )
            db.session.commit()
            # Queue task in Celery
            celery_task = process_task.apply_async(args=[task.id], queue=task.queue)
            task.celery_task_id = celery_task.id
            task.status = "queued"
            db.session.commit()
            logger.info(f"Task {task_id} created and queued with Celery task_id: {celery_task.id}")
            return jsonify({
                "msg": "Task created and queued",
                "task_id": task.id,
                "celery_task_id": celery_task.id,
                "status": task.status,
                "task": {
                    "task_type": task.task_type,
                    "data": task.data,
                    "queue": task.queue,
                    "created_at": task.created_at.isoformat()
                }
            }), 201
        except Exception as e:
            db.session.rollback()
            logger.error(f"Database error during task creation: {str(e)}")
            return jsonify({"msg": "Failed to create task", "error": str(e)}), 500
    except Exception as e:
        db.session.rollback()
        logger.error(f"Unexpected error in create_task: {str(e)}")
        return jsonify({"msg": "Unexpected error occurred", "error": str(e)}), 500


@jwt_required()
def list_task():
    """
    Lists tasks for the authenticated user. Admins see all tasks.

    Returns:
        JSON response with task list and counts, or error message.
    """
    user_id = get_jwt_identity()
    logger.debug(f"Fetching tasks for user_id: {user_id}")

    user = db.session.get(User, user_id)
    if not user:
        logger.error(f"User not found for user_id: {user_id}")
        return jsonify({"msg": "User not found"}), 404

    # Fetch tasks based on user role
    if user.role == "admin":
        tasks = Task.query.all()
        total_tasks = len(tasks)
        user_tasks = Task.query.filter_by(user_id=user_id).count()
        logger.debug(f"Admin user retrieved {total_tasks} total tasks, {user_tasks} user tasks")
    else:
        tasks = user.task
        total_tasks = None
        user_tasks = len(tasks)
        logger.debug(f"Non-admin user retrieved {user_tasks} tasks")

    # Check if tasks list is empty
    if not tasks:
        logger.info(f"No tasks found for user_id: {user_id}, role: {user.role}")
        return jsonify({"msg": "No tasks found", "user_tasks": user_tasks}), 200

    # Build task list
    task_list = [{
        "task_id": t.id,
        "status": t.status,
        "task_type": t.task_type,
        "data": t.data if t.data is not None else {},
        "result": t.result if t.result is not None else {},
        "queue": t.queue,
        "created_at": t.created_at.isoformat(),
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        **({"user_id": t.user_id} if user.role == "admin" else {})
    } for t in tasks]

    # Build response with counts
    response = {
        "user_tasks": user_tasks,
        "tasks": task_list,
        **({"total_tasks": total_tasks} if user.role == "admin" else {})
    }

    logger.debug(f"Returning {len(task_list)} tasks for user_id: {user_id}, role: {user.role}, user_tasks: {user_tasks}" + (f", total_tasks: {total_tasks}" if total_tasks is not None else ""))
    return jsonify(response), 200


@jwt_required()
def get_task(task_id):
    """
    Retrieves details for a specific task. Users can access their own tasks; admins can access all.

    Args:
        task_id (str): UUID of the task.

    Returns:
        JSON response with task details, or error message.
    """
    try:
        # Validate UUID format
        try:
            UUID(task_id)
        except ValueError:
            logger.error(f"Invalid task_id format: {task_id}")
            return jsonify({"msg": "Invalid task_id format, must be a valid UUID"}), 400

        # Get user identity
        user_id = get_jwt_identity()
        logger.debug(f"Fetching task_id: {task_id} by user_id: {user_id}")

        # Validate user
        user = db.session.get(User, user_id)
        if not user:
            logger.error(f"User not found for user_id: {user_id}")
            return jsonify({"msg": "User not found"}), 404

        # Fetch task
        task = db.session.get(Task, task_id)
        if not task:
            logger.error(f"Task not found for task_id: {task_id}")
            return jsonify({"msg": "Task not found"}), 404

        # Check authorization
        if task.user_id != user_id and user.role != "admin":
            logger.warning(f"Unauthorized access attempt by user_id: {user_id} (role: {user.role}) for task_id: {task_id}")
            return jsonify({"msg": "Unauthorized: You can only access your own tasks or must be an admin"}), 403

        # Log task data
        logger.debug(f"Task {task_id} data: {task.data}, result: {task.result}")

        # Build task details
        task_data = {
            "task_id": task.id,
            "task_type": task.task_type,
            "status": task.status,
            "data": task.data if task.data is not None else {},
            "result": task.result if t.result is not None else {},
            "queue": task.queue,
            "created_at": task.created_at.isoformat(),
            "updated_at": task.updated_at.isoformat() if task.updated_at else None,
            **({"user_id": task.user_id} if user.role == "admin" else {})
        }

        # Build response
        response = {
            "msg": "Task retrieved successfully",
            "task": task_data
        }

        logger.debug(f"Returning task {task_id} for user_id: {user_id}, role: {user.role}")
        return jsonify(response), 200

    except SQLAlchemyError as e:
        logger.error(f"Database error in get_task for task_id {task_id}: {str(e)}")
        return jsonify({"msg": "Database error occurred", "error": str(e)}), 500
    except Exception as e:
        logger.error(f"Unexpected error in get_task for task_id {task_id}: {str(e)}")
        return jsonify({"msg": "Internal server error", "error": str(e)}), 500


@jwt_required()
def update_task(task_id):
    """
    Updates a task"s task_type, data, or queue (admin only).

    Args:
        task_id (str): UUID of the task.

    Returns:
        JSON response with updated task details, or error message.
    """
    try:
        UUID(task_id)
    except ValueError:
        logger.error(f"Invalid task_id format: {task_id}")
        return jsonify({"msg": "Invalid task_id format, must be a valid UUID"}), 400

    user_id = get_jwt_identity()
    logger.debug(f"Authenticated user_id: {user_id}")
    user = db.session.get(User, user_id)
    if not user:
        logger.error(f"User not found for user_id: {user_id}")
        return jsonify({"msg": "User not found"}), 404

    task = db.session.get(Task, task_id)
    if not task:
        logger.error(f"Task not found for task_id: {task_id}")
        return jsonify({"msg": "Task not found"}), 404
    if task.user_id != user_id and user.role != "admin":
        logger.warning(f"Unauthorized access attempt by user_id: {user_id} for task_id: {task_id}")
        return jsonify({"msg": "Unauthorized"}), 403

    # Get JSON data
    data = request.get_json()
    if not data:
        logger.warning(f"No input data provided for task_id: {task_id}")
        return jsonify({"msg": "No input data provided"}), 400

    logger.debug(f"Received data for task_id {task_id}: {data}")

    # Store original values
    original_values = {
        "task_type": task.task_type,
        "data": task.data,
        "queue": task.queue
    }

    # Update fields if provided
    updated = False
    if "task_type" in data and data["task_type"] != task.task_type:
        task.task_type = data["task_type"].lower()
        updated = True
        logger.debug(f"Updated task_type to: {task.task_type}")

    if "data" in data:
        new_data = data["data"]
        if not isinstance(new_data, dict):
            logger.error(f"Invalid data format for task_id {task_id}: expected a JSON object")
            return jsonify({"msg": "Invalid data format, must be a JSON object"}), 400

        new_data = new_data.copy()
        if "subject" in new_data:
            new_data["subject"] = new_data["subject"].lower() if isinstance(new_data["subject"], str) else new_data["subject"]
        if "to" in new_data:
            new_data["to"] = new_data["to"].lower() if isinstance(new_data["to"], str) else new_data["to"]

        if new_data != task.data:
            task.data = new_data
            updated = True
            logger.debug(f"Updated data to: {new_data}")

    if user.role == "admin" and "queue" in data and data["queue"] != task.queue:
        task.queue = data["queue"].lower()
        updated = True
        logger.debug(f"Updated queue to: {task.queue}")

    if not updated:
        logger.info(f"No fields updated for task_id: {task_id}")
        return jsonify({"msg": "No changes made to task", "task": original_values}), 200

    # Update timestamp
    task.updated_at = datetime.utcnow()
    logger.debug(f"Updated updated_at to: {task.updated_at}")

    # Commit changes
    try:
        db.session.commit()
        logger.info(f"Task {task_id} updated successfully")
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f"Failed to update task {task_id}: {str(e)}")
        return jsonify({"msg": "Failed to update task", "details": str(e)}), 500

    # Fetch updated task
    updated_task = db.session.get(Task, task_id)
    return jsonify({
        "msg": "Task Updated",
        "task": {
            "task_id": updated_task.id,
            "task_type": updated_task.task_type,
            "data": updated_task.data,
            "queue": updated_task.queue,
            "updated_at": updated_task.updated_at.isoformat() if updated_task.updated_at else None
        }
    }), 200


@jwt_required()
def delete_task(task_id):
    """
    Deletes a specific task. Users can delete their own tasks; admins can delete all.

    Args:
        task_id (str): UUID of the task.

    Returns:
        JSON response confirming deletion, or error message.
    """
    try:
        UUID(task_id)
    except ValueError:
        logger.error(f"Invalid task_id format: {task_id}")
        return jsonify({"msg": "Invalid task_id format, must be a valid UUID"}), 400

    user_id = get_jwt_identity()
    logger.debug(f"Attempting to delete task {task_id} by user_id: {user_id}")

    user = db.session.get(User, user_id)
    if not user:
        logger.error(f"User not found for user_id: {user_id}")
        return jsonify({"msg": "User not found"}), 404

    task = db.session.get(Task, task_id)
    if not task:
        logger.error(f"Task not found for task_id: {task_id}")
        return jsonify({"msg": "Task not found"}), 404

    if task.user_id != user_id and user.role != "admin":
        logger.warning(f"Unauthorized delete attempt by user_id: {user_id} (role: {user.role}) for task_id: {task_id}")
        return jsonify({"msg": "Unauthorized"}), 403

    task_data = {
        "task_id": task.id,
        "task_type": task.task_type,
        "data": task.data if task.data is not None else {},
        "queue": task.queue,
        **({"user_id": task.user_id} if user.role == "admin" else {})
    }

    try:
        db.session.delete(task)
        db.session.commit()
        logger.info(f"Task {task_id} deleted successfully by user_id: {user_id}, role: {user.role}, task details: {task_data}")
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f"Failed to delete task {task_id}: {str(e)}")
        return jsonify({"msg": "Failed to delete task", "details": str(e)}), 500

    response = {
        "msg": "Task deleted",
        "task_id": task_id,
        **({"task": task_data} if user.role == "admin" else {})
    }
    return jsonify(response), 200


@jwt_required()
def task_status(task_id):
    """
    Retrieves the status of a specific task.

    Args:
        task_id (str): UUID of the task.

    Returns:
        JSON response with task status and creator task count, or error message.
    """
    try:
        UUID(task_id)
    except ValueError:
        logger.error(f"Invalid task_id format: {task_id}")
        return jsonify({"msg": "Invalid task_id format, must be a valid UUID"}), 400

    user_id = get_jwt_identity()
    logger.debug(f"Fetching status for task {task_id} by user_id: {user_id}")

    user = db.session.get(User, user_id)
    if not user:
        logger.error(f"User not found for user_id: {user_id}")
        return jsonify({"msg": "User not found"}), 404

    task = db.session.get(Task, task_id)
    if not task:
        logger.error(f"Task not found for task_id: {task_id}")
        return jsonify({"msg": "Task not found"}), 404

    if task.user_id != user_id and user.role != "admin":
        logger.warning(f"Unauthorized access attempt by user_id: {user_id} (role: {user.role}) for task_id: {task_id}")
        return jsonify({"msg": "Unauthorized"}), 403

    creator_tasks = Task.query.filter_by(user_id=task.user_id).count()
    logger.debug(f"Task {task_id} creator (user_id: {task.user_id}) has {creator_tasks} tasks")

    task_data = {
        "task_id": task.id,
        "status": task.status,
        "result": task.result if task.result is not None else {},
        "task_type": task.task_type,
        "queue": task.queue,
        **({"user_id": task.user_id} if user.role == "admin" else {})
    }

    response = {
        "task": task_data,
        "creator_tasks": creator_tasks
    }

    logger.debug(f"Returning status for task {task_id} for user_id: {user_id}, role: {user.role}, creator_tasks: {creator_tasks}")
    return jsonify(response), 200


@jwt_required()
def update_status(task_id):
    """
    Updates the status and result of a task. Restricted to admins.

    Args:
        task_id (str): UUID of the task.

    Returns:
        JSON response with updated task details and creator task count, or error message.
    """
    try:
        UUID(task_id)
    except ValueError:
        logger.error(f"Invalid task_id format: {task_id}")
        return jsonify({"msg": "Invalid task_id format, must be a valid UUID"}), 400

    user_id = get_jwt_identity()
    logger.debug(f"Attempting to update status for task {task_id} by user_id: {user_id}")

    user = db.session.get(User, user_id)
    if not user:
        logger.error(f"User not found for user_id: {user_id}")
        return jsonify({"msg": "User not found"}), 404

    if user.role != "admin":
        logger.warning(f"Unauthorized status update attempt by user_id: {user_id} (role: {user.role}) for task_id: {task_id}")
        return jsonify({"msg": "Unauthorized: Admin access required"}), 403

    task = db.session.get(Task, task_id)
    if not task:
        logger.error(f"Task not found for task_id: {task_id}")
        return jsonify({"msg": "Task not found"}), 404

    data = request.get_json()
    if not data or "status" not in data:
        logger.warning(f"No status provided for task_id: {task_id}")
        return jsonify({"msg": "Status field is required"}), 400

    logger.debug(f"Received data for task_id {task_id}: {data}")

    valid_statuses = {"pending", "running", "completed", "Assigned and Pending"}
    new_status = data["status"].lower()
    if new_status not in valid_statuses:
        logger.warning(f"Invalid status provided for task_id {task_id}: {new_status}")
        return jsonify({"msg": f"Invalid status, must be one of: {", ".join(valid_statuses)}"}), 400

    updated = False
    if new_status != task.status:
        task.status = new_status
        updated = True
        logger.debug(f"Updated status to: {new_status}")
    if "result" in data and data["result"] != task.result:
        task.result = data["result"]
        updated = True
        logger.debug(f"Updated result to: {data["result"]}")

    if not updated:
        logger.info(f"No changes made to task_id: {task_id}, status and result unchanged")
        creator_tasks = Task.query.filter_by(user_id=task.user_id).count()
        return jsonify({
            "msg": "No changes made to task status or result",
            "task": {
                "task_id": task.id,
                "status": task.status,
                "task_type": task.task_type,
                "data": task.data if task.data is not None else {},
                "result": task.result if task.result is not None else {},
                "queue": task.queue,
                "created_at": task.created_at.isoformat(),
                "updated_at": task.updated_at.isoformat() if task.updated_at else None,
                "user_id": task.user_id
            },
            "creator_tasks": creator_tasks
        }), 200

    task.updated_at = datetime.utcnow()
    logger.debug(f"Updated updated_at to: {task.updated_at}")

    try:
        db.session.commit()
        logger.info(f"Task {task_id} status updated successfully by user_id: {user_id}, role: {user.role}")
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f"Failed to update task {task_id}: {str(e)}")
        return jsonify({"msg": "Failed to update task status", "details": str(e)}), 500

    creator_tasks = Task.query.filter_by(user_id=task.user_id).count()
    logger.debug(f"Task {task_id} creator (user_id: {task.user_id}) has {creator_tasks} tasks")

    response = {
        "msg": "Task status updated",
        "task": {
            "task_id": task.id,
            "status": task.status,
            "task_type": task.task_type,
            "result": task.result if task.result is not None else {},
            "queue": task.queue,
            "user_id": task.user_id
        },
        "creator_tasks": creator_tasks
    }

    logger.debug(f"Returning updated task {task_id} for user_id: {user_id}, role: {user.role}, creator_tasks: {creator_tasks}")
    return jsonify(response), 200


@jwt_required()
def assign_task():
    """
    Assigns a queued task (oldest first) to an idle worker with fewer than 3 tasks.
    Updates task status to "Assigned and Pending" and worker status to "active".
    Restricted to admins.

    Returns:
        JSON response with assigned task and worker details, or error message.
    """
    try:
        user_id = get_jwt_identity()
        logger.debug(f"Assigning task by user_id: {user_id}")

        user = db.session.get(User, user_id)
        if not user:
            logger.error(f"User not found for user_id: {user_id}")
            return jsonify({"msg": "User not found"}), 404

        if user.role != "admin":
            logger.warning(f"Unauthorized access attempt by user_id: {user_id} (role: {user.role})")
            return jsonify({"msg": "Unauthorized: Admin access required"}), 403

        task = Task.query.filter_by(status="queued").order_by(Task.created_at.asc()).first()
        if not task:
            logger.debug("No queued tasks available")
            return jsonify({"msg": "No queued tasks available"}), 404

        task_count_subquery = db.session.query(
            worker_task.c.worker_id,
            func.count(worker_task.c.task_id).label("task_count")
        ).group_by(worker_task.c.worker_id).subquery()

        worker = db.session.query(Worker).outerjoin(
            task_count_subquery,
            Worker.id == task_count_subquery.c.worker_id
        ).filter(
            Worker.status == "idle",
            (task_count_subquery.c.task_count < 3) | (task_count_subquery.c.task_count.is_(None))
        ).first()

        if not worker:
            logger.debug(f"No idle workers with fewer than 3 tasks available for task_id: {task.id}")
            return jsonify({"msg": "No idle workers available"}), 404

        existing_worker = db.session.execute(
            select(worker_task.c.worker_id).where(worker_task.c.task_id == task.id)
        ).scalar()
        if existing_worker:
            logger.warning(f"Task {task.id} is already assigned to worker {existing_worker}")
            return jsonify({"msg": f"Task is already assigned to worker {existing_worker}"}), 409

        try:
            db.session.execute(
                worker_task.insert().values(worker_id=worker.id, task_id=task.id)
            )
            worker.status = "active"
            worker.updated_at = datetime.utcnow()
            task.status = "Assigned and Pending"
            task.updated_at = datetime.utcnow()
            db.session.commit()
            logger.info(f"Task {task.id} assigned to worker {worker.id} successfully")
        except IntegrityError as e:
            db.session.rollback()
            logger.error(f"Integrity error assigning task {task.id} to worker {worker.id}: {str(e)}")
            return jsonify({"msg": "Assignment failed: Database integrity error"}), 409
        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"Database error assigning task {task.id} to worker {worker.id}: {str(e)}")
            return jsonify({"msg": "Database error occurred", "error": str(e)}), 500

        response = {
            "msg": "Task assigned successfully",
            "task": {
                "task_id": task.id,
                "task_type": task.task_type,
                "status": task.status,
                "data": task.data if task.data is not None else {},
                "result": task.result if task.result is not None else {},
                "queue": task.queue,
                "created_at": task.created_at.isoformat(),
                "updated_at": task.updated_at.isoformat() if task.updated_at else None,
                "user_id": task.user_id
            },
            "worker": {
                "worker_id": worker.id,
                "name": worker.name,
                "queue_name": worker.queue_name,
                "status": worker.status,
                "created_at": worker.created_at.isoformat(),
                "updated_at": worker.updated_at.isoformat() if worker.updated_at else None
            }
        }

        logger.debug(f"Returning assigned task {task.id} to worker {worker.id} for user_id: {user_id}")
        return jsonify(response), 200

    except Exception as e:
        logger.error(f"Unexpected error in assign_task: {str(e)}")
        return jsonify({"msg": "Internal server error", "error": str(e)}), 500
    
    
@jwt_required()
def assign_task_to_worker(task_id):
    """
    Assigns a task to a specific worker.

    Args:
        task_id (str): The ID of the task to assign.

    Returns:
        JSON response with task details or error.
    """
    try:
        current_user = get_jwt_identity()
        task = Task.query.get(task_id)
        if not task:
            logger.warning(f"Task not found: id={task_id}")
            return jsonify({"msg": "Task not found"}), 404

        data = request.get_json()
        if not data or "name" not in data:
            logger.warning("Missing worker name in assign_task_to_worker request")
            return jsonify({"msg": "Worker name is required"}), 400

        worker = Worker.query.filter_by(name=data["name"]).first()
        if not worker:
            logger.warning(f"Worker not found: name={data['name']}")
            return jsonify({"msg": "Worker not found"}), 404

        if worker.status not in ["idle", "active"]:
            logger.warning(f"Worker is not available: name={worker.name}, status={worker.status}")
            return jsonify({"msg": "Worker is not idle or active"}), 400

        # Update task queue and worker_task association
        task.queue = worker.queue_name
        task.status = "Assigned and Pending"
        db.session.execute(
            worker_task.delete().where(worker_task.c.task_id == task_id)
        )
        db.session.execute(
            worker_task.insert().values(worker_id=worker.id, task_id=task_id)
        )
        worker.status = "active"
        try:
            db.session.commit()
            # Re-queue task in Celery
            celery_task = process_task.apply_async(args=[task.id], queue=worker.queue_name)
            task.celery_task_id = celery_task.id
            db.session.commit()
            logger.info(f"Task assigned to worker: task_id={task_id}, worker_id={worker.id}")
            return jsonify({
                "msg": "Task assigned successfully",
                "task": {
                    "task_id": task.id,
                    "task_type": task.task_type,
                    "status": task.status,
                    "queue": task.queue
                }
            }), 200
        except Exception as e:
            db.session.rollback()
            logger.error(f"Database error during task assignment: {str(e)}")
            return jsonify({"msg": "Failed to assign task", "error": str(e)}), 500
    except Exception as e:
        logger.error(f"Unexpected error in assign_task_to_worker: {str(e)}")
        return jsonify({"msg": "Unexpected error occurred", "error": str(e)}), 500