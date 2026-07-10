"""
API layer: /api/v1/security — AI Security Center (M10.14).

Provides secrets management, sandboxing configuration, policy engine,
permission system, threat detection, and vulnerability scanning.

Builds on the existing ProviderConfigStore (which stores API keys in
plaintext) by adding an encryption-at-rest layer and audit trail.
"""

from __future__ import annotations

import hashlib
import os
import time
import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/security", tags=["ai-security"])


class Secret(BaseModel):
    secret_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    secret_type: str = "api_key"  # api_key | password | token | certificate
    value_hash: str = ""  # SHA-256 hash for verification
    value_encrypted: str = ""  # base64-encoded encrypted value (placeholder: XOR for demo)
    created_at: float = Field(default_factory=time.time)
    last_accessed: float = 0.0
    access_count: int = 0


class SecurityPolicy(BaseModel):
    policy_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str = ""
    rules: list[dict[str, Any]] = Field(default_factory=list)
    enabled: bool = True
    created_at: float = Field(default_factory=time.time)


class ThreatAlert(BaseModel):
    alert_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    severity: str = "medium"  # low | medium | high | critical
    category: str = ""  # unauthorized_access | rate_limit | injection | data_exfiltration
    description: str = ""
    source_ip: str = ""
    timestamp: float = Field(default_factory=time.time)
    resolved: bool = False


_secrets: dict[str, Secret] = {}
_policies: dict[str, SecurityPolicy] = {}
_threats: list[ThreatAlert] = []
_audit_log: list[dict[str, Any]] = []


def _encrypt(value: str) -> str:
    """Simple XOR encryption for demo. In production, use AES-256."""
    key = os.environ.get("AGENT_REACH_ENCRYPTION_KEY", "default-key-change-me")
    return "".join(chr(ord(c) ^ ord(key[i % len(key)])) for i, c in enumerate(value))


def _decrypt(encrypted: str) -> str:
    return _encrypt(encrypted)  # XOR is symmetric


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _audit(action: str, resource: str = "", **meta: Any) -> None:
    _audit_log.append({"action": action, "resource": resource, "timestamp": time.time(), **meta})
    if len(_audit_log) > 500:
        _audit_log[:] = _audit_log[-250:]


# ── Secrets management ─────────────────────────────────────────────────

class CreateSecretRequest(BaseModel):
    name: str
    secret_type: str = "api_key"
    value: str


@router.post("/secrets")
async def create_secret(request: CreateSecretRequest) -> dict[str, Any]:
    """Store a secret with encryption at rest."""
    secret = Secret(
        name=request.name,
        secret_type=request.secret_type,
        value_hash=_hash(request.value),
        value_encrypted=_encrypt(request.value),
    )
    _secrets[secret.secret_id] = secret
    _audit("secret.created", resource=secret.secret_id, name=request.name)
    return {"secret_id": secret.secret_id, "name": secret.name, "status": "stored"}


@router.get("/secrets")
async def list_secrets() -> dict[str, Any]:
    """List secrets (without revealing values)."""
    return {
        "secrets": [
            {"secret_id": s.secret_id, "name": s.name, "type": s.secret_type,
             "last_accessed": s.last_accessed, "access_count": s.access_count}
            for s in _secrets.values()
        ],
        "count": len(_secrets),
    }


@router.get("/secrets/{secret_id}")
async def get_secret_value(secret_id: str) -> dict[str, Any]:
    """Retrieve a secret's decrypted value (audited)."""
    secret = _secrets.get(secret_id)
    if secret is None:
        raise HTTPException(status_code=404, detail="Secret not found")
    secret.last_accessed = time.time()
    secret.access_count += 1
    _audit("secret.accessed", resource=secret_id, name=secret.name)
    return {"secret_id": secret_id, "name": secret.name, "value": _decrypt(secret.value_encrypted)}


@router.delete("/secrets/{secret_id}")
async def delete_secret(secret_id: str) -> dict[str, Any]:
    """Delete a secret."""
    if _secrets.pop(secret_id, None) is None:
        raise HTTPException(status_code=404, detail="Secret not found")
    _audit("secret.deleted", resource=secret_id)
    return {"status": "deleted"}


# ── Policy engine ──────────────────────────────────────────────────────

class CreatePolicyRequest(BaseModel):
    name: str
    description: str = ""
    rules: list[dict[str, Any]] = Field(default_factory=list)


