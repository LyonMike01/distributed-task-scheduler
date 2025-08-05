# Distributed Task Scheduler with REST API and Worker's Node

## Overview
The **Distributed Task Scheduler with REST API and Worker's Node** is a scalable task management system designed to create, assign, and track tasks across distributed worker nodes. It provides a RESTful API for managing users, tasks, and workers, with JWT-based authentication for secure access. Worker nodes handle task execution, making the system suitable for background job processing, workflow automation, or distributed computing.

## Features
- **User Management**: Register, authenticate, update, and delete users with role-based access (e.g., `user`, `worker`).
- **Task Management**: Create, list, update, delete, and track tasks with attributes like title, description, priority, and due date.
- **Worker Management**: Manage worker nodes for task execution, including creation, status tracking, and assignment.
- **Task Assignment**: Assign tasks to users or worker nodes for distributed processing.
- **Authentication**: Secure endpoints with JWT tokens.
- **Scalability**: Designed for distributed environments, with worker nodes handling tasks asynchronously.

## Prerequisites
- **Git**: For version control.
- **Python 3.8+**: For running the API (assumed to be Python-based, e.g., Flask).
- **Docker** (optional): For containerized deployment.
- **Postman**: For testing the API using the provided `test.json` collection.
- **Database**: A relational PostgreSQL
- **Message Queue**: For task distribution Radis and Celery.

## Installation
1. **Clone the Repository** (after pushing to GitHub):
   ```bash
   git clone https://github.com/<your-username>/<your-repo-name>.git
   cd <your-repo-name>
   ```
2. **Set Up a Virtual Environment** (for Python):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. **Install Dependencies**:
   - If using Python, create a `requirements.txt` and install:
     ```bash
     pip install -r requirements.txt
     ```
   - If using Node.js, install dependencies:
     ```bash
     npm install
     ```
4. **Configure Environment Variables**:
   - Create a `.env` file based on `.env.example` (if provided) and set variables like:
     ```
     DATABASE_URL=<your-database-url>
     JWT_SECRET=<your-jwt-secret>
     API_PORT=5000
     ```
5. **Set Up the Database**:
   - Initialize the database (e.g., run migrations if using Flask-SQLAlchemy or similar).
   - Example for PostgreSQL:
     ```bash
     psql -U <username> -d <database> -f init.sql
     ```
6. **Run the API**:
   ```bash
   python app.py 
   ```
   The API will be available at `http://localhost:5000`.

## API Usage
The API is organized into three main categories: **User Endpoints**, **Task Endpoints**, and **Worker Endpoints**. Use the provided `test.json` Postman collection to test the API.

### Authentication
- **Sign Up**: `POST /signup` to create a user.
- **Sign In**: `POST /signin` to get a JWT token, required for most endpoints.
- Example:
  ```bash
  curl -X POST http://localhost:5000/signin \
  -H "Content-Type: application/json" \
  -d '{"email": "testuser@example.com", "password": "Test@1234"}'
  ```

### Key Endpoints
- **Users**:
  - `POST /signup`: Create a user.
  - `POST /signin`: Authenticate and get JWT.
  - `POST /reset_password`: Reset user password.
  - `PUT /update_user/<user_id>`: Update user details.
  - `DELETE /delete_user/<user_id>`: Delete a user.
  - `GET /list_users`: List all users.
- **Tasks**:
  - `POST /create_task`: Create a task.
  - `GET /tasks_list`: List all tasks.
  - `GET /get_task/<task_id>`: Get task details.
  - `PUT /update_task/<task_id>`: Update a task.
  - `DELETE /delete_task/<task_id>`: Delete a task.
  - `POST /assign_task`: Assign a task to a user.
  - `POST /assign_task_to_worker/<task_id>`: Assign a task to a worker.
