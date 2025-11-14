# NexaCore ERP Beginner Field Manual (GCP Edition)

Welcome! This field manual is written for someone who has never deployed
software before but wants to take the NexaCore ERP desktop app online for
multiple companies. Every instruction below is intentionally explicit—expect
directions such as **exact console menus to click**, **buttons to press**, and
the **commands to type**. Work through the sections in order. By the end you’ll
have a reproducible workflow that covers cloud setup, backend development,
client updates, packaging, and releases.

> ✅ **You’ve already completed several prerequisites** (Docker Desktop,
> PostgreSQL, Bitwarden, GitHub). This manual acknowledges that progress and
> focuses on expanding each area with step-by-step guidance.

---

## 0. Orientation checklist (15 minutes)

1. **Organize your workspace**
   1. Create a folder on your computer named `nexacore-online`.
   2. Inside it, clone your GitHub repository:
      ```bash
      git clone https://github.com/<your-username>/<your-repo>.git
      cd <your-repo>
      ```
   3. Open the folder in Visual Studio Code (`File → Open Folder…`).

2. **Confirm Python & virtual environment**
   1. In VS Code, open a terminal (`Terminal → New Terminal`).
   2. Run `python --version` and verify it’s **3.11 or newer**.
   3. Create a venv for backend work:
      ```bash
      python -m venv .venv
      # Windows PowerShell
      .\.venv\Scripts\Activate
      # macOS/Linux
      source .venv/bin/activate
      ```
   4. You’ll see `(.venv)` appear at the start of the terminal prompt—this means
      the environment is active.

3. **Install the Google Cloud CLI (if you skipped it earlier)**
   1. Download from https://cloud.google.com/sdk/docs/install (choose your OS).
   2. After installation, run `gcloud init` in a terminal.
   3. Sign in with your Google account. If the wizard asks for a default project
      and you haven’t created one yet, pick **Skip**—you will set it later.
   4. Confirm the CLI works with `gcloud auth list`.

4. **Document credentials in Bitwarden**
   1. Open https://vault.bitwarden.com and sign in.
   2. Create a new folder named **NexaCore ERP** (`My Vault → Folders → +`).
   3. Any password, API key, or secret generated during this manual goes into
      that folder so nothing is lost.

---

## 1. Create and prepare your Google Cloud project (45 minutes)

### 1.1 Start a new project

1. Go to https://console.cloud.google.com/ and sign in.
2. At the top navigation bar, click the **project dropdown** (usually shows
   “Select a project” or an existing project name).
3. Click **New Project**.
4. Set the project name to `nexacore-online` (or any name you like).
5. Choose your billing account when prompted, then click **Create**.
6. Wait for the toast notification “Project created”. Click the notification or
   re-open the project dropdown and select the new project.
7. In your local terminal, run `gcloud config set project <PROJECT_ID>` so the
   CLI points at the right project by default (replace `<PROJECT_ID>` with the
   ID shown on the project dashboard).

### 1.2 Enable required APIs

1. With the new project selected, open the left-hand menu (**☰** icon).
2. Navigate to **APIs & Services → Library**.
3. Enable these APIs one by one (use the search bar in the library):
   - **Cloud SQL Admin API**
   - **Compute Engine API**
   - **Artifact Registry API**
   - **Secret Manager API**
   - **Cloud Run Admin API** (needed if you later choose Cloud Run)
4. For each API page, click **Enable** and wait for confirmation before moving
   to the next.

### 1.3 Set up IAM users (optional but recommended)

1. Open **IAM & Admin → IAM**.
2. Click **Grant Access**.
3. Add your primary Google account with the **Owner** role (if not already).
4. For collaborators, assign the **Editor** role or more limited custom roles.
5. Document any service accounts you create later in Bitwarden.

---

## 2. Prepare networking and security on GCP (60 minutes)

### 2.1 Create a VPC network

1. Open **VPC network → VPC networks**.
2. Click **Create VPC network**.
3. Fill in the form:
   - **Name**: `nexacore-vpc`
   - **Subnets**: choose **Custom**.
4. Under **Subnets**, click **Add subnet** twice to create:
   - **Public subnet**: name `public-subnet`, region `us-central1` (or your
     preferred), IP range `10.0.1.0/24`.
   - **Private subnet**: name `private-subnet`, same region, IP range
     `10.0.2.0/24`.
