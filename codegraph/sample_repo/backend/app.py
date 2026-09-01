from flask import Flask
from backend.services.user_service import UserService
from backend.config import get_secret_key

app = Flask(__name__)
service = UserService()


@app.route("/api/users/<user_id>", methods=["GET"])
def get_user(user_id):
    """Return a single user by id."""
    return service.get_user(user_id)


@app.route("/api/users", methods=["POST"])
def create_user():
    """Create a new user."""
    return service.create_user("new")


@app.route("/api/health", methods=["GET"])
def health():
    """Health check endpoint."""
    key = get_secret_key()
    return {"status": "ok", "has_key": bool(key)}
