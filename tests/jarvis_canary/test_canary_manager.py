"""灰度发布管理器测试"""

import pytest

from jarvis.jarvis_canary import (
    CanaryManager,
    CanaryRelease,
    ReleaseStage,
    RolloutStrategy,
    TrafficRule,
)


class TestCanaryRelease:
    """CanaryRelease测试"""

    def test_create_release(self) -> None:
        release = CanaryRelease(
            name="test",
            stable_version="v1.0.0",
            canary_version="v1.1.0",
        )
        assert release.name == "test"
        assert release.stable_version == "v1.0.0"
        assert release.canary_version == "v1.1.0"
        assert release.traffic_percentage == 0.0
        assert release.stage == ReleaseStage.CREATED

    def test_default_values(self) -> None:
        release = CanaryRelease(
            name="test",
            stable_version="v1",
            canary_version="v2",
        )
        assert release.strategy == RolloutStrategy.LINEAR
        assert release.step_percentage == 10.0
        assert release.max_percentage == 100.0


class TestTrafficRule:
    """TrafficRule测试"""

    def test_create_rule(self) -> None:
        rule = TrafficRule(
            name="beta_users",
            condition=lambda ctx: ctx.get("user_type") == "beta",
            target_version="v2.0.0",
        )
        assert rule.name == "beta_users"
        assert rule.enabled is True
        assert rule.priority == 0

    def test_rule_condition(self) -> None:
        rule = TrafficRule(
            name="test",
            condition=lambda ctx: ctx.get("flag") is True,
            target_version="v2",
        )
        assert rule.condition({"flag": True}) is True
        assert rule.condition({"flag": False}) is False


