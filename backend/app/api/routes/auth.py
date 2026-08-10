import hmac
from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app.api.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.user import User
from app.core.config import settings
from app.schemas.auth import BrowserLogin, BrowserSession, BrowserToken, Token
from app.schemas.user import UserRead
from app.services.auth_service import AuthService
from app.services.browser_auth_service import BrowserAuthService
from app.services.exceptions import AuthenticationError, InactiveUserError

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/login", response_model=Token)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)) -> Token:
    try: return AuthService(db).authenticate(form.username, form.password)[1]
    except InactiveUserError: raise HTTPException(status_code=403, detail="Usuario inactivo")
    except AuthenticationError: raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales incorrectas", headers={"WWW-Authenticate": "Bearer"})


@router.get("/me", response_model=UserRead)
def me(user: User = Depends(get_current_active_user)) -> User: return user


REFRESH_COOKIE = "te_refresh"
CSRF_COOKIE = "te_csrf"


def _set_browser_cookies(response: Response, refresh: str, csrf: str) -> None:
    common = dict(secure=settings.browser_cookie_secure, samesite=settings.browser_cookie_samesite)
    response.set_cookie(REFRESH_COOKIE, refresh, httponly=True, path="/api/v1/auth/browser",
        max_age=settings.browser_refresh_token_days * 86400, **common)
    response.set_cookie(CSRF_COOKIE, csrf, httponly=False, path="/",
        max_age=settings.browser_refresh_token_days * 86400, **common)


def _clear_browser_cookies(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, path="/api/v1/auth/browser",
        secure=settings.browser_cookie_secure, samesite=settings.browser_cookie_samesite)
    response.delete_cookie(CSRF_COOKIE, path="/", secure=settings.browser_cookie_secure,
        samesite=settings.browser_cookie_samesite)


def _validate_origin(request: Request) -> None:
    if settings.app_env.lower() != "production":
        return
    origin = request.headers.get("origin")
    if not origin or origin not in settings.browser_origin_list:
        raise HTTPException(status_code=403, detail="Origen no permitido")


def _validate_csrf(cookie_value: str | None, header_value: str | None) -> str:
    if not cookie_value or not header_value or not hmac.compare_digest(cookie_value, header_value):
        raise HTTPException(status_code=403, detail="Token CSRF inválido")
    return cookie_value


@router.post("/browser/login", response_model=BrowserToken)
def browser_login(data: BrowserLogin, response: Response, request: Request,
                  db: Session = Depends(get_db)) -> BrowserToken:
    _validate_origin(request)
    try:
        token, refresh, csrf = BrowserAuthService(db).login(data.identifier, data.password)
    except AuthenticationError:
        raise HTTPException(status_code=401, detail="Las credenciales ingresadas no son válidas.")
    _set_browser_cookies(response, refresh, csrf)
    return token


@router.post("/browser/refresh", response_model=BrowserToken)
def browser_refresh(response: Response, request: Request,
                    refresh: str | None = Cookie(None, alias=REFRESH_COOKIE),
                    csrf_cookie: str | None = Cookie(None, alias=CSRF_COOKIE),
                    csrf_header: str | None = Header(None, alias="X-CSRF-Token"),
                    db: Session = Depends(get_db)) -> BrowserToken:
    _validate_origin(request)
    csrf = _validate_csrf(csrf_cookie, csrf_header)
    if not refresh:
        raise HTTPException(status_code=401, detail="Sesión no válida")
    try:
        token, new_refresh, new_csrf = BrowserAuthService(db).refresh(refresh, csrf)
    except AuthenticationError:
        _clear_browser_cookies(response)
        raise HTTPException(status_code=401, detail="Sesión no válida")
    _set_browser_cookies(response, new_refresh, new_csrf)
    return token


@router.post("/browser/logout", status_code=204)
def browser_logout(response: Response, request: Request,
                   refresh: str | None = Cookie(None, alias=REFRESH_COOKIE),
                   csrf_cookie: str | None = Cookie(None, alias=CSRF_COOKIE),
                   csrf_header: str | None = Header(None, alias="X-CSRF-Token"),
                   db: Session = Depends(get_db)) -> Response:
    _validate_origin(request)
    if refresh or csrf_cookie or csrf_header:
        _validate_csrf(csrf_cookie, csrf_header)
    BrowserAuthService(db).logout(refresh)
    _clear_browser_cookies(response)
    response.status_code = 204
    return response


@router.get("/browser/session", response_model=BrowserSession)
def browser_session(refresh: str | None = Cookie(None, alias=REFRESH_COOKIE),
                    db: Session = Depends(get_db)) -> BrowserSession:
    if not refresh:
        raise HTTPException(status_code=401, detail="Sesión no válida")
    try:
        user = BrowserAuthService(db).session(refresh)
    except AuthenticationError:
        raise HTTPException(status_code=401, detail="Sesión no válida")
    return BrowserSession(authenticated=True, user=UserRead.model_validate(user))
