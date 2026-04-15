"""Authentication routes — login, register, forgot/reset password."""
import hashlib
import secrets
from datetime import datetime, timezone, timedelta
from functools import wraps

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    session, flash, g
)
from app.db import get_db
from app.models import user as user_model

bp = Blueprint("auth", __name__)


def _now():
    return datetime.now(timezone.utc).isoformat()


# ── Decorators ──

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("auth.login"))
        g.current_user = user_model.get_by_id(session["user_id"])
        if g.current_user is None or g.current_user["status"] != "active":
            session.clear()
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


def optional_login(f):
    """Load user if logged in, otherwise set g.current_user to None."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" in session:
            g.current_user = user_model.get_by_id(session["user_id"])
            if g.current_user is None or g.current_user["status"] != "active":
                g.current_user = None
        else:
            g.current_user = None
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


def can_edit_node(node_id_param="node_id"):
    """Decorator: check if current user can edit the given node."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            node_id = kwargs.get(node_id_param)
            if g.current_user["is_super_user"]:
                return f(*args, **kwargs)
            db = get_db()
            row = db.execute(
                """SELECT 1 FROM user_groups ug
                   JOIN group_nodes gn ON ug.group_id = gn.group_id
                   JOIN groups gr ON ug.group_id = gr.id
                   WHERE ug.user_id = ? AND gn.node_id = ? AND gr.is_active = 1
                   LIMIT 1""",
                (g.current_user["id"], node_id),
            ).fetchone()
            if not row:
                flash("你沒有編輯這個 node 的權限", "error")
                return redirect(url_for("main.tracker"))
            return f(*args, **kwargs)
        return decorated
    return decorator


# ── Login / Logout ──

