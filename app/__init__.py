"""
Flask app factory.
"""
from datetime import timedelta

from flask import Flask
from flasgger import Swagger
from config import get_config
from . import db
from app.routes import main as main_routes
from app.routes import auth as auth_routes
from app.routes import issues as issue_routes
from app.routes import admin as admin_routes
from app.routes import attachments as attachment_routes


class _ScriptNameMiddleware:
    """Set SCRIPT_NAME so Flask generates prefixed URLs.

    Used when a reverse proxy (e.g. Traefik) strips the path prefix
    before forwarding.  The request path is already ``/dashboard``,
    but ``url_for()`` and ``request.script_root`` must still produce
    ``/GiteaTracker/dashboard``-style URLs for the browser.
    """

    def __init__(self, app, prefix):
        self.app = app
        self.prefix = prefix

    def __call__(self, environ, start_response):
        environ["SCRIPT_NAME"] = self.prefix
        return self.app(environ, start_response)


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

    # Swagger UI
    swagger_config = {
        "headers": [],
        "specs": [
            {
                "endpoint": "apispec",
                "route": "/apispec.json",
                "rule_filter": lambda rule: True,
                "model_filter": lambda tag: True,
            }
        ],
        "static_url_path": "/flasgger_static",
        "swagger_ui": True,
        "specs_route": "/apidocs/",
    }
    swagger_template = {
        "info": {
            "title": "Gitea Tracker API",
            "description": "Gitea Tracker 的完整 API 文件",
            "version": "1.0.0",
        },
        "tags": [
            {"name": "Auth", "description": "認證相關 (登入/登出/註冊/密碼重設)"},
            {"name": "Dashboard", "description": "儀表板 & 總覽"},
            {"name": "Tracker", "description": "追蹤器主表 & 篩選"},
            {"name": "Issues", "description": "議題操作 (Cell 更新/Timeline/關單/批次)"},
            {"name": "Meeting", "description": "會議模式"},
            {"name": "Calendar", "description": "行事曆檢視"},
            {"name": "Export", "description": "匯出"},
            {"name": "Admin - Users", "description": "使用者管理 (需管理員)"},
            {"name": "Admin - Groups", "description": "群組管理 (需管理員)"},
            {"name": "Admin - Nodes", "description": "Node 管理 (需管理員)"},
            {"name": "Admin - Settings", "description": "系統設定 (需管理員)"},
            {"name": "Admin - Excel", "description": "Excel 匯入 (需管理員)"},
            {"name": "Admin - Audit", "description": "稽核日誌 (需管理員)"},
            {"name": "Attachments", "description": "附件下載"},
            {"name": "Health", "description": "健康檢查"},
        ],
    }
    Swagger(app, config=swagger_config, template=swagger_template)

    # Inject dynamic settings into template context
    @app.context_processor
    def inject_dynamic_settings():
        import json as _json
        from app.models import setting as setting_model
        raw_mappings = setting_model.get("gitea_url_mappings", "[]")
        try:
            _url_mappings = _json.loads(raw_mappings)
        except (ValueError, TypeError):
            _url_mappings = []
        return {
            "col_topic_min_width": setting_model.get("col_topic_min_width", "280"),
            "col_path_min_width": setting_model.get("col_path_min_width", "220"),
            "gitea_url_mappings": _url_mappings,
        }

    # Reverse proxy path prefix (e.g. /GiteaTracker)
    # The reverse proxy strips the prefix before forwarding, so Flask
    # receives bare paths like /dashboard.  We only need SCRIPT_NAME so
    # that url_for() and request.script_root produce prefixed URLs.
    base_url = (app.config.get("BASE_URL") or "").rstrip("/")
    if base_url:
        app.config["APPLICATION_ROOT"] = base_url
        app.wsgi_app = _ScriptNameMiddleware(app.wsgi_app, base_url)

    return app
