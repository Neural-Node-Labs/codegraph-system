from backend.config import get_db_url


class UserService:
    """Handles user lookups and creation."""

    def get_user(self, user_id):
        """Fetch a user by id."""
        db_url = get_db_url()
        return {"id": user_id, "db": db_url}

    def create_user(self, name):
        """Create a new user record."""
        return {"name": name}
