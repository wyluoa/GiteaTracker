"""
Flask app factory.
"""
from flask import Flask
from config import get_config
from app import db
from app.routes import main as main_routes


def create_app():
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.from_object(get_config())

    db.init_app(app)

    app.register_blueprint(main_routes.bp)

    return app
