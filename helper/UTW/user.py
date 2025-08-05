from flask import jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity, create_access_token
from helper.models import db, User, Task, worker_task
from werkzeug.security import generate_password_hash
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
import logging
from datetime import datetime
from uuid import UUID

logger = logging.getLogger(__name__)

def signup():
    """
    Creates a new user.

    Returns:
        JSON response with user details or error message.
    """
    try:
        data = request.get_json()
        if not data or not all(key in data for key in ["username", "email", "password", "role"]):
            logger.warning("Missing required fields in signup request")
            return jsonify({"msg": "Username, email, password, and role are required"}), 400

        username = data["username"].lower()
        email = data["email"].lower()
        password = data["password"]
        role = data["role"].lower()

        # Validate role
        valid_roles = {"user", "admin"}
        if role not in valid_roles:
            logger.warning(f"Invalid role: {role}")
            return jsonify({"msg": f"Invalid role, must be one of: {", ".join(valid_roles)}"}), 400

        # Validate password format
        password_error = User.validate_password(password)
        if password_error:
            logger.warning(f"Password validation failed: {password_error}")
            return jsonify({"msg": password_error}), 400

        # Check if user exists
        if User.query.filter_by(username=username).first() or User.query.filter_by(email=email).first():
            logger.warning(f"User already exists: username={username}, email={email}")
            return jsonify({"msg": "User already exists"}), 400

        # Create user
        user = User(
            username=username,
            email=email,
            password=password,  # Handled by set_password in User
            role=role
        )

        try:
            db.session.add(user)
            db.session.commit()
            logger.info(f"User created successfully: username={username}, email={email}, role={role}")
        except Exception as e:
            db.session.rollback()
            logger.error(f"Database error during signup: {str(e)}")
            return jsonify({"msg": "Failed to create user", "error": str(e)}), 500

        response = {
            "msg": "User created successfully",
            "user": {
                "user_id": user.id,
                "username": user.username,
                "email": user.email,
                "role": user.role,
                "created_at": user.created_at.isoformat()
            }
        }

        return jsonify(response), 201
    except Exception as e:
        logger.error(f"Unexpected error in signup: {str(e)}")
        return jsonify({"msg": "Unexpected error occurred", "error": str(e)}), 500

def signin():
    """
    Authenticates a user and returns a JWT.

    Returns:
        JSON response with access token or error message.
    """
    try:
        data = request.get_json()
        if not data or not all(key in data for key in ["email", "password"]):
            logger.warning("Missing email or password in signin request")
            return jsonify({"msg": "email and password are required"}), 400

        email = data["email"].lower()
        password = data["password"]

        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            logger.warning(f"Invalid credentials for user: {user.username}")
            return jsonify({"msg": "Invalid credentials"}), 401

        access_token = create_access_token(identity=user.id)
        logger.info(f"User signed in successfully: username={user.username}")
        return jsonify({
            "msg": "Signin successful",
            "access_token": access_token,
            "user": {
                "user_id": user.id,
                "username": user.username,
                "email": user.email,
                "role": user.role
            }
        }), 200
    except Exception as e:
        logger.error(f"Unexpected error in signin: {str(e)}")
        return jsonify({"msg": "Unexpected error occurred", "error": str(e)}), 500


@jwt_required()
def reset_password():
    """
    Resets the password for the authenticated user.

    Returns:
        JSON response confirming password reset, or error message.
    """
    user_id = get_jwt_identity()
    logger.debug(f"Reset password request for user_id: {user_id}")

    data = request.get_json()
    if not data:
        logger.warning(f"No input data provided for user_id: {user_id}")
        return jsonify({"msg": "No input data provided"}), 400

    new_password = data.get("new_password")
    confirm_password = data.get("confirm_password")

    logger.debug(f"Received new_password: [hidden], confirm_password: [hidden]")

    user = db.session.get(User, user_id)
    if not user:
        logger.error(f"User not found for user_id: {user_id}")
        return jsonify({"msg": "User not found"}), 404

    if new_password != confirm_password:
        logger.warning(f"Password reset failed for user_id: {user_id}: Passwords do not match")
        return jsonify({"msg": "New password and confirm password do not match"}), 400

    validation_error = User.validate_password(new_password)
    if validation_error:
        logger.warning(f"Password reset failed for user_id: {user_id}: {validation_error}")
        return jsonify({"msg": validation_error}), 400

    try:
        user.password = generate_password_hash(new_password)
        user.updated_at = datetime.utcnow() if hasattr(user, "updated_at") else None
        db.session.commit()
        logger.info(f"Password reset successful for user_id: {user_id}")
        return jsonify({"msg": "Password reset successful"}), 200
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f"Password reset failed for user_id: {user_id}: {str(e)}")
        return jsonify({"msg": f"Failed to reset password: {str(e)}"}), 500


