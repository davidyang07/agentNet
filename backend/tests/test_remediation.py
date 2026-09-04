from app.remediation.analyze import recommend
from app.schemas.experiment import ExperimentConfig


def test_no_recommendation_when_compromise_fraction_is_low():
    config = ExperimentConfig(seed=1, node_count=25, defense_enabled=True)
    assert recommend(config, compromise_fraction=0.1) == []


def test_no_recommendation_exactly_at_threshold():
    config = ExperimentConfig(seed=1, node_count=25)
    assert recommend(config, compromise_fraction=0.3) == []


def test_recommends_enabling_defense_when_disabled_and_compromise_is_high():
    config = ExperimentConfig(seed=1, node_count=25, defense_enabled=False)
    recs = recommend(config, compromise_fraction=0.5)
    assert len(recs) == 1
    assert recs[0].config_diff == {"defense_enabled": True}


def test_recommends_raising_detector_sensitivity_when_defense_enabled_but_insufficient():
    config = ExperimentConfig(
        seed=1, node_count=25, defense_enabled=True, detector_sensitivity=0.2
    )
    recs = recommend(config, compromise_fraction=0.5)
    assert len(recs) == 1
    assert recs[0].config_diff == {"detector_sensitivity": 0.4}


def test_sensitivity_recommendation_is_capped_at_one():
    config = ExperimentConfig(
        seed=1, node_count=25, defense_enabled=True, detector_sensitivity=0.9
    )
    recs = recommend(config, compromise_fraction=0.5)
    assert recs[0].config_diff == {"detector_sensitivity": 1.0}


def test_no_recommendation_when_sensitivity_already_maxed():
    config = ExperimentConfig(
        seed=1, node_count=25, defense_enabled=True, detector_sensitivity=1.0
    )
    assert recommend(config, compromise_fraction=0.9) == []
