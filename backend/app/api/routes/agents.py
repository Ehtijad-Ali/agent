"""Agent endpoints (brief §2, §3, and the Refinement Index in §8).

Agents are created disabled. Enabling one is a separate, explicit call, so
nothing starts acting as a side effect of being configured.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import ActivityEntry, Agent, AgentOutput, BacklinkAudit, BacklinkCheck
from app.schemas.agent import (
    AgentCreate,
    AgentOut,
    AgentOutputOut,
    AgentOutputPage,
    AgentUpdate,
    BacklinkAuditOut,
    BacklinkCheckOut,
    BacklinkRules,
    ContentRules,
    EngagementRules,
    PublishRequest,
    RefinementIndex,
)
from app.services import backlink_service
from app.services.content_service import ContentError, available_cities, generate_output
from app.services.refinement_service import compute

router = APIRouter(prefix="/agents", tags=["agents"])
logger = logging.getLogger("signal.agents")

ACTOR = "you"


def _validate_rules(agent_type: str, rules: dict) -> dict:
    """Check the rules against the shape for this agent type.

    The column is JSON so each type can differ, but "flexible" must not mean
    "unchecked" -- a content agent with a typo in contactEmail would otherwise
    fail only when it tried to generate.
    """
    model = {
        "engagement": EngagementRules,
        "content": ContentRules,
        "backlink_audit": BacklinkRules,
    }[agent_type]
    try:
        return model.model_validate(rules).model_dump(by_alias=True)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid rules for a {agent_type} agent: {exc}",
        ) from exc


def _get_or_404(db: Session, agent_id: str) -> Agent:
    agent = db.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"No agent with id {agent_id}."
        )
    return agent


def _out(agent: Agent) -> AgentOut:
    return AgentOut(
        id=agent.id,
        name=agent.name,
        agent_type=agent.agent_type,
        description=agent.description,
        enabled=bool(agent.enabled),
        rules=agent.rules or {},
        created_at=agent.created_at,
        updated_at=agent.updated_at,
    )


@router.get("", response_model=list[AgentOut])
def list_agents(
    db: Session = Depends(get_db),
    agent_type: str | None = Query(None, alias="type"),
    enabled: bool | None = Query(None),
) -> list[AgentOut]:
    stmt = select(Agent).order_by(Agent.created_at.desc())
    if agent_type:
        stmt = stmt.where(Agent.agent_type == agent_type)
    if enabled is not None:
        stmt = stmt.where(Agent.enabled == (1 if enabled else 0))
    return [_out(a) for a in db.execute(stmt).scalars().all()]


@router.get("/types")
def list_types() -> dict:
    """The agent types that exist, with the rule shape each expects."""
    return {
        "types": [
            {
                "type": "engagement",
                "label": "Monitor and engage",
                "description": (
                    "Watches connected platforms, scores leads and drafts "
                    "replies for human approval."
                ),
                "ruleSchema": EngagementRules.model_json_schema(by_alias=True),
            },
            {
                "type": "content",
                "label": "Generate ad content",
                "description": (
                    "Generates per-city classified-ad copy for manual posting. "
                    "Does not submit anything -- see docs/feasibility.md."
                ),
                "ruleSchema": ContentRules.model_json_schema(by_alias=True),
            },
            {
                "type": "backlink_audit",
                "label": "Audit backlinks",
                "description": (
                    "Reads page URLs from a Google Sheet, opens each page and "
                    "checks whether its link to your site is dofollow. Results "
                    "download as a CSV that lines up with the sheet."
                ),
                "ruleSchema": BacklinkRules.model_json_schema(by_alias=True),
            },
        ]
    }


@router.post("", response_model=AgentOut, status_code=status.HTTP_201_CREATED)
def create_agent(request: AgentCreate, db: Session = Depends(get_db)) -> AgentOut:
    # No explicit type check: AgentType is a Literal over AGENT_TYPES, so an
    # unknown type is rejected as a 422 during request validation before this
    # body runs. A second check here would be unreachable.
    agent = Agent(
        name=request.name.strip(),
        agent_type=request.agent_type,
        description=request.description,
        enabled=1 if request.enabled else 0,
        rules=_validate_rules(request.agent_type, request.rules),
    )
    db.add(agent)
    db.add(
        ActivityEntry(
            actor=ACTOR,
            action="created agent",
            item=agent.name,
            after=agent.agent_type,
        )
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An agent named '{request.name}' already exists.",
        ) from exc

    db.refresh(agent)
    return _out(agent)


@router.get("/{agent_id}", response_model=AgentOut)
def get_agent(agent_id: str, db: Session = Depends(get_db)) -> AgentOut:
    return _out(_get_or_404(db, agent_id))


@router.patch("/{agent_id}", response_model=AgentOut)
def update_agent(
    agent_id: str, request: AgentUpdate, db: Session = Depends(get_db)
) -> AgentOut:
    agent = _get_or_404(db, agent_id)
    before = "enabled" if agent.enabled else "disabled"

    if request.name is not None:
        agent.name = request.name.strip()
    if request.description is not None:
        agent.description = request.description
    if request.rules is not None:
        agent.rules = _validate_rules(agent.agent_type, request.rules)
    if request.enabled is not None:
        agent.enabled = 1 if request.enabled else 0

    db.add(
        ActivityEntry(
            actor=ACTOR,
            action="updated agent",
            item=agent.name,
            before=before,
            after="enabled" if agent.enabled else "disabled",
        )
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Another agent already has that name.",
        ) from exc

    db.refresh(agent)
    return _out(agent)


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_agent(agent_id: str, db: Session = Depends(get_db)) -> None:
    agent = _get_or_404(db, agent_id)
    if backlink_service.is_running(agent.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An audit is running for this agent. Wait for it to finish first.",
        )
    db.execute(delete(BacklinkCheck).where(BacklinkCheck.agent_id == agent.id))
    db.execute(delete(BacklinkAudit).where(BacklinkAudit.agent_id == agent.id))
    db.delete(agent)
    db.add(
        ActivityEntry(actor=ACTOR, action="deleted agent", item=agent.name)
    )
    db.commit()


# --- content agents (brief §2) ---------------------------------------------


@router.get("/{agent_id}/cities")
def remaining_cities(agent_id: str, db: Session = Depends(get_db)) -> dict:
    """Cities this agent has not posted to yet (brief §2.2)."""
    agent = _get_or_404(db, agent_id)
    cities = available_cities(db, agent.id)
    return {
        "remaining": len(cities),
        "cities": [
            {"key": c.key, "city": c.name, "state": c.state, "zipcode": c.zipcode}
            for c in cities
        ],
    }


@router.post(
    "/{agent_id}/generate",
    response_model=AgentOutputOut,
    status_code=status.HTTP_201_CREATED,
)
def generate(agent_id: str, db: Session = Depends(get_db)) -> AgentOutputOut:
    """Generate the next ad for a content agent.

    Produces content only. Nothing is submitted anywhere -- the operator posts
    it and records the URL with /publish.
    """
    agent = _get_or_404(db, agent_id)
    if not agent.enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Agent '{agent.name}' is disabled. Enable it first.",
        )

    try:
        output = generate_output(db, agent)
    except ContentError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    db.add(
        ActivityEntry(
            actor=ACTOR,
            action="generated content",
            item=f"{agent.name} / {output.city}, {output.state}",
            after=output.category,
        )
    )
    db.commit()
    db.refresh(output)
    return AgentOutputOut.model_validate(output)


@router.get("/{agent_id}/outputs", response_model=AgentOutputPage)
def list_outputs(
    agent_id: str,
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200, alias="perPage"),
    output_status: str | None = Query(None, alias="status"),
) -> AgentOutputPage:
    """Generated content and where it was published (brief §2.9)."""
    _get_or_404(db, agent_id)

    conditions = [AgentOutput.agent_id == agent_id]
    if output_status:
        conditions.append(AgentOutput.status == output_status)

    total = db.execute(
        select(func.count(AgentOutput.id)).where(*conditions)
    ).scalar_one()
    rows = (
        db.execute(
            select(AgentOutput)
            .where(*conditions)
            .order_by(AgentOutput.created_at.desc())
            .limit(per_page)
            .offset((page - 1) * per_page)
        )
        .scalars()
        .all()
    )
    return AgentOutputPage(
        items=[AgentOutputOut.model_validate(r) for r in rows],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.post("/outputs/{output_id}/publish", response_model=AgentOutputOut)
def mark_published(
    output_id: str, request: PublishRequest, db: Session = Depends(get_db)
) -> AgentOutputOut:
    """Record where the operator actually posted the generated ad."""
    from datetime import UTC, datetime

    output = db.get(AgentOutput, output_id)
    if output is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No agent output with id {output_id}.",
        )

    output.published_url = request.published_url.strip()
    output.status = "published"
    output.published_at = datetime.now(UTC)
    db.add(
        ActivityEntry(
            actor=ACTOR,
            action="published content",
            item=f"{output.city}, {output.state}",
            after=output.published_url,
        )
    )
    db.commit()
    db.refresh(output)
    return AgentOutputOut.model_validate(output)


# --- refinement (brief §8) -------------------------------------------------


@router.get("/{agent_id}/refinement", response_model=RefinementIndex)
def agent_refinement(
    agent_id: str, db: Session = Depends(get_db), days: int = Query(30, ge=1, le=365)
) -> RefinementIndex:
    agent = _get_or_404(db, agent_id)
    return RefinementIndex.model_validate(compute(db, agent, days))


# --- backlink audits --------------------------------------------------------


def _audit_agent_or_409(db: Session, agent_id: str) -> Agent:
    agent = _get_or_404(db, agent_id)
    if agent.agent_type != "backlink_audit":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Agent '{agent.name}' is not a backlink-audit agent.",
        )
    return agent


def _audit_out(db: Session, agent_id: str) -> BacklinkAuditOut:
    audit = db.get(BacklinkAudit, agent_id)
    if audit is None:
        return BacklinkAuditOut(status="idle")
    checks = (
        db.execute(
            select(BacklinkCheck)
            .where(BacklinkCheck.agent_id == agent_id)
            .order_by(BacklinkCheck.row)
        )
        .scalars()
        .all()
    )
    counts: dict[str, int] = {}
    for check in checks:
        counts[check.result] = counts.get(check.result, 0) + 1
    return BacklinkAuditOut(
        status=audit.status,
        total=audit.total,
        done=audit.done,
        error=audit.error,
        started_at=audit.started_at,
        finished_at=audit.finished_at,
        counts=counts,
        items=[BacklinkCheckOut.model_validate(c) for c in checks],
    )


@router.post("/{agent_id}/audit", response_model=BacklinkAuditOut)
def start_audit(agent_id: str, db: Session = Depends(get_db)) -> BacklinkAuditOut:
    """Start checking every URL in the agent's sheet. Poll GET .../audit."""
    agent = _audit_agent_or_409(db, agent_id)
    if not agent.enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Agent '{agent.name}' is disabled. Enable it first.",
        )
    if not str((agent.rules or {}).get("sheetUrl", "")).strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Add the Google Sheet link first.",
        )
    if backlink_service.is_running(agent.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An audit is already running for this agent.",
        )
    backlink_service.start_audit(agent)
    db.expire_all()
    return _audit_out(db, agent.id)


@router.get("/{agent_id}/audit", response_model=BacklinkAuditOut)
def get_audit(agent_id: str, db: Session = Depends(get_db)) -> BacklinkAuditOut:
    _audit_agent_or_409(db, agent_id)
    return _audit_out(db, agent_id)


@router.get("/{agent_id}/audit.csv")
def audit_csv(agent_id: str, db: Session = Depends(get_db)) -> Response:
    """Results in sheet order; the Result column pastes into column B."""
    agent = _audit_agent_or_409(db, agent_id)
    checks = (
        db.execute(
            select(BacklinkCheck)
            .where(BacklinkCheck.agent_id == agent_id)
            .order_by(BacklinkCheck.row)
        )
        .scalars()
        .all()
    )
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in agent.name.lower())[:60]
    return Response(
        content=backlink_service.to_csv(checks),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="backlinks-{safe or "audit"}.csv"'},
    )
