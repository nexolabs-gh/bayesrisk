"""La capa de compatibilidad ``nikodym`` 1.21.0 (enmienda RENOMBRE-BAYESRISK, D-REN-3/7).

Cada prueba corre en un subproceso con ``compat/nikodym/src`` en el ``PYTHONPATH``: el alias se
instala en ``sys.meta_path`` y no debe contaminar el proceso de la suite. Lo que se prueba es lo que
promete el paquete: avisa UNA vez, ``nikodym.<ruta>`` es el MISMO módulo ``bayesrisk.<ruta>``
(no una copia), lo que no existe en bayesrisk no existe en nikodym, ``python -m nikodym.ui``
arranca, y un pickle escrito con las rutas de nikodym ≤ 1.20 carga con las clases de bayesrisk.
Aparte, sin subproceso: los alias de clase de D-REN-3 y la paridad de *extras* y LICENSE de los dos
paquetes.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import tomllib
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
COMPAT = RAIZ / "compat" / "nikodym"


def _correr(codigo: str, *args: str) -> subprocess.CompletedProcess[str]:
    entorno = dict(os.environ)
    entorno["PYTHONPATH"] = os.pathsep.join(
        [str(COMPAT / "src"), str(RAIZ / "src"), entorno.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    orden = [sys.executable, *args] if args else [sys.executable, "-c", textwrap.dedent(codigo)]
    return subprocess.run(
        orden, check=False, capture_output=True, text=True, timeout=180, env=entorno
    )


def test_import_nikodym_avisa_una_sola_vez() -> None:
    resultado = _correr(
        """
        import warnings
        with warnings.catch_warnings(record=True) as vistos:
            warnings.simplefilter("always")
            import nikodym
            import nikodym
            import nikodym.binning
            from nikodym.scorecard import FittedScorecardBundle
            import importlib
            importlib.import_module("nikodym")
        avisos = [
            w for w in vistos
            if issubclass(w.category, DeprecationWarning)
            and "nikodym ahora se llama bayesrisk" in str(w.message)
        ]
        print(len(avisos), avisos[0].filename.replace("\\\\", "/").rsplit("/", 1)[-1])
        """
    )
    assert resultado.returncode == 0, resultado.stderr
    cuantos, archivo = resultado.stdout.split()
    assert cuantos == "1"
    # El aviso apunta al código del usuario (``<string>`` aquí), no a los internos de importlib.
    assert archivo == "<string>"


def test_los_submodulos_son_el_mismo_objeto_que_en_bayesrisk() -> None:
    resultado = _correr(
        """
        import sys, warnings
        warnings.simplefilter("ignore", DeprecationWarning)
        import nikodym, bayesrisk
        import nikodym.binning, bayesrisk.binning
        import nikodym.scorecard.bundle as viejo
        import bayesrisk.scorecard.bundle as nuevo
        from nikodym.core.config import NikodymConfig
        from bayesrisk.core.config import BayesRiskConfig
        assert nikodym.binning is bayesrisk.binning
        assert viejo is nuevo
        assert sys.modules["nikodym.scorecard.bundle"] is sys.modules["bayesrisk.scorecard.bundle"]
        assert NikodymConfig is BayesRiskConfig
        # El spec del módulo real no quedó con el nombre del alias.
        assert bayesrisk.binning.__spec__.name == "bayesrisk.binning"
        assert nuevo.__spec__.name == "bayesrisk.scorecard.bundle"
        assert nikodym.Scorecard is bayesrisk.Scorecard
        assert nikodym.run is bayesrisk.run
        assert nikodym.__version__ == "1.21.0"
        try:
            import nikodym.pd
        except ModuleNotFoundError:
            print("ok")
        """
    )
    assert resultado.returncode == 0, resultado.stderr
    assert resultado.stdout.strip() == "ok"


def test_un_pickle_con_las_rutas_de_nikodym_carga_con_bayesrisk(tmp_path: Path) -> None:
    """Pickle escrito con ``nikodym.core.config.schema.NikodymConfig``, cargado en otro proceso."""
    archivo = tmp_path / "config.pkl"
    escribir = _correr(
        f"""
        import pickle, warnings
        warnings.simplefilter("ignore", DeprecationWarning)
        import nikodym
        from bayesrisk.core.config import BayesRiskConfig
        from bayesrisk.core.exceptions import BayesRiskError
        cfg = BayesRiskConfig(name="legado")
        # Reproduce los bytes de nikodym 1.20: la clase se nombra por su ruta y nombre viejos.
        for clase, modulo, nombre in (
            (BayesRiskConfig, "nikodym.core.config.schema", "NikodymConfig"),
            (BayesRiskError, "nikodym.core.exceptions", "NikodymError"),
        ):
            clase.__module__, clase.__qualname__ = modulo, nombre
        datos = pickle.dumps({{"cfg": cfg, "error": BayesRiskError("x")}})
        assert b"nikodym.core.config.schema" in datos and b"NikodymConfig" in datos
        open(r"{archivo}", "wb").write(datos)
        print("ok")
        """
    )
    assert escribir.returncode == 0, escribir.stderr
    leer = _correr(
        f"""
        import pickle, warnings
        warnings.simplefilter("ignore", DeprecationWarning)
        from bayesrisk.core.config import BayesRiskConfig
        from bayesrisk.core.exceptions import BayesRiskError
        import nikodym  # lo que el usuario tiene instalado: bayesrisk + nikodym 1.21
        objeto = pickle.loads(open(r"{archivo}", "rb").read())
        assert type(objeto["cfg"]) is BayesRiskConfig, type(objeto["cfg"])
        assert objeto["cfg"].name == "legado"
        assert type(objeto["error"]) is BayesRiskError
        print("ok")
        """
    )
    assert leer.returncode == 0, leer.stderr
    assert leer.stdout.strip() == "ok"


def test_python_m_nikodym_ui_arranca() -> None:
    resultado = _correr("", "-W", "ignore::DeprecationWarning", "-m", "nikodym.ui", "--help")
    assert resultado.returncode == 0, resultado.stderr
    assert "--no-open" in resultado.stdout


def test_los_nombres_de_clase_anteriores_son_alias_del_mismo_objeto() -> None:
    import bayesrisk.core as core
    from bayesrisk.core import base, exceptions
    from bayesrisk.core import config as config_pkg
    from bayesrisk.core.config import schema

    pares = {
        schema.NikodymConfig: schema.BayesRiskConfig,
        schema.NikodymBaseConfig: schema.BayesRiskBaseConfig,
        exceptions.NikodymError: exceptions.BayesRiskError,
        base.BaseNikodymEstimator: base.BaseBayesRiskEstimator,
        base.NikodymClassifier: base.BayesRiskClassifier,
        base.NikodymTransformer: base.BayesRiskTransformer,
        config_pkg.NikodymConfig: schema.BayesRiskConfig,
        core.NikodymConfig: schema.BayesRiskConfig,
        core.NikodymError: exceptions.BayesRiskError,
    }
    for viejo, nuevo in pares.items():
        assert viejo is nuevo
    # Fuera de ``__all__``: la documentación y el autocompletado muestran sólo los nombres nuevos.
    assert "NikodymConfig" not in core.__all__
    assert "NikodymConfig" not in config_pkg.__all__


def test_compat_replica_los_extras_y_la_licencia() -> None:
    principal = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    compat = tomllib.loads((COMPAT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert compat["name"] == "nikodym"
    assert compat["dependencies"] == ["bayesrisk>=2.0,<3"]
    assert set(compat["optional-dependencies"]) == set(principal["optional-dependencies"])
    for extra, requisitos in compat["optional-dependencies"].items():
        assert requisitos == [f"bayesrisk[{extra}]>=2.0,<3"], extra
    assert "Development Status :: 7 - Inactive" in compat["classifiers"]
    assert compat["scripts"] == {"nikodym-ui": "bayesrisk.ui.__main__:main"}
    assert principal["scripts"] == {"bayesrisk-ui": "bayesrisk.ui.__main__:main"}
    assert (COMPAT / "LICENSE").read_bytes() == (RAIZ / "LICENSE").read_bytes()
    # El paquete de compatibilidad no trae código de la librería: un solo módulo.
    modulos = sorted(
        p.relative_to(COMPAT / "src").as_posix() for p in (COMPAT / "src").rglob("*.py")
    )
    assert modulos == ["nikodym/__init__.py"]


def test_el_tema_del_informe_anterior_sigue_validando() -> None:
    from bayesrisk.report.config import HtmlRenderConfig

    assert HtmlRenderConfig(theme="nikodym").theme == "bayesrisk"
    assert HtmlRenderConfig().theme == "bayesrisk"


def test_un_lineage_viejo_compara_su_version_contra_bayesrisk() -> None:
    import warnings
    from importlib import metadata

    from bayesrisk.core import study

    actual = metadata.version("bayesrisk")
    with warnings.catch_warnings(record=True) as vistos:
        warnings.simplefilter("always")
        study._advertir_drift_versiones({"nikodym": actual})
    assert not vistos, [str(w.message) for w in vistos]
    with warnings.catch_warnings(record=True) as vistos:
        warnings.simplefilter("always")
        study._advertir_drift_versiones({"nikodym": "1.19.0"})
    assert len(vistos) == 1
    assert "'bayesrisk': ('1.19.0'" in str(vistos[0].message)
