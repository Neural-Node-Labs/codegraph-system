import os


def get_db_url():
    return os.getenv("DATABASE_URL")


def get_secret_key():
    return os.getenv("SECRET_KEY")
