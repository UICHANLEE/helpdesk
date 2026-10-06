from __future__ import annotations

import unittest
from copy import deepcopy

from backend.sheets.sync import SheetSyncError, plan


class SheetSyncPlanTest(unittest.TestCase):
    def setUp(self) -> None:
        self.headers = ["Incident ID", "질문", "상태"]
        self.properties = {"질문 로그": {"sheetId": 0, "rowCount": 2}}
        self.data = {"tabs": [{"name": "질문 로그", "key_column": "A", "headers": self.headers,
                               "rows": [["INC-1", "기존 질문", "resolved"],
                                        ["INC-2", '=IMPORTDATA("https://example.com")', "new"]]}]}

    def test_upsert_and_retry_are_idempotent(self) -> None:
        first = plan(self.data, {"질문 로그": [self.headers, ["INC-1", "기존 질문", "resolved"]]}, self.properties)
        self.assertEqual((first["inserted_rows"], first["updated_rows"], first["unchanged_rows"]), (1, 0, 1))
        self.assertEqual(first["writes"][0]["range"], "'질문 로그'!A3:C3")
        self.assertEqual(first["writes"][0]["values"][0][1], '=IMPORTDATA("https://example.com")')
        self.assertEqual(first["expansions"][0]["appendDimension"]["length"], 1)

        current = {"질문 로그": [self.headers, *deepcopy(self.data["tabs"][0]["rows"])]}
        retry = plan(self.data, current, {"질문 로그": {"sheetId": 0, "rowCount": 3}})
        self.assertEqual(retry["writes"], [])
        self.assertEqual(retry["unchanged_rows"], 2)

        self.data["tabs"][0]["rows"][0][2] = "verifying"
        changed = plan(self.data, current, {"질문 로그": {"sheetId": 0, "rowCount": 3}})
        self.assertEqual((changed["updated_rows"], changed["inserted_rows"]), (1, 0))
        self.assertEqual(changed["writes"][0]["range"], "'질문 로그'!A2:C2")

    def test_duplicate_sheet_key_stops_upload(self) -> None:
        with self.assertRaises(SheetSyncError):
            plan(self.data, {"질문 로그": [self.headers, ["INC-1"], ["INC-1"]]}, self.properties)


if __name__ == "__main__":
    unittest.main()
