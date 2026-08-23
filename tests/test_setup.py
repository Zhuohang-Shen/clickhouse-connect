import runpy
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).parents[1]
SETUP_PATH = ROOT / "setup.py"


def _run_setup(
    monkeypatch: pytest.MonkeyPatch,
    setup: Callable[..., None],
    *,
    cythonize: Callable[..., list[Any]] | None = None,
    skip_cython: bool = False,
) -> None:
    setuptools = ModuleType("setuptools")
    setuptools.find_packages = lambda **_kwargs: []  # type: ignore[attr-defined]
    setuptools.setup = setup  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "setuptools", setuptools)

    if cythonize is None:
        monkeypatch.setitem(sys.modules, "Cython", None)
        monkeypatch.setitem(sys.modules, "Cython.Build", None)
    else:
        cython = ModuleType("Cython")
        cython.__version__ = "test"  # type: ignore[attr-defined]
        cython_build = ModuleType("Cython.Build")
        cython_build.cythonize = cythonize  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "Cython", cython)
        monkeypatch.setitem(sys.modules, "Cython.Build", cython_build)

    if skip_cython:
        monkeypatch.setenv("CLICKHOUSE_CONNECT_SKIP_CYTHON", "1")
    else:
        monkeypatch.delenv("CLICKHOUSE_CONNECT_SKIP_CYTHON", raising=False)
    monkeypatch.chdir(ROOT)
    runpy.run_path(str(SETUP_PATH), run_name="__main__")


def test_cython_import_failure_requires_explicit_opt_out(monkeypatch: pytest.MonkeyPatch) -> None:
    setup_calls = 0

    def setup(**_kwargs: Any) -> None:
        nonlocal setup_calls
        setup_calls += 1

    with pytest.raises(RuntimeError, match="CLICKHOUSE_CONNECT_SKIP_CYTHON=1"):
        _run_setup(monkeypatch, setup)

    assert setup_calls == 0


def test_cythonize_failure_requires_explicit_opt_out(monkeypatch: pytest.MonkeyPatch) -> None:
    setup_calls = 0

    def setup(**_kwargs: Any) -> None:
        nonlocal setup_calls
        setup_calls += 1

    def cythonize(*_args: Any, **_kwargs: Any) -> list[Any]:
        raise ValueError("invalid Cython source")

    with pytest.raises(RuntimeError, match="CLICKHOUSE_CONNECT_SKIP_CYTHON=1"):
        _run_setup(monkeypatch, setup, cythonize=cythonize)

    assert setup_calls == 0


def test_setup_failure_is_not_retried_without_extensions(monkeypatch: pytest.MonkeyPatch) -> None:
    class SetupError(Exception):
        pass

    setup_calls = 0

    def setup(**_kwargs: Any) -> None:
        nonlocal setup_calls
        setup_calls += 1
        raise SetupError("broken package metadata")

    with pytest.raises(SetupError, match="broken package metadata"):
        _run_setup(monkeypatch, setup, cythonize=lambda *_args, **_kwargs: [object()])

    assert setup_calls == 1


def test_explicit_skip_cython_builds_without_extensions(monkeypatch: pytest.MonkeyPatch) -> None:
    setup_calls: list[dict[str, Any]] = []

    def setup(**kwargs: Any) -> None:
        setup_calls.append(kwargs)

    def cythonize(*_args: Any, **_kwargs: Any) -> list[Any]:
        raise AssertionError("Cython must not be imported when explicitly skipped")

    _run_setup(monkeypatch, setup, cythonize=cythonize, skip_cython=True)

    assert len(setup_calls) == 1
    assert setup_calls[0]["ext_modules"] == []
