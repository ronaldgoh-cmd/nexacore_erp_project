"""Helpers for planning and storing cloud integration details."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Iterable, List

from .database import SessionLocal
from .models import CloudSettings


@dataclass
class CloudEnvironment:
    """Represents the desired remote environment configuration."""

    provider: str = "digitalocean"
    region: str = ""
    spaces_region: str = ""
    spaces_bucket: str = ""
    control_panel_url: str = "https://cloud.digitalocean.com"
    api_endpoint: str = ""
    api_token: str = ""
    last_synced_at: datetime | None = None

    @property
    def is_configured(self) -> bool:
        return bool(self.api_token and (self.api_endpoint or self.region))


@dataclass
class ProvisioningStep:
    """Simple description of a step required for going online."""

    title: str
    details: str
    reference: str | None = None


def load_cloud_environment(account_id: str = "default") -> CloudEnvironment:
    """Return saved cloud configuration or defaults."""

    with SessionLocal() as session:
        row = session.query(CloudSettings).filter(CloudSettings.account_id == account_id).first()
        if not row:
            return CloudEnvironment()
        return CloudEnvironment(
            provider=row.provider,
            region=row.region,
            spaces_region=row.spaces_region,
            spaces_bucket=row.spaces_bucket,
            control_panel_url=row.control_panel_url or "https://cloud.digitalocean.com",
            api_endpoint=row.api_endpoint,
            api_token=row.api_token,
            last_synced_at=row.last_synced_at,
        )


def save_cloud_environment(env: CloudEnvironment, account_id: str = "default") -> None:
    """Persist the cloud configuration."""

    with SessionLocal() as session:
        row = session.query(CloudSettings).filter(CloudSettings.account_id == account_id).first()
        payload = asdict(env)
        if row is None:
            row = CloudSettings(account_id=account_id)
            session.add(row)
        row.provider = payload.get("provider", row.provider)
        row.region = payload.get("region", row.region)
        row.spaces_region = payload.get("spaces_region", row.spaces_region)
        row.spaces_bucket = payload.get("spaces_bucket", row.spaces_bucket)
        row.control_panel_url = payload.get("control_panel_url", row.control_panel_url)
        row.api_endpoint = payload.get("api_endpoint", row.api_endpoint)
        row.api_token = payload.get("api_token", row.api_token)
        row.last_synced_at = payload.get("last_synced_at", row.last_synced_at)
        session.commit()


def digitalocean_provisioning_plan(env: CloudEnvironment | None = None) -> List[ProvisioningStep]:
    """High-level provisioning steps for DigitalOcean deployment."""

    env = env or CloudEnvironment()
    base_ref = "https://docs.digitalocean.com"
    steps: List[ProvisioningStep] = [
        ProvisioningStep(
            title="Create a DigitalOcean project",
            details="Organise droplets, managed databases and Spaces under a dedicated project for the ERP stack.",
            reference=f"{base_ref}/products/projects/",
        ),
        ProvisioningStep(
            title="Generate an API token",
            details="Create a Personal Access Token with write permissions so the ERP can provision and sync data.",
            reference=f"{base_ref}/reference/api/create-personal-access-token/",
        ),
        ProvisioningStep(
            title="Provision a managed PostgreSQL database",
            details="Use DigitalOcean Managed Databases for the shared production datastore. Note the connection string.",
            reference=f"{base_ref}/products/databases/postgresql/how-to/create/",
        ),
        ProvisioningStep(
            title="Create a Spaces bucket",
            details="Configure a Spaces bucket for document uploads and media that need to sync across clients.",
            reference=f"{base_ref}/products/spaces/",
        ),
        ProvisioningStep(
            title="Set up a droplet or App Platform service",
            details="Host the API/synchronisation service that brokers communication between desktop clients and the cloud.",
            reference=f"{base_ref}/products/app-platform/",
        ),
        ProvisioningStep(
            title="Whitelist trusted IP addresses",
            details="Restrict database and Spaces access to the droplet/App Platform IPs and VPN endpoints.",
            reference=f"{base_ref}/products/networking/how-to/configure-firewalls/",
        ),
    ]

    if env.is_configured:
        steps.append(
            ProvisioningStep(
                title="Schedule synchronisation jobs",
                details="Automate exports/imports between the local SQLite stores and the cloud database once credentials are stored.",
            )
        )
    else:
        steps.append(
            ProvisioningStep(
                title="Enter API credentials inside NexaCore",
                details="Capture the API endpoint, Spaces bucket and token so the desktop client can begin syncing when ready.",
            )
        )
    return steps


def render_plan_summary(steps: Iterable[ProvisioningStep]) -> str:
    """Return a bullet list representation suitable for tooltips or logs."""

    lines = []
    for step in steps:
        ref = f" (ref: {step.reference})" if step.reference else ""
        lines.append(f"• {step.title}{ref}\n  {step.details}")
    return "\n".join(lines)


def cloud_status_summary(account_id: str = "default") -> str:
    """Quick summary string for status bars or diagnostics."""

    env = load_cloud_environment(account_id)
    if env.is_configured:
        when = env.last_synced_at.isoformat() if env.last_synced_at else "never"
        return (
            "DigitalOcean integration configured — "
            f"region: {env.region or 'unspecified'}, spaces: {env.spaces_bucket or 'unset'}, last sync: {when}"
        )
    return "DigitalOcean integration not configured. Configure API token and regions to begin syncing."
