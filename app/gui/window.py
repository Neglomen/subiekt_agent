import tkinter as tk
from tkinter import ttk, messagebox
import queue
import time
import sys
import os
import uuid
import webbrowser
from pathlib import Path
import winreg

import app.config as app_config
from app.config import SferaSettings, save_sfera_settings

class AgentWindow(tk.Toplevel):
    def __init__(self, parent, agent_manager, log_queue):
        super().__init__(parent)
        self.parent = parent
        self.agent_manager = agent_manager
        self.log_queue = log_queue
        
        self.title("SuppSales Subiekt GT Agent - Panel Kontrolny")
        self.geometry("750x550")
        self.minsize(650, 450)
        
        # Ikona okna (jeśli istnieje)
        self._setup_window_icon()
        
        # Cykliczne sprawdzanie logów i statusu
        self.protocol("WM_DELETE_WINDOW", self.withdraw)  # Zamykanie okna tylko ukrywa je do traya
        
        # Stylowanie
        self._apply_styles()
        
        # Budowanie komponentów
        self._create_widgets()
        
        # Uruchomienie cykli aktualizacji GUI
        self.update_logs()
        self.update_status_ui()

    def _setup_window_icon(self):
        try:
            icon_path = Path(app_config.BASE_DIR) / "app" / "gui" / "assets" / "icon.png"
            if icon_path.exists():
                self.icon_photo = tk.PhotoImage(file=str(icon_path))
                self.iconphoto(False, self.icon_photo)
        except Exception:
            pass

    def _apply_styles(self):
        style = ttk.Style(self)
        style.theme_use('vista' if 'vista' in style.theme_names() else 'clam')
        
        # Kolory i czcionki
        style.configure("TNotebook", background="#f0f2f5")
        style.configure("TNotebook.Tab", padding=[12, 6], font=("Segoe UI", 10))
        style.configure("TFrame", background="#ffffff")
        style.configure("TLabelframe", background="#ffffff", font=("Segoe UI", 10, "bold"))
        style.configure("TLabelframe.Label", background="#ffffff", foreground="#2c3e50")
        
        style.configure("TLabel", background="#ffffff", font=("Segoe UI", 10))
        style.configure("Header.TLabel", font=("Segoe UI", 12, "bold"), foreground="#2c3e50")
        
        style.configure("TButton", font=("Segoe UI", 10), padding=5)
        style.configure("Action.TButton", font=("Segoe UI", 10, "bold"))
        style.configure("TCheckbutton", background="#ffffff")

    def _create_widgets(self):
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Zakładki
        self.tab_status = ttk.Frame(self.notebook)
        self.tab_logs = ttk.Frame(self.notebook)
        self.tab_settings = ttk.Frame(self.notebook)
        
        self.notebook.add(self.tab_status, text=" Status ")
        self.notebook.add(self.tab_logs, text=" Logi ")
        self.notebook.add(self.tab_settings, text=" Ustawienia ")
        
        self._build_status_tab()
        self._build_logs_tab()
        self._build_settings_tab()

    # --- ZAKŁADKA STATUS ---
    def _build_status_tab(self):
        frame = self.tab_status
        
        # Header
        header = ttk.Label(frame, text="Status działania agenta SuppSales", style="Header.TLabel")
        header.pack(anchor="w", padx=20, pady=15)
        
        # Grid ze statusem
        status_box = ttk.LabelFrame(frame, text=" Parametry połączeń ")
        status_box.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # Wskaźnik działania Agenta
        ttk.Label(status_box, text="Uruchomiony serwer API:").grid(row=0, column=0, sticky="w", padx=15, pady=10)
        self.lbl_agent_status = ttk.Label(status_box, text="Nieznany", font=("Segoe UI", 10, "bold"))
        self.lbl_agent_status.grid(row=0, column=1, sticky="w", padx=5, pady=10)
        
        # Wskaźnik Sfery GT
        ttk.Label(status_box, text="Połączenie ze Sferą GT:").grid(row=1, column=0, sticky="w", padx=15, pady=10)
        
        sfera_indicator_frame = ttk.Frame(status_box)
        sfera_indicator_frame.grid(row=1, column=1, sticky="w", padx=5, pady=10)
        
        self.canvas_sfera = tk.Canvas(sfera_indicator_frame, width=15, height=15, bg="white", highlightthickness=0)
        self.canvas_sfera.pack(side=tk.LEFT)
        self.sfera_dot = self.canvas_sfera.create_oval(2, 2, 13, 13, fill="red")
        
        self.lbl_sfera_status = ttk.Label(sfera_indicator_frame, text="Rozłączono", font=("Segoe UI", 10))
        self.lbl_sfera_status.pack(side=tk.LEFT, padx=5)
        
        # Wskaźnik Cloudflare Tunnel
        ttk.Label(status_box, text="Cloudflare Tunnel:").grid(row=2, column=0, sticky="w", padx=15, pady=10)
        
        cf_indicator_frame = ttk.Frame(status_box)
        cf_indicator_frame.grid(row=2, column=1, sticky="w", padx=5, pady=10)
        
        self.canvas_cf = tk.Canvas(cf_indicator_frame, width=15, height=15, bg="white", highlightthickness=0)
        self.canvas_cf.pack(side=tk.LEFT)
        self.cf_dot = self.canvas_cf.create_oval(2, 2, 13, 13, fill="red")
        
        self.lbl_cf_status = ttk.Label(cf_indicator_frame, text="Wyłączony", font=("Segoe UI", 10))
        self.lbl_cf_status.pack(side=tk.LEFT, padx=5)
        
        # Publiczny URL
        ttk.Label(status_box, text="Publiczny adres URL:").grid(row=3, column=0, sticky="nw", padx=15, pady=10)
        
        url_frame = ttk.Frame(status_box)
        url_frame.grid(row=3, column=1, sticky="w", padx=5, pady=10)
        
        self.lbl_cf_url = ttk.Label(url_frame, text="Brak aktywnego tunelu", foreground="gray", cursor="hand2")
        self.lbl_cf_url.pack(side=tk.LEFT)
        self.lbl_cf_url.bind("<Button-1>", lambda e: self._open_tunnel_url())
        
        self.btn_copy_url = ttk.Button(url_frame, text="Kopiuj", width=8, command=self._copy_tunnel_url)
        self.btn_copy_url.pack(side=tk.LEFT, padx=10)
        self.btn_copy_url.pack_forget() # Schowaj na początku
        
        # Uptime
        ttk.Label(status_box, text="Czas działania:").grid(row=4, column=0, sticky="w", padx=15, pady=10)
        self.lbl_uptime = ttk.Label(status_box, text="00:00:00")
        self.lbl_uptime.grid(row=4, column=1, sticky="w", padx=5, pady=10)
        
        # Sekcja przycisków akcji
        action_frame = ttk.Frame(frame)
        action_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=20, pady=20)
        
        self.btn_start = ttk.Button(action_frame, text="Uruchom agenta", style="Action.TButton", command=self._action_start)
        self.btn_start.pack(side=tk.LEFT, padx=5)
        
        self.btn_stop = ttk.Button(action_frame, text="Zatrzymaj agenta", command=self._action_stop)
        self.btn_stop.pack(side=tk.LEFT, padx=5)
        
        self.btn_restart = ttk.Button(action_frame, text="Restartuj agenta", command=self._action_restart)
        self.btn_restart.pack(side=tk.LEFT, padx=5)

    def _open_tunnel_url(self):
        url = self.lbl_cf_url.cget("text")
        if url.startswith("http"):
            webbrowser.open(url)

    def _copy_tunnel_url(self):
        url = self.lbl_cf_url.cget("text")
        if url.startswith("http"):
            self.clipboard_clear()
            self.clipboard_append(url)
            messagebox.showinfo("Kopiowanie", "Adres URL został skopiowany do schowka!")

    def _action_start(self):
        self.agent_manager.start()
        
    def _action_stop(self):
        self.agent_manager.stop()
        
    def _action_restart(self):
        self.agent_manager.restart()

    # --- ZAKŁADKA LOGI ---
    def _build_logs_tab(self):
        frame = self.tab_logs
        
        # Panel kontrolny logów (u góry)
        control_frame = ttk.Frame(frame)
        control_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(control_frame, text="Filtr logów:").pack(side=tk.LEFT, padx=5)
        self.log_level_filter = ttk.Combobox(control_frame, values=["DEBUG", "INFO", "WARNING", "ERROR"], state="readonly", width=12)
        self.log_level_filter.set("INFO")
        self.log_level_filter.pack(side=tk.LEFT, padx=5)
        self.log_level_filter.bind("<<ComboboxSelected>>", lambda e: self._clear_text_widget_logs())
        
        btn_clear = ttk.Button(control_frame, text="Wyczyść logi", command=self._clear_text_widget_logs)
        btn_clear.pack(side=tk.RIGHT, padx=5)
        
        # Główny terminal logów
        text_frame = ttk.Frame(frame)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.log_text = tk.Text(text_frame, wrap=tk.WORD, font=("Consolas", 9), bg="#1e1e1e", fg="#d4d4d4", insertbackground="white")
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=scrollbar.set)
        
        # Definiowanie tagów do kolorowania
        self.log_text.tag_config("DEBUG", foreground="#7f8c8d")
        self.log_text.tag_config("INFO", foreground="#ecf0f1")
        self.log_text.tag_config("WARNING", foreground="#f1c40f")
        self.log_text.tag_config("ERROR", foreground="#e74c3c")
        
        self.log_text.config(state=tk.DISABLED)
        self.logged_lines = []

    def _clear_text_widget_logs(self):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state=tk.DISABLED)
        # Ponownie wczytaj odfiltrowane logi z zapamiętanych linii
        self._redisplay_logs()

    def _redisplay_logs(self):
        self.log_text.config(state=tk.NORMAL)
        min_level = self.log_level_filter.get()
        level_values = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3}
        min_val = level_values.get(min_level, 1)
        
        for level, line in self.logged_lines:
            line_val = level_values.get(level, 1)
            if line_val >= min_val:
                self.log_text.insert(tk.END, line + "\n", level)
                
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    # --- ZAKŁADKA USTAWIENIA ---
    def _build_settings_tab(self):
        frame = self.tab_settings
        
        # Zawijamy w Canvas z Scrollbarem, na wypadek gdyby okno było za małe
        canvas = tk.Canvas(frame, borderwidth=0, background="#ffffff", highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Grid dla ustawień
        # --- Sekcja 1: Subiekt & SQL ---
        db_frame = ttk.LabelFrame(scrollable_frame, text=" Konfiguracja Bazy Danych i Sfery GT ")
        db_frame.pack(fill=tk.X, expand=True, padx=15, pady=10)
        
        ttk.Label(db_frame, text="Serwer SQL:").grid(row=0, column=0, sticky="w", padx=10, pady=5)
        self.ent_db_server = ttk.Entry(db_frame, width=45)
        self.ent_db_server.grid(row=0, column=1, sticky="w", padx=10, pady=5)
        
        ttk.Label(db_frame, text="Nazwa Bazy Danych:").grid(row=1, column=0, sticky="w", padx=10, pady=5)
        self.ent_db_name = ttk.Entry(db_frame, width=45)
        self.ent_db_name.grid(row=1, column=1, sticky="w", padx=10, pady=5)
        
        ttk.Label(db_frame, text="Operator Sfery:").grid(row=2, column=0, sticky="w", padx=10, pady=5)
        self.ent_operator = ttk.Entry(db_frame, width=45)
        self.ent_operator.grid(row=2, column=1, sticky="w", padx=10, pady=5)
        
        ttk.Label(db_frame, text="Hasło Operatora:").grid(row=3, column=0, sticky="w", padx=10, pady=5)
        self.ent_password = ttk.Entry(db_frame, width=45, show="*")
        self.ent_password.grid(row=3, column=1, sticky="w", padx=10, pady=5)
        
        # --- Sekcja 2: Ustawienia Agenta API ---
        agent_frame = ttk.LabelFrame(scrollable_frame, text=" Ustawienia Serwera Agenta ")
        agent_frame.pack(fill=tk.X, expand=True, padx=15, pady=10)
        
        ttk.Label(agent_frame, text="Klucz API Agenta (API Key):").grid(row=0, column=0, sticky="w", padx=10, pady=5)
        
        api_key_frame = ttk.Frame(agent_frame)
        api_key_frame.grid(row=0, column=1, sticky="w", padx=10, pady=5)
        
        self.ent_api_key = ttk.Entry(api_key_frame, width=32)
        self.ent_api_key.pack(side=tk.LEFT)
        
        btn_gen_key = ttk.Button(api_key_frame, text="Generuj", width=8, command=self._generate_api_key)
        btn_gen_key.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(agent_frame, text="Port Serwera API:").grid(row=1, column=0, sticky="w", padx=10, pady=5)
        self.ent_port = ttk.Entry(agent_frame, width=12)
        self.ent_port.grid(row=1, column=1, sticky="w", padx=10, pady=5)
        
        # --- Sekcja 3: Tunel Cloudflare ---
        cf_frame = ttk.LabelFrame(scrollable_frame, text=" Tunel Cloudflare ")
        cf_frame.pack(fill=tk.X, expand=True, padx=15, pady=10)
        
        self.var_cf_enabled = tk.BooleanVar()
        self.chk_cf_enabled = ttk.Checkbutton(cf_frame, text="Włącz Cloudflare Tunnel", variable=self.var_cf_enabled, command=self._toggle_cf_inputs)
        self.chk_cf_enabled.grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=5)
        
        self.lbl_cf_token = ttk.Label(cf_frame, text="Token Named Tunnel (opcjonalny):")
        self.lbl_cf_token.grid(row=1, column=0, sticky="w", padx=10, pady=5)
        self.ent_cf_token = ttk.Entry(cf_frame, width=45, show="*")
        self.ent_cf_token.grid(row=1, column=1, sticky="w", padx=10, pady=5)
        
        self.lbl_cf_custom_url = ttk.Label(cf_frame, text="Własna domena (np. agent.firma.pl):")
        self.lbl_cf_custom_url.grid(row=2, column=0, sticky="w", padx=10, pady=5)
        self.ent_cf_custom_url = ttk.Entry(cf_frame, width=45)
        self.ent_cf_custom_url.grid(row=2, column=1, sticky="w", padx=10, pady=5)
        
        # --- Sekcja 4: Systemowe ---
        sys_frame = ttk.LabelFrame(scrollable_frame, text=" Systemowe ")
        sys_frame.pack(fill=tk.X, expand=True, padx=15, pady=10)
        
        self.var_autostart = tk.BooleanVar()
        self.chk_autostart = ttk.Checkbutton(sys_frame, text="Uruchamiaj automatycznie przy starcie systemu Windows", variable=self.var_autostart)
        self.chk_autostart.grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=5)
        
        # Przyciski zapisu
        save_frame = ttk.Frame(scrollable_frame)
        save_frame.pack(fill=tk.X, expand=True, padx=15, pady=15)
        
        btn_save = ttk.Button(save_frame, text="Zapisz i restartuj agenta", style="Action.TButton", command=self._save_settings)
        btn_save.pack(side=tk.RIGHT, padx=10)
        
        # Wczytanie początkowych wartości z konfiguracji
        self._load_settings_into_inputs()

    def _toggle_cf_inputs(self):
        state = tk.NORMAL if self.var_cf_enabled.get() else tk.DISABLED
        self.ent_cf_token.config(state=state)
        self.ent_cf_custom_url.config(state=state)

    def _generate_api_key(self):
        new_key = uuid.uuid4().hex + uuid.uuid4().hex[:16]
        self.ent_api_key.delete(0, tk.END)
        self.ent_api_key.insert(0, new_key)

    def _load_settings_into_inputs(self):
        sfera = app_config.settings.sfera
        
        self.ent_db_server.insert(0, sfera.db_server_name)
        self.ent_db_name.insert(0, sfera.db_name)
        self.ent_operator.insert(0, sfera.sfera_operator)
        self.ent_password.insert(0, sfera.sfera_operator_password)
        self.ent_api_key.insert(0, sfera.agent_api_key)
        self.ent_port.insert(0, str(sfera.agent_port))
        
        self.var_cf_enabled.set(sfera.cloudflare_enabled)
        self.ent_cf_token.insert(0, sfera.cloudflare_token)
        self.ent_cf_custom_url.insert(0, sfera.cloudflare_custom_url)
        self._toggle_cf_inputs()
        
        self.var_autostart.set(self._get_autostart_registry())

    def _save_settings(self):
        try:
            port = int(self.ent_port.get().strip())
        except ValueError:
            messagebox.showerror("Błąd", "Port musi być liczbą całkowitą!")
            return
            
        # Zapisz ustawienia do Pydantic
        sfera_settings = SferaSettings(
            db_server_name=self.ent_db_server.get().strip(),
            db_name=self.ent_db_name.get().strip(),
            sfera_operator=self.ent_operator.get().strip(),
            sfera_operator_password=self.ent_password.get(),
            agent_api_key=self.ent_api_key.get().strip(),
            cloudflare_enabled=self.var_cf_enabled.get(),
            cloudflare_token=self.ent_cf_token.get().strip(),
            cloudflare_custom_url=self.ent_cf_custom_url.get().strip(),
            agent_port=port,
            autostart_enabled=self.var_autostart.get()
        )
        
        try:
            # Zapis do .env
            save_sfera_settings(sfera_settings)
            
            # Zapis do rejestru Windows dla Autostartu
            self._set_autostart_registry(self.var_autostart.get())
            
            # Restart agenta aby zaaplikować nowe ustawienia
            self.agent_manager.restart()
            messagebox.showinfo("Sukces", "Ustawienia zostały zapisane. Agent restartuje się...")
            self.notebook.select(self.tab_status) # Przełącz na status
        except Exception as e:
            messagebox.showerror("Błąd zapisu", f"Nie udało się zapisać ustawień: {e}")

    # --- REGISTRY AUTOSTART HELPERS ---
    def _set_autostart_registry(self, enabled):
        REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
        APP_NAME = "SuppSalesAgent"
        
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_SET_VALUE)
            if enabled:
                # W paczce exe sys.executable to ścieżka do naszego Exe.
                # W środowisku python (dev) to ścieżka do python.exe.
                if getattr(sys, 'frozen', False):
                    cmd = f'"{sys.executable}"'
                else:
                    cmd = f'"{sys.executable}" "{Path(sys.argv[0]).resolve()}"'
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        except Exception as e:
            # Dodatkowe logowanie błędu, nie blokujemy zapisu ustawień
            logger.error(f"Nie udało się zmodyfikować wpisu autostartu w rejestrze: {e}")

    def _get_autostart_registry(self):
        REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
        APP_NAME = "SuppSalesAgent"
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_READ)
            try:
                winreg.QueryValueEx(key, APP_NAME)
                return True
            except FileNotFoundError:
                return False
            finally:
                winreg.CloseKey(key)
        except Exception:
            return False

    # --- CYKLICZNE AKTUALIZACJE GUI ---
    def update_logs(self):
        # Pobieraj z kolejki logów i dodawaj do log_text
        has_new_logs = False
        while True:
            try:
                level, msg = self.log_queue.get_nowait()
                self.logged_lines.append((level, msg))
                # Zachowaj max 1000 linii w pamięci
                if len(self.logged_lines) > 1000:
                    self.logged_lines.pop(0)
                has_new_logs = True
            except queue.Empty:
                break
                
        if has_new_logs:
            self._redisplay_logs()
            
        # Wywołaj ponownie za 200 ms
        self.after(200, self.update_logs)

    def update_status_ui(self):
        # Sprawdzamy status serwera API
        is_active = self.agent_manager.is_active
        self.lbl_agent_status.config(
            text="URUCHOMIONY" if is_active else "ZATRZYMANY",
            foreground="green" if is_active else "red"
        )
        
        # Włącz/wyłącz przyciski akcji
        if is_active:
            self.btn_start.config(state=tk.DISABLED)
            self.btn_stop.config(state=tk.NORMAL)
            self.btn_restart.config(state=tk.NORMAL)
        else:
            self.btn_start.config(state=tk.NORMAL)
            self.btn_stop.config(state=tk.DISABLED)
            self.btn_restart.config(state=tk.DISABLED)
            
        # Aktualizacja statusu Sfery GT
        from app.sfera.sfera_worker import sfera_worker
        sfera_connected = sfera_worker.is_ready and sfera_worker._sfera and sfera_worker._sfera.is_connected
        
        if sfera_connected:
            self.canvas_sfera.itemconfig(self.sfera_dot, fill="green")
            self.lbl_sfera_status.config(text="Połączono", foreground="green")
        else:
            self.canvas_sfera.itemconfig(self.sfera_dot, fill="red")
            self.lbl_sfera_status.config(text="Rozłączono" if is_active else "Nieaktywne", foreground="red" if is_active else "gray")
            
        # Aktualizacja statusu Cloudflare
        cf_manager = self.agent_manager.cloudflare_manager
        cf_enabled = app_config.settings.sfera.cloudflare_enabled
        
        if not cf_enabled:
            self.canvas_cf.itemconfig(self.cf_dot, fill="gray")
            self.lbl_cf_status.config(text="Wyłączony", foreground="gray")
            self.lbl_cf_url.config(text="Brak aktywnego tunelu (Cloudflare wyłączone)", foreground="gray", cursor="")
            self.btn_copy_url.pack_forget()
        elif cf_manager and cf_manager.public_url:
            self.canvas_cf.itemconfig(self.cf_dot, fill="green")
            self.lbl_cf_status.config(text="Połączono", foreground="green")
            self.lbl_cf_url.config(text=cf_manager.public_url, foreground="blue", cursor="hand2")
            self.btn_copy_url.pack(side=tk.LEFT, padx=10)
        else:
            self.canvas_cf.itemconfig(self.cf_dot, fill="yellow")
            self.lbl_cf_status.config(text="Łączenie...", foreground="orange")
            self.lbl_cf_url.config(text="Generowanie linku tunelu...", foreground="orange", cursor="")
            self.btn_copy_url.pack_forget()
            
        # Uuptime
        if is_active and self.agent_manager.start_time:
            elapsed = int(time.time() - self.agent_manager.start_time)
            hours, remainder = divmod(elapsed, 3600)
            minutes, seconds = divmod(remainder, 60)
            self.lbl_uptime.config(text=f"{hours:02d}:{minutes:02d}:{seconds:02d}")
        else:
            self.lbl_uptime.config(text="00:00:00")
            
        # Ponownie za 500 ms
        self.after(500, self.update_status_ui)
