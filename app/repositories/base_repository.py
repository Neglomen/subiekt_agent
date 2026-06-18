# Plik: subiekt_agent/app/repositories/base_repository.py

from app.sfera.sfera_instance import SferaInstance

class BaseRepository:
    """Klasa bazowa dla wszystkich repozytoriów, wstrzykuje instancję Sfery."""
    def __init__(self, sfera: SferaInstance):
        self._sfera = sfera

    @property
    def ado_connection(self):
        return self._sfera.ado_connection