from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from desktop.monitoring.constants import (
    BROWSERS,
    DEFAULT_RULES,
    PDF_READERS,
    TERMINALS,
    PROJECT_CAPABLE_EXECUTABLES,
    SITE_CAPABLE_EXECUTABLES,
)
from desktop.monitoring.state import Classification, SessionContext


class ApplicationClassifier:
    def __init__(self, repository: Any) -> None:
        self.repository = repository

    def classify(
        self,
        executable_name: str,
        session: SessionContext | None = None,
        *,
        transient_title: str | None = None,
    ) -> Classification:
        normalized = executable_name.lower()
        manual = self.repository.get_application_rule(normalized)
        if manual is not None and manual.enabled:
            return Classification(
                manual.classification,
                manual.category,
                "manual_rule",
            )

        if normalized in PROJECT_CAPABLE_EXECUTABLES and transient_title:
            normalized_title = self._normalize_text(transient_title)
            for rule in self.repository.get_project_rules():
                terms = json.loads(rule.match_terms)
                if any(term in normalized_title for term in terms):
                    return Classification(
                        rule.classification,
                        rule.category,
                        "project_rule",
                        project_rule_id=rule.id,
                        project_key=rule.project_key,
                        project_display_name=rule.display_name,
                        context_source="project_rule",
                    )

        if (
            normalized in SITE_CAPABLE_EXECUTABLES
            and self._is_chatgpt_title(transient_title)
        ):
            return Classification(
                "productive",
                "study",
                "site_allowlist",
                site_key="chatgpt",
                context_source="site_allowlist",
            )

        default = DEFAULT_RULES.get(normalized)
        if default and default[1] == "ignored":
            return Classification(default[1], default[2], "default_rule")

        session_result = self._session_classification(normalized, session)
        if session_result is not None:
            return session_result

        if default:
            return Classification(default[1], default[2], "default_rule")
        return Classification("neutral", "other", "fallback")

    @staticmethod
    def _normalize_text(value: str) -> str:
        ascii_text = unicodedata.normalize("NFKD", value).encode(
            "ascii", "ignore"
        ).decode("ascii")
        return re.sub(r"\s+", " ", ascii_text.casefold()).strip()

    @staticmethod
    def _is_chatgpt_title(value: str | None) -> bool:
        if not value:
            return False
        normalized = re.sub(r"\s+", " ", value).strip().casefold()
        return normalized == "chatgpt" or normalized.endswith(
            (" - chatgpt", " – chatgpt", " — chatgpt")
        )

    @staticmethod
    def _session_classification(
        executable_name: str,
        session: SessionContext | None,
    ) -> Classification | None:
        if session is None:
            return None
        session_type = session.session_type
        if session_type in {"study", "reading"} and (
            executable_name in BROWSERS or executable_name in PDF_READERS
        ):
            return Classification("productive", "study", "session_context")
        if session_type == "programming" and (
            executable_name in BROWSERS
            or executable_name in TERMINALS
            or executable_name
            in {"code.exe", "pycharm64.exe", "devenv.exe"}
        ):
            return Classification(
                "productive",
                "programming",
                "session_context",
            )
        if session.related_category == "work" and executable_name in BROWSERS:
            return Classification("productive", "work", "session_context")
        return None
