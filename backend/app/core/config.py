from functools import lru_cache
from urllib.parse import quote_plus
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Territorio Electoral API"
    app_env: str = "development"
    app_debug: bool = True
    api_v1_prefix: str = "/api/v1"
    postgres_db: str = "territorio_electoral"
    postgres_user: str = "territorio_user"
    postgres_password: str = "territorio_password"
    postgres_host: str = "db"
    postgres_port: int = 5432
    secret_key: str = "replace-with-a-secure-secret-at-least-32-chars"
    access_token_expire_minutes: int = 60
    browser_access_token_minutes: int = 15
    browser_refresh_token_days: int = 7
    browser_refresh_token_hmac_secret: str = "replace-with-secure-random-secret"
    browser_cookie_secure: bool = False
    browser_cookie_samesite: str = "lax"
    browser_max_active_sessions: int = 5
    browser_allowed_origins: str = "http://localhost:5173"
    frontend_origins: str = "http://localhost:5173"
    trusted_hosts: str = "localhost,127.0.0.1,testserver"
    enable_api_docs: bool = True
    secure_headers_enabled: bool = True
    jwt_algorithm: str = "HS256"
    initial_admin_email: str = "admin@example.com"
    initial_admin_username: str = "admin"
    initial_admin_password: str = "ChangeThisPassword123"
    initial_admin_first_name: str = "Administrador"
    initial_admin_last_name: str = "Sistema"
    survey_submission_hmac_secret: str = "replace-with-secure-random-secret"
    survey_min_aggregate_responses: int = 5
    data_import_max_file_mb: int = 100
    data_import_max_errors: int = 1000
    data_import_batch_size: int = 1000
    map_max_features: int = 5000
    map_max_point_features_without_clustering: int = 500
    map_default_simplify_tolerance: float = 0.0001
    map_max_simplify_tolerance: float = 0.01
    map_max_geojson_bytes: int = 10000000
    map_geometry_import_max_file_mb: int = 100
    map_cluster_min_zoom: int = 0
    map_cluster_max_zoom: int = 22
    report_output_dir: str = "/app/generated-reports"
    report_max_file_mb: int = 50
    report_max_rows: int = 50000
    report_artifact_retention_days: int = 30
    report_max_active_artifacts_per_campaign: int = 100
    report_max_selected_surveys: int = 20
    report_max_selected_processes: int = 10
    report_max_selected_indicators: int = 50
    report_pdf_max_table_rows: int = 5000
    alert_max_open_per_campaign: int = 1000
    alert_default_inactivity_days: int = 14
    alert_default_data_stale_days: int = 365
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore")

    @model_validator(mode="after")
    def validate_security_settings(self) -> "Settings":
        report_limits = (self.report_max_file_mb, self.report_max_rows, self.report_artifact_retention_days, self.report_max_active_artifacts_per_campaign, self.report_max_selected_surveys, self.report_max_selected_processes, self.report_max_selected_indicators, self.report_pdf_max_table_rows, self.alert_max_open_per_campaign, self.alert_default_inactivity_days, self.alert_default_data_stale_days)
        if not self.report_output_dir.strip() or any(value <= 0 for value in report_limits):
            raise ValueError("La configuración de informes y alertas debe ser positiva")
        if not self.secret_key.strip():
            raise ValueError("SECRET_KEY no puede estar vacía")
        if self.jwt_algorithm != "HS256":
            raise ValueError("JWT_ALGORITHM debe ser HS256")
        if self.access_token_expire_minutes <= 0:
            raise ValueError("ACCESS_TOKEN_EXPIRE_MINUTES debe ser positivo")
        if self.browser_access_token_minutes <= 0 or self.browser_refresh_token_days <= 0 or self.browser_max_active_sessions <= 0:
            raise ValueError("La configuración de sesiones de navegador debe ser positiva")
        if self.browser_cookie_samesite.lower() not in {"lax", "strict", "none"}:
            raise ValueError("BROWSER_COOKIE_SAMESITE debe ser lax, strict o none")
        if self.data_import_max_file_mb <= 0 or self.data_import_max_errors <= 0 or self.data_import_batch_size <= 0:
            raise ValueError("La configuraci?n de importaci?n debe ser positiva")
        if self.map_max_features <= 0 or not 0 < self.map_max_point_features_without_clustering <= self.map_max_features:
            raise ValueError("Los límites de features del mapa son inválidos")
        if not 0 <= self.map_default_simplify_tolerance <= self.map_max_simplify_tolerance:
            raise ValueError("Las tolerancias de simplificación son inválidas")
        if self.map_max_geojson_bytes <= 0 or self.map_geometry_import_max_file_mb <= 0:
            raise ValueError("Los límites de tamaño geográfico deben ser positivos")
        if not 0 <= self.map_cluster_min_zoom <= self.map_cluster_max_zoom <= 22:
            raise ValueError("El rango de zoom del mapa es inválido")
        if self.survey_min_aggregate_responses < 3:
            raise ValueError("SURVEY_MIN_AGGREGATE_RESPONSES debe ser al menos 3")
        if self.app_env.lower() == "production" and self.survey_submission_hmac_secret.lower() in {"replace-with-secure-random-secret", "change-me", "secret", ""}:
            raise ValueError("SURVEY_SUBMISSION_HMAC_SECRET debe configurarse de forma segura en producci?n")
        if self.app_env.lower() == "production" and self.secret_key.lower() in {"replace-with-a-secure-secret-at-least-32-chars", "change-me", "secret"}:
            raise ValueError("SECRET_KEY debe configurarse de forma segura en producción")
        if self.app_env.lower() == "production":
            if self.browser_refresh_token_hmac_secret.lower() in {"replace-with-secure-random-secret", "change-me", "secret", ""}:
                raise ValueError("BROWSER_REFRESH_TOKEN_HMAC_SECRET debe configurarse de forma segura en producción")
            if not self.browser_cookie_secure:
                raise ValueError("BROWSER_COOKIE_SECURE debe estar activo en producción")
        return self

    @property
    def frontend_origin_list(self) -> list[str]:
        return [value.strip() for value in self.frontend_origins.split(",") if value.strip()]

    @property
    def browser_origin_list(self) -> list[str]:
        return [value.strip() for value in self.browser_allowed_origins.split(",") if value.strip()]

    @property
    def trusted_host_list(self) -> list[str]:
        return [value.strip() for value in self.trusted_hosts.split(",") if value.strip()]

    @property
    def database_url(self) -> str:
        user, password = quote_plus(self.postgres_user), quote_plus(self.postgres_password)
        return f"postgresql+psycopg://{user}:{password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
