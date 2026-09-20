from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4
import hashlib
import logging
from ..models.domain import Case, Investigation
from ..models.workflow import InvestigationEvent
from .evidence import evidence_fingerprint
from .revisions import record_revision

logger = logging.getLogger(__name__)
TERMINAL = {"AWAITING_ACTION", "COMPLETE", "ERROR"}
TRANSITIONS = {
    "CREATED": {"PLANNING"}, "PLANNING": {"COLLECTING"}, "COLLECTING": {"ANALYZING"},
    "ANALYZING": {"AWAITING_ACTION", "COMPLETE"},
    "AWAITING_ACTION": {"EXECUTING_ACTION", "REANALYZING"},
    "EXECUTING_ACTION": {"REANALYZING"}, "REANALYZING": {"AWAITING_ACTION", "COMPLETE"},
    "COMPLETE": {"REANALYZING", "EXECUTING_ACTION"},
}

class InvalidTransition(ValueError):
    pass

class InvestigationOrchestrator:
    """Controls generic steps; all source-specific behavior lives in tools."""
    def __init__(self, repository, seed_factory, planner, tools, evidence, reasoning, actions, live_seed_factory=None, graph_limit=40, gemini=None):
        self.gemini = gemini
        self.live_seed_factory, self.graph_limit = live_seed_factory, graph_limit
        self.repository, self.seed_factory, self.planner = repository, seed_factory, planner
        self.tools, self.evidence, self.reasoning, self.actions = tools, evidence, reasoning, actions
        self.lock = RLock()

    def get(self, id):
        case = self.repository.get(id)
        if case is None:
            raise KeyError("Investigation not found")
        return case

    def event(self, case, type, title, description, evidence_ids=(), **metadata):
        case.events.append(InvestigationEvent(id=uuid4().hex, investigation_id=case.investigation.id,
            timestamp=datetime.now(timezone.utc), event_type=type, title=title, description=description,
            related_evidence_ids=list(evidence_ids), metadata={"state": case.investigation.status, **metadata}))

    def transition(self, case, target):
        previous = case.investigation.status
        if target not in TRANSITIONS.get(previous, set()):
            raise InvalidTransition(f"Cannot move from {previous} to {target}")
        case.investigation.status = target

    def save(self, case):
        case.version += 1
        self.repository.save(case)
        return case

    def create(self, seeds, question, mode="fixture"):
        factory = self.live_seed_factory if mode == "live" else self.seed_factory
        if factory is None:
            raise InvalidTransition("Live collection is not configured")
        entities = factory(seeds)
        case = Case(fixture=mode == "fixture", graph_limit=self.graph_limit, investigation=Investigation(id=uuid4().hex, seed_entity=entities[0].id,
            seed_entities=[e.id for e in entities], objective=question, created_at=datetime.now(timezone.utc),
            status="CREATED", summary="Investigation created. Evidence has not yet been collected."),
            fixture_notice="Synthetic development observations only. Supplied seed addresses are inputs, not verified identities." if mode == "fixture" else "LIVE blockchain provider records. Collection is bounded; flows do not establish ownership or attribution.",
            entities=entities, transactions=[], evidence=[], claims=[], hypotheses=[], actions=[], revision=0)
        if mode == "live" and self.gemini and self.gemini.settings.enabled:
            case.reasoning_mode = "gemini"
            case.max_auto_steps = self.gemini.settings.max_auto_steps
        self.event(case, "investigation_created", "Investigation created", f"{len(seeds)} seed(s) and the investigation question saved.")
        return self.save(case)

    def fingerprint(self, case):
        completed = ",".join(sorted(a.id for a in case.actions if a.status == "completed"))
        return hashlib.sha256((evidence_fingerprint(case) + completed).encode()).hexdigest()

    def advance(self, id, expected_version):
        with self.lock:
            original = self.get(id)
            if original.version != expected_version or original.investigation.status in TERMINAL:
                return original
            case = original.model_copy(deep=True)
            try:
                self.perform_next_operation(case)
                return self.save(case)
            except Exception as exc:
                logger.warning("Investigation operation failed: %s (%s)", id, type(exc).__name__)
                # Roll back any partial operation and persist a resumable failure.
                original.resume_state = original.investigation.status
                original.investigation.status = "ERROR"
                original.error = getattr(exc, "safe_message", "Collection or analysis failed. Retry the interrupted step.")
                if original.plan:
                    for step in original.plan.steps:
                        if step.status == "running":
                            step.status = "failed"
                    original.plan.status = "failed"
                if original.active_action_id:
                    failed_action = next(a for a in original.actions if a.id == original.active_action_id)
                    if failed_action.status == "running": failed_action.status = "failed"
                self.event(original, "operation_failed", "Investigation paused", original.error, error_type=type(exc).__name__)
                return self.save(original)

    def perform_next_operation(self, case):
        state = case.investigation.status
        if state == "CREATED":
            case.plan = self.gemini.create_plan(case) if case.reasoning_mode == "gemini" else self.planner.create_plan(case)
            self.transition(case, "PLANNING")
            self.event(case, "plan_created", "Investigation plan generated", f"{len(case.plan.steps)} steps prioritized from the question.")
        elif state in {"PLANNING", "COLLECTING"} and case.reasoning_mode == "gemini":
            self.gemini_collection(case)
        elif state in {"PLANNING", "COLLECTING"}:
            if not case.plan:
                raise InvalidTransition("Collection requires a plan")
            if state == "PLANNING":
                self.transition(case, "COLLECTING")
            running = next((s for s in case.plan.steps if s.status == "running"), None)
            if running is None:
                step = next(s for s in case.plan.steps if s.status == "pending")
                step.status = "running"
                self.event(case, "collection_started", step.title, step.reason, step_id=step.id, tool=step.tool_or_adapter)
                return
            tool = self.tools.for_action(running.capability)
            result = tool.execute(case, running.capability)
            added = self.evidence.merge(case, result)
            for warning in result.warnings:
                self.event(case, "collection_warning", "Partial collection", warning)
            if result.collections:
                self.event(case, "collection_summary", "Blockchain collection inspected",
                    f"{sum(s['examined'] for s in result.collections.values())} records examined; {len(result.transactions)} normalized events; {len({id for s in result.collections.values() for id in s['significant_ids']})} significant relationships selected.", added)
            case.investigation.summary = f"{len(case.evidence)} evidence record(s) collected. Assessment is pending completion of the plan."
            running.produced_evidence_ids = added
            running.status = "completed"
            self.event(case, "evidence_collected", running.title + " complete",
                f"{len(result.transactions)} transfer(s) inspected; {len(added)} new evidence record(s) normalized.",
                added, step_id=running.id, tool=tool.name, observation_count=len(result.observations))
            if all(s.status == "completed" for s in case.plan.steps):
                case.plan.status = "completed"
                self.transition(case, "ANALYZING")
                self.event(case, "evidence_normalized", "Evidence structured", f"{len(case.evidence)} provenance-preserving records ready for analysis.")
        elif state == "EXECUTING_ACTION":
            action = next(a for a in case.actions if a.id == case.active_action_id)
            tool = self.tools.for_action(action.action_type)
            result = tool.execute(case, action.action_type)
            added = self.evidence.merge(case, result)
            for warning in result.warnings:
                self.event(case, "collection_warning", "Partial collection", warning)
            if result.collections:
                self.event(case, "collection_summary", "Blockchain collection inspected",
                    f"{sum(s['examined'] for s in result.collections.values())} records examined; {len(result.transactions)} normalized events; {len({id for s in result.collections.values() for id in s['significant_ids']})} significant relationships selected.", added)
            action.status = "completed"
            if case.reasoning_mode == "gemini":
                self.complete_plan_step(case, action.id, added)
            self.event(case, "action_completed", action.title + " complete",
                f"{len(added)} new evidence record(s) persisted. Assessment is being reevaluated.", added, action_id=action.id, tool=tool.name)
            self.transition(case, "REANALYZING")
        elif state in {"ANALYZING", "REANALYZING"}:
            self.finish_analysis(case)
        else:
            raise InvalidTransition("No operation is available")

    def finish_analysis(self, case):
        fingerprint = self.fingerprint(case)
        if fingerprint != case.analyzed_fingerprint:
            initial = not case.revisions
            if case.reasoning_mode == "gemini":
                if not self.gemini:
                    raise InvalidTransition("Gemini adapter is unavailable")
                self.gemini.evaluate(case)
            else:
                self.reasoning.evaluate(case)
            self.event(case, "claim_created", "Claims built" if initial else "Claims reevaluated",
                f"{len(case.claims)} statements classified as fact, inference or unknown.")
            self.event(case, "explanation_created", "Competing explanations evaluated",
                f"{len(case.hypotheses)} evidence-linked explanations; unsupported conclusions were not created.")
            if case.reasoning_mode != "gemini":
                self.actions.generate(case)
                self.actions.important_unknown(case)
            if case.important_unknown:
                self.event(case, "unknown_identified", "Important unknown identified", case.important_unknown.question)
            reason = "Initial investigation" if initial else "After " + next((a.title for a in case.actions if a.id == case.active_action_id), "new evidence")
            record_revision(case, reason)
            case.analyzed_fingerprint = self.fingerprint(case)
            self.event(case, "case_reanalyzed", "Initial assessment ready" if initial else "Case reevaluated",
                f"Revision {case.revision} saved with evidence and reasoning changes.", revision=case.revision)
        pending = sorted((a for a in case.actions if a.status == "pending"), key=lambda a: (-a.total_score, a.id))
        self.transition(case, "AWAITING_ACTION" if pending else "COMPLETE")
        if pending:
            self.event(case, "action_recommended", "Recommended next step ready", pending[0].title, action_id=pending[0].id)
        else:
            self.event(case, "investigation_complete", "Available collection complete", "Remaining unknowns are not treated as resolved.")
        case.active_action_id = None
        if case.reasoning_mode == "gemini":
            if pending and pending[0].execution_mode == "AUTO" and not case.automation_paused and case.auto_steps < case.max_auto_steps:
                self.begin_auto_action(case, pending[0])
            else:
                self.event(case, "analyst_control", "Control returned to analyst",
                    "Automatic step limit reached." if case.auto_steps >= case.max_auto_steps else
                    "Automation is paused." if case.automation_paused else "The next step requires analyst choice or manual work.")

    def complete_plan_step(self, case, action_id, added):
        if case.plan:
            for step in case.plan.steps:
                if step.action_id == action_id:
                    step.status = "completed"
                    step.produced_evidence_ids = added
            if all(s.status == "completed" for s in case.plan.steps): case.plan.status = "completed"

    def begin_auto_action(self, case, action):
        self.tools.for_action(action.action_type)
        self.transition(case, "EXECUTING_ACTION")
        case.active_action_id = action.id
        action.status = "running"
        case.auto_steps += 1
        if case.plan:
            for step in case.plan.steps:
                if step.action_id == action.id: step.status = "running"
        self.event(case, "automatic_tool_requested", "Gemini-selected collection", action.title + ": " + action.rationale,
            action_id=action.id, automatic_step=case.auto_steps, limit=case.max_auto_steps)

    def gemini_collection(self, case):
        if case.investigation.status == "PLANNING": self.transition(case, "COLLECTING")
        if case.active_action_id is None:
            first = next((a for a in case.actions if a.status == "pending"), None)
            if not first or first.execution_mode != "AUTO" or case.automation_paused or case.auto_steps >= case.max_auto_steps:
                self.transition(case, "ANALYZING")
                return
            self.tools.for_action(first.action_type)
            first.status = "running"
            case.active_action_id = first.id
            case.auto_steps += 1
            for step in case.plan.steps:
                if step.action_id == first.id: step.status = "running"
            self.event(case, "collection_started", first.title, first.rationale, automatic_step=case.auto_steps)
            return
        action = next(a for a in case.actions if a.id == case.active_action_id)
        result = self.tools.for_action(action.action_type).execute(case, action.action_type)
        added = self.evidence.merge(case, result)
        action.status = "completed"
        self.complete_plan_step(case, action.id, added)
        for warning in result.warnings: self.event(case, "collection_warning", "Collection limitation", warning)
        self.event(case, "evidence_collected", action.title + " complete", f"{len(added)} evidence records saved; Gemini will reevaluate.", added)
        self.transition(case, "ANALYZING")

    def pause_automation(self, id):
        with self.lock:
            case = self.get(id)
            case.automation_paused = True
            self.event(case, "automation_paused", "Automation paused by analyst", "The current operation can finish; no further automatic tools will start.")
            return self.save(case)

    def start_action(self, id, action_id):
        with self.lock:
            case = self.get(id)
            action = next((a for a in case.actions if a.id == action_id), None)
            if action is None:
                raise KeyError("Action not found")
            if action.status in {"running", "completed"}:
                return case
            if case.investigation.status not in {"AWAITING_ACTION", "COMPLETE"}:
                raise InvalidTransition("Wait for the current operation before starting another action")
            if action.execution_mode == "MANUAL":
                raise InvalidTransition("This action requires manual analyst work; attach the resulting evidence when available")
            self.tools.for_action(action.action_type)
            if case.reasoning_mode == "gemini":
                case.auto_steps = 1
                case.automation_paused = False
            if not case.revisions:
                record_revision(case, "Imported earlier mock snapshot; prior operation history is unavailable")
            self.transition(case, "EXECUTING_ACTION")
            action.status = "running"
            case.active_action_id = action.id
            self.event(case, "action_started", action.title, action.rationale, action_id=action.id)
            return self.save(case)

    def reanalyze(self, id):
        with self.lock:
            case = self.get(id)
            if case.investigation.status not in {"AWAITING_ACTION", "COMPLETE"}:
                raise InvalidTransition("Analysis can be requested after collection or an action completes")
            if self.fingerprint(case) == case.analyzed_fingerprint:
                return case
            self.transition(case, "REANALYZING")
            return self.save(case)

    def retry(self, id):
        with self.lock:
            case = self.get(id)
            if case.investigation.status != "ERROR":
                return case
            case.investigation.status = case.resume_state
            case.resume_state = None
            case.error = None
            if case.plan:
                case.plan.status = "completed" if all(s.status == "completed" for s in case.plan.steps) else "active"
                for step in case.plan.steps:
                    if step.status == "failed":
                        step.status = "running"
            if case.active_action_id:
                failed_action = next(a for a in case.actions if a.id == case.active_action_id)
                if failed_action.status == "failed": failed_action.status = "running"
            self.event(case, "operation_retried", "Interrupted step resumed", "Previously persisted evidence is preserved.")
            return self.save(case)

    def attach(self, id, observation):
        with self.lock:
            case = self.get(id)
            if case.investigation.status not in {"AWAITING_ACTION", "COMPLETE"}:
                raise InvalidTransition("Wait for the current operation before attaching evidence")
            from .tools import ToolResult
            added = self.evidence.merge(case, ToolResult(observations=[observation]))
            if not added:
                return case
            self.event(case, "evidence_collected", "Analyst source attached", "Supplied text was stored; the URL was not fetched.", added)
            self.transition(case, "REANALYZING")
            return self.save(case)

    def pivot(self, id, entity_id, direction):
        with self.lock:
            case = self.get(id)
            if case.fixture:
                raise InvalidTransition("Graph pivots require a LIVE case")
            if case.investigation.status not in {"AWAITING_ACTION", "COMPLETE"}:
                raise InvalidTransition("Wait for the current operation before expanding")
            target = next((e for e in case.entities if e.id == entity_id and e.entity_type in {"wallet", "contract"}), None)
            if target is None:
                raise KeyError("Wallet or contract not found in this case")
            action = self.actions.pivot_action(case, target, direction)
            existing = next((a for a in case.actions if a.id == action.id), None)
            if existing and existing.status == "completed":
                return case
            if existing is None:
                case.actions.append(action)
                self.save(case)
            return self.start_action(id, action.id)

    def public_search(self, id, target_id, query, capability):
        with self.lock:
            case = self.get(id)
            if case.fixture:
                raise InvalidTransition("Public web collection requires a LIVE case")
            if case.investigation.status not in {"AWAITING_ACTION", "COMPLETE"}:
                raise InvalidTransition("Wait for the current operation before searching")
            action = self.actions.public_action(case, target_id, query, capability)
            existing = next((a for a in case.actions if a.id == action.id), None)
            if existing and existing.status == "completed":
                return case
            if existing is None:
                case.actions.append(action)
                self.save(case)
            return self.start_action(id, action.id)


    def add_seed(self, id, address):
        from .chains import seed_entity
        with self.lock:
            case = self.get(id)
            if case.fixture or case.investigation.status not in {"AWAITING_ACTION", "COMPLETE"}:
                raise InvalidTransition("Add a chain seed to a settled LIVE case")
            entity = seed_entity(address)
            if entity.id in case.investigation.seed_entities: return case
            if len(case.investigation.seed_entities) >= 10: raise InvalidTransition("At most ten seeds per case")
            if not any(e.id == entity.id for e in case.entities): case.entities.append(entity)
            case.investigation.seed_entities.append(entity.id)
            self.event(case,"seed_added","Chain seed added",entity.chain + ": " + entity.value)
            self.save(case)
            return self.pivot(id,entity.id,"inspect")

    def add_relationship(self, id, source_id, target_id, evidence_ids, statement):
        from .tools import Observation, ToolResult
        from ..models.domain import CrossChainRelationship
        with self.lock:
            case = self.get(id)
            if case.fixture or case.investigation.status not in {"AWAITING_ACTION", "COMPLETE"}:
                raise InvalidTransition("Relationships require a settled LIVE case")
            entities = {e.id:e for e in case.entities}
            if source_id not in entities or target_id not in entities: raise KeyError("Relationship entity not found")
            if {entities[source_id].chain,entities[target_id].chain} != {"ethereum","solana"}:
                raise InvalidTransition("Select one Ethereum and one Solana entity")
            if not set(evidence_ids) <= {e.id for e in case.evidence}: raise KeyError("Relationship evidence not found")
            digest=hashlib.sha256((source_id+target_id+statement+str(sorted(evidence_ids))).encode()).hexdigest()[:24]
            if any(r.id == "relation-"+digest for r in case.relationships): return case
            observation=Observation(id="analyst-relation-"+digest,evidence_type="analyst_input",title="Analyst-proposed cross-chain relationship",
                description=statement,source_type="analyst_relationship",source_identifier="analyst:"+digest,
                raw_data={"referenced_evidence_ids":evidence_ids,"reasoning_category":"INFERENCE","verified":False},
                linked_entity_ids=[source_id,target_id],reliability="LOW",directness="indirect",reproducible=False)
            self.evidence.merge(case,ToolResult(observations=[observation]))
            case.relationships.append(CrossChainRelationship(id="relation-"+digest,source_entity_id=source_id,target_entity_id=target_id,
                statement=statement,evidence_ids=[observation.id]+evidence_ids))
            self.event(case,"relationship_proposed","Possible cross-chain transition", "Analyst assertion recorded with cited evidence; not a verified bridge match.",[observation.id])
            self.transition(case,"REANALYZING")
            return self.save(case)
