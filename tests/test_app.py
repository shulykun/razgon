import pytest
import json
from app import create_app, db as _db
from app.models import User, Project, Report, ChatMessage, IntegrationLog


def _make_project(**kwargs):
    """Helper: create a project with required user_id."""
    defaults = {"site_name": "test.com", "objective": "sales", "metrika_counter_id": "999", "user_id": 1}
    defaults.update(kwargs)
    return Project(**defaults)


@pytest.fixture
def app():
    """Create test app with in-memory SQLite."""
    app = create_app()
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test"
    app.config["WTF_CSRF_ENABLED"] = False

    with app.app_context():
        _db.create_all()
        # Create a default user for FK
        user = User(yandex_id="999", name="Test User")
        _db.session.add(user)
        _db.session.commit()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_session(client):
    """Simulate logged-in user with OAuth token."""
    with client.session_transaction() as sess:
        sess["oauth_token"] = "test-token"
        sess["yandex_id"] = "12345"
        sess["user_name"] = "Test User"
    return client


# ==========================================
# Test: Pages load
# ==========================================

class TestPages:
    def test_promo_page(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "Начать" in html

    def test_dashboard_loads(self, client):
        resp = client.get("/dashboard")
        assert resp.status_code == 200

    def test_setup_requires_auth(self, client):
        resp = client.get("/setup/choose-site")
        assert resp.status_code in (200, 302)

    def test_setup_with_auth(self, auth_session):
        resp = auth_session.get("/setup/choose-site")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "Настройка проекта" in html
        assert "Увеличить охват" in html

    def test_report_page(self, auth_session, app):
        with app.app_context():
            project = _make_project()
            _db.session.add(project)
            _db.session.commit()
            pid = project.id
        resp = auth_session.get(f"/project/{pid}/report")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "chat" in html.lower() or "Чат" in html


# ==========================================
# Test: API endpoints
# ==========================================

class TestAPI:
    def test_get_goals(self, auth_session):
        resp = auth_session.get("/api/counters/12345/goals")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert any(g["id"] == "ecommerce_revenue" for g in data)
        assert any(g["type"] == "action" for g in data)

    def test_create_project(self, auth_session, app):
        resp = auth_session.post("/api/projects", json={
            "counter_id": "12345",
            "goal_id": "67890",
            "objective": "sales",
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert "project_id" in data

        with app.app_context():
            project = _db.session.get(Project, data["project_id"])
            assert project is not None
            assert project.objective == "sales"
            assert project.metrika_counter_id == "12345"

    def test_project_status_empty(self, auth_session, app):
        with app.app_context():
            project = _make_project()
            _db.session.add(project)
            _db.session.commit()
            pid = project.id

        resp = auth_session.get(f"/api/projects/{pid}/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ready"] is False

    def test_project_status_ready(self, auth_session, app):
        with app.app_context():
            project = _make_project()
            _db.session.add(project)
            _db.session.commit()
            report = Report(project_id=project.id, ai_report_text="Ваш отчёт готов!")
            _db.session.add(report)
            _db.session.commit()
            pid = project.id

        resp = auth_session.get(f"/api/projects/{pid}/status")
        data = resp.get_json()
        assert data["ready"] is True
        assert "отчёт" in data["text"]

    def test_project_status_error(self, auth_session, app):
        with app.app_context():
            project = _make_project()
            _db.session.add(project)
            _db.session.commit()
            report = Report(project_id=project.id, ai_report_text="Ошибка генерации: timeout")
            _db.session.add(report)
            _db.session.commit()
            pid = project.id

        resp = auth_session.get(f"/api/projects/{pid}/status")
        data = resp.get_json()
        assert data["ready"] is False
        assert data["error"] is True

    def test_chat_stub(self, auth_session, app):
        with app.app_context():
            project = _make_project()
            _db.session.add(project)
            _db.session.commit()
            pid = project.id

        resp = auth_session.post(f"/api/projects/{pid}/chat", json={"message": "Что делать?"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["role"] == "assistant"
        assert len(data["text"]) > 0

    def test_project_logs_empty(self, auth_session, app):
        with app.app_context():
            project = _make_project()
            _db.session.add(project)
            _db.session.commit()
            pid = project.id

        resp = auth_session.get(f"/api/projects/{pid}/logs")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) == 0


# ==========================================
# Test: DB models
# ==========================================

class TestModels:
    def test_user_create(self, app):
        with app.app_context():
            user = User(yandex_id="111", name="Test", email="test@test.com")
            _db.session.add(user)
            _db.session.commit()
            assert user.id is not None
            assert user.name == "Test"

    def test_project_with_reports(self, app):
        with app.app_context():
            project = _make_project()
            _db.session.add(project)
            _db.session.commit()
            report = Report(project_id=project.id, ai_report_text="Test report")
            _db.session.add(report)
            _db.session.commit()

            assert len(project.reports) == 1
            assert project.reports[0].ai_report_text == "Test report"

    def test_chat_messages(self, app):
        with app.app_context():
            project = _make_project()
            _db.session.add(project)
            _db.session.commit()
            msg1 = ChatMessage(project_id=project.id, role="user", text="Привет")
            msg2 = ChatMessage(project_id=project.id, role="assistant", text="Здравствуйте!")
            _db.session.add_all([msg1, msg2])
            _db.session.commit()
            assert len(project.messages) == 2

    def test_integration_log(self, app):
        with app.app_context():
            project = _make_project()
            _db.session.add(project)
            _db.session.commit()

            log = IntegrationLog(
                source="metrika", level="error", method="report_search_queries",
                project_id=project.id, status_code=403,
                error_message="Forbidden: invalid OAuth token",
                duration_ms=150,
            )
            _db.session.add(log)
            _db.session.commit()

            saved = IntegrationLog.query.first()
            assert saved.source == "metrika"
            assert saved.level == "error"
            assert saved.duration_ms == 150


# ==========================================
# Test: Integration modules (stubs)
# ==========================================

class TestIntegrations:
    def test_metrika_stubs(self):
        from app.integrations.metrika import (
            report_entry_pages, report_sources, report_keywords,
            report_day_hour, report_cities, report_ecommerce_funnel
        )
        r1 = report_entry_pages("tok", "123")
        assert "totals" in r1 and "rows" in r1

        r2 = report_sources("tok", "123")
        assert "totals" in r2 and "rows" in r2

        r3 = report_keywords("tok", "123")
        assert "totals" in r3 and "rows" in r3

        r4 = report_day_hour("tok", "123")
        assert "by_day" in r4 and "by_hour" in r4

        r5 = report_cities("tok", "123")
        assert "totals" in r5 and "rows" in r5

        r6 = report_ecommerce_funnel("tok", "123")
        assert isinstance(r6, list)
        assert len(r6) == 5
        assert r6[0]["step"] == "Просмотр товара"

    def test_webmaster_stubs(self):
        from app.integrations.webmaster import (
            report_search_queries, report_low_ctr_queries,
            report_crawl_errors, report_excluded_pages,
            report_indexing_status, report_popular_search_pages
        )
        r1 = report_search_queries("tok", "host1")
        assert "queries" in r1

        r2 = report_low_ctr_queries("tok", "host1")
        assert "queries" in r2

        r3 = report_crawl_errors("tok", "host1")
        assert "summary" in r3 and "top_errors" in r3

        r4 = report_excluded_pages("tok", "host1")
        assert "reasons" in r4

        r5 = report_indexing_status("tok", "host1")
        assert "indexed" in r5 and "excluded" in r5

        r6 = report_popular_search_pages("tok", "host1")
        assert "pages" in r6

    def test_agent_client_exists(self):
        from app.agent.client import call_agent
        assert callable(call_agent)

    def test_report_service_metrics(self):
        from app.integrations.metrika import _base_metrics
        assert "ym:s:visits" in _base_metrics()
        assert "goal" not in _base_metrics()

        m = _base_metrics("12345")
        assert "ym:s:goal12345reaches" in m

        m = _base_metrics("ecommerce_revenue")
        assert "ym:s:ecommerceRevenue" in m
        assert "goal" not in m
