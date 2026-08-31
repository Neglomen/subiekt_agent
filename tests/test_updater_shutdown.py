"""
Zamykanie agenta przed uruchomieniem instalatora.

Aktualizacja potrafila padac na bledach dostepu do plikow, bo agent w praktyce nie
konczyl pracy: `apply_update` wolal `sys.exit(0)` z watku pobierania, a `sys.exit()`
poza watkiem glownym konczy wylacznie ten watek. Do tego `cloudflared.exe` / `ngrok.exe`
agent pobiera do katalogu instalacji i uruchamia jako procesy potomne — samo zamkniecie
agenta ich nie ubija, a dopoki zyja, Inno Setup nie nadpisze plikow.
"""
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services import updater as updater_module
from app.services.updater import UpdateManager


@pytest.fixture
def manager(tmp_path: Path) -> UpdateManager:
    m = UpdateManager()
    installer = tmp_path / "SuppSalesAgent_Setup.exe"
    installer.write_bytes(b"udawany instalator")
    m.downloaded_file_path = installer
    return m


def test_services_are_stopped_before_the_installer_starts(manager):
    """
    Kolejnosc jest istotna: najpierw zwalniamy pliki, dopiero potem instalator.
    Odwrotnie instalator zaczyna kopiowac, gdy tunel wciaz trzyma swoja binarke.
    """
    kolejnosc = []

    with patch.object(UpdateManager, "_release_file_locks", side_effect=lambda: kolejnosc.append("stop")), patch(
        "app.services.updater.subprocess.Popen", side_effect=lambda *a, **k: kolejnosc.append("instalator")
    ), patch("app.services.updater.time.sleep"), patch("app.services.updater.os._exit") as exit_mock:
        manager.apply_update()

    assert kolejnosc == ["stop", "instalator"]
    exit_mock.assert_called_once_with(0)


def test_process_is_ended_with_os_exit_not_sys_exit(manager):
    """
    `sys.exit()` w watku pobierania konczylby tylko ten watek, a proces agenta zylby
    dalej i trzymal wlasne pliki. Regresja pilnuje, ze nie wraca stary sposob.
    """
    with patch.object(UpdateManager, "_release_file_locks"), patch(
        "app.services.updater.subprocess.Popen"
    ), patch("app.services.updater.time.sleep"), patch("app.services.updater.os._exit") as exit_mock, patch.object(
        sys, "exit"
    ) as sys_exit_mock:
        manager.apply_update()

    exit_mock.assert_called_once_with(0)
    sys_exit_mock.assert_not_called()


def test_missing_installer_does_not_kill_the_agent(tmp_path):
    """Bez pobranego pliku nie ma czego instalowac — agent ma zyc dalej."""
    m = UpdateManager()
    m.downloaded_file_path = tmp_path / "nie-ma-takiego.exe"

    with patch("app.services.updater.os._exit") as exit_mock, patch(
        "app.services.updater.subprocess.Popen"
    ) as popen_mock:
        m.apply_update()

    exit_mock.assert_not_called()
    popen_mock.assert_not_called()


def test_failed_installer_launch_reports_error_and_keeps_running(manager):
    """
    Gdy instalator nie wystartuje, zamkniecie agenta zostawiloby uzytkownika bez
    dzialajacej aplikacji i bez aktualizacji. Zostajemy przy zyciu i mowimy, co nie wyszlo.
    """
    with patch.object(UpdateManager, "_release_file_locks"), patch(
        "app.services.updater.subprocess.Popen", side_effect=OSError("brak dostepu")
    ), patch("app.services.updater.time.sleep"), patch("app.services.updater.os._exit") as exit_mock:
        manager.apply_update()

    exit_mock.assert_not_called()
    assert manager.download_status == "error"
    assert "brak dostepu" in manager.error_message


def test_release_file_locks_stops_tunnels_through_agent_manager(manager):
    """
    Zatrzymanie idzie przez `AgentManager.stop()`, bo to jedyne miejsce, ktore domyka
    tunele, uvicorna i SferaWorkera naraz.
    """
    agent_manager = MagicMock()
    fake_tray = types.ModuleType("app.gui.tray")
    fake_tray._tray_instance = types.SimpleNamespace(agent_manager=agent_manager)

    with patch.dict(sys.modules, {"app.gui.tray": fake_tray}):
        manager._release_file_locks()

    agent_manager.stop.assert_called_once()


def test_release_file_locks_survives_a_broken_tray(manager):
    """
    Awaria sprzatania nie moze zablokowac aktualizacji — gorszy jest agent, ktory nie
    daje sie zaktualizowac, niz instalator, ktory trafi na zablokowany plik i o tym powie.
    """
    agent_manager = MagicMock()
    agent_manager.stop.side_effect = RuntimeError("tray padl")
    fake_tray = types.ModuleType("app.gui.tray")
    fake_tray._tray_instance = types.SimpleNamespace(agent_manager=agent_manager)

    with patch.dict(sys.modules, {"app.gui.tray": fake_tray}):
        manager._release_file_locks()  # nie moze rzucic


def test_release_file_locks_handles_missing_tray_instance(manager):
    """Agent uruchomiony bez traya (np. w testach albo headless) nie ma czego zatrzymywac."""
    fake_tray = types.ModuleType("app.gui.tray")
    fake_tray._tray_instance = None

    with patch.dict(sys.modules, {"app.gui.tray": fake_tray}):
        manager._release_file_locks()  # nie moze rzucic


def test_updater_no_longer_imports_sys():
    """
    `sys` zostal usuniety razem z `sys.exit`. Gdyby wrocil, to sygnal, ze ktos przywrocil
    stary sposob konczenia procesu.
    """
    assert not hasattr(updater_module, "sys")
