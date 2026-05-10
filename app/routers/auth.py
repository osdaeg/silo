import os
from fastapi import HTTPException, Security, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

API_TOKEN = os.getenv("SILO_API_TOKEN", "changeme")

security = HTTPBearer(auto_error=False)


def require_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Security(security),
):
    # Skip auth for dashboard HTML pages (browser access)
    if request.url.path.startswith("/dashboard"):
        return True

    if credentials is None or credentials.credentials != API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid or missing token")
    return True


from fastapi import APIRouter
router = APIRouter()
