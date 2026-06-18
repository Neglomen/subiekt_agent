import json
import logging
from typing import Dict, Any

from app.config import BASE_DIR, MappingSettings

logger = logging.getLogger(__name__)

class ConfigService:
    """Serwis do zarządzania konfiguracją agenta z pliku config.json."""

    def __init__(self):
        self.config_path = BASE_DIR / "config.json"

    def get_config(self) -> MappingSettings:
        """Odczytuje i zwraca aktualną konfigurację z pliku config.json."""
        if not self.config_path.exists():
            logger.warning("Plik config.json nie istnieje. Zwracam domyślne ustawienia.")
            return MappingSettings()
        
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return MappingSettings(**data)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Błąd odczytu lub parsowania config.json: {e}. Zwracam domyślne ustawienia.")
            return MappingSettings()

    def save_config(self, settings) -> MappingSettings:
        """
        Zapisuje konfigurację do pliku config.json i odświeża globalny obiekt settings.
        Przyjmuje zarówno MappingSettings jak i AllMappingsRead (lub dowolny Pydantic model).
        """
        import app.config as app_config

        # Konwertujemy wejście do słownika, a następnie do MappingSettings
        # aby mieć pewność że wszyskie pola są poprawnie zwalidowane
        if isinstance(settings, MappingSettings):
            mapping_settings = settings
        else:
            # AllMappingsRead lub inny kompatybilny model — konwertuj przez dict
            raw = settings.model_dump() if hasattr(settings, 'model_dump') else dict(settings)
            mapping_settings = MappingSettings(**raw)

        try:
            json_content = mapping_settings.model_dump_json(indent=2)
            with open(self.config_path, "w", encoding="utf-8") as f:
                f.write(json_content)
            logger.info(f"Pomyślnie zapisano konfigurację do pliku: {self.config_path}")
        except IOError as e:
            logger.error(f"Błąd zapisu do pliku config.json: {e}")
            raise

        # === KLUCZOWE: Odśwież globalny obiekt settings w pamięci ===
        # Dzięki temu agent używa nowej konfiguracji natychmiast, bez restartu.
        app_config.settings = app_config.AppConfig(
            sfera_settings=app_config.settings.sfera,
            mapping_settings=mapping_settings
        )
        logger.info(f"Globalny obiekt settings odświeżony. ksef_enabled={mapping_settings.ksef_enabled}")

        return mapping_settings

    def update_payment_mappings(self, mappings: Dict[str, str]) -> MappingSettings:
        """Aktualizuje tylko mapowania płatności i zapisuje całość."""
        current_settings = self.get_config()
        current_settings.payment_type_mappings = mappings
        return self.save_config(current_settings)

    def update_service_mappings(self, mappings_data: Dict[str, Any]) -> MappingSettings:
        """Aktualizuje tylko mapowania usług i zapisuje całość."""
        current_settings = self.get_config()
        current_settings.service_mappings = mappings_data
        return self.save_config(current_settings)