@jwt_required()
def update_user(user_id):
    """
    Updates a user"s username and role (admin only for role).
    Accessible by admin or the same user.

    Args:
        user_id (str): UUID of the user to update.

    Returns:
        JSON response with updated user details, or error message.
    """
    try:
        UUID(user_id)
    except ValueError:
        logger.error(f"Invalid user_id format: {user_id}")
        return jsonify({"msg": "Invalid user_id format, must be a valid UUID"}), 400

    current_user_id = get_jwt_identity()
    logger.debug(f"Updating user_id: {user_id} by current_user_id: {current_user_id}")

    current_user = db.session.get(User, current_user_id)
    if not current_user:
        logger.error(f"Current user not found for current_user_id: {current_user_id}")
        return jsonify({"msg": "Current user not found"}), 404

    if user_id != current_user_id and current_user.role != "admin":
        logger.warning(f"Unauthorized update attempt by current_user_id: {current_user_id} (role: {current_user.role}) for user_id: {user_id}")
        return jsonify({"msg": "Unauthorized: You can only update your own profile or must be an admin"}), 403

    user = db.session.get(User, user_id)
    if not user:
        logger.error(f"User not found for user_id: {user_id}")
        return jsonify({"msg": "User not found"}), 404

    data = request.get_json()
    if not data:
        logger.warning(f"No input data provided for user_id: {user_id}")
        return jsonify({"msg": "No input data provided"}), 400

    logger.debug(f"Received data for user_id {user_id}: {data}")

    updated = False
    original_values = {
        "username": user.username,
        "role": user.role
    }

    if "username" in data and data["username"] != user.username:
        new_username = data["username"].lower()
        if not isinstance(new_username, str) or not new_username.strip():
            logger.error(f"Invalid username format for user_id {user_id}: {new_username}")
            return jsonify({"msg": "Username must be a non-empty string"}), 400
        if User.query.filter_by(username=new_username).first():
            logger.warning(f"Username already exists: {new_username}")
            return jsonify({"msg": "Username already exists"}), 400
        user.username = new_username
        updated = True
        logger.debug(f"Updated username to: {new_username}")

    if "role" in data and data["role"] != user.role:
        if current_user.role != "admin":
            logger.warning(f"Non-admin current_user_id {current_user_id} attempted to update role for user_id: {user_id}")
            return jsonify({"msg": "Unauthorized: Only admins can update user roles"}), 403
        new_role = data["role"].lower()
        valid_roles = {"user", "admin"}
        if new_role not in valid_roles:
            logger.error(f"Invalid role for user_id {user_id}: {new_role}")
            return jsonify({"msg": f"Invalid role, must be one of: {", ".join(valid_roles)}"}), 400
        user.role = new_role
        updated = True
        logger.debug(f"Updated role to: {new_role}")

    if not updated:
        logger.info(f"No fields updated for user_id: {user_id}")
        return jsonify({"msg": "No changes made to user", "user": original_values}), 200

    user.updated_at = datetime.utcnow() if hasattr(user, "updated_at") else None
    logger.debug(f"Updated updated_at to: {user.updated_at}")

    try:
        db.session.commit()
        logger.info(f"User {user_id} updated successfully")
    except IntegrityError:
        db.session.rollback()
        logger.error(f"IntegrityError updating user {user_id}: Username already exists")
        return jsonify({"msg": "Username already exists"}), 400
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f"Failed to update user {user_id}: {str(e)}")
        return jsonify({"msg": "Failed to update user", "details": str(e)}), 500

    updated_user = db.session.get(User, user_id)
    return jsonify({
        "msg": "User updated",
        "user": {
            "id": updated_user.id,
            "username": updated_user.username,
            "email": updated_user.email,
            "role": updated_user.role,
            "created_at": updated_user.created_at.isoformat(),
            "updated_at": updated_user.updated_at.isoformat() if hasattr(updated_user, "updated_at") and updated_user.updated_at else None
        }
    }), 200
    
   
  
