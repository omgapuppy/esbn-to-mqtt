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

    assert config["name"] == "esbn-to-mqtt"
    assert config["slug"] == "esbn_to_mqtt"
    assert config["options"]["mqtt_host"] == "core-mosquitto"
    assert config["options"]["mqtt_port"] == 1883
    assert config["options"]["poll_interval_hours"] == 6
    assert config["schema"]["esbn_password"] == "password"
    assert config["schema"]["mqtt_password"] == "password"
    assert config["schema"]["mqtt_host"] == "str"
    assert config["schema"]["mqtt_port"] == "port"
    assert "mqtt:need" in config["services"]
    assert config["options"]["log_level"] == "info"
    assert config["schema"]["log_level"] == "list(trace|debug|info|notice|warning|error|fatal)"


def test_app_build_metadata() -> None:
    build = load_yaml(ROOT / "esbn-to-mqtt" / "build.yaml")

    assert build["build_from"] == {
        "aarch64": "ghcr.io/home-assistant/aarch64-base:3.22",
        "amd64": "ghcr.io/home-assistant/amd64-base:3.22",
    }


def test_ci_workflow_metadata() -> None:
    workflow = load_yaml_as_strings(ROOT / ".github" / "workflows" / "ci.yml")

    assert workflow["name"] == "CI"
    assert "pull_request" in workflow["on"]
    assert workflow["on"]["push"]["branches"] == ["codex/**", "feature/**", "fix/**"]


def test_release_workflow_metadata() -> None:
    workflow = load_yaml_as_strings(ROOT / ".github" / "workflows" / "release.yml")
    publish_job = workflow["jobs"]["publish"]
    workflow_text = (ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )

    assert workflow["name"] == "Release"
    assert workflow["on"]["pull_request"]["types"] == ["closed"]
    assert workflow["permissions"] == {"contents": "write", "packages": "write"}
    assert "github.event.pull_request.merged == true" in publish_job["if"]
    assert "contains(github.event.pull_request.labels.*.name, 'release')" in publish_job["if"]
    assert "version:" in workflow_text
    assert "amd64-${{ env.IMAGE_NAME }}:${{ steps.app.outputs.version }}" in workflow_text
    assert "aarch64-${{ env.IMAGE_NAME }}:${{ steps.app.outputs.version }}" in workflow_text
    assert "gh release create" in workflow_text
    assert "--generate-notes" in workflow_text
