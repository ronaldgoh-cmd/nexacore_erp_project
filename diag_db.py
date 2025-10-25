# diag_db.py
from sqlalchemy import text
from nexacore_erp.core.database import SessionLocal
from nexacore_erp.core.tenant import id as tenant_id

def run():
    with SessionLocal() as s:
        eng = s.bind
        print("DB URL:", getattr(eng, "url", "<unknown>"))
        print("Tenant:", tenant_id())

        names = [r[0] for r in s.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )).fetchall()]
        print("Tables:", ", ".join(names) or "<none>")

        has_emp = "employees" in names
        print("employees present:", has_emp)
        if not has_emp:
            return

        total = s.execute(text("SELECT COUNT(*) FROM employees")).scalar() or 0
        by_tenant = s.execute(text(
            "SELECT COUNT(*) FROM employees WHERE account_id = :a"
        ), {"a": tenant_id()}).scalar() or 0
        tenants = s.execute(text(
            "SELECT account_id, COUNT(*) FROM employees GROUP BY account_id ORDER BY COUNT(*) DESC"
        )).fetchall()
        sample = s.execute(text(
            "SELECT id, code, full_name, account_id FROM employees ORDER BY id DESC LIMIT 5"
        )).fetchall()

        print("employees rows total:", total)
        print("rows for current tenant:", by_tenant)
        print("rows by tenant:", tenants)
        print("sample:", sample)

if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        print("ERROR:", repr(e))
