"""
Flask app factory.
"""
from datetime import timedelta

from flask import Flask
from config import get_config
from app import db
from app.routes import main as main_routes
from app.routes import auth as auth_routes
from app.routes import issues as issue_routes
from app.routes import admin as admin_routes


def create_app():
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.from_object(get_config())

    # Session config
    app.permanent_session_lifetime = timedelta(hours=app.config.get("SESSION_HOURS", 24))

    db.init_app(app)

    app.register_blueprint(auth_routes.bp)
    app.register_blueprint(main_routes.bp)
    app.register_blueprint(issue_routes.bp)
    app.register_blueprint(admin_routes.bp)

    return app
