from app import db
from datetime import datetime


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    yandex_id = db.Column(db.String(64), unique=True, nullable=False)
    name = db.Column(db.String(128))
    email = db.Column(db.String(128))
    oauth_token = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    projects = db.relationship("Project", backref="user", lazy=True)


class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    site_name = db.Column(db.String(256), nullable=False)
    objective = db.Column(db.String(32))  # sales, optimize, efficiency, audience
    metrika_counter_id = db.Column(db.String(64))
    webmaster_host_id = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reports = db.relationship("Report", backref="project", lazy=True)
    messages = db.relationship("ChatMessage", backref="project", lazy=True)


class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), nullable=False)
    raw_data = db.Column(db.Text)  # JSON string with Metrika + Webmaster data
    ai_report_text = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), nullable=False)
    role = db.Column(db.String(16), nullable=False)  # "user" or "assistant"
    text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class IntegrationLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("project.id"), nullable=True)
    source = db.Column(db.String(32), nullable=False)  # metrika, webmaster, agent
    level = db.Column(db.String(16), nullable=False)  # info, warning, error
    method = db.Column(db.String(64))  # report_search_queries, call_agent, etc.
    request_url = db.Column(db.Text)
    request_params = db.Column(db.Text)  # JSON
    status_code = db.Column(db.Integer)
    response_snippet = db.Column(db.Text)  # first 1000 chars of response or error
    error_message = db.Column(db.Text)
    duration_ms = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
