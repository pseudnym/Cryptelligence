import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from .api.routes import router
from .repositories.sqlite import SQLiteCaseRepository
from .services.tools import FixtureProvider, ToolRegistry, MockEthereumTool, MockOSINTTool, MockRelationshipTool
from .services.planning import DeterministicPlanner
from .services.reasoning import DeterministicReasoningEngine
from .services.evidence import EvidenceService
from .services.actions import ActionEngine
from .services.orchestrator import InvestigationOrchestrator

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
logger = logging.getLogger(__name__)

def create_app(database_path: str | None = None, ethereum_provider=None, ethereum_settings=None, osint_provider=None, osint_settings=None, source_fetcher=None, gemini_client=None, gemini_settings=None, solana_provider=None, solana_settings=None):
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        default = str(Path(__file__).resolve().parents[1] / "data" / "investigations.sqlite3")
        repository = SQLiteCaseRepository(database_path or os.getenv("DATABASE_PATH", default))
        provider = FixtureProvider()
        from .services.ethereum_provider import EthereumSettings, entity
        from .services.blockscout import BlockscoutEthereumProvider
        from .services.ethereum_tool import EthereumInvestigationTool
        settings = ethereum_settings or EthereumSettings.from_env()
        live_provider = ethereum_provider or BlockscoutEthereumProvider(settings)
        from .services.osint_provider import OSINTSettings, LiveSearchProvider
        from .services.osint_tool import LiveOSINTTool
        from .services.public_source import PublicPageFetcher
        search_settings = osint_settings or OSINTSettings.from_env()
        search_tool = LiveOSINTTool(osint_provider or LiveSearchProvider(search_settings), search_settings,
                                    source_fetcher or PublicPageFetcher(search_settings))
        from .services.gemini import GeminiSettings, GeminiClient, OllamaClient, GeminiEngine
        from .services.gemini_tools import CaseReadTool
        ai_settings = gemini_settings or GeminiSettings.from_env()
        ai_client = gemini_client or (OllamaClient(ai_settings) if ai_settings.provider == "ollama" else GeminiClient(ai_settings))
        ai = GeminiEngine(ai_client, ai_settings)
        from .services.solana_provider import SolanaSettings, SolanaRPCProvider
        from .services.solana_tool import SolanaInvestigationTool
        from .services.chains import seed_entity
        sol_settings = solana_settings or SolanaSettings.from_env()
        sol_tool = SolanaInvestigationTool(solana_provider or SolanaRPCProvider(sol_settings), sol_settings)
        app.state.repository = repository
        app.state.orchestrator = InvestigationOrchestrator(repository, provider.seed_entities,
            DeterministicPlanner(), ToolRegistry([MockEthereumTool(provider), MockOSINTTool(provider), MockRelationshipTool(provider), EthereumInvestigationTool(live_provider, settings), search_tool, sol_tool, CaseReadTool()]),
            EvidenceService(), DeterministicReasoningEngine(), ActionEngine(),
            live_seed_factory=lambda addresses: [seed_entity(address) for address in addresses], graph_limit=settings.graph_limit, gemini=ai)
        yield
        repository.close()

    app = FastAPI(title="Evidence Engine · Ethereum Investigation", lifespan=lifespan)
    app.include_router(router)
    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception):
        logger.exception("Request failed: %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Unexpected local error. Check the backend log."})
    return app

app = create_app()
