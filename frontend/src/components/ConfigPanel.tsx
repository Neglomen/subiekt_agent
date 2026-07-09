import React, { useState, useEffect } from 'react';
import { Eye, EyeOff, Copy, X, Save, RotateCcw } from 'lucide-react';
import { Toast } from './Toast';

// --- TYPES ---
export interface GUIConfig {
  db_server_name: string;
  db_name: string;
  sfera_operator: string;
  sfera_operator_password: string;
  agent_api_key: string;
  agent_port: number;
  cloudflare_enabled: boolean;
  cloudflare_token: string;
  cloudflare_custom_url: string;
  autostart_enabled: boolean;
  // Ngrok tunnel
  ngrok_enabled: boolean;
  ngrok_authtoken: string;
  ngrok_domain: string;
  // Mapping settings (from config.json)
  ksef_enabled: boolean;
  fiscalization_enabled: boolean;
  fiscal_printer_id: number;
  distributed_costs_keywords: string[];
}

interface ConfigPanelProps {
  config: GUIConfig;
  onSave: (newConfig: GUIConfig) => Promise<boolean>;
  onReset: () => Promise<boolean>;
}

export const ConfigPanel: React.FC<ConfigPanelProps> = ({ config, onSave, onReset }) => {
  const [formData, setFormData] = useState<GUIConfig>({ ...config });
  const [activeTab, setActiveTab] = useState<'sfera' | 'network' | 'tunnel' | 'subiekt' | 'system'>('sfera');
  const [showApiKey, setShowApiKey] = useState(false);
  const [keywordInput, setKeywordInput] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [isResetting, setIsResetting] = useState(false);
  const [toasts, setToasts] = useState<{ id: string; type: 'success' | 'error'; message: string }[]>([]);

  useEffect(() => {
    setFormData({ ...config });
  }, [config]);

  const addToast = (type: 'success' | 'error', message: string) => {
    const id = Math.random().toString(36).substring(2, 9);
    setToasts((prev) => [...prev, { id, type, message }]);
  };

  const removeToast = (id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value, type } = e.target;
    const val = type === 'checkbox' ? (e.target as HTMLInputElement).checked : value;
    
    setFormData((prev) => ({
      ...prev,
      [name]: val,
    }));
  };

  const generateApiKey = () => {
    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
    let key = '';
    for (let i = 0; i < 48; i++) {
      key += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    setFormData((prev) => ({ ...prev, agent_api_key: key }));
    addToast('success', 'Wygenerowano nowy klucz API. Zapisz konfigurację, aby go zatwierdzić.');
  };

  const copyApiKey = () => {
    navigator.clipboard.writeText(formData.agent_api_key);
    addToast('success', 'Klucz API został skopiowany do schowka!');
  };

  const handleAddKeyword = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if ((e.key === 'Enter' || e.key === ',') && keywordInput.trim()) {
      e.preventDefault();
      const word = keywordInput.trim().replace(',', '');
      if (!formData.distributed_costs_keywords.includes(word)) {
        setFormData((prev) => ({
          ...prev,
          distributed_costs_keywords: [...prev.distributed_costs_keywords, word],
        }));
      }
      setKeywordInput('');
    }
  };

  const handleRemoveKeyword = (index: number) => {
    setFormData((prev) => ({
      ...prev,
      distributed_costs_keywords: prev.distributed_costs_keywords.filter((_, i) => i !== index),
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    const success = await onSave(formData);
    setIsSaving(false);
    if (success) {
      addToast('success', 'Konfiguracja została zapisana i zaktualizowana w pamięci agenta.');
    } else {
      addToast('error', 'Wystąpił błąd podczas zapisywania konfiguracji.');
    }
  };

  const handleReset = async () => {
    if (window.confirm('Czy na pewno chcesz zresetować wszystkie ustawienia do wartości domyślnych? Stracisz obecną konfigurację.')) {
      setIsResetting(true);
      const success = await onReset();
      setIsResetting(false);
      if (success) {
        addToast('success', 'Przywrócono domyślne ustawienia agenta.');
      } else {
        addToast('error', 'Wystąpił błąd podczas resetowania ustawień.');
      }
    }
  };

  return (
    <div className="bg-slate-900/40 backdrop-blur-xl border border-white/5 rounded-2xl overflow-hidden p-6 mb-8 relative">
      <div className="absolute -bottom-10 -right-10 w-32 h-32 bg-primary/5 blur-3xl rounded-full"></div>

      {/* Tabs Menu */}
      <div className="flex flex-wrap border-b border-white/5 mb-6">
        <button
          onClick={() => setActiveTab('sfera')}
          className={`px-5 py-3 text-sm font-bold tracking-tight border-b-2 transition-colors cursor-pointer ${
            activeTab === 'sfera'
              ? 'border-primary text-text-main bg-primary/5'
              : 'border-transparent text-text-muted hover:text-text-main'
          }`}
        >
          Sfera GT & Baza SQL
        </button>
        <button
          onClick={() => setActiveTab('network')}
          className={`px-5 py-3 text-sm font-bold tracking-tight border-b-2 transition-colors cursor-pointer ${
            activeTab === 'network'
              ? 'border-primary text-text-main bg-primary/5'
              : 'border-transparent text-text-muted hover:text-text-main'
          }`}
        >
          Sieć & Zabezpieczenia
        </button>
        <button
          onClick={() => setActiveTab('tunnel')}
          className={`px-5 py-3 text-sm font-bold tracking-tight border-b-2 transition-colors cursor-pointer ${
            activeTab === 'tunnel'
              ? 'border-primary text-text-main bg-primary/5'
              : 'border-transparent text-text-muted hover:text-text-main'
          }`}
        >
          Tunele HTTP
        </button>
        <button
          onClick={() => setActiveTab('subiekt')}
          className={`px-5 py-3 text-sm font-bold tracking-tight border-b-2 transition-colors cursor-pointer ${
            activeTab === 'subiekt'
              ? 'border-primary text-text-main bg-primary/5'
              : 'border-transparent text-text-muted hover:text-text-main'
          }`}
        >
          Konfiguracja Subiekta
        </button>
        <button
          onClick={() => setActiveTab('system')}
          className={`px-5 py-3 text-sm font-bold tracking-tight border-b-2 transition-colors cursor-pointer ${
            activeTab === 'system'
              ? 'border-primary text-text-main bg-primary/5'
              : 'border-transparent text-text-muted hover:text-text-main'
          }`}
        >
          Opcje Systemowe
        </button>
      </div>

      {/* Form Content */}
      <form onSubmit={handleSubmit}>
        
        {/* TAB 1: Sfera & SQL */}
        {activeTab === 'sfera' && (
          <div className="space-y-5 animate-fadeIn">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              <div>
                <label className="block text-xs font-bold text-text-muted tracking-wider uppercase mb-2">Serwer SQL</label>
                <input
                  type="text"
                  name="db_server_name"
                  value={formData.db_server_name}
                  onChange={handleInputChange}
                  placeholder="np. LIDER-PC\INSERTGT"
                  className="w-full bg-slate-950/60 border border-white/10 rounded-xl px-4 py-2.5 text-text-main font-mono text-sm focus:outline-none focus:border-primary/50"
                  required
                />
                <span className="text-[10px] text-text-muted mt-1 block">Adres serwera bazy danych Microsoft SQL Server.</span>
              </div>
              
              <div>
                <label className="block text-xs font-bold text-text-muted tracking-wider uppercase mb-2">Nazwa Bazy Danych</label>
                <input
                  type="text"
                  name="db_name"
                  value={formData.db_name}
                  onChange={handleInputChange}
                  placeholder="np. MojaFirma"
                  className="w-full bg-slate-950/60 border border-white/10 rounded-xl px-4 py-2.5 text-text-main font-mono text-sm focus:outline-none focus:border-primary/50"
                  required
                />
                <span className="text-[10px] text-text-muted mt-1 block">Nazwa podmiotu w Subiekcie GT.</span>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-5 pt-2">
              <div>
                <label className="block text-xs font-bold text-text-muted tracking-wider uppercase mb-2">Operator Sfery</label>
                <input
                  type="text"
                  name="sfera_operator"
                  value={formData.sfera_operator}
                  onChange={handleInputChange}
                  placeholder="Szef"
                  className="w-full bg-slate-950/60 border border-white/10 rounded-xl px-4 py-2.5 text-text-main text-sm focus:outline-none focus:border-primary/50"
                  required
                />
                <span className="text-[10px] text-text-muted mt-1 block">Operator Subiekta z uprawnieniem do Sfery.</span>
              </div>
              
              <div>
                <label className="block text-xs font-bold text-text-muted tracking-wider uppercase mb-2">Hasło Operatora</label>
                <input
                  type="password"
                  name="sfera_operator_password"
                  value={formData.sfera_operator_password}
                  onChange={handleInputChange}
                  placeholder="Brak hasła"
                  className="w-full bg-slate-950/60 border border-white/10 rounded-xl px-4 py-2.5 text-text-main text-sm focus:outline-none focus:border-primary/50"
                />
                <span className="text-[10px] text-text-muted mt-1 block">Hasło logowania dla wybranego operatora.</span>
              </div>
            </div>
          </div>
        )}

        {/* TAB 2: Sieć & Zabezpieczenia */}
        {activeTab === 'network' && (
          <div className="space-y-5 animate-fadeIn">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
              <div className="md:col-span-1">
                <label className="block text-xs font-bold text-text-muted tracking-wider uppercase mb-2">Port Nasłuchiwania</label>
                <input
                  type="number"
                  name="agent_port"
                  value={formData.agent_port}
                  onChange={handleInputChange}
                  className="w-full bg-slate-950/60 border border-white/10 rounded-xl px-4 py-2.5 text-text-main font-mono text-sm focus:outline-none focus:border-primary/50"
                  required
                  min="80"
                  max="65535"
                />
                <span className="text-[10px] text-text-muted mt-1 block">Domyślny port lokalny serwera HTTP agenta.</span>
              </div>

              <div className="md:col-span-2">
                <label className="block text-xs font-bold text-text-muted tracking-wider uppercase mb-2">Klucz Autoryzacji API Key</label>
                <div className="flex gap-2">
                  <div className="relative flex-1">
                    <input
                      type={showApiKey ? 'text' : 'password'}
                      name="agent_api_key"
                      value={formData.agent_api_key}
                      onChange={handleInputChange}
                      className="w-full bg-slate-950/60 border border-white/10 rounded-xl pl-4 pr-10 py-2.5 text-text-main font-mono text-sm focus:outline-none focus:border-primary/50"
                      required
                    />
                    <button
                      type="button"
                      onClick={() => setShowApiKey(!showApiKey)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-main cursor-pointer"
                    >
                      {showApiKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                  <button
                    type="button"
                    onClick={copyApiKey}
                    className="p-2.5 rounded-xl border border-white/10 hover:border-white/20 bg-slate-950/40 hover:bg-slate-950/80 text-text-main cursor-pointer"
                    title="Kopiuj"
                  >
                    <Copy className="w-4 h-4" />
                  </button>
                  <button
                    type="button"
                    onClick={generateApiKey}
                    className="px-4 py-2.5 rounded-xl border border-white/10 hover:border-white/20 bg-slate-950/40 hover:bg-slate-950/80 text-text-main text-xs font-bold uppercase tracking-wider cursor-pointer"
                  >
                    Generuj
                  </button>
                </div>
                <span className="text-[10px] text-text-muted mt-1 block">Klucz przesyłany w nagłówku X-API-Key przy każdym żądaniu z SuppSales.</span>
              </div>
            </div>
          </div>
        )}

        {/* TAB 3: Tunele HTTP */}
        {activeTab === 'tunnel' && (
          <div className="space-y-6 animate-fadeIn">

            {/* === CLOUDFLARE SECTION === */}
            <div className="bg-slate-950/30 rounded-2xl border border-white/5 p-5">
              <div className="flex items-center gap-3 mb-4">
                <div className="w-8 h-8 rounded-xl bg-orange-500/10 flex items-center justify-center">
                  <span className="text-orange-400 text-sm font-black">CF</span>
                </div>
                <div>
                  <h3 className="text-sm font-extrabold text-text-main">Cloudflare Tunnel</h3>
                  <p className="text-[10px] text-text-muted">Zalecany — bez konfiguracji routera, bez stałego IP. Wymaga cloudflared.exe (auto-pobieranie).</p>
                </div>
              </div>

              <div className="flex items-center gap-3 bg-slate-950/40 p-3.5 rounded-xl border border-white/5 mb-4">
                <input
                  type="checkbox"
                  id="cloudflare_enabled"
                  name="cloudflare_enabled"
                  checked={formData.cloudflare_enabled}
                  onChange={handleInputChange}
                  className="w-5 h-5 accent-primary bg-slate-950 rounded cursor-pointer"
                />
                <label htmlFor="cloudflare_enabled" className="text-sm font-bold text-text-main cursor-pointer select-none">
                  Włącz tunel Cloudflare
                </label>
              </div>

              {formData.cloudflare_enabled && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-5 animate-fadeIn">
                  <div>
                    <label className="block text-xs font-bold text-text-muted tracking-wider uppercase mb-2">
                      Token Named Tunnel <span className="text-[10px] lowercase text-text-muted">(opcjonalny)</span>
                    </label>
                    <input
                      type="password"
                      name="cloudflare_token"
                      value={formData.cloudflare_token}
                      onChange={handleInputChange}
                      placeholder="Wklej token tunelu z panelu Cloudflare"
                      className="w-full bg-slate-950/60 border border-white/10 rounded-xl px-4 py-2.5 text-text-main font-mono text-sm focus:outline-none focus:border-primary/50"
                    />
                    <span className="text-[10px] text-text-muted mt-1 block">
                      Bez tokenu uruchomi <strong>Quick Tunnel</strong> z losowym URL trycloudflare.com.
                    </span>
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-text-muted tracking-wider uppercase mb-2">
                      Własna Domena <span className="text-[10px] lowercase text-text-muted">(wymaga Named Tunnel)</span>
                    </label>
                    <input
                      type="text"
                      name="cloudflare_custom_url"
                      value={formData.cloudflare_custom_url}
                      onChange={handleInputChange}
                      placeholder="np. agent.mojadomena.pl"
                      className="w-full bg-slate-950/60 border border-white/10 rounded-xl px-4 py-2.5 text-text-main font-mono text-sm focus:outline-none focus:border-primary/50"
                    />
                    <span className="text-[10px] text-text-muted mt-1 block">
                      Adres podpięty pod Named Tunnel w konsoli Cloudflare Zero Trust.
                    </span>
                  </div>
                </div>
              )}
            </div>

            {/* === NGROK SECTION === */}
            <div className="bg-slate-950/30 rounded-2xl border border-white/5 p-5">
              <div className="flex items-center gap-3 mb-4">
                <div className="w-8 h-8 rounded-xl bg-emerald-500/10 flex items-center justify-center">
                  <span className="text-emerald-400 text-sm font-black">NG</span>
                </div>
                <div>
                  <h3 className="text-sm font-extrabold text-text-main">ngrok Tunnel</h3>
                  <p className="text-[10px] text-text-muted">Alternatywa dla Cloudflare — popularne narzędzie, darmowe konto wystarczy. Wymaga ngrok.exe (auto-pobieranie).</p>
                </div>
              </div>

              <div className="flex items-center gap-3 bg-slate-950/40 p-3.5 rounded-xl border border-white/5 mb-4">
                <input
                  type="checkbox"
                  id="ngrok_enabled"
                  name="ngrok_enabled"
                  checked={formData.ngrok_enabled}
                  onChange={handleInputChange}
                  className="w-5 h-5 accent-primary bg-slate-950 rounded cursor-pointer"
                />
                <label htmlFor="ngrok_enabled" className="text-sm font-bold text-text-main cursor-pointer select-none">
                  Włącz tunel ngrok
                </label>
              </div>

              {formData.ngrok_enabled && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-5 animate-fadeIn">
                  <div>
                    <label className="block text-xs font-bold text-text-muted tracking-wider uppercase mb-2">
                      Authtoken ngrok <span className="text-[10px] lowercase text-text-muted">(zalecany)</span>
                    </label>
                    <input
                      type="password"
                      name="ngrok_authtoken"
                      value={formData.ngrok_authtoken}
                      onChange={handleInputChange}
                      placeholder="Token z dashboard.ngrok.com"
                      className="w-full bg-slate-950/60 border border-white/10 rounded-xl px-4 py-2.5 text-text-main font-mono text-sm focus:outline-none focus:border-primary/50"
                    />
                    <span className="text-[10px] text-text-muted mt-1 block">
                      Bez tokenu tunel może nie działać na nowych wersjach ngrok. Darmowe konto wystarczy.
                    </span>
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-text-muted tracking-wider uppercase mb-2">
                      Stała domena ngrok <span className="text-[10px] lowercase text-text-muted">(opcjonalna, plan Pro)</span>
                    </label>
                    <input
                      type="text"
                      name="ngrok_domain"
                      value={formData.ngrok_domain}
                      onChange={handleInputChange}
                      placeholder="np. moj-agent.ngrok.app"
                      className="w-full bg-slate-950/60 border border-white/10 rounded-xl px-4 py-2.5 text-text-main font-mono text-sm focus:outline-none focus:border-primary/50"
                    />
                    <span className="text-[10px] text-text-muted mt-1 block">
                      Bez domeny ngrok wygeneruje losowy URL (zmienia się po każdym restarcie).
                    </span>
                  </div>
                </div>
              )}
            </div>

            {(formData.cloudflare_enabled && formData.ngrok_enabled) && (
              <div className="bg-yellow-500/10 border border-yellow-500/20 rounded-xl px-4 py-3 text-[11px] text-yellow-400">
                ⚠️ Oba tunele są włączone jednocześnie. To działa, ale SuppSales powinien wskazywać tylko jeden URL. Zalecamy wybranie jednego.
              </div>
            )}
          </div>
        )}

        {/* TAB 4: Konfiguracja Subiekta */}
        {activeTab === 'subiekt' && (
          <div className="space-y-5 animate-fadeIn">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              
              {/* Opcje KSeF & Fiskalizacja */}
              <div className="space-y-3">
                <label className="block text-xs font-bold text-text-muted tracking-wider uppercase mb-2">Integracja systemowa</label>
                
                <div className="flex items-center gap-3 bg-slate-950/30 p-3.5 rounded-xl border border-white/5">
                  <input
                    type="checkbox"
                    id="ksef_enabled"
                    name="ksef_enabled"
                    checked={formData.ksef_enabled}
                    onChange={handleInputChange}
                    className="w-4 h-4 accent-primary cursor-pointer"
                  />
                  <label htmlFor="ksef_enabled" className="text-sm font-bold text-text-main cursor-pointer select-none">
                    Włącz obsługę KSeF w dokumentach
                  </label>
                </div>

                <div className="flex items-center gap-3 bg-slate-950/30 p-3.5 rounded-xl border border-white/5">
                  <input
                    type="checkbox"
                    id="fiscalization_enabled"
                    name="fiscalization_enabled"
                    checked={formData.fiscalization_enabled}
                    onChange={handleInputChange}
                    className="w-4 h-4 accent-primary cursor-pointer"
                  />
                  <label htmlFor="fiscalization_enabled" className="text-sm font-bold text-text-main cursor-pointer select-none">
                    Włącz automatyczną fiskalizację faktur
                  </label>
                </div>
              </div>

              {/* Drukarka Fiskalna ID */}
              <div>
                <label className="block text-xs font-bold text-text-muted tracking-wider uppercase mb-2">ID Drukarki Fiskalnej w Subiekcie</label>
                <input
                  type="number"
                  name="fiscal_printer_id"
                  value={formData.fiscal_printer_id}
                  onChange={handleInputChange}
                  className="w-full bg-slate-950/60 border border-white/10 rounded-xl px-4 py-2.5 text-text-main font-mono text-sm focus:outline-none focus:border-primary/50"
                  min="0"
                />
                <span className="text-[10px] text-text-muted mt-1 block">Identyfikator urządzenia rejestrującego ze słownika Subiekta GT.</span>
              </div>

            </div>

            {/* Słowa kluczowe rozbicia kosztów dostawy */}
            <div className="pt-2">
              <label className="block text-xs font-bold text-text-muted tracking-wider uppercase mb-2">
                Rozbijanie Kosztów Dostawy (Słowa Kluczowe)
              </label>
              
              <div className="bg-slate-950/60 border border-white/10 rounded-xl p-3 flex flex-wrap gap-2 items-center focus-within:border-primary/50 min-h-[50px]">
                {formData.distributed_costs_keywords.map((word, index) => (
                  <span
                    key={index}
                    className="flex items-center gap-1.5 text-xs font-semibold bg-primary/20 border border-primary/30 text-violet-300 px-2.5 py-1 rounded-lg"
                  >
                    {word}
                    <button
                      type="button"
                      onClick={() => handleRemoveKeyword(index)}
                      className="text-violet-400 hover:text-violet-200 cursor-pointer"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </span>
                ))}
                <input
                  type="text"
                  value={keywordInput}
                  onChange={(e) => setKeywordInput(e.target.value)}
                  onKeyDown={handleAddKeyword}
                  placeholder="Dodaj słowo kluczowe i naciśnij Enter"
                  className="bg-transparent border-none outline-none text-text-main text-xs min-w-[200px] flex-1 py-1"
                />
              </div>
              <span className="text-[10px] text-text-muted mt-1 block">
                Pozycje zawierające te słowa kluczowe w nazwach będą interpretowane i rozbijane jako koszty przesyłki/dostawy.
              </span>
            </div>
          </div>
        )}

        {/* TAB 5: Systemowe */}
        {activeTab === 'system' && (
          <div className="space-y-5 animate-fadeIn">
            <div className="flex items-center gap-3 bg-slate-950/40 p-4 rounded-xl border border-white/5">
              <input
                type="checkbox"
                id="autostart_enabled"
                name="autostart_enabled"
                checked={formData.autostart_enabled}
                onChange={handleInputChange}
                className="w-5 h-5 accent-primary bg-slate-950 rounded cursor-pointer"
              />
              <label htmlFor="autostart_enabled" className="text-sm font-bold text-text-main cursor-pointer select-none">
                Uruchamiaj agenta automatycznie przy starcie systemu Windows
              </label>
            </div>
            <span className="text-[10px] text-text-muted block -mt-3 ml-8">
              Dodaje wpis do rejestru Windows w sekcji Autostartu użytkownika (nie wymaga uprawnień administratora).
            </span>
          </div>
        )}

        {/* Buttons bottom panel */}
        <div className="mt-8 pt-4 border-t border-white/5 flex justify-between items-center">
          <button
            type="button"
            onClick={handleReset}
            disabled={isResetting}
            className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider px-5 py-2.5 rounded-xl border border-red-500/30 hover:border-red-500/50 bg-red-500/5 hover:bg-red-500/10 text-red-400 transition-all cursor-pointer disabled:opacity-50"
          >
            <RotateCcw className="w-4 h-4" />
            Resetuj do domyślnych
          </button>
          
          <button
            type="submit"
            disabled={isSaving}
            className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider px-6 py-2.5 rounded-xl bg-gradient-to-r from-primary to-purple-600 hover:from-primary/95 hover:to-purple-600/95 text-white shadow-lg shadow-primary/20 hover:scale-[1.01] active:scale-[0.99] transition-all cursor-pointer disabled:opacity-50"
          >
            <Save className="w-4 h-4" />
            {isSaving ? 'Zapisywanie...' : 'Zapisz i restartuj agenta'}
          </button>
        </div>

      </form>

      {/* Render Toast Notifications */}
      <div className="fixed bottom-6 right-6 z-50 flex flex-col gap-3">
        {toasts.map((toast) => (
          <Toast
            key={toast.id}
            type={toast.type}
            message={toast.message}
            onClose={() => removeToast(toast.id)}
          />
        ))}
      </div>

    </div>
  );
};
