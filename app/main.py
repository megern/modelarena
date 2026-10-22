from .access import AccessControl
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from .core import BenchmarkRequest, analyze

app = FastAPI(title="ModelArena", version="0.4.0")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def index():
    return Path(__file__).with_name("index.html").read_text()


@app.post("/analyze")
def run(request: BenchmarkRequest):
    return analyze(request)


from .guard import InputGuard

app.add_middleware(InputGuard)


app.mount(
    "/assets", StaticFiles(directory=Path(__file__).with_name("static")), name="assets"
)


@app.get("/guide", response_class=PlainTextResponse)
def user_guide():
    return Path(__file__).with_name("USER_GUIDE.md").read_text()


from fastapi import HTTPException
from .jobs import JobSubmission, QueueFull, manager


@app.post("/jobs", status_code=202)
def submit_job(request: JobSubmission):
    try:
        return manager.submit(request)
    except QueueFull as error:
        raise HTTPException(status_code=429, detail=str(error)) from error


@app.get("/jobs/{job_id}")
def job_status(job_id: str):
    try:
        return manager.snapshot(job_id)
    except KeyError as error:
        raise HTTPException(
            status_code=404, detail="Unknown or expired in-memory job"
        ) from error


@app.delete("/jobs/{job_id}", status_code=202)
def cancel_job(job_id: str):
    try:
        return manager.cancel(job_id)
    except KeyError as error:
        raise HTTPException(
            status_code=404, detail="Unknown or expired in-memory job"
        ) from error


app.add_middleware(AccessControl)