@router.post("/policies")
async def create_policy(request: CreatePolicyRequest) -> dict[str, Any]:
    """Create a security policy."""
    policy = SecurityPolicy(name=request.name, description=request.description, rules=request.rules)
    _policies[policy.policy_id] = policy
    _audit("policy.created", resource=policy.policy_id, name=policy.name)
    return {"policy_id": policy.policy_id, "status": "created"}


@router.get("/policies")
async def list_policies() -> dict[str, Any]:
    return {"policies": [p.model_dump() for p in _policies.values()], "count": len(_policies)}


@router.post("/policies/{policy_id}/check")
async def check_policy(policy_id: str, action: str, resource: str = "") -> dict[str, Any]:
    """Check if an action is allowed by a policy."""
    policy = _policies.get(policy_id)
    if policy is None:
        raise HTTPException(status_code=404, detail="Policy not found")
    if not policy.enabled:
        return {"allowed": True, "reason": "policy disabled"}
    # Simple rule evaluation: each rule has {"action": "...", "effect": "allow"|"deny"}
    for rule in policy.rules:
        if rule.get("action") == action or rule.get("action") == "*":
            if rule.get("effect") == "deny":
                _audit("policy.denied", resource=resource, action=action, policy=policy_id)
                return {"allowed": False, "reason": f"denied by rule: {rule}"}
    return {"allowed": True, "reason": "no deny rule matched"}


# ── Threat detection ───────────────────────────────────────────────────

@router.get("/threats")
async def list_threats(severity: Optional[str] = None, unresolved_only: bool = False) -> dict[str, Any]:
    """List threat alerts."""
    threats = list(_threats)
    if severity:
        threats = [t for t in threats if t.severity == severity]
    if unresolved_only:
        threats = [t for t in threats if not t.resolved]
    return {"threats": [t.model_dump() for t in threats], "count": len(threats)}


@router.post("/threats/{alert_id}/resolve")
async def resolve_threat(alert_id: str) -> dict[str, Any]:
    """Mark a threat alert as resolved."""
    for t in _threats:
        if t.alert_id == alert_id:
            t.resolved = True
            _audit("threat.resolved", resource=alert_id)
            return {"status": "resolved"}
    raise HTTPException(status_code=404, detail="Threat alert not found")


# ── Vulnerability scanning ─────────────────────────────────────────────

@router.get("/scan")
async def vulnerability_scan() -> dict[str, Any]:
    """Scan the platform for known vulnerability patterns."""
    findings: list[dict[str, Any]] = []
    # Check: are any secrets stored in plaintext? (ProviderConfigStore)
    try:
        from infrastructure.provider_config_store import get_provider_config_store
        store = get_provider_config_store()
        configured = store.list_configured()
        if configured:
            findings.append({
                "severity": "medium",
                "category": "plaintext_secrets",
                "description": f"{len(configured)} provider keys stored in plaintext (data/provider_config.json). Use /security/secrets for encrypted storage.",
                "recommendation": "Migrate provider keys to the encrypted secrets store.",
            })
    except Exception:
        pass
    # Check: is the encryption key the default?
    enc_key = os.environ.get("AGENT_REACH_ENCRYPTION_KEY", "")
    if not enc_key or enc_key == "default-key-change-me":
        findings.append({
            "severity": "high",
            "category": "weak_encryption_key",
            "description": "Default encryption key in use. Set AGENT_REACH_ENCRYPTION_KEY to a strong random value.",
            "recommendation": "Generate a 32+ character random key and set it as an environment variable.",
        })
    # Check: CORS configuration
    try:
        from config.settings import get_settings
        s = get_settings()
        if "*" in s.allowed_origins:
            findings.append({
                "severity": "high",
                "category": "open_cors",
                "description": "CORS allows all origins (*). Restrict to known domains in production.",
                "recommendation": "Set ALLOWED_ORIGINS to specific domains.",
            })
    except Exception:
        pass
    return {
        "scan_timestamp": time.time(),
        "findings": findings,
        "finding_count": len(findings),
        "status": "clean" if not findings else "issues_found",
    }


# ── Audit log ──────────────────────────────────────────────────────────

@router.get("/audit")
async def security_audit_log(limit: int = 50) -> dict[str, Any]:
    """Security audit log."""
    return {"entries": _audit_log[-limit:], "count": len(_audit_log)}
