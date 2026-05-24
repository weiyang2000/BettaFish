from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

LEGACY_TERMS = (
    "streamlit",
    "SingleEngineApp",
    "8501",
    "8502",
    "8503",
    "streamlit_reports",
    "localhost:5000",
)

PRODUCTION_SURFACES = (
    "README.md",
    "README-EN.md",
    "Dockerfile",
    "docker-compose.yml",
    "app.py",
    "requirements.txt",
    ".gitignore",
    "docs/openapi/saas-platform.yaml",
    "docs/saas-frontend-integration.md",
    "apps/api/README.md",
    "apps/api/main.py",
    "apps/api/services/engines.py",
    "apps/web/src/lib/mock-data.ts",
    "apps/web/src/lib/types.ts",
    "apps/web/src/components/ConsoleShell.tsx",
    "apps/web/tests/saas-console.spec.ts",
    "apps/web/tests/saas-console-real-api.spec.ts",
    "ReportEngine/agent.py",
    "ReportEngine/flask_interface.py",
    "report_engine_only.py",
)


def test_production_surfaces_do_not_reference_legacy_streamlit_delivery():
    matches = []
    for relative_path in PRODUCTION_SURFACES:
        path = REPO_ROOT / relative_path
        assert path.exists(), f"Expected production surface to exist: {relative_path}"
        text = path.read_text(encoding="utf-8", errors="replace").lower()
        for term in LEGACY_TERMS:
            if term.lower() in text:
                matches.append(f"{relative_path}: {term}")

    assert matches == []


def test_legacy_streamlit_entrypoints_are_removed():
    removed_paths = [
        "templates/index.html",
        "SingleEngineApp/query_engine_streamlit_app.py",
        "SingleEngineApp/media_engine_streamlit_app.py",
        "SingleEngineApp/insight_engine_streamlit_app.py",
    ]

    for relative_path in removed_paths:
        assert not (REPO_ROOT / relative_path).exists(), f"Legacy entrypoint still exists: {relative_path}"


def test_runtime_dependencies_do_not_install_streamlit():
    requirements = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    active_requirements = [
        line.split("#", 1)[0].strip().lower()
        for line in requirements
        if line.split("#", 1)[0].strip()
    ]

    assert not any(line.startswith("streamlit") for line in active_requirements)


def test_deployment_defaults_launch_fastapi_without_legacy_ports():
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert 'CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]' in dockerfile
    assert "EXPOSE 8000" in dockerfile
    assert "uvicorn apps.api.main:app --host 0.0.0.0 --port 8000" in compose
    assert '"8000:8000"' in compose

    combined = f"{dockerfile}\n{compose}"
    for port in ("8501", "8502", "8503"):
        assert port not in combined


def test_engine_report_paths_use_neutral_directory_names():
    report_paths = [
        "ReportEngine/agent.py",
        "ReportEngine/flask_interface.py",
        "report_engine_only.py",
    ]

    for relative_path in report_paths:
        text = (REPO_ROOT / relative_path).read_text(encoding="utf-8", errors="replace")
        assert "engine_reports" in text
        assert "streamlit_reports" not in text
