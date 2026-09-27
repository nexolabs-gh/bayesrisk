"""nikodym ahora se llama bayesrisk.

``nikodym`` 1.21.0 es el último release de este nombre y no trae código de la librería: mantiene
funcionando lo escrito para nikodym ≤ 1.20 —``import nikodym``, ``from nikodym.scorecard import
…``, ``python -m nikodym.ui`` y los pickles/joblib guardados— resolviendo cada ``nikodym.<ruta>``
al **mismo** módulo ``bayesrisk.<ruta>`` (no a una copia). Avisa una vez por proceso con un
``DeprecationWarning``. Para migrar basta reemplazar el import: ``import bayesrisk``.

Enmienda RENOMBRE-BAYESRISK (D-REN-7) en el repositorio de bayesrisk.
"""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.machinery
import importlib.util
import sys
import warnings
from types import CodeType, ModuleType
from typing import Any

import bayesrisk as _bayesrisk

__version__ = "1.21.0"
__all__ = [nombre for nombre in _bayesrisk.__all__ if nombre != "__version__"]

_VIEJO = "nikodym."
_NUEVO = "bayesrisk."


class _AliasLoader(importlib.abc.Loader):
    """Entrega el módulo real de bayesrisk bajo el nombre viejo, sin ejecutarlo de nuevo."""

    def __init__(self, real: str) -> None:
        self._real = real
        self._spec_real: importlib.machinery.ModuleSpec | None = None

    def create_module(self, spec: importlib.machinery.ModuleSpec) -> ModuleType:
        modulo = importlib.import_module(self._real)
        self._spec_real = modulo.__spec__
        return modulo

    def exec_module(self, module: ModuleType) -> None:
        # `importlib` le asigna al módulo el spec del alias antes de llamar aquí: se le devuelve el
        # suyo, para que el módulo real siga describiéndose como `bayesrisk.<ruta>`.
        if self._spec_real is not None:
            module.__spec__ = self._spec_real

    def get_code(self, fullname: str) -> CodeType | None:
        """Código del módulo real: lo pide ``runpy`` para ``python -m nikodym.<ruta>``."""
        spec = importlib.util.find_spec(self._real)
        if spec is None or spec.loader is None:
            return None
        return spec.loader.get_code(self._real)  # type: ignore[attr-defined, no-any-return]


class _AliasFinder(importlib.abc.MetaPathFinder):
    """Resuelve ``nikodym.<ruta>`` a ``bayesrisk.<ruta>``; lo que no existe allí no existe aquí."""

    def find_spec(
        self,
        fullname: str,
        path: Any = None,
        target: ModuleType | None = None,
    ) -> importlib.machinery.ModuleSpec | None:
        if not fullname.startswith(_VIEJO):
            return None
        real = _NUEVO + fullname[len(_VIEJO) :]
        try:
            spec_real = importlib.util.find_spec(real)
        except ModuleNotFoundError:
            return None
        if spec_real is None:
            return None
        return importlib.machinery.ModuleSpec(
            fullname,
            _AliasLoader(real),
            is_package=spec_real.submodule_search_locations is not None,
        )


if not any(isinstance(finder, _AliasFinder) for finder in sys.meta_path):
    sys.meta_path.insert(0, _AliasFinder())

warnings.warn(
    "nikodym ahora se llama bayesrisk: reemplaza `import nikodym` por `import bayesrisk` "
    "(https://docs.bayesadvisory.cl/migrar-desde-nikodym/). nikodym 1.21 es el último release "
    "de este nombre y sólo reexporta bayesrisk.",
    DeprecationWarning,
    stacklevel=2,
)


def __getattr__(name: str) -> Any:
    """Delega en ``bayesrisk`` lo que este módulo no define (también sus atributos perezosos)."""
    try:
        return getattr(_bayesrisk, name)
    except AttributeError:
        raise AttributeError(f"module 'nikodym' has no attribute {name!r}") from None


def __dir__() -> list[str]:
    return sorted({*globals(), *dir(_bayesrisk)})
