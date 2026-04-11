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
from app.routes import attachments as attachment_routes


def create_app():
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.from_object(get_config())

    # Session config
    app.permanent_session_lifetime = timedelta(hours=app.config.get("SESSION_HOURS", 24))

    db.init_app(app)

    # Static asset cache (1 week)
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 604800

    # Error handlers
    from app.errors import register_error_handlers
    register_error_handlers(app)

    app.register_blueprint(auth_routes.bp)
    app.register_blueprint(main_routes.bp)
    app.register_blueprint(issue_routes.bp)
    app.register_blueprint(admin_routes.bp)
    app.register_blueprint(attachment_routes.bp)

    return app
