from pathlib import Path

import pytest


def test_rejects_legacy_conda_section(tmp_path: Path) -> None:
    from dekk.environment.spec import EnvironmentSpec
    from dekk.cli.errors import ValidationError

    spec_path = tmp_path / ".dekk.toml"
    spec_path.write_text(
        '[project]\nname = "x"\n\n[conda]\nname="x"\nfile="environment.yaml"\n',
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        EnvironmentSpec.from_file(spec_path)


def test_parses_environment_section(tmp_path: Path) -> None:
    from dekk.environment.spec import EnvironmentSpec
    from dekk.environment.types import EnvironmentKind

    spec_path = tmp_path / ".dekk.toml"
    spec_path.write_text(
        '[project]\nname = "x"\n\n'
        "[environment]\n"
        'type = "conda"\n'
        'path = "{project}/.dekk/env"\n'
        'file = "environment.yaml"\n',
        encoding="utf-8",
    )

    spec = EnvironmentSpec.from_file(spec_path)
    assert spec.environment is not None
    assert spec.environment.type == "conda"
    assert spec.environment.kind is EnvironmentKind.CONDA
    assert "{project}" in spec.environment.path
    assert spec.environment.file == "environment.yaml"
