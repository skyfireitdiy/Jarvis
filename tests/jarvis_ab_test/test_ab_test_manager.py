"""A/B测试管理器测试"""

import pytest

from jarvis.jarvis_ab_test import (
    ABTestManager,
    Experiment,
    ExperimentStatus,
    Variant,
)


class TestVariant:
    """Variant测试"""

    def test_create_variant(self) -> None:
        variant = Variant(name="control")
        assert variant.name == "control"
        assert variant.weight == 1.0

    def test_variant_with_config(self) -> None:
        variant = Variant(
            name="treatment",
            weight=2.0,
            config={"feature_enabled": True},
        )
        assert variant.weight == 2.0
        assert variant.config["feature_enabled"] is True


class TestExperiment:
    """Experiment测试"""

    def test_create_experiment(self) -> None:
        variants = [Variant(name="A"), Variant(name="B")]
        experiment = Experiment(name="test", variants=variants)
        assert experiment.name == "test"
        assert len(experiment.variants) == 2
        assert experiment.status == ExperimentStatus.DRAFT


class TestABTestManager:
    """ABTestManager测试"""

    def test_create_experiment(self) -> None:
        manager = ABTestManager()
        variants = [Variant(name="control"), Variant(name="treatment")]
        experiment = manager.create_experiment("test", variants)
        assert experiment.name == "test"
        assert manager.get_experiment("test") is not None

    def test_get_experiment_not_found(self) -> None:
        manager = ABTestManager()
        assert manager.get_experiment("nonexistent") is None

    def test_start_experiment(self) -> None:
        manager = ABTestManager()
        variants = [Variant(name="A")]
        manager.create_experiment("test", variants)
        manager.start_experiment("test")

        experiment = manager.get_experiment("test")
        assert experiment.status == ExperimentStatus.RUNNING
        assert experiment.started_at is not None

    def test_start_experiment_not_found(self) -> None:
        manager = ABTestManager()
        with pytest.raises(ValueError, match="not found"):
            manager.start_experiment("nonexistent")

    def test_pause_and_resume(self) -> None:
        manager = ABTestManager()
        variants = [Variant(name="A")]
        manager.create_experiment("test", variants)
        manager.start_experiment("test")

        manager.pause_experiment("test")
        experiment = manager.get_experiment("test")
        assert experiment.status == ExperimentStatus.PAUSED

        manager.resume_experiment("test")
        assert experiment.status == ExperimentStatus.RUNNING

    def test_complete_experiment(self) -> None:
        manager = ABTestManager()
        variants = [Variant(name="A")]
        manager.create_experiment("test", variants)
        manager.start_experiment("test")
        manager.complete_experiment("test")

        experiment = manager.get_experiment("test")
        assert experiment.status == ExperimentStatus.COMPLETED
        assert experiment.ended_at is not None

    def test_archive_experiment(self) -> None:
        manager = ABTestManager()
        variants = [Variant(name="A")]
        manager.create_experiment("test", variants)
        manager.archive_experiment("test")

        experiment = manager.get_experiment("test")
        assert experiment.status == ExperimentStatus.ARCHIVED

    def test_assign_variant_consistency(self) -> None:
        manager = ABTestManager()
        variants = [Variant(name="A"), Variant(name="B")]
        manager.create_experiment("test", variants)

        variant1 = manager.assign_variant("test", "user123")
        variant2 = manager.assign_variant("test", "user123")
        assert variant1.name == variant2.name

    def test_assign_variant_distribution(self) -> None:
        manager = ABTestManager()
        variants = [Variant(name="A", weight=1), Variant(name="B", weight=1)]
        manager.create_experiment("test", variants)

        counts = {"A": 0, "B": 0}
        for i in range(1000):
            variant = manager.assign_variant("test", f"user{i}")
            counts[variant.name] += 1

        assert counts["A"] > 300
        assert counts["B"] > 300

    def test_assign_variant_no_variants(self) -> None:
        manager = ABTestManager()
        manager.create_experiment("test", [])

        with pytest.raises(ValueError, match="no variants"):
            manager.assign_variant("test", "user123")

    def test_record_metric(self) -> None:
        manager = ABTestManager()
        variants = [Variant(name="A")]
        manager.create_experiment("test", variants)

        manager.record_metric("test", "A", "clicks", 1.0)
        manager.record_metric("test", "A", "clicks", 2.0)

        summary = manager.get_metric_summary("test", "A", "clicks")
        assert summary["count"] == 2
        assert summary["sum"] == 3.0

    def test_get_metric_summary_empty(self) -> None:
        manager = ABTestManager()
        variants = [Variant(name="A")]
        manager.create_experiment("test", variants)

        summary = manager.get_metric_summary("test", "A", "clicks")
        assert summary["count"] == 0

    def test_compare_variants(self) -> None:
        manager = ABTestManager()
        variants = [Variant(name="A"), Variant(name="B")]
        manager.create_experiment("test", variants)

        manager.record_metric("test", "A", "conversion", 0.1)
        manager.record_metric("test", "A", "conversion", 0.2)
        manager.record_metric("test", "B", "conversion", 0.3)
        manager.record_metric("test", "B", "conversion", 0.4)

        comparison = manager.compare_variants("test", "conversion")
        assert "A" in comparison
        assert "B" in comparison
        assert comparison["A"]["average"] == pytest.approx(0.15)
        assert comparison["B"]["average"] == pytest.approx(0.35)

    def test_get_winner_higher_is_better(self) -> None:
        manager = ABTestManager()
        variants = [Variant(name="A"), Variant(name="B")]
        manager.create_experiment("test", variants)

        manager.record_metric("test", "A", "conversion", 0.1)
        manager.record_metric("test", "B", "conversion", 0.3)

        winner = manager.get_winner("test", "conversion", higher_is_better=True)
        assert winner == "B"

    def test_get_winner_lower_is_better(self) -> None:
        manager = ABTestManager()
        variants = [Variant(name="A"), Variant(name="B")]
        manager.create_experiment("test", variants)

        manager.record_metric("test", "A", "latency", 100)
        manager.record_metric("test", "B", "latency", 200)

        winner = manager.get_winner("test", "latency", higher_is_better=False)
        assert winner == "A"

    def test_get_experiment_status(self) -> None:
        manager = ABTestManager()
        variants = [Variant(name="A"), Variant(name="B")]
        manager.create_experiment("test", variants)
        manager.start_experiment("test")

        status = manager.get_experiment_status("test")
        assert status["name"] == "test"
        assert status["status"] == "running"
        assert "A" in status["variants"]
        assert "B" in status["variants"]

    def test_list_experiments(self) -> None:
        manager = ABTestManager()
        manager.create_experiment("exp1", [Variant(name="A")])
        manager.create_experiment("exp2", [Variant(name="B")])
        manager.start_experiment("exp1")

        all_experiments = manager.list_experiments()
        assert "exp1" in all_experiments
        assert "exp2" in all_experiments

        running = manager.list_experiments(ExperimentStatus.RUNNING)
        assert "exp1" in running
        assert "exp2" not in running

    def test_delete_experiment(self) -> None:
        manager = ABTestManager()
        manager.create_experiment("test", [Variant(name="A")])
        manager.delete_experiment("test")

        assert manager.get_experiment("test") is None

    def test_weighted_variant_assignment(self) -> None:
        manager = ABTestManager()
        variants = [
            Variant(name="A", weight=1),
            Variant(name="B", weight=9),
        ]
        manager.create_experiment("test", variants)

        counts = {"A": 0, "B": 0}
        for i in range(1000):
            variant = manager.assign_variant("test", f"user{i}")
            counts[variant.name] += 1

        assert counts["B"] > counts["A"] * 2