@bp.route("/login", methods=["GET", "POST"])
def login():
    """登入
    ---
    tags:
      - Auth
    parameters:
      - name: username
        in: formData
        type: string
        required: true
        description: 使用者帳號
      - name: password
        in: formData
        type: string
        required: true
        description: 密碼
    responses:
      302:
        description: 登入成功，重導至 tracker；失敗則回到登入頁
    """
    if "user_id" in session:
        return redirect(url_for("main.tracker"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = user_model.get_by_username(username)

        if user and user["status"] == "active" and user_model.verify_password(user, password):
            session.clear()
            session["user_id"] = user["id"]
            session.permanent = True
            return redirect(url_for("main.tracker"))

        if user and user["status"] == "pending":
            flash("帳號尚在審核中，請等待管理員核准", "error")
        elif user and user["status"] == "disabled":
            flash("帳號已停用，請聯繫管理員", "error")
        else:
            flash("帳號或密碼錯誤", "error")

    return render_template("login.html")


@bp.route("/change_password", methods=["GET", "POST"])
@login_required
def change_password():
    """修改密碼
    ---
    tags:
      - Auth
    parameters:
      - name: current_password
        in: formData
        type: string
        required: true
        description: 目前密碼
      - name: new_password
        in: formData
        type: string
        required: true
        description: 新密碼 (至少 6 字元)
      - name: new_password2
        in: formData
        type: string
        required: true
        description: 確認新密碼
    responses:
      200:
        description: 顯示修改密碼表單
      302:
        description: 修改成功後重導至 tracker
    """
    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        new_password2 = request.form.get("new_password2", "")

        if not user_model.verify_password(g.current_user, current_password):
            flash("目前密碼不正確", "error")
            return render_template("change_password.html")
        if len(new_password) < 6:
            flash("新密碼至少 6 個字元", "error")
            return render_template("change_password.html")
        if new_password != new_password2:
            flash("兩次新密碼不一致", "error")
            return render_template("change_password.html")

        import bcrypt
        password_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
        db = get_db()
        db.execute("UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
                   (password_hash, _now(), g.current_user["id"]))
        db.commit()
        flash("密碼已修改", "success")
        return redirect(url_for("main.tracker"))

    return render_template("change_password.html")


@bp.route("/logout")
def logout():
    """登出
    ---
    tags:
      - Auth
    responses:
      302:
        description: 清除 session 並重導至登入頁
    """
    session.clear()
    return redirect(url_for("auth.login"))


# ── Register ──

@bp.route("/register", methods=["GET", "POST"])
def register():
    """註冊新帳號
    ---
    tags:
      - Auth
    parameters:
      - name: username
        in: formData
        type: string
        required: true
        description: 帳號 (至少 2 字元)
      - name: email
        in: formData
        type: string
        required: true
        description: Email
      - name: display_name
        in: formData
        type: string
        required: true
        description: 顯示名稱
      - name: password
        in: formData
        type: string
        required: true
        description: 密碼 (至少 6 字元)
      - name: password2
        in: formData
        type: string
        required: true
        description: 確認密碼
    responses:
      302:
        description: 註冊成功 (狀態為 pending，待管理員審核)
    """
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        display_name = request.form.get("display_name", "").strip()
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")

        errors = []
        if not username or len(username) < 2:
            errors.append("帳號至少 2 個字元")
        if not email or "@" not in email:
            errors.append("請輸入有效的 Email")
        if not display_name:
            errors.append("請輸入顯示名稱")
        if len(password) < 6:
            errors.append("密碼至少 6 個字元")
        if password != password2:
            errors.append("兩次密碼不一致")
        if user_model.get_by_username(username):
            errors.append("帳號已被使用")

        db = get_db()
        existing_email = db.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone()
        if existing_email:
            errors.append("Email 已被使用")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("register.html",
                                   username=username, email=email, display_name=display_name)

        user_model.create_user(
            username=username, email=email, display_name=display_name,
            password=password, status="pending",
        )
        flash("帳號已建立，等待管理員審核。審核通過後您會收到通知信。", "success")
        return redirect(url_for("auth.login"))

    return render_template("register.html")


# ── Forgot Password ──

@bp.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    """忘記密碼 — 寄送重設連結
    ---
    tags:
      - Auth
    parameters:
      - name: email
        in: formData
        type: string
        required: true
        description: 註冊時使用的 Email
    responses:
      302:
        description: 無論 Email 是否存在，皆顯示相同訊息 (防止洩漏)
    """
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        # Always show the same message to avoid leaking email existence
        flash("如果該 Email 存在，我們已寄送密碼重設連結。", "success")

        db = get_db()
        user = db.execute("SELECT * FROM users WHERE email = ? AND status = 'active'",
                          (email,)).fetchone()
        if user:
            token = secrets.token_urlsafe(48)
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            expires = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
            db.execute(
                """INSERT INTO password_reset_tokens
                   (user_id, token_hash, expires_at, created_at)
                   VALUES (?, ?, ?, ?)""",
                (user["id"], token_hash, expires, _now()),
            )
            db.commit()

            reset_url = url_for("auth.reset_password", token=token, _external=True)

            # Send reset email via company mail API
            from app.mail import send_mail
            from app.models import setting as setting_model
            mail_from = setting_model.get("mail_from", "")
            if mail_from:
                send_mail(
                    from_addr=mail_from,
                    to_addr=email,
                    subject="[Gitea Tracker] 密碼重設",
                    body=f"您好 {user['display_name']}，\n\n"
                         f"請點擊以下連結重設密碼（1 小時內有效）：\n\n"
                         f"{reset_url}\n\n"
                         f"如果您沒有申請重設密碼，請忽略此信。",
                )
            else:
                print(f"[Password Reset] mail_from not configured. URL: {reset_url}")

        return redirect(url_for("auth.login"))

    return render_template("forgot_password.html")


# ── Reset Password ──

@bp.route("/reset_password/<token>", methods=["GET", "POST"])
def reset_password(token):
    """重設密碼
    ---
    tags:
      - Auth
    parameters:
      - name: token
        in: path
        type: string
        required: true
        description: 密碼重設 Token (從 Email 連結取得)
      - name: password
        in: formData
        type: string
        required: true
        description: 新密碼 (至少 6 字元)
      - name: password2
        in: formData
        type: string
        required: true
        description: 確認新密碼
    responses:
      302:
        description: 密碼重設成功，重導至登入頁
    """
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    db = get_db()
    row = db.execute(
        """SELECT * FROM password_reset_tokens
           WHERE token_hash = ? AND used_at IS NULL AND expires_at > ?""",
        (token_hash, _now()),
    ).fetchone()

    if not row:
        flash("連結無效或已過期", "error")
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")

        if len(password) < 6:
            flash("密碼至少 6 個字元", "error")
            return render_template("reset_password.html", token=token)
        if password != password2:
            flash("兩次密碼不一致", "error")
            return render_template("reset_password.html", token=token)

        import bcrypt
        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        db.execute("UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
                   (password_hash, _now(), row["user_id"]))
        db.execute("UPDATE password_reset_tokens SET used_at = ? WHERE id = ?",
                   (_now(), row["id"]))
        db.commit()

        flash("密碼已重設，請重新登入", "success")
        return redirect(url_for("auth.login"))

    return render_template("reset_password.html", token=token)
