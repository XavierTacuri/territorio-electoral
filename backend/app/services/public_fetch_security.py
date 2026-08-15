import ipaddress,socket
from urllib.parse import urljoin,urlparse
from app.core.config import settings
from app.services.exceptions import BusinessRuleError

BLOCKED_HOSTS={"localhost","localhost.localdomain"}
def validate_public_url(url:str,*,allow_private:bool|None=None)->str:
    parsed=urlparse(url)
    if parsed.scheme not in {"http","https"} or not parsed.hostname or parsed.username or parsed.password:raise BusinessRuleError("URL pública inválida")
    host=parsed.hostname.rstrip(".").lower()
    if host in BLOCKED_HOSTS:raise BusinessRuleError("Destino bloqueado por protección SSRF")
    allowed=settings.public_fetch_allow_private_hosts if allow_private is None else allow_private
    try:addresses={x[4][0] for x in socket.getaddrinfo(host,parsed.port or (443 if parsed.scheme=="https" else 80),type=socket.SOCK_STREAM)}
    except socket.gaierror as exc:raise BusinessRuleError("No se pudo resolver el destino") from exc
    for raw in addresses:
        ip=ipaddress.ip_address(raw)
        if not allowed and (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified):raise BusinessRuleError("Destino bloqueado por protección SSRF")
    return url
def validate_redirect(base:str,location:str,*,allow_private:bool|None=None)->str:return validate_public_url(urljoin(base,location),allow_private=allow_private)
