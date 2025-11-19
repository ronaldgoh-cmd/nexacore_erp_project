# NexaCore ERP Cloud Go-Live Playbook

This playbook continues where the "NexaCore ERP Beginner Field Manual" left off.
It walks you—click by click—through the remaining steps required to take your
single-user desktop build online, serve multiple companies, and distribute a
self-updating executable. Every task is written prescriptively so you can follow
it even if you have never shipped software before.

> **Legend**
> - **⏱ Time** estimates help plan your day. Double the number if you prefer to
>   move slowly or take notes.
> - **⚙ Commands** appear in monospace blocks. Copy/paste them into the exact
>   terminal described in the surrounding text.
> - **☁ Console menus** are shown as `Menu → Submenu → Screen` so you know which
>   buttons to click inside Google Cloud or GitHub.

---

## 1. Confirm your cloud foundation (15 minutes)

1. Open **https://console.cloud.google.com/** and make sure the project dropdown
   shows the project you created earlier (for example `nexacore-online`).
2. In a second browser tab, open **https://bitwarden.com** and unlock your vault.
   Keep it visible; you will save at least five new secrets during this playbook.
3. On your laptop, reopen the repository folder (`nexacore-online`) in Visual
   Studio Code → `File → Open Folder…`. Press ``Ctrl+` `` to open the integrated
   terminal. Activate the virtual environment: `source .venv/bin/activate`
   (macOS/Linux) or `.\.venv\Scripts\Activate` (Windows PowerShell).
4. Run `gcloud config list` in that terminal. Confirm the **project** value matches
   the one shown in the console. If not, set it with
   `gcloud config set project <PROJECT_ID>`.

---

## 2. Design for simultaneous users (60 minutes)

You want every user to see updates instantly (e.g., User 1 adds an employee and
User 2 sees the new record without refreshing). The repository already contains
a tenant-aware WebSocket service so all you need to do is configure it and wire
the desktop client to listen for events.

1. **Review the backend WebSocket pieces**
   1. Pull the latest code (`git pull origin work`). Open
      `backend/app/websocket_manager.py` and skim the `broadcast_event` helper so
      you understand the JSON payload the desktop client should expect.
   2. Open `backend/app/main.py` and confirm the `/ws` endpoint is present. It
      requires a valid JWT access token via the `token` query parameter and keeps
      the connection scoped per tenant.
   3. In `backend/app/routers/employees.py`, note that the `create_employee`
      handler already calls `broadcast_event` with channel `"employees"` and an
      `action` of `"created"`.

2. **Start the backend WebSocket server**
   1. From the `backend/` folder run `uvicorn app.main:app --reload --ws websockets`.
      The `/ws` endpoint is active alongside the existing REST routes.
   2. If you deploy inside Docker Compose, expose port `8000` and keep HTTPS open
      on the VM so secure WebSocket (`wss://`) connections succeed.

3. **Update the desktop client** (inside `nexacore_erp/`)
   1. Locate the module responsible for API calls (search for `requests.post`).
   2. Install `websocket-client` into the desktop app environment.
   3. When the desktop UI loads, open a background thread that connects to
      `wss://<your-domain>/ws?token=<JWT>` (reuse the login token you already
      store). No extra subscribe call is needed because the backend scopes each
      connection by tenant.
   4. On message receive, parse the JSON payload
      (`{"channel": "employees", "action": "created", "data": {...}}`) and refresh
      the matching UI table.

4. **Test WebSockets locally**
   1. Start the backend with `make dev` (or `uvicorn backend.app.main:app --reload`).
   2. Run two instances of the desktop client on your laptop.
   3. Add a sample employee from instance A and watch instance B update without
      pressing refresh. If nothing happens, watch the backend logs for errors.
   4. Commit the WebSocket code (`git add backend/app/* nexacore_erp/*`).