class TestCanaryManager:
    """CanaryManager测试"""

    def test_create_release(self) -> None:
        manager = CanaryManager()
        release = manager.create_release(
            name="api",
            stable_version="v1.0.0",
            canary_version="v1.1.0",
        )
        assert release.name == "api"
        assert manager.get_release("api") is not None

    def test_get_release_not_found(self) -> None:
        manager = CanaryManager()
        assert manager.get_release("nonexistent") is None

    def test_start_canary(self) -> None:
        manager = CanaryManager()
        manager.create_release("api", "v1", "v2")
        manager.start_canary("api", initial_percentage=5.0)

        release = manager.get_release("api")
        assert release.traffic_percentage == 5.0
        assert release.stage == ReleaseStage.CANARY

    def test_start_canary_not_found(self) -> None:
        manager = CanaryManager()
        with pytest.raises(ValueError, match="not found"):
            manager.start_canary("nonexistent")

    def test_increase_traffic_linear(self) -> None:
        manager = CanaryManager()
        manager.create_release("api", "v1", "v2", step_percentage=10.0)
        manager.start_canary("api", initial_percentage=10.0)

        new_percentage = manager.increase_traffic("api")
        assert new_percentage == 20.0

    def test_increase_traffic_exponential(self) -> None:
        manager = CanaryManager()
        manager.create_release("api", "v1", "v2", strategy=RolloutStrategy.EXPONENTIAL)
        manager.start_canary("api", initial_percentage=10.0)

        new_percentage = manager.increase_traffic("api")
        assert new_percentage == 20.0

    def test_increase_traffic_custom(self) -> None:
        manager = CanaryManager()
        manager.create_release("api", "v1", "v2")
        manager.start_canary("api", initial_percentage=10.0)

        new_percentage = manager.increase_traffic("api", percentage=25.0)
        assert new_percentage == 35.0

    def test_increase_traffic_max(self) -> None:
        manager = CanaryManager()
        manager.create_release("api", "v1", "v2")
        manager.start_canary("api", initial_percentage=95.0)

        new_percentage = manager.increase_traffic("api", percentage=20.0)
        assert new_percentage == 100.0

        release = manager.get_release("api")
        assert release.stage == ReleaseStage.ROLLING

    def test_complete_release(self) -> None:
        manager = CanaryManager()
        manager.create_release("api", "v1", "v2")
        manager.start_canary("api")
        manager.complete_release("api")

        release = manager.get_release("api")
        assert release.traffic_percentage == 100.0
        assert release.stage == ReleaseStage.COMPLETED

    def test_rollback(self) -> None:
        manager = CanaryManager()
        manager.create_release("api", "v1", "v2")
        manager.start_canary("api", initial_percentage=50.0)
        manager.rollback("api")

        release = manager.get_release("api")
        assert release.traffic_percentage == 0.0
        assert release.stage == ReleaseStage.ROLLED_BACK

    def test_pause_and_resume(self) -> None:
        manager = CanaryManager()
        manager.create_release("api", "v1", "v2")
        manager.start_canary("api", initial_percentage=30.0)

        manager.pause("api")
        release = manager.get_release("api")
        assert release.stage == ReleaseStage.PAUSED

        manager.resume("api")
        assert release.stage == ReleaseStage.CANARY

    def test_add_rule(self) -> None:
        manager = CanaryManager()
        manager.create_release("api", "v1", "v2")

        rule = TrafficRule(
            name="beta",
            condition=lambda ctx: ctx.get("beta") is True,
            target_version="v2",
            priority=10,
        )
        manager.add_rule("api", rule)

        release = manager.get_release("api")
        assert len(release.rules) == 1

    def test_remove_rule(self) -> None:
        manager = CanaryManager()
        manager.create_release("api", "v1", "v2")

        rule = TrafficRule(
            name="beta",
            condition=lambda ctx: True,
            target_version="v2",
        )
        manager.add_rule("api", rule)
        manager.remove_rule("api", "beta")

        release = manager.get_release("api")
        assert len(release.rules) == 0

    def test_route_with_rule(self) -> None:
        manager = CanaryManager()
        manager.create_release("api", "v1", "v2")
        manager.start_canary("api", initial_percentage=0.0)

        rule = TrafficRule(
            name="beta",
            condition=lambda ctx: ctx.get("beta") is True,
            target_version="v2",
        )
        manager.add_rule("api", rule)

        version = manager.route("api", {"beta": True})
        assert version == "v2"

        version = manager.route("api", {"beta": False})
        assert version == "v1"

    def test_route_by_percentage(self) -> None:
        manager = CanaryManager()
        manager.create_release("api", "v1", "v2")
        manager.start_canary("api", initial_percentage=100.0)

        version = manager.route("api")
        assert version == "v2"

    def test_register_and_call_handler(self) -> None:
        manager = CanaryManager()
        manager.create_release("api", "v1", "v2")
        manager.start_canary("api", initial_percentage=100.0)

        manager.register_handler("api", "v1", lambda: "stable")
        manager.register_handler("api", "v2", lambda: "canary")

        result = manager.call("api")
        assert result == "canary"

    def test_call_no_handler(self) -> None:
        manager = CanaryManager()
        manager.create_release("api", "v1", "v2")
        manager.start_canary("api")

        with pytest.raises(ValueError, match="No handlers"):
            manager.call("api")

    def test_get_status(self) -> None:
        manager = CanaryManager()
        manager.create_release("api", "v1", "v2")
        manager.start_canary("api", initial_percentage=25.0)

        status = manager.get_status("api")
        assert status["name"] == "api"
        assert status["traffic_percentage"] == 25.0
        assert status["stage"] == "canary"

    def test_list_releases(self) -> None:
        manager = CanaryManager()
        manager.create_release("api1", "v1", "v2")
        manager.create_release("api2", "v1", "v2")

        releases = manager.list_releases()
        assert "api1" in releases
        assert "api2" in releases

    def test_delete_release(self) -> None:
        manager = CanaryManager()
        manager.create_release("api", "v1", "v2")
        manager.delete_release("api")

        assert manager.get_release("api") is None

    def test_rule_priority(self) -> None:
        manager = CanaryManager()
        manager.create_release("api", "v1", "v2")

        rule1 = TrafficRule(
            name="low",
            condition=lambda ctx: True,
            target_version="v1",
            priority=1,
        )
        rule2 = TrafficRule(
            name="high",
            condition=lambda ctx: True,
            target_version="v2",
            priority=10,
        )

        manager.add_rule("api", rule1)
        manager.add_rule("api", rule2)

        version = manager.route("api")
        assert version == "v2"