5. Scroll to **Firewall rules** and enable these options:
   - **Allow internal traffic within the VPC** ✔️
   - **Allow HTTP traffic** ✔️
   - **Allow HTTPS traffic** ✔️
6. Click **Create** and wait until the VPC shows a green checkmark.

### 2.2 Configure firewall rules (tighten security)

1. Still under **VPC network**, open **Firewall**.
2. Click **Create firewall rule**.
3. Create a rule named `allow-ssh-from-your-ip`:
   - **Targets**: `Specified target tags`
   - **Target tags**: `nexacore-app`
   - **Source IPv4 ranges**: enter your home/office public IP (find it via
     https://ifconfig.me) followed by `/32`, e.g., `203.0.113.42/32`.
   - **Protocols and ports**: check `tcp`, enter `22`.
4. Click **Create**.
5. Repeat to create a rule named `allow-https`:
   - **Targets**: `Specified target tags`
   - **Target tags**: `nexacore-app`
   - **Source IPv4 ranges**: `0.0.0.0/0`
   - **Protocols and ports**: check `tcp`, enter `443`.
6. Later, when you spin up the Compute Engine VM, you’ll assign the
   `nexacore-app` network tag so these rules apply automatically.

### 2.3 Reserve static IPs (for HTTPS endpoints)

1. Navigate to **VPC network → External IP addresses**.
2. Click **Reserve static address**.
3. Name it `nexacore-app-ip`, set **Type** to `Regional`, choose the same region
   as your VM, and leave the network tier as `Premium`.
4. Click **Reserve**.

Record the allocated IP address in Bitwarden.

---

## 3. Provision Cloud SQL for PostgreSQL (45 minutes)

### 3.1 Launch the instance

1. Go to **SQL** in the left-hand menu.
2. Click **Create instance**.
3. Select **PostgreSQL**.
4. Configure:
   - **Instance ID**: `nexacore-postgres`
   - **Password**: click **Generate**, copy the password into Bitwarden under
     “Cloud SQL Postgres admin”.
   - **Region**: match your VPC region (e.g., `us-central1`).
   - **Zone availability**: `Single zone` (cheaper for starters).
   - **Machine type**: `db-f1-micro` or `db-g1-small` (low cost while testing).
5. Under **Configuration options → Connections**:
   - Expand **Networking** → set **Private IP** → click **Set up private
     services access**.
   - Follow the prompt to create a private service connection using your VPC.
   - After creation, choose `nexacore-vpc` and the `private-subnet`.
6. Under **Authorized networks**, **do not** add public networks—stick to
   private connectivity for security.
7. Click **Create instance**. This can take a few minutes.

### 3.2 Create the application database and user

1. Once the instance status is **RUNNABLE**, click the instance name.
2. In the top tab bar, select **Databases** → click **Create database**.
   - Name: `nexacore`
   - Click **Create**.
3. Next, select the **Users** tab → **Add user account**.
   - **User name**: `nexacore_app`
   - **Password**: click **Generate**, store in Bitwarden under
     “Cloud SQL PostgreSQL app user”.
   - **Type**: `Built-in database user`
   - Click **Add**.

### 3.3 Note connection information

1. On the instance overview page, copy the **Instance connection name** (format:
   `project:region:instance`). Add it to Bitwarden as “Cloud SQL connection name”.
2. You will use a Cloud SQL Proxy connector when running locally and inside your
   backend container.

---

## 4. Configure Google Secret Manager (20 minutes)

1. Navigate to **Security → Secret Manager**.
2. Click **Create Secret** for each secret:
   - **Name**: `DATABASE_URL`
     - **Secret value**: `postgresql+asyncpg://nexacore_app:<PASSWORD>@/nexacore?host=/cloudsql/<INSTANCE_CONNECTION_NAME>`
       (replace placeholders). This format works with the Cloud SQL Proxy socket.
   - **Name**: `JWT_SECRET`
     - Generate a 64-character random string (`openssl rand -hex 32`) and paste it.
   - **Name**: `SMTP_PASSWORD` (if you plan to send emails).
3. After each creation, click **Add a new version** if you later rotate values.
4. In Bitwarden, record that secrets live in GCP Secret Manager and note who has
   access.

---

## 5. Create a Compute Engine VM for the backend (60 minutes)

### 5.1 Launch the VM

1. Open **Compute Engine → VM instances**.
2. If prompted to enable the API, click **Enable** and wait.
3. Click **Create Instance**.
4. Configure the basics:
   - **Name**: `nexacore-backend`
   - **Region/Zone**: match your database (e.g., `us-central1-a`).
   - **Machine configuration**: choose **e2-small (2 vCPU, 2 GB RAM)**.
5. Under **Boot disk**, click **Change** → select **Debian 12 (Bookworm)**.
   *Why?* The remaining instructions rely on the `apt-get` package manager that
   ships with Debian/Ubuntu images. **Do not** leave the default
   *Container-Optimized OS* image selected—COS does not include `apt-get`, so the
   commands below will fail with the exact error `sudo: apt-get: command not
   found`. If you already created a VM with COS, delete it and recreate the
   instance with Debian 12 so you can follow along without detours.
6. Under **Firewall**, check **Allow HTTPS traffic** (HTTP optional if you plan
   to set up an HTTPS load balancer later).
7. Expand **Networking**:
   - **Network tags**: add `nexacore-app` (so the firewall rules apply).
   - **Network interfaces**: ensure the interface is attached to
     `nexacore-vpc / public-subnet`.
   - **External IP**: choose the reserved static IP `nexacore-app-ip`.
8. Click **Create**. Wait for the VM to start.

### 5.2 Install Docker & Docker Compose (Debian/Ubuntu images)

1. SSH into the VM via the console: click the **SSH** button beside the instance.
2. In the SSH terminal, run `lsb_release -d`. Confirm it prints a Debian/Ubuntu
   description. If it says anything else (e.g., *Container-Optimized OS*), stop
   here, delete the VM, and recreate it with Debian 12—otherwise the next
   commands will not work.
3. Run the Docker installation commands:
   ```bash
   sudo apt-get update
   sudo apt-get install -y ca-certificates curl gnupg
   sudo install -m 0755 -d /etc/apt/keyrings
   curl -fsSL https://download.docker.com/linux/debian/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
   echo \
     "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian \
     $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
     sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
   sudo apt-get update
   sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
   sudo usermod -aG docker $USER
   exit
   ```
4. Reconnect via SSH to pick up the new Docker group membership (`SSH` button
   again) and verify with `docker version`.

> 💡 **Already on Container-Optimized OS?** Docker is pre-installed there, but
> the system uses a different package manager. You can either recreate the VM
> with Debian (recommended for this manual) or continue by prefixing Docker
> commands with `sudo` and skipping the `apt-get` steps.

### 5.3 Install the Google Cloud CLI on the VM

1. Still on the Debian/Ubuntu VM, run:
   ```bash
   sudo apt-get install -y apt-transport-https ca-certificates gnupg
   curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg | \
     sudo gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg
   echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] http://packages.cloud.google.com/apt cloud-sdk main" | \
     sudo tee /etc/apt/sources.list.d/google-cloud-sdk.list
   sudo apt-get update
   sudo apt-get install -y google-cloud-cli
   ```
2. The CLI is now installed. You will authenticate it in Section 6 after the
   service account key is uploaded.

### 5.4 Install the Cloud SQL Auth Proxy

1. While connected to the VM over SSH, run:
   ```bash
   curl -o cloud-sql-proxy https://dl.google.com/cloudsql/cloud_sql_proxy.linux.amd64
   chmod +x cloud-sql-proxy
   sudo mv cloud-sql-proxy /usr/local/bin/
   ```
2. Create a systemd service file `/etc/systemd/system/cloud-sql-proxy.service`:
   ```bash
   sudo tee /etc/systemd/system/cloud-sql-proxy.service > /dev/null <<'SERVICE'
   [Unit]
   Description=Cloud SQL Proxy
   After=network.target

   [Service]
   ExecStart=/usr/local/bin/cloud-sql-proxy -instances=<PROJECT>:<REGION>:nexacore-postgres=tcp:5432
   Restart=always

   [Install]
   WantedBy=multi-user.target
   SERVICE
   ```
   Replace `<PROJECT>` and `<REGION>` with your project ID and region.
3. Reload systemd and start the service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now cloud-sql-proxy
   sudo systemctl status cloud-sql-proxy
   ```
   Confirm the status shows **active (running)**.

4. Store the service configuration path in Bitwarden for reference.

---

## 6. Harden access with service accounts (30 minutes)

1. In the Google Cloud console, go to **IAM & Admin → Service Accounts**.
2. Click **Create Service Account**.
3. Provide:
   - **Name**: `nexacore-backend-sa`
   - **ID** auto-fills; click **Create and continue**.
4. Grant roles:
   - `Cloud SQL Client`
   - `Secret Manager Secret Accessor`
5. Click **Done**.
6. Click the new service account → **Keys** tab → **Add key → Create new key → JSON**.
7. Download the JSON file and store it securely (Bitwarden → Attachments).
8. Upload the key to your VM (from your local terminal):
   ```bash
   gcloud compute scp /path/to/key.json nexacore-backend:~/service-account.json --zone=<ZONE>
   ```
9. On the VM SSH session, move the key to a protected location:
   ```bash
   sudo mkdir -p /etc/nexacore
   sudo mv ~/service-account.json /etc/nexacore/service-account.json
   sudo chmod 600 /etc/nexacore/service-account.json
   ```
10. Configure the Cloud SQL Proxy service to use the key by editing
    `/etc/systemd/system/cloud-sql-proxy.service` and adding at the end of the
    `ExecStart` line:
    ` --credentials-file=/etc/nexacore/service-account.json`
11. Reload and restart the service:
    ```bash
    sudo systemctl daemon-reload
    sudo systemctl restart cloud-sql-proxy
    ```
12. Confirm status again with `sudo systemctl status cloud-sql-proxy`.
13. Authenticate the Google Cloud CLI on the VM so deployment scripts can read
    secrets:
    ```bash
    gcloud auth activate-service-account --key-file=/etc/nexacore/service-account.json
    gcloud config set project <PROJECT_ID>
    ```

---

## 7. Scaffold the backend FastAPI project (90 minutes)

### 7.1 Create project structure locally

1. In your repository root (locally), create folders:
   ```bash
   mkdir -p backend/app backend/alembic backend/tests
   ```
2. Add an empty `__init__.py` so Python treats the folder as a package:
   ```bash
   touch backend/app/__init__.py
   ```
3. Create `backend/pyproject.toml` with dependencies:
```toml
[project]
name = "nexacore-backend"
version = "0.1.0"
requires-python = ">=3.11"

[project.dependencies]
fastapi = "^0.110"
uvicorn = {extras = ["standard"], version = "^0.29"}
sqlalchemy = "^2.0"
asyncpg = "^0.29"
alembic = "^1.13"
pydantic = "^2.5"
python-dotenv = "^1.0"
httpx = "^0.27"
passlib = "^1.7"
pyjwt = "^2.8"

[build-system]
requires = ["setuptools", "wheel"]
build-backend = "setuptools.build_meta"
```
4. Create `backend/app/main.py` with a starter FastAPI app and health check.
5. Copy existing SQLAlchemy models from `nexacore_erp/database/models` into
   `backend/app/models`. Keep the `account_id` field for multi-tenancy.

### 7.2 Configure environment management

1. Create `.env` in the `backend` folder:
   ```dotenv
   DATABASE_URL=postgresql+asyncpg://nexacore_app:<password>@127.0.0.1:5432/nexacore
   SECRET_KEY=replace-me
   ```
   When running on the VM, the Cloud SQL Proxy listens on `127.0.0.1:5432`, so
   this matches.
2. Add `.env` to `.gitignore` to avoid committing secrets:
   ```bash
   echo ".env" >> backend/.gitignore
   ```

### 7.3 Initialize Alembic migrations

1. Activate your virtual environment (`source .venv/bin/activate`).
2. Install dependencies:
   ```bash
   pip install -e backend
   ```
3. Initialize Alembic:
   ```bash
   cd backend
   alembic init alembic
   ```
4. Edit `backend/alembic/env.py` to import your models and read `DATABASE_URL`
   from environment variables.
5. Generate the first migration:
   ```bash
   alembic revision --autogenerate -m "create base tables"
   alembic upgrade head
   ```
6. Confirm tables appear in Cloud SQL by connecting via the Cloud SQL proxy or
   `psql` from your local machine.

### 7.4 Implement authentication and tenant middleware

1. Create `backend/app/auth.py` with routes for registration and login.
2. Store hashed passwords using `passlib.context.CryptContext`.
3. Create dependency `get_current_user()` that reads a JWT from the
   `Authorization: Bearer <token>` header.
4. Inside `backend/app/dependencies.py`, enforce `account_id` scoping for all
   queries (e.g., `session.execute(select(Employee).filter_by(account_id=user.account_id))`).

### 7.5 Build the first module endpoint (Employees)

1. Create `backend/app/routers/employees.py` with `APIRouter`.
2. Add endpoints:
   - `GET /employees/` → returns a list of employees for the tenant.
   - `POST /employees/` → creates a new employee.
3. Register the router in `backend/app/main.py`.
4. Write tests in `backend/tests/test_employees.py` using `pytest` and `httpx.AsyncClient`.
5. Run tests locally: `pytest backend/tests`.

### 7.6 Containerize the backend

1. Create `backend/Dockerfile` (this is the exact file already committed in the repo):
   ```dockerfile
   # syntax=docker/dockerfile:1
   FROM python:3.11-slim AS runtime

   ENV PYTHONDONTWRITEBYTECODE=1 \
       PYTHONUNBUFFERED=1

   WORKDIR /app

   # Install system dependencies required by asyncpg and uvicorn
   RUN apt-get update \
       && apt-get install -y --no-install-recommends build-essential libpq-dev \
       && rm -rf /var/lib/apt/lists/*

   COPY pyproject.toml ./
   COPY app app

   RUN pip install --upgrade pip \
       && pip install --no-cache-dir .

   COPY alembic alembic
   COPY alembic.ini ./

   ENV PORT=8000
   EXPOSE 8000

   CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
   ```
2. Copy `backend/.env.example` to `backend/.env` and edit secrets for your environment. The Docker services read those values automatically.
3. Launch the stack locally with Docker Compose (PostgreSQL and the API run together):
   ```bash
   cd backend
   docker compose up --build
   ```
4. When the logs show `Application startup complete.`, open http://127.0.0.1:8000/docs to confirm the API works.
5. Stop the containers with `Ctrl+C`, then run `docker compose down` to cleanly tear them down.

---

## 8. Deploy the backend to the VM (45 minutes)

### 8.1 Push image to Artifact Registry

1. In Google Cloud, go to **Artifact Registry → Repositories**.
2. Click **Create Repository**.
   - Name: `nexacore-backend`
   - Format: `Docker`
   - Location type: `Region`
   - Region: same as VM
   - Click **Create**.
3. Authenticate Docker locally with gcloud:
   ```bash
   gcloud auth login
   gcloud config set project <PROJECT_ID>
   gcloud auth configure-docker <REGION>-docker.pkg.dev
   ```
4. Build and push the image:
   ```bash
   docker build -t <REGION>-docker.pkg.dev/<PROJECT_ID>/nexacore-backend/api:0.1.0 backend
   docker push <REGION>-docker.pkg.dev/<PROJECT_ID>/nexacore-backend/api:0.1.0
   ```

### 8.2 Create a deployment script on the VM

1. SSH into the VM.
2. Create `/home/<user>/deploy.sh`:
   ```bash
   #!/bin/bash
   set -euo pipefail

   IMAGE="$1"
   CONTAINER_NAME=nexacore-backend

   docker pull "$IMAGE"
   docker stop "$CONTAINER_NAME" 2>/dev/null || true
   docker rm "$CONTAINER_NAME" 2>/dev/null || true

   docker run -d \
     --name "$CONTAINER_NAME" \
     --restart unless-stopped \
     -p 443:8000 \
     --env PORT=8000 \
     --env DATABASE_URL=$(gcloud secrets versions access latest --secret=DATABASE_URL) \
     --env JWT_SECRET=$(gcloud secrets versions access latest --secret=JWT_SECRET) \
     "$IMAGE"
   ```
3. Make it executable: `chmod +x deploy.sh`.
4. Test the script: `./deploy.sh <REGION>-docker.pkg.dev/<PROJECT_ID>/nexacore-backend/api:0.1.0`.
5. Verify the container is running: `docker ps`.
6. From your local machine, run `curl https://<STATIC_IP>/health` (or open in
   browser). Configure HTTPS via an HTTPS load balancer or Caddy/nginx inside
   the container for production-grade TLS.

---

## 9. Wire the Qt desktop client to the new backend (90 minutes)

### 9.1 Create an API service layer

1. Inside the existing `nexacore_erp` package, create `services/api_client.py`.
2. Implement functions using `httpx.AsyncClient` for login, listing employees,
   etc.
3. Store the base URL in a config file (`config.json`) and add logic to fetch it
   from environment variables.

### 9.2 Replace SQLite interactions

1. Search the repo for `sqlite` references (`rg "sqlite"`).
2. For each DAO (e.g., `nexacore_erp/database/employee_repository.py`):
   - Replace direct SQLAlchemy session usage with calls to the API client.
   - Handle authentication tokens by storing them in memory when the user logs
     in.
3. For read-heavy screens, call the backend and populate Qt models from the JSON
   responses.

### 9.3 Handle real-time updates

1. Add a dependency to `PyQt6.QtWebSockets` or install the `websockets` library.
2. Create a WebSocket manager class that connects to `wss://<STATIC_IP>/ws`.
3. When the backend broadcasts events like `employee.created`, update the
   relevant table models.
4. Include reconnection logic so the client automatically reconnects if the
   connection drops.

### 9.4 Implement maintenance and version checks

1. On app startup, call `/status`. If it returns `{"maintenance": true}`, show a
   modal dialog and disable navigation.
2. Include the client version in the login request. If the backend responds with
   `426 Upgrade Required`, open the updater (next section).

---

## 10. Build installers and an auto-updater (60 minutes)

### 10.1 Create a PyInstaller spec

1. Activate your virtual environment.
2. Install PyInstaller: `pip install pyinstaller`.
3. Create `nexacore.spec`:
   ```python
   block_cipher = None

   a = Analysis([
       'nexacore_launcher.py',
   ],
   ...)
   ```
   Customize the spec to include Qt resources (`binaries`, `datas`).
4. Run `pyinstaller nexacore.spec`.
5. Test the executable on a clean Windows VM. Document the steps (copy zipped
   installer, run it, verify login screen).

### 10.2 Develop the updater

1. Create `updater/manifest.json` hosted on GitHub Pages or Google Cloud
   Storage. Structure:
   ```json
   { "latest_version": "1.0.0", "download_url": "https://storage.googleapis.com/<bucket>/NexaCore-1.0.0.exe" }
   ```
2. Write `nexacore_launcher.py` that:
   - Fetches the manifest (`requests.get`).
   - Compares `latest_version` to local version stored in a file.
   - Downloads the installer if a newer version exists (use `requests` with
     streaming to display progress).
   - Launches the main app.
3. Upload installers to a Google Cloud Storage bucket:
   - In console: **Cloud Storage → Buckets → Create**.
   - Name: `nexacore-installers-<unique-id>`.
   - Location type: `Region`, choose same region.
   - Access control: `Uniform`.
   - Upload your `.exe` via the UI (`Upload Files`).
4. Make the download object public if distributing widely (`⋮ → Edit permissions
   → Add principal → allUsers → Storage Object Viewer`).

---

## 11. Automate with GitHub Actions (45 minutes)

### 11.1 CI workflow

1. In your repo, create `.github/workflows/ci.yml`:
   ```yaml
   name: CI

   on:
     push:
       branches: [ main ]
     pull_request:
       branches: [ main ]

   jobs:
     test:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - uses: actions/setup-python@v5
           with:
             python-version: '3.11'
         - name: Install backend
           run: |
             python -m pip install --upgrade pip
             pip install -e backend
             pip install pytest
         - name: Run tests
           run: pytest backend/tests
   ```
2. Commit and push. Verify the workflow appears under **GitHub → Actions** and
   completes successfully.

### 11.2 Deployment workflow

1. Create `.github/workflows/deploy.yml`:
   ```yaml
   name: Deploy Backend

   on:
     push:
       tags:
         - 'backend-v*'

   jobs:
     deploy:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - uses: google-github-actions/setup-gcloud@v2
           with:
             project_id: ${{ secrets.GCP_PROJECT_ID }}
             service_account_key: ${{ secrets.GCP_SA_KEY }}
         - name: Build and push image
           run: |
             gcloud auth configure-docker <REGION>-docker.pkg.dev
             docker build -t <REGION>-docker.pkg.dev/${{ secrets.GCP_PROJECT_ID }}/nexacore-backend/api:${GITHUB_REF_NAME} backend
             docker push <REGION>-docker.pkg.dev/${{ secrets.GCP_PROJECT_ID }}/nexacore-backend/api:${GITHUB_REF_NAME}
         - name: Trigger remote deploy script
           run: |
             gcloud compute ssh nexacore-backend --zone=<ZONE> --command "~/deploy.sh <REGION>-docker.pkg.dev/${{ secrets.GCP_PROJECT_ID }}/nexacore-backend/api:${GITHUB_REF_NAME}"
   ```
2. Store the required secrets in the GitHub repository (`Settings → Secrets and
   variables → Actions → New repository secret`).
   - `GCP_PROJECT_ID`
   - `GCP_SA_KEY` (paste the JSON from a dedicated deployment service account).
3. Create your first deployment tag: `git tag backend-v0.1.0 && git push origin backend-v0.1.0`.
4. Watch the workflow run and confirm the backend redeploys.

---

## 12. Multi-tenant data handling (60 minutes)

### 12.1 Tenant onboarding flow

1. Add a `/tenants` endpoint in the backend to create new companies:
   - Request body: company name, admin email, timezone.
   - Backend generates an `account_id`, creates tenant records, sends admin an
     invite email.
2. Store the tenant selection in the client’s login screen (dropdown or input).
3. After login, keep `account_id` inside the JWT payload. All backend queries
   use it to filter data.

### 12.2 Database enforcement

1. In SQLAlchemy models, ensure every table includes `account_id` with an index.
2. Add SQLAlchemy `session_events.before_flush` hooks to enforce that any new
   object automatically inherits the current tenant ID.
3. Create Postgres Row-Level Security (RLS) policies once comfortable:
   ```sql
   ALTER TABLE employees ENABLE ROW LEVEL SECURITY;
   CREATE POLICY tenant_isolation ON employees
     USING (account_id = current_setting('app.current_account')::uuid);
   ```
4. In the backend, set `SET app.current_account = '<uuid>'` at the start of each
   request.

### 12.3 Bulk updates across tenants

1. Write Alembic scripts so they are idempotent.
2. Create a management command `python -m backend.manage run-migration --all-tenants`:
   - Fetch list of tenants from the database.
   - Loop through each and apply necessary data fixes.
3. Log results to a table `migration_log` with columns `migration_name`,
   `tenant_id`, `status`, `timestamp`.

---

## 13. Maintenance windows and observability (45 minutes)

### 13.1 Maintenance toggle

1. Add a table `system_status` with columns `id`, `maintenance_mode`,
   `message`.
2. Create admin endpoints:
   - `GET /admin/status`
   - `POST /admin/status` to toggle maintenance mode.
3. Update the client to display the `message` when maintenance is active.

### 13.2 Logging and monitoring

1. Inside the backend container, configure structured logging using Python’s
   `logging` module with JSON output. Send logs to stdout so GCP captures them
   in **Cloud Logging**.
2. In the Google Cloud console, open **Logging → Logs Explorer** to view logs.
3. Set up an uptime check:
   - Go to **Monitoring → Uptime checks**.
   - Click **Create uptime check**.
   - Target: HTTPS → use your static IP or domain.
   - Set email/SMS notifications.
4. Schedule monthly tasks:
   - Test restoring a Cloud SQL backup (use the **Create clone** feature).
   - Review VM and database metrics under **Monitoring → Dashboards**.

---

## 14. Suggested pacing roadmap (4 weeks)

| Week | Focus | Concrete Outcomes |
|------|-------|-------------------|
| 1 | Sections 0–5 | Project organized, GCP project live, Cloud SQL + VM ready. |
| 2 | Sections 6–8 | Backend scaffolding complete, first API deployed. |
| 3 | Sections 9–10 | Desktop client consuming API, installer + updater prototype. |
| 4 | Sections 11–13 | Automated deployments, multi-tenant enforcement, monitoring in place. |

Check off items in Bitwarden or a project board as you complete them. Taking
notes after each session will accelerate future maintenance work.

---

## 15. Additional learning resources

* **Google Cloud Skills Boost** – guided labs for Compute Engine, Cloud SQL, and
  networking.
* **FastAPI Tutorial** – https://fastapi.tiangolo.com/tutorial/
* **SQLAlchemy ORM Tutorial** – https://docs.sqlalchemy.org/en/20/tutorial/
* **PyInstaller Manual** – https://pyinstaller.org/en/stable/
* **GitHub Actions Documentation** – https://docs.github.com/actions

Keep this manual open as you work. If you discover variations that better fit
your workflow, append them to the doc so future you (and teammates) benefit from
those lessons.
