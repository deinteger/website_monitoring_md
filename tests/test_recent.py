import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
sys.path.insert(0, HERE)

import collect  # noqa: E402
import fixture_site as fx  # noqa: E402
import make_schedule  # noqa: E402
import recent_changes  # noqa: E402
import run_all  # noqa: E402

REGION = {"tag": "table", "class": "board"}


class RecentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = fx.start()
        cls.port = cls.srv.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        self.ws = tempfile.mkdtemp()
        fx.STATE.pages.clear()
        fx.STATE.pages["/notice"] = fx.board([("n3", "2026-08-24"), ("n2", "2026-08-20"), ("n1", "2026-08-01")])
        fx.STATE.pages["/data"] = fx.board([("d1", "2026-05-20")])
        fx.write_workspace(self.ws, self.port, [
            {"id": "notice", "name": "공지", "url": "/notice", "cycle": "daily", "region": REGION, "owner": "총무과"},
            {"id": "data", "name": "자료실", "url": "/data", "cycle": "daily", "region": REGION, "owner": "기획과"}])

    def tearDown(self):
        shutil.rmtree(self.ws, ignore_errors=True)

    def collect(self, mode, today):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            return collect.main(["--workspace", self.ws, "--mode", mode, "--today", today])

    def recent(self, *args):
        buf, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
            code = recent_changes.main(["--workspace", self.ws, "--json"] + list(args))
        return code, (json.loads(buf.getvalue()) if buf.getvalue().strip().startswith("{") else buf.getvalue()), err.getvalue()

    def scenario(self):
        self.collect("full", "2026-08-26")
        fx.STATE.pages["/notice"] = fx.board([("n5", "2026-08-27"), ("n4", "2026-08-26"), ("n3", "2026-08-24"), ("n2", "2026-08-20"), ("n1", "2026-08-01")])
        fx.STATE.pages["/data"] = fx.board([("d2", "2026-08-27"), ("d1", "2026-05-20")])
        self.collect("incremental", "2026-08-28")

    def test_yesterday_and_day_before(self):
        """'어제 그제' = --days 2 (오늘 제외). 게시일이 기간 안인 글만 나온다."""
        self.scenario()
        code, r, _ = self.recent("--days", "2", "--today", "2026-08-28")
        self.assertEqual(code, 0)
        self.assertEqual((r["from"], r["to"]), ("2026-08-26", "2026-08-27"))
        self.assertEqual(sorted(p["title"] for p in r["posts"]), ["d2", "n4", "n5"])
        self.assertEqual(r["posts"][0]["date"], "2026-08-27")
        self.assertEqual(dict((b["board"], b["count"]) for b in r["boards"]), {"공지": 2, "자료실": 1})
        self.assertEqual(r["warnings"], [])
        self.assertTrue(all(p["url"].startswith("http://127.0.0.1") for p in r["posts"]))

    def test_transition_improved(self):
        self.scenario()
        _, r, _ = self.recent("--days", "2", "--today", "2026-08-28")
        self.assertEqual([x["board"] for x in r["transitions"]["improved"]], ["자료실"])     # 지연 -> 정상
        self.assertEqual(r["transitions"]["newly_stale"], [])

    def test_by_seen_excludes_baseline(self):
        self.scenario()
        _, r, _ = self.recent("--days", "1", "--include-today", "--by", "seen", "--today", "2026-08-28")
        self.assertEqual(sorted(p["title"] for p in r["posts"]), ["d2", "n4", "n5"])       # 8/28에 처음 확인한 글
        _, r, _ = self.recent("--from", "2026-08-24", "--to", "2026-08-24", "--today", "2026-08-28")
        self.assertEqual([p["title"] for p in r["posts"]], ["n3"])
        self.assertIsNone(r["posts"][0]["first_seen"])                                     # 최초 수집분은 확인일 알 수 없음
        _, r, _ = self.recent("--from", "2026-08-24", "--to", "2026-08-24", "--by", "seen", "--today", "2026-08-28")
        self.assertEqual(r["posts"], [])

    def test_warns_when_data_is_stale(self):
        self.scenario()
        _, r, _ = self.recent("--days", "2", "--today", "2026-08-30")       # 기간 8/28~8/29, 마지막 점검 8/28
        self.assertTrue(any("마지막 점검일은 2026-08-28" in w for w in r["warnings"]))

    def test_refresh_runs_incremental_first(self):
        self.scenario()
        fx.STATE.pages["/notice"] = fx.board([("n6", "2026-08-29"), ("n5", "2026-08-27"), ("n4", "2026-08-26"), ("n3", "2026-08-24")])
        _, r, _ = self.recent("--days", "2", "--today", "2026-08-30")
        self.assertNotIn("n6", [p["title"] for p in r["posts"]])           # 점검 전에는 새 글을 모른다
        code, r, err = self.recent("--days", "2", "--today", "2026-08-30", "--refresh")
        self.assertIn("n6", [p["title"] for p in r["posts"]])
        self.assertIn("최신화", err)

    def test_markdown_and_files(self):
        self.scenario()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            recent_changes.main(["--workspace", self.ws, "--days", "2", "--today", "2026-08-28"])
        md = buf.getvalue()
        self.assertIn("최근 현행화 조회 (2026-08-26 ~ 2026-08-27, 게시일 기준)", md)
        self.assertIn("게시물 **3건**", md)
        self.assertTrue(os.path.exists(os.path.join(self.ws, "reports", "recent", "2026-08-26_2026-08-27_posted.json")))

    def test_run_all_writes_latest_for_chat_ai(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            run_all.main(["--workspace", self.ws, "--mode", "full", "--today", "2026-08-26", "--judge", "no"])
        latest = json.load(open(os.path.join(self.ws, "reports", "recent", "latest.json"), encoding="utf-8"))
        self.assertEqual((latest["from"], latest["to"]), ("2026-08-13", "2026-08-26"))   # 최근 14일(오늘 포함)
        self.assertEqual(sorted(p["title"] for p in latest["posts"]), ["n2", "n3"])

    def test_no_data_message(self):
        code, _, _ = self.recent("--today", "2026-08-28")
        self.assertEqual(code, 1)


class ScheduleTests(unittest.TestCase):
    def gen(self, *a):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
            code = make_schedule.main(list(a))
        return code, buf.getvalue()

    def test_windows_command_keeps_windows_paths(self):
        code, out = self.gen("--os", "windows", "--time", "07:10", "--workspace", "C:\\work\\ws", "--root", "C:\\kit")
        self.assertEqual(code, 0)
        self.assertIn("schtasks /Create /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 07:10", out)
        self.assertIn("C:\\kit\\scripts\\run_all.py", out)
        self.assertIn("C:\\work\\ws", out)
        self.assertNotIn("/home/", out.split("\n")[0])
        self.assertIn("schtasks /Delete", out)

    def test_linux_cron_monthly_full(self):
        code, out = self.gen("--os", "linux", "--time", "07:30", "--schedule", "monthly", "--day", "1", "--mode", "full",
                             "--workspace", "/home/me/ws", "--root", "/home/me/kit", "--typo-check")
        self.assertIn("30 7 1 * * ", out)
        self.assertIn("/home/me/kit/scripts/run_all.py --workspace /home/me/ws --mode full --judge no --typo-check", out)

    def test_validation(self):
        self.assertEqual(self.gen("--os", "linux", "--time", "25:99")[0], 1)
        self.assertEqual(self.gen("--os", "linux", "--schedule", "monthly", "--day", "31")[0], 1)


if __name__ == "__main__":
    unittest.main()
