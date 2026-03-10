from fastapi import FastAPI
from app.core.config import settings
from app.api.routes import auth,organization, item, audit

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Secure, async, multi-tenant backend service",
    version="1.0.0"
)


app.include_router(auth.router)
app.include_router(organization.router)
app.include_router(item.router)
app.include_router(audit.router)

@app.get("/health")
async def health_check():
    return {"status": "healthy"}