import os

def get_db_uri(default_uri):
    uri = os.getenv("SQLALCHEMY_DATABASE_URI", default_uri)
    if uri and uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql://", 1)
    return uri

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "fallback-secret")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

class DevConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = get_db_uri("sqlite:///matbakh_elshorta_dev.db")

class ProdConfig(Config):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = get_db_uri("sqlite:///matbakh_elshorta.db")
