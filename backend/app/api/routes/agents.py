"""Agent endpoints (brief §2, §3, and the Refinement Index in §8).

Agents are created disabled. Enabling one is a separate, explicit call, so
nothing starts acting as a side effect of being configured.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db, session_scope
from app.models import ActivityEntry, Agent, AgentOutput, BacklinkCheck, ScanRun
from app.schemas.agent import (
    AgentCreate,
    AgentOut,
    AgentOutputOut,
    AgentOutputPage,
    AgentUpdate,
    BacklinkAuditOut,
    BacklinkAuditRules,
    BacklinkCheckOut,
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
        "backlink_audit": BacklinkAuditRules,
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


_SHEET_LINK = re.compile(r"https://docs\.google\.com/spreadsheets/d/\S+")


def _scan_now(db: Session, background: BackgroundTasks, agent: Agent) -> None:
    """Run a scan as soon as an engagement agent is switched on.

    Scheduled scans run twice a day, so without this a freshly enabled agent
    does nothing visible for up to twelve hours -- which reads as broken.
    """
    if agent.agent_type != "engagement" or not agent.enabled:
        return
    from app.api.routes.scans import _execute
    from app.services.ingestion_service import build_connectors

    if not build_connectors():
        return

    scan = ScanRun(status="running", trigger="manual")
    db.add(scan)
    db.commit()
    background.add_task(_execute, scan.id)


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
                "ruleSchema": BacklinkAuditRules.model_json_schema(by_alias=True),
            },
        ]
    }


@router.post("", response_model=AgentOut, status_code=status.HTTP_201_CREATED)
def create_agent(
    request: AgentCreate, background: BackgroundTasks, db: Session = Depends(get_db)
) -> AgentOut:
    # No explicit type check: AgentType is a Literal over AGENT_TYPES, so an
    # unknown type is rejected as a 422 during request validation before this
    # body runs. A second check here would be unreachable.
    rules = dict(request.rules)
    if request.agent_type == "backlink_audit" and not rules.get("sheetUrl"):
        # People paste the sheet link into the description; use it rather than
        # make them enter it twice.
        found = _SHEET_LINK.search(request.description or "")
        if found:
            rules["sheetUrl"] = found.group(0)
    agent = Agent(
        name=request.name.strip(),
        agent_type=request.agent_type,
        description=request.description,
        enabled=1 if request.enabled else 0,
        rules=_validate_rules(request.agent_type, rules),
    )
    db.add(agent)
    db.add(
        ActivityEntry(
            actor=ACTOR,
            action="created agent",
            item=agent.name,
            after=agent.agent_type
            + ("" if agent.enabled else " (disabled -- enable it to start)"),
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
    _scan_now(db, background, agent)
    return _out(agent)


@router.get("/{agent_id}", response_model=AgentOut)
def get_agent(agent_id: str, db: Session = Depends(get_db)) -> AgentOut:
    return _out(_get_or_404(db, agent_id))


@router.patch("/{agent_id}", response_model=AgentOut)
def update_agent(
    agent_id: str,
    request: AgentUpdate,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
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
    if before == "disabled":
        _scan_now(db, background, agent)
    return _out(agent)


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_agent(agent_id: str, db: Session = Depends(get_db)) -> None:
    agent = _get_or_404(db, agent_id)
    db.query(BacklinkCheck).filter(BacklinkCheck.agent_id == agent.id).delete()
    _audits.pop(agent.id, None)
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


# --- backlink audit agents ---------------------------------------------------

# Progress of the current or last run per agent. In memory because a run lasts
# minutes and the API is one process; the results themselves are persisted.
_audits: dict[str, dict] = {}

_RESULT_KINDS = ("dofollow", "nofollow", "not_found", "error")


async def _run_audit(agent_id: str) -> None:
    state = _audits[agent_id]
    db = session_scope()
    try:
        agent = db.get(Agent, agent_id)
        rules = BacklinkAuditRules.model_validate(agent.rules or {})
        urls = await backlink_service.read_sheet(rules.sheet_url, rules.url_column)
        urls = urls[: rules.max_urls]
        state["total"] = len(urls)

        # In batches so the progress counter moves while the run is going.
        results = []
        for start in range(0, len(urls), 25):
            results.extend(
                await backlink_service.audit(urls[start : start + 25], rules.target_domain)
            )
            state["done"] = len(results)

        db.query(BacklinkCheck).filter(BacklinkCheck.agent_id == agent_id).delete()
        now = datetime.now(UTC)
        for r in results:
            db.add(
                BacklinkCheck(
                    agent_id=agent_id,
                    row=r.row,
                    page_url=r.page_url,
                    result=r.result,
                    rel=r.rel[:255],
                    link_href=r.link_href,
                    anchor_text=r.anchor_text,
                    http_status=r.http_status,
                    detail=r.detail,
                    checked_at=now,
                )
            )
        counts = {k: sum(1 for r in results if r.result == k) for k in _RESULT_KINDS}
        db.add(
            ActivityEntry(
                actor=agent.name[:64],
                action="backlink audit",
                item=f"{len(results)} page(s) checked",
                after=", ".join(f"{v} {k.replace('_', ' ')}" for k, v in counts.items()),
            )
        )
        db.commit()
        state["status"] = "completed"
    except backlink_service.BacklinkError as exc:
        state.update(status="failed", error=str(exc))
    except Exception as exc:  # noqa: BLE001 -- a failed run must be reported, not lost
        logger.exception("Backlink audit for %s failed", agent_id)
        db.rollback()
        state.update(status="failed", error=f"Unexpected error: {exc!r}"[:300])
    finally:
        state["finished_at"] = datetime.now(UTC)
        db.close()


def _audit_agent(db: Session, agent_id: str) -> Agent:
    agent = _get_or_404(db, agent_id)
    if agent.agent_type != "backlink_audit":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Agent '{agent.name}' is not a backlink-audit agent.",
        )
    return agent


@router.post(
    "/{agent_id}/audit",
    response_model=BacklinkAuditOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_audit(
    agent_id: str, background: BackgroundTasks, db: Session = Depends(get_db)
) -> BacklinkAuditOut:
    """Start checking every URL in the agent's sheet. Poll GET .../audit."""
    agent = _audit_agent(db, agent_id)
    if not agent.enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Agent '{agent.name}' is disabled. Enable it first.",
        )
    rules = BacklinkAuditRules.model_validate(agent.rules or {})
    if not rules.sheet_url:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Set the Google Sheet link for this agent first.",
        )
    if _audits.get(agent_id, {}).get("status") == "running":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="An audit is already running."
        )

    begin_audit(db, agent)
    background.add_task(_run_audit, agent_id)
    return get_audit(agent_id, db)