- **Workers**:
  - `POST /create_worker`: Create a worker node.
  - `GET /workers_list`: List all workers.
  - `GET /worker_status/<worker_id>`: Check worker status.
  - `PUT /update_worker/<worker_id>`: Update worker details.
  - `DELETE /delete_worker/<worker_id>`: Delete a worker.

For detailed request/response formats, import `test.json` into Postman.

## Testing
- Use the `test.json` Postman collection to test all endpoints.
- Set the `baseUrl` variable to `http://localhost:5000` in Postman.
- Run tests to verify status codes (200, 201) and response properties (e.g., `user_id`, `task_id`).

## Deployment
### Local Deployment
- Run the API locally:
  ```bash
  python app.py
  ```
- Optionally, use Docker:
  ```bash
  docker build -t task-scheduler-api .
  docker run -p 5000:5000 task-scheduler-api
  ```

### GitHub Deployment (First Version)
See the [GitHub Deployment](#github-deployment) section below.

## Worker Nodes
- Worker nodes are responsible for task execution in the distributed system.
- Implementation details (e.g., Celery, RabbitMQ) depend on the backend setup.
- To start a worker node:
  ```bash
  celery -A worker worker --loglevel=info  # Example for Celery
  ```

## Contributing
1. Fork the repository.
2. Create a feature branch:
   ```bash
   git checkout -b feature/<your-feature>
   ```
3. Commit changes:
   ```bash
   git commit -m "Add <your-feature>"
   ```
4. Push to your fork:
   ```bash
   git push origin feature/<your-feature>
   ```
5. Open a pull request on GitHub.

## License
[MIT License](LICENSE) (or specify your preferred license).

## Contact
For issues or questions, open a GitHub issue or contact the maintainer at `<your-email>`.

---

## GitHub Deployment

To deploy the first version to GitHub, follow these steps:

### Prerequisites
- A GitHub account.
- Git installed on your machine.
- The project directory initialized as a Git repository.

### Steps
1. **Initialize Git Repository** (if not already done):
   ```bash
   cd <your-project-directory>
   git init
   ```
2. **Add Files**:
   - Ensure the `.gitignore` and `README.md` files (above) are in the project root.
   - Add the `test.json` Postman collection and other project files (e.g., `app.py`, `requirements.txt`).
   ```bash
   git add .
   ```
3. **Commit Changes**:
   ```bash
   git commit -m "Initial commit: Add Distributed Task Scheduler with REST API and Worker's Node"
   ```
4. **Create a GitHub Repository**:
   - Go to `https://github.com/new`.
   - Enter a repository name (e.g., `distributed-task-scheduler`).
   - Choose public or private, and avoid initializing with a README (since we have one).
   - Click "Create repository".
5. **Link Local Repository to GitHub**:
   - Copy the repository URL (e.g., `https://github.com/<your-username>/distributed-task-scheduler.git`).
   - Link it:
     ```bash
     git remote add origin https://github.com/<your-username>/distributed-task-scheduler.git
     ```
6. **Push to GitHub**:
   ```bash
   git push -u origin main
   ```
   - If `main` isn’t your default branch (e.g., `master`), replace `main` with your branch name.
7. **Verify on GitHub**:
   - Visit your repository on GitHub to confirm the files (`.gitignore`, `README.md`, `test.json`, etc.) are uploaded.
8. **Tag the First Version**:
   - Create a version tag (e.g., `v1.0.0`):
     ```bash
     git tag v1.0.0
     git push origin v1.0.0
     ```
9. **Optional: Create a Release**:
   - On GitHub, go to the repository, click "Releases", then "Create a new release".
   - Use the `v1.0.0` tag, add a title (e.g., "Initial Release"), and describe the release.
   - Click "Publish release".

### Notes
- Ensure sensitive data (e.g., `.env` files, API keys) is excluded via `.gitignore`.
- If you encounter authentication issues, use a Personal Access Token or SSH key for GitHub.
- Update the `README.md` with the actual repository URL after creation.