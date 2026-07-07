# Plik: subiekt_agent/app/config.py

import json
import logging
from pathlib import Path
from typing import Dict

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

import sys

# Ścieżka bazowa projektu (subiekt_agent/)
if getattr(sys, 'frozen', False):
    # W wersji skompilowanej .exe pliki .env i config.json znajdują się w tym samym folderze co .exe
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent

class SferaSettings(BaseSettings):
    """Konfiguracja połączenia ze Sferą wczytywana z .env."""
    db_server_name: str = "SERVER\\SQL"
    db_name: str = "DATABASE"
    sfera_operator: str = "Szef"
    sfera_operator_password: str = ""
    agent_api_key: str = "SECRET_API_KEY_PLACEHOLDER"
    
    # Ustawienia GUI i Tunelu Cloudflare
    cloudflare_enabled: bool = False
    cloudflare_token: str = ""
    cloudflare_custom_url: str = ""
    agent_port: int = 8000
    autostart_enabled: bool = False

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding='utf-8',
        extra='ignore'
    )

class ServiceMappings(BaseModel):
    delivery_prepaid: str = "DOSTAWA"
    delivery_cod: str = "POBRANIE"
    additional_services: Dict[str, str] = Field(default_factory=dict)

class MappingSettings(BaseModel):
    """Struktura dla mapowań wczytywanych z config.json."""
    ksef_enabled: bool = False
    fiscalization_enabled: bool = False
    fiscal_printer_id: int | None = None
    payment_type_mappings: Dict[str, str] = {
        "ONLINE": "Przelew",
        "CASH_ON_DELIVERY": "Pobranie"
    }
    service_mappings: ServiceMappings = Field(default_factory=ServiceMappings)
    product_mappings: Dict[str, str] = Field(default_factory=dict)
    distributed_costs_keywords: list[str] = Field(default_factory=list)

class AppConfig:
    """Główny obiekt konfiguracyjny, łączący wszystkie ustawienia."""
    def __init__(self, sfera_settings: SferaSettings, mapping_settings: MappingSettings):
        self.sfera = sfera_settings
        self.mappings = mapping_settings

def load_config() -> AppConfig:
    """Wczytuje konfigurację z plików .env i config.json."""
    sfera_settings = SferaSettings()

    config_json_path = BASE_DIR / "config.json"
    mapping_data = {}
    if config_json_path.exists():
        try:
            with open(config_json_path, "r", encoding="utf-8") as f:
                mapping_data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Nie udało się wczytać lub sparsować pliku config.json: {e}")
            
    mapping_settings = MappingSettings(**mapping_data)
    
    return AppConfig(sfera_settings=sfera_settings, mapping_settings=mapping_settings)

# Globalna instancja konfiguracji dostępna w całej aplikacji
settings = load_config()

def save_sfera_settings(sfera_settings: SferaSettings):
    """Zapisuje SferaSettings do pliku .env i aktualizuje globalną konfigurację."""
    env_path = BASE_DIR / ".env"
    lines = [
        "# Sekrety i konfiguracja środowiskowa\n",
        f"DB_SERVER_NAME={json.dumps(sfera_settings.db_server_name)}\n",
        f"DB_NAME={json.dumps(sfera_settings.db_name)}\n",
        f"SFERA_OPERATOR={json.dumps(sfera_settings.sfera_operator)}\n",
        f"SFERA_OPERATOR_PASSWORD={json.dumps(sfera_settings.sfera_operator_password)}\n",
        f"AGENT_API_KEY={json.dumps(sfera_settings.agent_api_key)}\n",
        f"CLOUDFLARE_ENABLED={str(sfera_settings.cloudflare_enabled).upper()}\n",
        f"CLOUDFLARE_TOKEN={json.dumps(sfera_settings.cloudflare_token)}\n",
        f"CLOUDFLARE_CUSTOM_URL={json.dumps(sfera_settings.cloudflare_custom_url)}\n",
        f"AGENT_PORT={sfera_settings.agent_port}\n",
        f"AUTOSTART_ENABLED={str(sfera_settings.autostart_enabled).upper()}\n",
    ]
    try:
        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(lines)
        
        # Odśwież globalny settings
        global settings
        settings = load_config()
        logger.info("Zapisano ustawienia .env i odświeżono konfigurację w pamięci.")
    except Exception as e:
        logger.error(f"Nie udało się zapisać pliku .env: {e}")
        raise