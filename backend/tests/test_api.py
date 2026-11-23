"""Tests for the REST and WebSocket API (FastAPI TestClient)."""

import time
from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.config import Settings
from app.models.schemas import KPI, NetworkInfo, StateSnapshot
from app.optimizer.registry import IMPLEMENTED_STRATEGIES


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(Settings())) as test_client:
        yield test_client


def runner(client: TestClient):
    return client.app.state.runner


def state(client: TestClient) -> dict:
    return client.get("/state").json()


def wait_for(check: Callable[[], bool], timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while not check():
        assert time.monotonic() < deadline, "timed out waiting for condition"
        time.sleep(0.02)


def hold_body(train_id: str, station: str, minutes: int = 5) -> dict:
    return {
        "action": {
            "kind": "hold",
            "train_id": train_id,
            "at_station": station,
            "hold_minutes": minutes,
            "reason": "t",
        }
    }


def first_train_and_station(client: TestClient) -> tuple[str, str]:
    train = state(client)["trains"][0]
    return train["id"], train["next_stations"][1]["station"]


# ---- health, network, state -----------------------------------------------------------------
def test_health(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_network(client: TestClient) -> None:
    info = NetworkInfo.model_validate(client.get("/network").json())
    assert len(info.stations) == 15 and len(info.blocks) == 45
    assert "not real" in info.disclaimer
    assert {s.code for s in info.stations if s.is_junction} == {"VDJ", "RMJ"}


def test_state_is_a_valid_snapshot(client: TestClient) -> None:
    snap = StateSnapshot.model_validate(state(client))
    assert snap.tick == 0 and snap.running is False and len(snap.trains) == 25


def test_scenario_info(client: TestClient) -> None:
    info = client.get("/scenario").json()
    assert info == {
        "seed": 42,
        "intensity": "none",
        "month": 1,
        "speed": 1.0,
        "running": False,
        "tick": 0,
        "finished": False,
    }


def kpis_when_ready(client: TestClient, path: str = "/kpis", timeout: float = 180.0):
    """Poll until the background job is done; return the 200 response."""
    deadline = time.monotonic() + timeout
    while True:
        response = client.get(path)
        if response.status_code != 202:
            return response
        assert time.monotonic() < deadline, "KPI job did not finish in time"
        time.sleep(0.5)


def test_kpis_are_computed_in_the_background_through_the_real_api(client: TestClient) -> None:
    first = client.get("/kpis")
    assert first.status_code == 202  # nothing is cached yet: the call returns at once instead of blocking
    assert first.headers["Retry-After"] == "2"
    body = first.json()
    assert body["status"] == "computing" and body["total"] == 4 and body["retry_after_s"] == 2
    started = time.monotonic()
    assert client.get("/health").json() == {"status": "ok"}  # the API stays responsive while workers run
    assert client.get("/state").status_code == 200
    assert time.monotonic() - started < 2.0

    ready = kpis_when_ready(client)
    assert ready.status_code == 200 and "Retry-After" not in ready.headers
    kpis = {name: KPI.model_validate(value) for name, value in ready.json().items()}
    assert list(kpis) == ["no_control", "fcfs", "priority", "cpsat"]
    assert all(k.strategy.value == name and k.avg_delay_min > 0 for name, k in kpis.items())
    assert kpis["no_control"].conflicts_avoided == 0
    assert client.get("/kpis").json() == ready.json()  # cached, same body as before

    detail = client.get("/kpis/detail")  # same cached job: ready at once, with the extra numbers
    assert detail.status_code == 200 and list(detail.json()) == list(kpis)
    assert detail.json()["no_control"]["actions_applied"] == 0 and detail.json()["fcfs"]["trains_finished"] == 25
    assert detail.json()["priority"]["priority_weighted_delay"] > 0 and detail.json()["cpsat"]["trains_finished"] == 25


def test_kpis_restart_for_a_new_scenario(client: TestClient) -> None:
    ready = kpis_when_ready(client).json()
    client.post("/scenario/reset", json={"seed": 8, "intensity": "low"})
    assert client.get("/kpis").status_code == 202  # a new scenario needs new numbers
    again = kpis_when_ready(client).json()
    assert again != ready and list(again) == list(ready)


def test_kpi_detail_reports_progress_too(client: TestClient) -> None:
    first = client.get("/kpis/detail")
    assert first.status_code == 202 and first.headers["Retry-After"] == "2"
    assert kpis_when_ready(client, "/kpis/detail").status_code == 200


def test_kpis_are_precomputed_after_a_reset_when_enabled() -> None:
    with TestClient(create_app(Settings(precompute_kpis=True))) as precomputing:
        service = runner(precomputing).kpi_service
        assert runner(precomputing).kpi_key in service._jobs  # started at start-up, before anyone asked
        precomputing.post("/scenario/reset", json={"seed": 9})
        assert (9, runner(precomputing).intensity, runner(precomputing).month) in service._jobs
        assert kpis_when_ready(precomputing).status_code == 200


def test_a_crashed_kpi_worker_gives_503_and_the_next_call_starts_again(client: TestClient) -> None:
    from concurrent.futures import Future

    service = runner(client).kpi_service
    broken: Future = Future()
    broken.set_exception(RuntimeError("worker died"))
    service._jobs[runner(client).kpi_key] = {name: broken for name in IMPLEMENTED_STRATEGIES}
    response = client.get("/kpis")
    assert response.status_code == 503 and "worker died" in response.json()["detail"]
    assert client.get("/kpis").status_code == 202  # the failed job was forgotten: a fresh one is running


# ---- start / pause / reset / speed -----------------------------------------------------------------
def test_start_runs_and_pause_stops_ticks(client: TestClient) -> None:
    assert client.post("/scenario/start", json={"speed": 20}).json()["running"] is True
    wait_for(lambda: state(client)["tick"] >= 5)
    paused = client.post("/scenario/pause").json()
    assert paused["running"] is False
    frozen = state(client)["tick"]
    time.sleep(0.4)
    assert state(client)["tick"] == frozen
    client.post("/scenario/start")  # resume continues from where it stopped
    wait_for(lambda: state(client)["tick"] > frozen)
    assert client.get("/scenario").json()["running"] is True


def test_start_without_body_works_and_is_idempotent(client: TestClient) -> None:
    assert client.post("/scenario/start").status_code == 200
    assert client.post("/scenario/start").status_code == 200
    assert client.post("/scenario/pause").status_code == 200


def test_start_with_new_seed_rebuilds(client: TestClient) -> None:
    client.post("/scenario/start", json={"seed": 5, "speed": 20})
    client.post("/scenario/pause")
    assert client.get("/scenario").json()["seed"] == 5


def test_start_bad_input(client: TestClient) -> None:
    assert client.post("/scenario/start", json={"speed": 100}).status_code == 422
    assert client.post("/scenario/start", json={"speed": 0.1}).status_code == 422
    assert client.post("/scenario/start", json={"seed": "abc"}).status_code == 422
    assert client.post("/scenario/start", json={"strategy": "bogus"}).status_code == 422
    assert client.post("/scenario/start", json={"surprise": 1}).status_code == 422
    assert client.post("/scenario/start", json={"strategy": "ai_optimizer"}).status_code == 422  # old name
    assert client.get("/scenario").json()["running"] is False


def test_start_after_finish_is_a_conflict(client: TestClient) -> None:
    runner(client).engine.run_until_done()
    reply = client.post("/scenario/start")
    assert reply.status_code == 409 and "reset" in reply.json()["detail"]
    assert client.get("/scenario").json()["finished"] is True
    client.post("/scenario/reset")
    assert client.post("/scenario/start").status_code == 200


def test_reset_with_same_seed_gives_identical_snapshots(client: TestClient) -> None:
    body = {"seed": 7, "intensity": "medium"}
    fresh = client.post("/scenario/reset", json=body).json()
    assert fresh["tick"] == 0 and fresh["running"] is False
    for _ in range(150):
        runner(client).engine.step()
    first = state(client)
    client.post("/scenario/reset", json=body)
    for _ in range(150):
        runner(client).engine.step()
    assert state(client) == first
    client.post("/scenario/reset", json={"seed": 8, "intensity": "medium"})
    for _ in range(150):
        runner(client).engine.step()
    assert state(client) != first


def test_reset_keeps_unspecified_values_and_stops_a_running_sim(client: TestClient) -> None:
    client.post("/scenario/reset", json={"seed": 9, "intensity": "low", "month": 7})
    client.post("/scenario/start", json={"speed": 20})
    wait_for(lambda: state(client)["tick"] >= 3)
    reply = client.post("/scenario/reset", json={"month": 11}).json()
    assert reply["tick"] == 0 and reply["running"] is False
    assert reply["sim_time"].startswith("2026-11-15")
    info = client.get("/scenario").json()
    assert (info["seed"], info["intensity"], info["month"], info["running"]) == (9, "low", 11, False)


def test_reset_bad_input(client: TestClient) -> None:
    assert client.post("/scenario/reset", json={"month": 13}).status_code == 422
    assert client.post("/scenario/reset", json={"intensity": "extreme"}).status_code == 422
    assert client.post("/scenario/reset", json={"seed": 1.5}).status_code == 422


def test_speed_endpoint_and_effect(client: TestClient) -> None:
    assert client.post("/scenario/speed", json={"speed": 5}).json() == {"speed": 5.0}
    assert client.get("/scenario").json()["speed"] == 5.0
    assert client.post("/scenario/speed", json={"speed": 0.1}).status_code == 422
    assert client.post("/scenario/speed", json={"speed": 25}).status_code == 422
    assert client.post("/scenario/speed", json={}).status_code == 422

    client.post("/scenario/start", json={"speed": 20})
    before = state(client)["tick"]
    time.sleep(1.0)
    assert state(client)["tick"] - before >= 10  # fast
    client.post("/scenario/speed", json={"speed": 0.5})
    time.sleep(0.3)  # let the loop pick the new pace up
    before = state(client)["tick"]
    time.sleep(1.0)
    assert state(client)["tick"] - before <= 1  # slow: one tick every 2 seconds


# ---- actions ------------------------------------------------------------------------------------------------
def test_hold_and_precedence_actions_are_queued(client: TestClient) -> None:
    train_id, station = first_train_and_station(client)
    reply = client.post("/actions", json=hold_body(train_id, station))
    assert reply.status_code == 200 and reply.json() == {"status": "queued", "applies_at_tick": 1}
    other = state(client)["trains"][1]["id"]
    precedence = {
        "action": {
            "kind": "precedence",
            "train_id": train_id,
            "at_station": station,
            "other_train_id": other,
            "reason": "t",
        }
    }
    assert client.post("/actions", json=precedence).status_code == 200


def test_action_errors_are_clear(client: TestClient) -> None:
    train_id, station = first_train_and_station(client)
    unknown = client.post("/actions", json=hold_body("NOPE", station))
    assert unknown.status_code == 400 and "unknown train" in unknown.json()["detail"]
    off_route = client.post("/actions", json=hold_body(train_id, "RGY"))
    assert off_route.status_code == 400 and "does not call at" in off_route.json()["detail"]
    self_yield = {
        "action": {
            "kind": "precedence",
            "train_id": train_id,
            "at_station": station,
            "other_train_id": train_id,
            "reason": "t",
        }
    }
    assert client.post("/actions", json=self_yield).status_code == 400
    runner(client).engine.run_until_done()
    gone = client.post("/actions", json=hold_body(train_id, station))
    assert gone.status_code == 400 and "already left" in gone.json()["detail"]


def test_action_validation_errors(client: TestClient) -> None:
    train_id, station = first_train_and_station(client)
    no_minutes = {"action": {"kind": "hold", "train_id": train_id, "at_station": station, "reason": "t"}}
    no_other = {"action": {"kind": "precedence", "train_id": train_id, "at_station": station, "reason": "t"}}
    assert client.post("/actions", json=no_minutes).status_code == 422
    assert client.post("/actions", json=no_other).status_code == 422
    assert client.post("/actions", json={}).status_code == 422
    assert client.post("/actions", json={"recommendation_id": "r-1"}).status_code == 422
    both = {**hold_body(train_id, station), "recommendation_id": "r-1", "decision": "apply"}
    assert client.post("/actions", json=both).status_code == 422
    assert client.post("/actions", json={"recommendation_id": "r-1", "decision": "maybe"}).status_code == 422


def test_unknown_recommendation_is_404(client: TestClient) -> None:
    reply = client.post("/actions", json={"recommendation_id": "r-001", "decision": "apply"})
    assert reply.status_code == 404 and "r-001" in reply.json()["detail"]


# ---- disruptions ---------------------------------------------------------------------------------------------------
def test_inject_disruption_shows_up_in_state(client: TestClient) -> None:
    reply = client.post("/disruptions", json={"kind": "fog", "duration_min": 30})
    assert reply.status_code == 201
    created = reply.json()
    assert created["id"] == "m-001" and created["kind"] == "fog" and created["speed_factor"] == 0.6
    assert [d["id"] for d in state(client)["disruptions"]] == ["m-001"]


def test_inject_closure_marks_the_block_closed(client: TestClient) -> None:
    body = {"kind": "block_closure", "duration_min": 60, "target_ids": ["KLP-MJG-2"]}
    assert client.post("/disruptions", json=body).status_code == 201
    closed = [b for b in state(client)["blocks"] if b["closed"]]
    assert [b["block_id"] for b in closed] == ["KLP-MJG-2"]


def test_inject_disruption_bad_input(client: TestClient) -> None:
    def post(**fields: object) -> int:
        return client.post("/disruptions", json={"kind": "fog", "duration_min": 30, **fields}).status_code

    assert post(kind="tornado") == 422
    assert post(duration_min=0) == 422
    assert post(speed_factor=2) == 422
    assert post(surprise=1) == 422
    assert post(target_ids=["NOPE-1"]) == 400
    assert post(kind="block_closure") == 400  # closures need a target
    assert post(kind="late_departure", target_ids=["NO-SUCH-TRAIN"]) == 400
    detail = client.post(
        "/disruptions", json={"kind": "fog", "duration_min": 30, "target_ids": ["NOPE-1"]}
    ).json()["detail"]
    assert "unknown block or station" in detail
    assert state(client)["disruptions"] == []


# ---- WebSocket --------------------------------------------------------------------------------------------------------
def test_ws_sends_hello_then_current_snapshot(client: TestClient) -> None:
    with client.websocket_connect("/ws/state") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello" and hello["seq"] == 0 and hello["data"]["protocol"] == 1
        first = ws.receive_json()
        assert first["type"] == "snapshot" and first["seq"] == 1
        assert StateSnapshot.model_validate(first["data"]).tick == 0


def test_ws_streams_valid_snapshots_while_running(client: TestClient) -> None:
    with client.websocket_connect("/ws/state") as ws:
        ws.receive_json()
        ws.receive_json()
        client.post("/scenario/start", json={"speed": 20})
        messages = [ws.receive_json() for _ in range(6)]
        client.post("/scenario/pause")
    assert [m["seq"] for m in messages] == list(range(2, 8))
    ticks = [StateSnapshot.model_validate(m["data"]).tick for m in messages]
    assert ticks == sorted(ticks) and ticks[-1] > ticks[0]


def test_ws_gets_reset_and_pause_updates(client: TestClient) -> None:
    with client.websocket_connect("/ws/state") as ws:
        ws.receive_json()
        ws.receive_json()
        client.post("/scenario/reset", json={"seed": 3})
        message = ws.receive_json()
        assert message["data"]["tick"] == 0 and message["data"]["running"] is False


def test_ws_receives_injected_disruption_in_next_snapshot(client: TestClient) -> None:
    with client.websocket_connect("/ws/state") as ws:
        ws.receive_json()
        ws.receive_json()
        client.post("/disruptions", json={"kind": "fog", "duration_min": 30})
        snap = StateSnapshot.model_validate(ws.receive_json()["data"])
        assert [d.id for d in snap.disruptions] == ["m-001"]


def test_ws_supports_many_clients_and_cleans_up_on_disconnect(client: TestClient) -> None:
    with client.websocket_connect("/ws/state") as first, client.websocket_connect("/ws/state") as second:
        for ws in (first, second):
            ws.receive_json()
            ws.receive_json()
        assert runner(client).subscriber_count == 2
        client.post("/scenario/start", json={"speed": 20})
        a, b = first.receive_json(), second.receive_json()
        assert a["type"] == b["type"] == "snapshot"
        client.post("/scenario/pause")
    wait_for(lambda: runner(client).subscriber_count == 0)


def test_server_survives_a_viewer_that_vanishes_mid_stream(client: TestClient) -> None:
    with client.websocket_connect("/ws/state") as ws:
        ws.receive_json()
        ws.receive_json()
        client.post("/scenario/start", json={"speed": 20})
        ws.receive_json()
    wait_for(lambda: runner(client).subscriber_count == 0)
    before = state(client)["tick"]
    wait_for(lambda: state(client)["tick"] > before)  # simulation keeps running without viewers


# ---- CORS ---------------------------------------------------------------------------------------------------------------
def test_cors_allows_the_frontend_origin_only(client: TestClient) -> None:
    ok = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert ok.headers["access-control-allow-origin"] == "http://localhost:5173"
    preflight = client.options(
        "/scenario/start",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"},
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "http://localhost:5173"
    other = client.get("/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in other.headers


# ---- conflicts, strategies and recommendations ----------------------------------------------------------------
def select_strategy(client: TestClient, name: str, intensity: str = "medium") -> None:
    client.post("/scenario/reset", json={"seed": 42, "intensity": intensity})
    assert client.post("/scenario/start", json={"strategy": name, "speed": 0.5}).status_code == 200
    client.post("/scenario/pause")


def step_until(client: TestClient, found: Callable[[dict], bool], limit: int = 900) -> dict:
    """Advance the paused simulation tick by tick until the state satisfies ``found``."""
    for _ in range(limit):
        snap = state(client)
        if found(snap):
            return snap
        runner(client).engine.step()
    raise AssertionError("condition never reached")


def test_start_with_a_strategy_selects_it(client: TestClient) -> None:
    for name in ("fcfs", "priority", "cpsat", "no_control"):
        select_strategy(client, name)
        assert state(client)["strategy"] == name and state(client)["kpis"]["strategy"] == name


def test_conflicts_appear_in_the_live_state_for_every_strategy(client: TestClient) -> None:
    select_strategy(client, "no_control")
    snap = step_until(client, lambda s: bool(s["conflicts"]))
    parsed = StateSnapshot.model_validate(snap)
    assert parsed.conflicts[0].train_ids and parsed.recommendations == []  # no control only watches


def test_fcfs_recommendations_can_be_applied(client: TestClient) -> None:
    select_strategy(client, "fcfs")
    snap = step_until(client, lambda s: bool(s["recommendations"]))
    rec = snap["recommendations"][0]
    assert rec["status"] == "proposed" and rec["strategy"] == "fcfs" and rec["action"]["reason"]
    assert rec["conflict_ids"][0] in {c["id"] for c in snap["conflicts"]}
    assert state(client)["recommendations"][0]["id"] == rec["id"]  # ids are stable between calls

    reply = client.post("/actions", json={"recommendation_id": rec["id"], "decision": "apply"})
    assert reply.status_code == 200 and reply.json() == {"status": "applied", "recommendation_id": rec["id"]}
    applied = next(r for r in state(client)["recommendations"] if r["id"] == rec["id"])
    assert applied["status"] == "applied"
    assert client.post("/actions", json={"recommendation_id": rec["id"], "decision": "apply"}).status_code == 409
    undo = client.post("/actions", json={"recommendation_id": rec["id"], "decision": "undo"})
    assert undo.status_code == 400 and "cannot be undone" in undo.json()["detail"]


def test_applying_a_recommendation_really_queues_the_action(client: TestClient) -> None:
    select_strategy(client, "fcfs")
    snap = step_until(client, lambda s: bool(s["recommendations"]))
    rec = snap["recommendations"][0]
    engine = runner(client).engine
    before = len(engine._queue)
    client.post("/actions", json={"recommendation_id": rec["id"], "decision": "apply"})
    assert len(engine._queue) == before + 1 and engine._queue[-1].train_id == rec["action"]["train_id"]


def test_recommendations_can_be_ignored_and_the_ignore_undone(client: TestClient) -> None:
    select_strategy(client, "priority", intensity="high")
    snap = step_until(client, lambda s: bool(s["recommendations"]))
    rec_id = snap["recommendations"][0]["id"]
    assert client.post("/actions", json={"recommendation_id": rec_id, "decision": "ignore"}).json()["status"] == "ignored"
    ignored = [r for r in state(client)["recommendations"] if r["id"] == rec_id]
    assert ignored and ignored[0]["status"] == "ignored"  # ignored stays ignored, it is not proposed again
    assert client.post("/actions", json={"recommendation_id": rec_id, "decision": "apply"}).status_code == 409
    assert client.post("/actions", json={"recommendation_id": rec_id, "decision": "undo"}).json()["status"] == "proposed"
    assert client.post("/actions", json={"recommendation_id": rec_id, "decision": "apply"}).status_code == 200


def test_a_stale_recommendation_is_refused_with_409(client: TestClient) -> None:
    select_strategy(client, "fcfs")
    snap = step_until(client, lambda s: bool(s["recommendations"]))
    rec = snap["recommendations"][0]
    train_id, station = rec["action"]["train_id"], rec["action"]["at_station"]
    engine = runner(client).engine
    while not engine._trains[train_id].has_passed(station):  # let the train leave that station
        engine.step()
    reply = client.post("/actions", json={"recommendation_id": rec["id"], "decision": "apply"})
    assert reply.status_code in (404, 409)  # expired (404) or invalid (409), never a crash


def test_reset_clears_recommendations_but_keeps_the_strategy(client: TestClient) -> None:
    select_strategy(client, "fcfs")
    step_until(client, lambda s: bool(s["recommendations"]))
    client.post("/scenario/reset")
    snap = state(client)
    assert snap["recommendations"] == [] and snap["strategy"] == "fcfs" and snap["tick"] == 0


def test_snapshot_recommendation_ids_do_not_change_on_repeated_calls(client: TestClient) -> None:
    select_strategy(client, "priority", intensity="high")
    step_until(client, lambda s: bool(s["recommendations"]))
    first = [r["id"] for r in state(client)["recommendations"]]
    assert first == [r["id"] for r in state(client)["recommendations"]] == [r["id"] for r in state(client)["recommendations"]]
