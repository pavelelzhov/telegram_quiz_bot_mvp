from __future__ import annotations

import unittest

from app.core.decision_audit_service import DecisionAuditEvent, DecisionAuditService


class DecisionAuditServiceTests(unittest.TestCase):
    def test_record_and_filter_by_chat(self) -> None:
        service = DecisionAuditService(keep_last=2)
        service.record(DecisionAuditEvent(chat_id=1, user_id=10, stage='decision_suppressed'))
        service.record(DecisionAuditEvent(chat_id=2, user_id=11, stage='reply_sent'))
        service.record(DecisionAuditEvent(chat_id=1, user_id=12, stage='validator_suppressed'))

        recent_all = service.recent()
        self.assertEqual(len(recent_all), 2)
        self.assertEqual(recent_all[0].chat_id, 2)
        self.assertEqual(recent_all[1].chat_id, 1)

        chat_one = service.recent(chat_id=1)
        self.assertEqual(len(chat_one), 1)
        self.assertEqual(chat_one[0].stage, 'validator_suppressed')


if __name__ == '__main__':
    unittest.main()
