from flask import Blueprint, jsonify


system_api = Blueprint("system_api", __name__)


@system_api.get("/health")
def health():
    return jsonify(status="ok")
