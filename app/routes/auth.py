"""Authentication routes — simple login for Phase 1."""
from functools import wraps

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    session, flash, g
)
from app.models import user as user_model

bp = Blueprint("auth", __name__)


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("auth.login"))
        g.current_user = user_model.get_by_id(session["user_id"])
        if g.current_user is None:
            session.clear()
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


def super_user_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not g.current_user["is_super_user"]:
            flash("需要管理員權限", "error")
            return redirect(url_for("main.tracker"))
        return f(*args, **kwargs)
    return decorated


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = user_model.get_by_username(username)

        if user and user["status"] == "active" and user_model.verify_password(user, password):
            session.clear()
            session["user_id"] = user["id"]
            session.permanent = True
            return redirect(url_for("main.tracker"))

        flash("帳號或密碼錯誤", "error")

    return render_template("login.html")


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
