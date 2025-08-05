from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from helper.config import Config
from helper.models import db
from helper.UTW.user import signup, signin, reset_password, update_user, delete_user, delete_user_tasks, list_users
from helper.UTW.task import create_task, list_task, get_task, update_task, delete_task, task_status, update_status, assign_task, assign_task_to_worker
from helper.UTW.worker import create_worker, list_workers, worker_status, update_worker, delete_worker
from datetime import timedelta
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config.from_object(Config)
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=2)
db.init_app(app)
jwt = JWTManager(app)

# Register user endpoints
app.route("/signup", methods=["POST"])(signup)
app.route("/signin", methods=["POST"])(signin)
app.route("/reset_password", methods=["POST"])(reset_password)
app.route("/update_user/<string:user_id>", methods=["PUT"])(update_user)
app.route("/delete_user/<string:user_id>", methods=["DELETE"])(delete_user)
app.route("/delete_user_task/<string:user_id>", methods=["DELETE"])(delete_user_tasks)
app.route("/list_users", methods=["GET"])(list_users)

# Register task endpoints
app.route("/create_task", methods=["POST"])(create_task)
app.route("/tasks_list", methods=["GET"])(list_task)
app.route("/get_task/<string:task_id>", methods=["GET"])(get_task)
app.route("/update_task/<string:task_id>", methods=["PUT"])(update_task)
app.route("/delete_task/<string:task_id>", methods=["DELETE"])(delete_task)
app.route("/task_status/<string:task_id>", methods=["GET"])(task_status)
app.route("/update_task_status/<string:task_id>", methods=["PUT"])(update_status)
app.route("/assign_task", methods=["POST"])(assign_task)
app.route("/assign_task_to_worker/<string:task_id>", methods=["POST"])(assign_task_to_worker)


# Register worker endpoints
app.route("/create_worker", methods=["POST"])(create_worker)
app.route("/workers_list", methods=["GET"])(list_workers)
app.route("/worker_status/<string:worker_id>", methods=["GET"])(worker_status)
app.route("/update_worker/<string:worker_id>", methods=["PUT"])(update_worker)
app.route("/delete_worker/<worker_id>", methods=["DELETE"])(delete_worker)

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True, host="0.0.0.0")