5. **Open port 443 on the VM for WebSockets**
   1. Go to `☰ → VPC network → Firewall`. Verify the existing `allow-https`
      rule targets the network tag `nexacore-app` (you configured that earlier).
   2. Open `Compute Engine → VM instances`, click your VM name, and confirm the
      **Network tags** section includes `nexacore-app`. This ensures WebSocket
      traffic over HTTPS reaches the backend container.

---

## 3. Rolling updates and maintenance windows (45 minutes)

You asked how to put every user into maintenance while you deploy an update.
The safest approach is to use Docker images with version tags, a "maintenance"
flag stored in the database, and a Cloud Storage bucket for release artifacts.

1. **Understand the built-in maintenance flag**
   1. Pull the latest backend and open `backend/app/models/system_status.py` to see
      the schema that stores `maintenance_mode` + a customizable message.
   2. The `/system/status` endpoint is public (no auth) so the desktop client can
      check it before syncing. The `/system/maintenance` endpoint requires an
      admin JWT and lets you flip the flag without writing SQL manually.
   3. If you have not created an admin yet, call `/auth/register` with
      `{"role": "admin"}` (temporarily allow the signup) or update an existing
      user’s row in PostgreSQL so the `role` column equals `admin`.

2. **Teach the desktop client to obey the flag**
   1. Before any data sync, call `/system/status`.
   2. If `maintenance_mode` is true, pop up a blocking dialog telling the user to
      wait. Close the app after displaying the message.

3. **Prepare Dockerized releases**
   1. Build the backend image locally: `docker build -t us-central1-docker.pkg.dev/<PROJECT_ID>/nexacore/backend:v1 .`
   2. Push it to Artifact Registry: `docker push ...`.
   3. SSH into the VM and pull the new tag: `docker pull ...:v1`.
   4. When ready to update, call `PUT /system/maintenance` with
      `{"maintenance_mode": true}` to block users, restart the container with the
      new tag, run migrations, then send another request with
      `{"maintenance_mode": false}`.

4. **Automate with a script**
   1. Create `scripts/deploy_backend.sh` containing commands:
      ```bash
      #!/usr/bin/env bash
      set -euo pipefail
      TOKEN="$1"  # pass an admin JWT when running the script
      curl -fsSL -X PUT \
        -H "Authorization: Bearer ${TOKEN}" \
        -H "Content-Type: application/json" \
        -d '{"maintenance_mode": true}' \
        https://<your-domain>/system/maintenance
      docker compose pull backend
      docker compose up -d backend
      alembic upgrade head
      curl -fsSL -X PUT \
        -H "Authorization: Bearer ${TOKEN}" \
        -H "Content-Type: application/json" \
        -d '{"maintenance_mode": false}' \
        https://<your-domain>/system/maintenance
      ```
   2. Run it on the VM each time you need a maintenance window.

---

## 4. Ship an executable desktop client (75 minutes)

1. **Prepare the build machine**
   1. Use your local Windows computer so the executable looks native.
   2. Install Python 3.11 and the dependencies listed in `requirements.txt`.
   3. Install PyInstaller globally: `pip install pyinstaller`.

2. **Create a spec file**
   1. In the repo root, run:
      ```bash
      pyinstaller nexacore_erp/__main__.py \
        --name NexaCoreERP \
        --onefile \
        --noconsole \
        --icon docs/assets/app.ico \
        --hidden-import=asyncio
      ```
   2. PyInstaller generates a `build/` folder and `dist/NexaCoreERP.exe`.
   3. Test the exe on the same machine. Double-click it; confirm it reaches the
      backend you started on the VM (`Settings → API URL → https://<your-domain>`).

3. **Sign the executable (optional but recommended)**
   1. Buy a code-signing certificate (e.g., Sectigo). Store the `.pfx` in
      Bitwarden.
   2. Use `signtool sign /f cert.pfx /tr http://timestamp.sectigo.com /td sha256 dist/NexaCoreERP.exe`.

4. **Distribute**
   1. Create a folder in Google Cloud Storage: `☰ → Cloud Storage → Buckets → Create`.
   2. Name it `nexacore-downloads` and make it **Uniform access control**.
   3. Upload `dist/NexaCoreERP.exe`. Click the file → **Copy URL**. Share the URL
      with customers.

