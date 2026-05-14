from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_yaml(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    assert isinstance(data, dict)
    return data


def load_yaml_as_strings(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.load(handle, Loader=yaml.BaseLoader)
    assert isinstance(data, dict)
    return data


def test_repository_metadata() -> None:
    repository = load_yaml(ROOT / "repository.yaml")

    assert repository["name"] == "esbn-to-mqtt Home Assistant app repository"
    assert repository["url"] == "https://github.com/omgapuppy/esbn-to-mqtt"


def test_app_metadata() -> None:
    config = load_yaml(ROOT / "esbn-to-mqtt" / "config.yaml")

    assert config["slug"] == "esbn_to_mqtt"
    assert config["options"]["poll_interval_hours"] == 6
    assert config["schema"]["esbn_password"] == "password"
    assert config["services"] == ["mqtt:need"]
    assert config["options"]["log_level"] == "info"
    assert config["schema"]["log_level"] == "list(trace|debug|info|notice|warning|error|fatal)"


def test_ci_workflow_metadata() -> None:
    workflow = load_yaml_as_strings(ROOT / ".github" / "workflows" / "ci.yml")

    assert workflow["name"] == "CI"
    assert workflow["on"]["pull_request"] == ""
    assert workflow["on"]["push"]["branches"] == ["codex/**", "feature/**", "fix/**"]