@jwt_required()
def delete_user(user_id):
    """
    Deletes a user from the database.
    Accessible by admin or the same user.

    Args:
        user_id (str): UUID of the user to delete.

    Returns:
        JSON response confirming deletion, or error message.
    """
    try:
        UUID(user_id)
    except ValueError:
        logger.error(f"Invalid user_id format: {user_id}")
        return jsonify({"msg": "Invalid user_id format, must be a valid UUID"}), 400

    current_user_id = get_jwt_identity()
    logger.debug(f"Deleting user_id: {user_id} by current_user_id: {current_user_id}")

    current_user = db.session.get(User, current_user_id)
    if not current_user:
        logger.error(f"Current user not found for current_user_id: {current_user_id}")
        return jsonify({"msg": "Current user not found"}), 404

    if user_id != current_user_id and current_user.role != "admin":
        logger.warning(f"Unauthorized delete attempt by current_user_id: {current_user_id} (role: {current_user.role}) for user_id: {user_id}")
        return jsonify({"msg": "Unauthorized: You can only delete your own account or must be an admin"}), 403

    user = db.session.get(User, user_id)
    if not user:
        logger.error(f"User not found for user_id: {user_id}")
        return jsonify({"msg": "User not found"}), 404

    user_data = {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "created_at": user.created_at.isoformat()
    }

    try:
        db.session.delete(user)
        db.session.commit()
        logger.info(f"User {user_id} deleted successfully by current_user_id: {current_user_id}, role: {current_user.role}")
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f"Failed to delete user {user_id}: {str(e)}")
        return jsonify({"msg": "Failed to delete user", "details": str(e)}), 500

    return jsonify({
        "msg": "User deleted",
        "user_id": user_id,
        "user": user_data
    }), 200


@jwt_required()
def delete_user_tasks(user_id):
    """
    Deletes all tasks created by a specific user.
    Accessible by admin or the same user.

    Args:
        user_id (str): UUID of the user whose tasks to delete.

    Returns:
        JSON response with count of deleted tasks, or error message.
    """
    try:
        UUID(user_id)
    except ValueError:
        logger.error(f"Invalid user_id format: {user_id}")
        return jsonify({"msg": "Invalid user_id format, must be a valid UUID"}), 400

    current_user_id = get_jwt_identity()
    logger.debug(f"Deleting tasks for user_id: {user_id} by current_user_id: {current_user_id}")

    current_user = db.session.get(User, current_user_id)
    if not current_user:
        logger.error(f"Current user not found for current_user_id: {current_user_id}")
        return jsonify({"msg": "Current user not found"}), 404

    if user_id != current_user_id and current_user.role != "admin":
        logger.warning(f"Unauthorized delete tasks attempt by current_user_id: {current_user_id} (role: {current_user.role}) for user_id: {user_id}")
        return jsonify({"msg": "Unauthorized: You can only delete your own tasks or must be an admin"}), 403

    user = db.session.get(User, user_id)
    if not user:
        logger.error(f"User not found for user_id: {user_id}")
        return jsonify({"msg": "User not found"}), 404

    tasks = Task.query.filter_by(user_id=user_id).all()
    task_count = len(tasks)
    if task_count == 0:
        logger.info(f"No tasks found for user_id: {user_id}")
        return jsonify({"msg": "No tasks found for user", "deleted_tasks": 0}), 200

    try:
        # Delete associated worker_task entries
        task_ids = [task.id for task in tasks]
        db.session.execute(worker_task.delete().where(worker_task.c.task_id.in_(task_ids)))
        # Delete tasks
        for task in tasks:
            db.session.delete(task)
        db.session.commit()
        logger.info(f"Deleted {task_count} tasks for user_id: {user_id} by current_user_id: {current_user_id}, role: {current_user.role}")
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f"Failed to delete tasks for user_id: {user_id}: {str(e)}")
        return jsonify({"msg": "Failed to delete tasks", "details": str(e)}), 500

    return jsonify({
        "msg": "User tasks deleted",
        "user_id": user_id,
        "deleted_tasks": task_count
    }), 200
    
     
from flask_jwt_extended import jwt_required, get_jwt_identity
from flask import jsonify
from helper.models import db, User, Task  # Import Task model
import logging

logger = logging.getLogger(__name__)

@jwt_required()
def list_users():
    """
    Lists all users and their associated tasks (admin access only).

    Returns:
        JSON response with list of users, including their tasks, or error.
    """
    try:
        current_user = User.query.get(get_jwt_identity())
        if current_user.role != "admin":
            logger.warning(f"Unauthorized list_users attempt by user_id={current_user.id}")
            return jsonify({"msg": "Unauthorized: Admin access required"}), 403

        users = User.query.all()
        response = {
            "msg": "Users and tasks retrieved successfully",
            "users": [{
                "user_id": user.id,
                "username": user.username,
                "email": user.email,
                "role": user.role,
                "created_at": user.created_at.isoformat(),
                "task": len(user.task)
            } for user in users]
        }
        logger.info("Users and tasks listed successfully")
        return jsonify(response), 200
    except Exception as e:
        logger.error(f"Unexpected error in list_users: {str(e)}")
        return jsonify({"msg": "Unexpected error occurred", "error": str(e)}), 500