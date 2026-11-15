"""ЛР8: RedactingAuditTrail — журнал аудиту операцій без ПДн (контракт AuditSink, ЛР4)."""
import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone

from privacy.sanitizer import redact


class RedactingAuditTrail:
    def __init__(self, logger=None):
        self._log = logger or logging.getLogger("warehouse")

    def record(self, action, movement, actor, rid=None):
        event = {"action": action, "rid": rid, "actor": actor,
                 "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "movement": redact(asdict(movement))}
        self._log.info(json.dumps(event, ensure_ascii=False, default=str))