5. **Auto-updates**
   1. Inside the desktop app, add a startup check: call
      `https://nexacore-downloads.storage.googleapis.com/latest.json`.
   2. Maintain this JSON file yourself with keys `version`, `mandatory`, `url`.
   3. When you publish a new exe, update `latest.json`. If the user’s version is
      older and `mandatory` is true, download the new installer and relaunch.

---

## 5. Support multiple companies (multi-tenancy) (90 minutes)

1. **Decide between single vs multi-database**
   - *Single database, tenant column*: easiest to manage updates. Add a column
     `tenant_id` to every table and scope queries by the logged-in tenant.
   - *Database-per-tenant*: better isolation but more maintenance. For desktop
     simplicity, start with the single database approach and revisit later.

2. **Implement tenant scoping**
   1. Create a table `tenants` with columns `id`, `name`, `status`.
   2. Create a `tenant_users` table linking tenant IDs to user logins.
   3. When a user signs in, the backend issues a JWT containing `tenant_id`.
   4. Use SQLAlchemy’s `SessionEvents.do_orm_execute` hook to automatically add
      `WHERE tenant_id = :tenant_id` to every query.
   5. When you insert new records, populate `tenant_id` from the authenticated
      user’s token.

3. **Separate file storage per tenant**
   1. If you store documents, create Cloud Storage folders like
      `gs://nexacore-docs/<tenant-id>/...`.
   2. Use signed URLs so only authenticated clients can upload/download files.

4. **Tenant onboarding checklist**
   1. In the desktop app, add a company creation wizard.
   2. When a new company signs up, call a backend endpoint `/tenants` that:
      - Inserts into the `tenants` table
      - Creates default chart of accounts, roles, etc.
      - Sends a welcome email with download + login instructions
   3. Document each tenant inside Bitwarden → secure note.

5. **Bulk updates across tenants**
   1. Because you use a single Docker image + single PostgreSQL schema, applying
      migrations automatically updates every tenant simultaneously.
   2. When adding tenant-specific features (e.g., tax modules), hide them behind
      feature flags stored in the `tenants` table.

---

## 6. Production readiness checklist (30 minutes)

1. **Monitoring**
   1. Enable Cloud Logging: `☰ → Logging → Logs Explorer`. Verify the VM’s
      `syslog` entries are visible.
   2. Install Prometheus Node Exporter on the VM if you want CPU/memory charts.

2. **Backups**
   1. In Cloud SQL → `nexacore-postgres → Backups`, enable automated backups.
   2. Download a weekly logical backup with `pg_dump` and store it in Cloud
      Storage.

3. **Disaster recovery drill**
   1. Create a second VM in another zone.
   2. Restore yesterday’s Cloud SQL backup into a new instance.
   3. Point the desktop client at the restored backend to verify it boots.

4. **Security sweep**
   1. Rotate all service account keys every 90 days. Delete the old key in
      `IAM & Admin → Service Accounts → nexacore-backend-sa → Keys`.
   2. Run `pip-audit` in the repo monthly to catch vulnerable dependencies.

---

## 7. Quick reference (bookmark this)

- **VM URL**: `http://34.87.155.9:8000` (replace with HTTPS once you install an
  SSL certificate via Nginx or Cloud Armor).
- **Local URL**: `http://127.0.0.1:8000` (for testing with the Cloud SQL Proxy).
- **Need help?** Create GitHub issues describing bugs or features and link back
  to the relevant step in this playbook so you can track progress.

Print this playbook or export it as a PDF, then check each box as you go. By the
end you will have:

1. A WebSocket-enabled backend so all users stay in sync.
2. A repeatable maintenance + deployment process.
3. A signed Windows executable that auto-updates.
4. A multi-tenant data model ready for multiple companies.

Keep iterating. Every production-grade ERP system grew out of a checklist just
like this one.
