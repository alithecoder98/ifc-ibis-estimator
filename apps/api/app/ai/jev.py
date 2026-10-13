"""Client for jev, the construction company's AI classification tool.

Stubbed until real API access/credentials exist (see CLAUDE.md "Still open" — we have
no docs for jev's actual request/response shape). The stub lets everything downstream
(Phase P.2's classification step) be built and tested now; `get_jev_client()` is the
only thing that needs to change once real credentials and API docs arrive.
"""

from dataclasses import dataclass

from app.core.config import get_settings


@dataclass
class JevResult:
    ibis_code: str | None
    internal_element: str | None
    confidence: float | None
    reasoning: str | None
    is_stub: bool = False


class JevClient:
    """Real implementation — not built yet. We have jev credentials settings
    (JEV_API_URL/JEV_API_KEY) but no API documentation for its request/response
    shape, so there's nothing honest to implement here yet. Raises rather than
    guessing at a contract that would just need to be rewritten once docs exist.
    """

    def __init__(self, api_url: str, api_key: str):
        self.api_url = api_url
        self.api_key = api_key

    def classify(self, profile_text: str) -> JevResult:
        raise NotImplementedError(
            "Real jev API integration isn't built - no API docs/access yet. "
            "See CLAUDE.md 'Still open'. JEV_API_URL/JEV_API_KEY are set, which is "
            "why get_jev_client() picked this class over the stub - either unset "
            "them to go back to the stub, or implement classify() once jev's actual "
            "API contract is known."
        )


class StubJevClient:
    """Used until real jev credentials exist. Always returns a result explicitly
    flagged as a stub (is_stub=True, confidence=0.0) so nothing downstream can
    mistake it for a real classification - every element routes to needs_review,
    which is correct: we have no real classification signal yet.
    """

    def classify(self, profile_text: str) -> JevResult:
        return JevResult(
            ibis_code=None,
            internal_element=None,
            confidence=0.0,
            reasoning="jev not yet configured (no JEV_API_URL/JEV_API_KEY) - stub result",
            is_stub=True,
        )


def get_jev_client() -> JevClient | StubJevClient:
    settings = get_settings()
    if settings.jev_api_url and settings.jev_api_key:
        return JevClient(settings.jev_api_url, settings.jev_api_key)
    return StubJevClient()
