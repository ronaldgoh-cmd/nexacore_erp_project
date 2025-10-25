from sqlalchemy.orm import Session
from werkzeug.security import generate_password_hash, check_password_hash
# If you prefer no extra dep, swap to hashlib.pbkdf2_hmac; werkzeug is convenient.
# pip install werkzeug

from .database import SessionLocal, init_db
from .models import User, UserSettings

def authenticate(username: str, password: str) -> User | None:
    with SessionLocal() as s:
        u = s.query(User).filter(User.username == username).first()
        if not u:
            return None
        return u if check_password_hash(u.password_hash, password) else None

def ensure_bootstrap_superadmin():
    """Create a default superadmin if no users exist."""
    init_db()
    with SessionLocal() as s:
        has_user = s.query(User).first()
        if has_user:
            return
        admin = User(
            account_id="default",
            username="admin",
            password_hash=generate_password_hash("admin123"),
            role="superadmin",
        )
        s.add(admin)
        s.flush()
        s.add(UserSettings(account_id="default", user_id=admin.id, timezone="Etc/UTC", theme="light"))
        s.commit()
