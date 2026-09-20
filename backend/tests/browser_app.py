"""Playwright-only server: LIVE provider responses are synthetic and offline."""
from app.main import create_app
from test_solana import rpc_provider, SOL
from dataclasses import replace
from test_gemini import MockGemini, AI
from app.api.routes import workspace
from fastapi import Request
from app.services.osint_provider import MockOSINTProvider
from test_osint import hit, SEARCH
from test_ethereum import normalized, record, A, B, C, SETTINGS

provider = normalized([
    (record(C, A, hash='0x' + '3' * 64), 'normal'),
    (record(A, B), 'normal'),
    (record(A, B, kind='token'), 'token'),
    (record(B, C, hash='0x' + '2' * 64), 'normal'),
])
app = create_app(':memory:', ethereum_provider=provider, ethereum_settings=SETTINGS, osint_provider=MockOSINTProvider([hit()]), osint_settings=SEARCH, gemini_client=MockGemini(), gemini_settings=replace(AI, enabled=False), solana_provider=rpc_provider(), solana_settings=SOL)

@app.post("/test/gemini-case")
def gemini_case(request: Request):
    # Test-only entry point. Production app.main never imports browser_app.
    service = request.app.state.orchestrator
    case = service.create([A], "Investigate flows, public sources and uncertainty.", "live")
    case.reasoning_mode = "gemini"
    case.max_auto_steps = 2
    return workspace(service.save(case))
