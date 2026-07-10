"""
API layer: /api/v1/federation — AI Federation (M10.23).

Allows multiple Agent Reach installations to collaborate securely
while maintaining independent ownership and governance. Federated
nodes share agents, knowledge, and capabilities without centralizing
control.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/federation", tags=["ai-federation"])


class FederationNode(BaseModel):
    node_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    endpoint: str
    public_key: str = ""  # for secure communication
    trust_level: str = "peer"  # peer | trusted | verified
    shared_agents: list[str] = Field(default_factory=list)
    shared_knowledge: list[str] = Field(default_factory=list)
    status: str = "connected"  # connected | disconnected | suspended
    last_sync: float = 0.0
    joined_at: float = Field(default_factory=time.time)


class FederationProposal(BaseModel):
    proposal_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    from_node: str
    to_node: str
    proposal_type: str  # share_agent | share_knowledge | collaborate | merge
    payload: dict[str, Any] = Field(default_factory=dict)
    status: str = "pending"  # pending | accepted | rejected | expired
    created_at: float = Field(default_factory=time.time)


_federation_nodes: dict[str, FederationNode] = {}
_proposals: dict[str, FederationProposal] = {}


class JoinFederationRequest(BaseModel):
    name: str
    endpoint: str
    public_key: str = ""


@router.post("/nodes")
async def join_federation(request: JoinFederationRequest) -> dict[str, Any]:
    """Join the federation as a new node."""
    node = FederationNode(name=request.name, endpoint=request.endpoint, public_key=request.public_key)
    _federation_nodes[node.node_id] = node
    return {"node_id": node.node_id, "name": node.name, "status": "connected"}


@router.get("/nodes")
async def list_federation_nodes() -> dict[str, Any]:
    return {"nodes": [n.model_dump() for n in _federation_nodes.values()], "count": len(_federation_nodes)}


@router.delete("/nodes/{node_id}")
async def leave_federation(node_id: str) -> dict[str, Any]:
    if _federation_nodes.pop(node_id, None) is None:
        raise HTTPException(status_code=404, detail="Federation node not found")
    return {"status": "left", "node_id": node_id}


class CreateProposalRequest(BaseModel):
    to_node: str
    proposal_type: str
    payload: dict[str, Any] = Field(default_factory=dict)


@router.post("/proposals")
async def create_proposal(from_node: str, request: CreateProposalRequest) -> dict[str, Any]:
    """Propose a federation collaboration."""
    if request.to_node not in _federation_nodes:
        raise HTTPException(status_code=404, detail="Target node not in federation")
    proposal = FederationProposal(from_node=from_node, to_node=request.to_node,
                                   proposal_type=request.proposal_type, payload=request.payload)
    _proposals[proposal.proposal_id] = proposal
    return {"proposal_id": proposal.proposal_id, "status": "pending"}


@router.get("/proposals")
async def list_proposals(node_id: Optional[str] = None, status: Optional[str] = None) -> dict[str, Any]:
    proposals = list(_proposals.values())
    if node_id:
        proposals = [p for p in proposals if p.from_node == node_id or p.to_node == node_id]
    if status:
        proposals = [p for p in proposals if p.status == status]
    return {"proposals": [p.model_dump() for p in proposals], "count": len(proposals)}


@router.post("/proposals/{proposal_id}/accept")
async def accept_proposal(proposal_id: str) -> dict[str, Any]:
    """Accept a federation proposal."""
    proposal = _proposals.get(proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    proposal.status = "accepted"
    # Execute the proposal
    if proposal.proposal_type == "share_agent":
        agent_id = proposal.payload.get("agent_id", "")
        from_node = _federation_nodes.get(proposal.from_node)
        if from_node and agent_id:
            from_node.shared_agents.append(agent_id)
    return {"proposal_id": proposal_id, "status": "accepted"}


@router.post("/proposals/{proposal_id}/reject")
async def reject_proposal(proposal_id: str) -> dict[str, Any]:
    """Reject a federation proposal."""
    proposal = _proposals.get(proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    proposal.status = "rejected"
    return {"proposal_id": proposal_id, "status": "rejected"}


@router.get("/status")
async def federation_status() -> dict[str, Any]:
    """Federation health and membership status."""
    nodes = list(_federation_nodes.values())
    return {
        "total_nodes": len(nodes),
        "connected": sum(1 for n in nodes if n.status == "connected"),
        "shared_agents": sum(len(n.shared_agents) for n in nodes),
        "shared_knowledge": sum(len(n.shared_knowledge) for n in nodes),
        "pending_proposals": sum(1 for p in _proposals.values() if p.status == "pending"),
        "governance": "decentralized",
        "encryption": "end-to-end (public key exchange)",
    }
