"""Real local ASGI routes with fake flash execution; never touches a UART."""
import asyncio
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI

from hardware_claw.deployment import http as module
from hardware_claw.projects.service import ProjectService, ProjectError, ROOT
from tests.test_projects import DESIGN

BASE = "http://127.0.0.1:8000"
P = module.PREFIX


class DeploymentHTTPTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        parent = ROOT / "temp/flash-web-tests"
        parent.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = ProjectService.create("web fixture", "Interface mechanism fixture only",
                                             workspace=self.root / "workspace")
        design = copy.deepcopy(DESIGN)
        design.update(components=[], connections=[], dependencies=[], pin_defines={})
        self.project.update_design(0, design)
        self.project.scaffold(1)
        self.project.write_files(2, {"src/main.cpp": '#include <Arduino.h>\nvoid setup(){Serial.begin(115200);Serial.println("HWCLAW_BOOT");}\nvoid loop(){delay(100);}',
                                     "README.md": "Software fixture, not functional hardware evidence."})
        self.controller = module.FlashController(self.root / "workspace")
        app = FastAPI()
        app.include_router(module.create_router(self.controller))
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 1234)), base_url=BASE)
        await self.client.get(P)
        bootstrap = (await self.client.get(P + "/api/bootstrap")).json()
        self.headers = {"Origin": BASE, "X-HWClaw-CSRF": bootstrap["csrf"]}
        self.owner = self.client.cookies.get(module.COOKIE)
        self.port_patch = patch.object(module, "list_ports", return_value=[])
        self.ports = self.port_patch.start()
        self.prepare_patch = patch.object(module, "prepare_upload", side_effect=self.fake_prepare)
        self.prepare = self.prepare_patch.start()
        self.compile_patch = patch.object(module, "compile_project", new_callable=AsyncMock)
        self.compile = self.compile_patch.start()
        self.compile.return_value = {"verdict": "pass"}
        self.execute_patch = patch.object(module, "execute_upload", new_callable=AsyncMock)
        self.execute = self.execute_patch.start()
        self.execute.side_effect = AssertionError("Hardware execution was not expected")
        self.addCleanup(self.port_patch.stop)
        self.addCleanup(self.prepare_patch.stop)
        self.addCleanup(self.compile_patch.stop)
        self.addCleanup(self.execute_patch.stop)

    async def asyncTearDown(self):
        await self.controller.shutdown()
        await self.client.aclose()

    def fake_prepare(self, project, version, *, port, board, hardware_reviewed):
        ready = bool(port and board and hardware_reviewed)
        return {"plan_id": "a" * 32, "project_id": project.id, "version": version,
                "ready": ready, "confirmation": "PRIVATE_TEST_TOKEN" if ready else None,
                "confirmation_sha256": "private", "profile": dict(module.PROFILE), "port": {"device": port} if port else None,
                "expires_at": 9999999999, "images": [], "blockers": [] if ready else ["请核对设备"],
                "warnings": [], "plan_path": str(project.meta / "uploads/fixture/plan.json"),
                "execution": "not_run", "tool": {"private": "host-only"}, "command_preview": ["not-executable"]}

    def body(self, **kwargs):
        return {"project_id": self.project.id, "version": 3, "rebuild": False, **kwargs}

    async def post(self, path, body, headers=None):
        return await self.client.post(P + "/api" + path, json=body, headers=self.headers if headers is None else headers)

    async def complete(self, response):
        self.assertEqual(response.status_code, 200, response.text)
        ident = response.json()["id"]
        await self.controller.jobs[ident]["task"]
        return (await self.client.get(P + "/api/jobs/" + ident)).json()

    async def ready_plan(self):
        return await self.complete(await self.post("/prepare", self.body(port="COM7", board=module.PROFILE["board"], hardware_reviewed=True)))

    async def test_page_assets_folder_listing_and_real_project_info(self):
        page = await self.client.get(P)
        self.assertIn("选择工程与设备", page.text)
        self.assertIn("frame-ancestors 'none'", page.headers["content-security-policy"])
        self.assertIn("HttpOnly", page.headers["set-cookie"])
        for name in ("app.js", "style.css", "flash.svg"):
            self.assertEqual((await self.client.get(P + "/assets/" + name)).status_code, 200)
        self.assertEqual((await self.client.get(P + "/assets/DS_Api.txt")).status_code, 404)
        projects = (await self.client.get(P + "/api/projects")).json()["items"]
        self.assertEqual([p["id"] for p in projects], [self.project.id])
        data = (await self.client.get(P + "/api/projects/" + self.project.id)).json()
        self.assertEqual(data["version"], 3)
        self.assertEqual(data["folder"], str(self.project.root))
        self.assertTrue(data["supported"])
        self.execute.assert_not_called()

    async def test_ports_does_not_open_device_or_call_flash(self):
        data = (await self.client.get(P + "/api/ports")).json()
        self.assertEqual(data, {"items": [], "serial_opened": False})
        self.execute.assert_not_called()

    async def test_post_requires_same_origin_cookie_and_csrf(self):
        for headers in ({}, {"Origin": "https://untrusted.example", "X-HWClaw-CSRF": self.headers["X-HWClaw-CSRF"]},
                        {"Origin": BASE, "X-HWClaw-CSRF": "wrong"}):
            response = await self.post("/prepare", self.body(), headers)
            self.assertEqual(response.status_code, 403)
        self.prepare.assert_not_called()
        self.execute.assert_not_called()
        self.assertEqual((await self.client.get(P, headers={"Host": "untrusted.example"})).status_code, 403)
        self.assertEqual((await self.client.get(P, headers={"Sec-Fetch-Site": "cross-site"})).status_code, 403)

    async def test_schema_rejects_paths_extra_fields_and_coerced_versions(self):
        for body in (self.body(version=True), self.body(version="3"), self.body(shell="erase"),
                     self.body(project_id="../../.secrets")):
            response = await self.post("/prepare", body)
            self.assertEqual(response.status_code, 422)
        self.prepare.assert_not_called()
        self.execute.assert_not_called()

    async def test_preview_saves_report_without_exposing_execution_token(self):
        job = await self.complete(await self.post("/prepare", self.body()))
        self.assertEqual(job["status"], "completed")
        self.assertFalse(job["result"]["plan"]["ready"])
        self.assertNotIn("confirmation", job["result"]["plan"])
        self.assertNotIn("command_preview", job["result"]["plan"])
        self.assertTrue((self.project.meta / "uploads/web_jobs" / (job["id"] + ".json")).is_file())
        self.execute.assert_not_called()

    async def test_ready_preview_still_needs_separate_human_confirmation(self):
        job = await self.ready_plan()
        self.assertTrue(job["result"]["plan"]["ready"])
        self.assertNotIn("PRIVATE_TEST_TOKEN", str(job))
        for body, code in (({"plan_id": "a" * 32, "confirmation_text": "yes"}, 422),
                           ({"plan_id": "b" * 32, "confirmation_text": "确认烧录"}, 409)):
            self.assertEqual((await self.post("/execute", body)).status_code, code)
        self.execute.assert_not_called()

    async def test_explicit_confirm_passes_server_owned_token_once_to_mock_runner(self):
        await self.ready_plan()
        self.execute.side_effect = None
        self.execute.return_value = {"status": "uploaded", "version": 3, "behavior": "not_run"}
        response = await self.post("/execute", {"plan_id": "a" * 32, "confirmation_text": "确认烧录"})
        job = await self.complete(response)
        self.assertEqual(job["status"], "completed")
        self.assertEqual(job["result"]["behavior"], "not_run")
        self.assertEqual(self.execute.await_args.args[2], "PRIVATE_TEST_TOKEN")
        self.assertNotIn("PRIVATE_TEST_TOKEN", str(job))
        repeated = await self.post("/execute", {"plan_id": "a" * 32, "confirmation_text": "确认烧录"})
        self.assertEqual(repeated.status_code, 409)
        self.assertEqual(self.execute.await_count, 1)

    async def test_stale_revision_is_blocked_before_compile_or_prepare(self):
        job = await self.complete(await self.post("/prepare", self.body(version=2, rebuild=True)))
        self.assertEqual(job["error"]["code"], "VERSION_CONFLICT")
        self.compile.assert_not_called()
        self.prepare.assert_not_called()

    async def test_rebuild_progress_and_failure_are_visible_without_flash(self):
        log = self.root / "fixture-build.log"
        async def compile_fixture(project, version, on_log, target):
            self.assertEqual(target, module.TARGET)
            log.write_text("TEST DOUBLE compiler error", encoding="utf-8")
            on_log(log)
            return {"verdict": "fail", "diagnostics": ["TEST DOUBLE compiler error"]}
        self.compile.side_effect = compile_fixture
        job = await self.complete(await self.post("/prepare", self.body(rebuild=True)))
        self.assertEqual(job["status"], "failed")
        self.assertEqual(job["error"]["code"], "BUILD_FAILED")
        self.assertIn("compiler error", job["log_tail"])
        self.prepare.assert_not_called()
        self.execute.assert_not_called()

    async def test_compile_error_and_device_change_are_not_reported_as_success(self):
        self.prepare.side_effect = ProjectError("UPLOAD_PORT_NOT_FOUND", "fixture port missing")
        job = await self.complete(await self.post("/prepare", self.body()))
        self.assertEqual(job["error"]["code"], "UPLOAD_PORT_NOT_FOUND")
        self.assertEqual(job["status"], "failed")
        self.execute.assert_not_called()

    async def test_job_ownership_and_busy_gate(self):
        gate = asyncio.Event()
        async def waiting_compile(*args, **kwargs):
            await gate.wait()
            return {"verdict": "pass"}
        self.compile.side_effect = waiting_compile
        response = await self.post("/prepare", self.body(rebuild=True))
        self.assertEqual(response.status_code, 200)
        ident = response.json()["id"]
        self.assertEqual((await self.post("/prepare", self.body())).status_code, 409)
        other = self.controller.new_session()
        with self.assertRaises(module.HTTPException) as caught:
            self.controller.get_job(other, ident)
        self.assertEqual(caught.exception.status_code, 404)
        cancelled = await self.post("/jobs/" + ident + "/cancel", {})
        self.assertEqual(cancelled.json()["status"], "cancelled")
        self.assertIsNone(self.controller.running)
        self.execute.assert_not_called()

    async def test_cancel_before_coroutine_starts_releases_busy_gate(self):
        async def never_started(job):
            raise AssertionError("Task should be cancelled before it starts")
        job = self.controller.start_job(self.owner, "prepare", self.project.id, 3, never_started)
        cancelled = await self.controller.cancel(self.owner, job["id"])
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertIsNone(self.controller.running)

    async def test_cancelled_upload_consumes_authorization_and_never_retries(self):
        await self.ready_plan()
        self.execute.side_effect = asyncio.CancelledError
        response = await self.post("/execute", {"plan_id": "a" * 32, "confirmation_text": "确认烧录"})
        ident = response.json()["id"]
        await asyncio.gather(self.controller.jobs[ident]["task"], return_exceptions=True)
        self.assertEqual(self.controller.jobs[ident]["status"], "cancelled")
        self.assertIsNone(self.controller.session(self.owner)["plan"])
        self.assertEqual(self.execute.await_count, 1)


if __name__ == "__main__":
    unittest.main()
