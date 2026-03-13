from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import settings

_bearer = HTTPBearer(auto_error=False)


def require_api_key(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
) -> str:
    if credentials is None or credentials.credentials != settings.things_agent_api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return credentials.credentials
