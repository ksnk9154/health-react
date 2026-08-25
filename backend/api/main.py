from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes.auth import router as auth_router
from api.routes.records import router as records_router
from api.routes.admin import router as admin_router
from api.routes.admin_analytics import router as admin_analytics_router
from api.routes.exports import router as exports_router
from api.routes.llm import router as llm_router
from api.routes.documents import router as documents_router
from api.routes.notifications import router as notifications_router
from api.routes.health_observations import router as health_observations_router
from api.routes.health_overview import router as health_overview_router
from api.routes.weight_goals import router as weight_goals_router
from api.routes.analyses import router as analyses_router
from db.migrate import create_tables_if_needed
from db.session import get_db_session

from auth.bootstrap import bootstrap_admin_if_needed



def create_app() -> FastAPI:
    app = FastAPI(title="Health API", version="0.1.0")

    # Create database tables on startup
    create_tables_if_needed()

    # Ensure admin user exists (safe/idempotent)
    bootstrap_admin_if_needed(get_db_session)


    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )


    app.include_router(auth_router, prefix="/auth", tags=["auth"])
    app.include_router(records_router, prefix="/records", tags=["records"])
    app.include_router(admin_router, prefix="/admin", tags=["admin"])
    app.include_router(
        admin_analytics_router,
        prefix="/admin",
        tags=["admin-analytics"],
    )
    app.include_router(exports_router, prefix="/exports", tags=["exports"])
    app.include_router(llm_router, prefix="/llm", tags=["llm"])
    app.include_router(documents_router, prefix="/api/v1", tags=["documents"])
    app.include_router(notifications_router, prefix="/api/notifications", tags=["notifications"])
    app.include_router(health_observations_router, prefix="/api/v1/health-observations", tags=["health-observations"])
    app.include_router(health_overview_router, prefix="/api/v1/health-overview", tags=["health-overview"])
    app.include_router(weight_goals_router, prefix="/api/v1/weight-goal", tags=["weight-goal"])
    app.include_router(analyses_router, prefix="/api/v1/documents", tags=["analyses"])

    # Optional: serve the React/Vite frontend from this backend.
    # When deployed as a combined container (backend/Dockerfile.multicloud),
    # the built frontend is copied into backend/static/. Mounting it here lets a
    # single container serve both the SPA and the API (no CORS issues).
    import os as _os
    _static_dir = _os.path.join(
        _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "static"
    )
    if _os.path.isdir(_static_dir):
        from fastapi.staticfiles import StaticFiles
        app.mount("/", StaticFiles(directory=_static_dir, html=True), name="frontend")

    return app


app = create_app()
