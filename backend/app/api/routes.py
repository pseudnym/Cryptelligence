from fastapi import APIRouter, HTTPException, Request
from ..schemas.requests import CreateInvestigation, OsintInput, PivotInput, PublicSearchInput, AddSeed, RelationshipInput
from ..models.workflow import AdvanceRequest
from ..services.graph import graph
from ..services.scoring import analysis
from ..services.osint import supplied_observation
from ..services.orchestrator import InvalidTransition

router = APIRouter()

def call(request, method, *args):
    try:
        return getattr(request.app.state.orchestrator, method)(*args)
    except KeyError as exc:
        raise HTTPException(404, exc.args[0]) from exc
    except InvalidTransition as exc:
        raise HTTPException(409, str(exc)) from exc

def get_case(request, id):
    return call(request, "get", id)

def workspace(case):
    return {**case.model_dump(mode="json"), "graph": graph(case), "analysis": analysis(case)}

@router.get("/health")
def health():
    return {"status": "ok", "mode": "fixture_and_live", "workflow": "interactive_loop"}

@router.post("/investigations", status_code=201)
def create(body: CreateInvestigation, request: Request):
    return workspace(call(request, "create", body.seeds, body.question, body.mode))

@router.get("/investigations/{case_id}")
def read(case_id: str, request: Request):
    return workspace(get_case(request, case_id))

@router.post("/investigations/{case_id}/advance")
def advance(case_id: str, body: AdvanceRequest, request: Request):
    return workspace(call(request, "advance", case_id, body.expected_version))

@router.post("/investigations/{case_id}/retry")
def retry(case_id: str, request: Request):
    return workspace(call(request, "retry", case_id))

@router.get("/investigations/{case_id}/graph")
def read_graph(case_id: str, request: Request):
    return graph(get_case(request, case_id))

@router.get("/investigations/{case_id}/{collection}")
def read_collection(case_id: str, collection: str, request: Request):
    if collection not in {"evidence", "claims", "hypotheses", "actions", "plan", "events", "revisions"}:
        raise HTTPException(404, "Collection not found")
    return getattr(get_case(request, case_id), collection)

@router.post("/investigations/{case_id}/plan")
def plan(case_id: str, body: AdvanceRequest, request: Request):
    case = get_case(request, case_id)
    return workspace(call(request, "advance", case_id, body.expected_version) if case.investigation.status == "CREATED" else case)

@router.post("/investigations/{case_id}/collect")
@router.post("/investigations/{case_id}/ingest")
def collect(case_id: str, body: AdvanceRequest, request: Request):
    case = get_case(request, case_id)
    if case.investigation.status not in {"PLANNING", "COLLECTING"}:
        raise HTTPException(409, "Collection requires an active plan")
    return workspace(call(request, "advance", case_id, body.expected_version))

@router.post("/investigations/{case_id}/analyze")
def analyze(case_id: str, request: Request):
    return workspace(call(request, "reanalyze", case_id))

@router.post("/investigations/{case_id}/actions/{action_id}/execute", status_code=202)
def execute(case_id: str, action_id: str, request: Request):
    return workspace(call(request, "start_action", case_id, action_id))

@router.post("/investigations/{case_id}/osint")
def osint(case_id: str, body: OsintInput, request: Request):
    observation = supplied_observation(get_case(request, case_id), body)
    return workspace(call(request, "attach", case_id, observation))

@router.post("/investigations/{case_id}/expand", status_code=202)
def expand(case_id: str, body: PivotInput, request: Request):
    return workspace(call(request, "pivot", case_id, body.entity_id, body.direction))

@router.get("/investigations/{case_id}/entities/{entity_id}/history")
def history(case_id: str, entity_id: str, request: Request, offset: int = 0, limit: int = 25):
    case = get_case(request, case_id)
    if not any(e.id == entity_id for e in case.entities):
        raise HTTPException(404, "Entity not found")
    rows = [t for t in case.transactions if entity_id in (t.sender, t.receiver)]
    offset, limit = max(0, offset), max(1, min(100, limit))
    return {"items": rows[offset:offset + limit], "total": len(rows), "offset": offset,
            "summaries": [s for s in case.collections.values() if s["entity_id"] == entity_id]}

@router.post("/investigations/{case_id}/search", status_code=202)
def public_search(case_id: str, body: PublicSearchInput, request: Request):
    return workspace(call(request, "public_search", case_id, body.target_id, body.query, body.capability))


@router.post("/investigations/{case_id}/pause")
def pause(case_id: str, request: Request):
    return workspace(call(request, "pause_automation", case_id))


@router.post("/investigations/{case_id}/seeds", status_code=202)
def add_seed(case_id: str, body: AddSeed, request: Request):
    return workspace(call(request,"add_seed",case_id,body.address))

@router.post("/investigations/{case_id}/relationships", status_code=202)
def relationship(case_id: str, body: RelationshipInput, request: Request):
    return workspace(call(request,"add_relationship",case_id,body.source_entity_id,body.target_entity_id,body.evidence_ids,body.statement))