def begin_audit(db: Session, agent: Agent, actor: str = ACTOR) -> None:
    """Mark an audit as running and log it. The caller schedules _run_audit."""
    _audits[agent.id] = {
        "status": "running",
        "total": 0,
        "done": 0,
        "error": None,
        "started_at": datetime.now(UTC),
        "finished_at": None,
    }
    db.add(ActivityEntry(actor=actor, action="started backlink audit", item=agent.name))
    db.commit()


def audit_running(agent_id: str) -> bool:
    return _audits.get(agent_id, {}).get("status") == "running"


@router.get("/{agent_id}/audit", response_model=BacklinkAuditOut)
def get_audit(agent_id: str, db: Session = Depends(get_db)) -> BacklinkAuditOut:
    _audit_agent(db, agent_id)
    rows = (
        db.execute(
            select(BacklinkCheck)
            .where(BacklinkCheck.agent_id == agent_id)
            .order_by(BacklinkCheck.row)
        )
        .scalars()
        .all()
    )
    # After a restart the in-memory state is gone but the results are not.
    state = _audits.get(agent_id) or {"status": "completed" if rows else "idle"}
    counts: dict[str, int] = {}
    for r in rows:
        counts[r.result] = counts.get(r.result, 0) + 1
    return BacklinkAuditOut(
        status=state["status"],
        total=state.get("total", len(rows)),
        done=state.get("done", len(rows)),
        error=state.get("error"),
        started_at=state.get("started_at"),
        finished_at=state.get("finished_at"),
        counts=counts,
        items=[BacklinkCheckOut.model_validate(r) for r in rows],
    )


@router.post("/{agent_id}/audit/sheet")
async def write_audit_to_sheet(agent_id: str, db: Session = Depends(get_db)) -> dict:
    """Write each result into the agent's sheet, next to its URL (column B by
    default). Needs GOOGLE_SERVICE_ACCOUNT_FILE and the sheet shared with that
    account as an Editor."""
    from app.services import google_sheets

    agent = _audit_agent(db, agent_id)
    if _audits.get(agent_id, {}).get("status") == "running":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Wait for the audit to finish first."
        )
    if not google_sheets.configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Writing to Google Sheets is not set up on the server. Use Download CSV instead.",
        )
    rules = BacklinkAuditRules.model_validate(agent.rules or {})
    rows = (
        db.execute(select(BacklinkCheck).where(BacklinkCheck.agent_id == agent_id))
        .scalars()
        .all()
    )
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Run the audit first; there are no results yet."
        )
    values = [(r.row, google_sheets.RESULT_LABELS.get(r.result, r.result)) for r in rows]
    try:
        written = await google_sheets.write_column(rules.sheet_url, rules.result_column, values)
    except google_sheets.SheetsError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    db.add(
        ActivityEntry(
            actor=ACTOR,
            action="wrote audit results to sheet",
            item=agent.name,
            after=f"{written} cell(s) in column {rules.result_column.upper()}",
        )
    )
    db.commit()
    return {"written": written, "column": rules.result_column.upper()}


@router.get("/{agent_id}/audit.csv")
def audit_csv(agent_id: str, db: Session = Depends(get_db)) -> Response:
    """Results in sheet order; the Result column pastes into column B."""
    agent = _audit_agent(db, agent_id)
    rows = (
        db.execute(select(BacklinkCheck).where(BacklinkCheck.agent_id == agent_id))
        .scalars()
        .all()
    )
    filename = re.sub(r"[^A-Za-z0-9_-]+", "-", agent.name).strip("-") or "backlinks"
    return Response(
        content=backlink_service.results_csv(rows),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}.csv"'},
    )
