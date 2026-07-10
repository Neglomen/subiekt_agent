import { useState, useEffect, useRef } from 'react';
import { 
  LayoutDashboard, 
  Settings, 
  Terminal, 
  BookOpen, 
  RefreshCw,
  Server,
  Activity,
  Copy,
  Check
} from 'lucide-react';
import { ConnectorFlow } from './components/ConnectorFlow';
import { StatusGrid } from './components/StatusGrid';
import { ConfigPanel, type GUIConfig } from './components/ConfigPanel';
import { LogTerminal } from './components/LogTerminal';
import { EndpointDoc } from './components/EndpointDoc';
import { Toast } from './components/Toast';

export default function App() {
  const [activeSection, setActiveSection] = useState<'dashboard' | 'config' | 'logs' | 'endpoints'>('dashboard');
  
  // Status states
  const [sferaConnected, setSferaConnected] = useState(false);
  const [cfConnected, setCfConnected] = useState(false);
  const [cfUrl, setCfUrl] = useState('');
  const [ngrokConnected, setNgrokConnected] = useState(false);
  const [ngrokUrl, setNgrokUrl] = useState('');
  
  // Config state
  const [config, setConfig] = useState<GUIConfig>({
    db_server_name: '',
    db_name: '',
    sfera_operator: '',
    sfera_operator_password: '',
    agent_api_key: '',
    agent_port: 8000,
    cloudflare_enabled: false,
    cloudflare_token: '',
    cloudflare_custom_url: '',
    autostart_enabled: false,
    ngrok_enabled: false,
    ngrok_authtoken: '',
    ngrok_domain: '',
    ksef_enabled: false,
    fiscalization_enabled: false,
    fiscal_printer_id: 0,
    distributed_costs_keywords: []
  });

  // Stats state
  const [stats, setStats] = useState({
    requests_last_60s: 0,
    request_history: [],
    avg_latency_ms: 0,
    products_checked_today: 0,
    bulk_stock_queries: 0,
    invoices_created_today: 0,
    last_invoice_number: '',
    last_invoice_status: '',
    last_invoice_time: '',
    last_stock_status: '',
    last_stock_time: '',
    ksef_enabled: false,
    fiscalization_enabled: false
  });

  // Logs state
  const [logs, setLogs] = useState<string[]>([]);
  const [wsConnected, setWsConnected] = useState(false);
  
  // System control states
  const [restarting, setRestarting] = useState(false);
  const [toasts, setToasts] = useState<{ id: string; type: 'success' | 'error'; message: string }[]>([]);
  const [copied, setCopied] = useState(false);
  
  const wsRef = useRef<WebSocket | null>(null);

  const addToast = (type: 'success' | 'error', message: string) => {
    const id = Math.random().toString(36).substring(2, 9);
    setToasts((prev) => [...prev, { id, type, message }]);
  };

  const removeToast = (id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  };

  const handleCopyUrl = (url: string) => {
    navigator.clipboard.writeText(url);
    setCopied(true);
    addToast('success', 'Skopiowano adres publiczny tunelu do schowka!');
    setTimeout(() => setCopied(false), 2000);
  };

  // --- API FETCHES ---
  const fetchConfig = async () => {
    try {
      const res = await fetch('/gui/config');
      if (res.ok) {
        const data = await res.json();
        setConfig(data);
      }
    } catch (err) {
      console.error('Failed to fetch config', err);
    }
  };

  const fetchStatus = async () => {
    try {
      const res = await fetch('/gui/status');
      if (res.ok) {
        const data = await res.json();
        setSferaConnected(data.sfera_connected);
        setCfConnected(data.cf_connected);
        setCfUrl(data.cf_url || '');
        setNgrokConnected(data.ngrok_connected || false);
        setNgrokUrl(data.ngrok_url || '');
      }
    } catch (err) {
      console.error('Failed to fetch status', err);
      setSferaConnected(false);
      setCfConnected(false);
      setNgrokConnected(false);
    }
  };

  const fetchStats = async () => {
    try {
      const res = await fetch('/gui/stats');
      if (res.ok) {
        const data = await res.json();
        setStats(data);
      }
    } catch (err) {
      console.error('Failed to fetch stats', err);
    }
  };

  // --- WS LOGS ---
  const connectLogsWs = () => {
    if (wsRef.current) {
      wsRef.current.close();
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    // Use relative path for proxy support
    const wsUrl = `${protocol}//${window.location.host}/ws/logs`;
    
    console.log(`Connecting to logs WebSocket: ${wsUrl}`);
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setWsConnected(true);
      console.log('Logs WebSocket connected.');
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        // Skip keepalive ping messages
        if (data && typeof data === 'object' && !Array.isArray(data) && 'ping' in data) return;
        if (Array.isArray(data)) {
          // Bulk initial backlog — array of raw log strings
          setLogs(data);
        } else if (typeof data === 'string') {
          // Single raw log string
          setLogs((prev) => {
            const next = [...prev, data];
            if (next.length > 1000) next.shift();
            return next;
          });
        }
      } catch {
        // Raw unparseable data — treat as plain string log line
        if (typeof event.data === 'string') {
          setLogs((prev) => {
            const next = [...prev, event.data];
            if (next.length > 1000) next.shift();
            return next;
          });
        }
      }
    };

    ws.onclose = () => {
      setWsConnected(false);
      console.log('Logs WebSocket disconnected. Reconnecting in 3s...');
      setTimeout(connectLogsWs, 3000);
    };

    ws.onerror = (err) => {
      console.error('Logs WebSocket error:', err);
      ws.close();
    };
  };

  // --- ACTIONS ---
  const handleTestSfera = async (): Promise<boolean> => {
    try {
      const res = await fetch('/gui/test-sfera', { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        setSferaConnected(data.sfera_connected);
        return data.sfera_connected;
      }
      return false;
    } catch (err) {
      console.error('Failed to test sfera', err);
      setSferaConnected(false);
      return false;
    }
  };

  const handleSaveConfig = async (newConfig: GUIConfig): Promise<boolean> => {
    try {
      const res = await fetch('/gui/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newConfig),
      });
      if (res.ok) {
        setConfig(newConfig);
        await fetchStatus();
        return true;
      }
      return false;
    } catch (err) {
      console.error('Failed to save config', err);
      return false;
    }
  };

  const handleResetConfig = async (): Promise<boolean> => {
    try {
      const res = await fetch('/gui/config/reset', { method: 'POST' });
      if (res.ok) {
        await fetchConfig();
        await fetchStatus();
        return true;
      }
      return false;
    } catch (err) {
      console.error('Failed to reset config', err);
      return false;
    }
  };

  const handleRestartAgent = async () => {
    setRestarting(true);
    addToast('success', 'Wysłano żądanie restartu agenta. Połączenie zostanie przerwane na kilka sekund.');
    
    try {
      await fetch('/gui/restart', { method: 'POST' });
    } catch (err) {
      // Fetch will fail because server shuts down, which is expected
    }

    // Wait and reconnect
    setTimeout(() => {
      window.location.reload();
    }, 4000);
  };

  // Setup periodic polling and WS log stream
  useEffect(() => {
    fetchConfig();
    fetchStatus();
    fetchStats();
    connectLogsWs();

    const statusInterval = setInterval(fetchStatus, 5000);
    const statsInterval = setInterval(fetchStats, 2000);

    return () => {
      clearInterval(statusInterval);
      clearInterval(statsInterval);
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-slate-950 relative">
      
      {/* Decorative background blurs */}
      <div className="absolute top-10 left-10 w-[500px] h-[500px] bg-primary/5 blur-[150px] rounded-full pointer-events-none z-0"></div>
      <div className="absolute bottom-10 right-10 w-[500px] h-[500px] bg-purple-500/5 blur-[150px] rounded-full pointer-events-none z-0"></div>
      
      {/* Premium Grid Pattern overlay */}
      <div className="absolute inset-0 bg-grid-premium opacity-60 pointer-events-none z-0"></div>

      {/* --- CUSTOM APP TITLE BAR (Frameless Window Drag Region) --- */}
      <header className="h-10 bg-slate-950/80 border-b border-white/5 flex items-center justify-between px-4 z-40 select-none pywebview-drag-region shrink-0">
        {/* Left Side: App branding */}
        <div className="flex items-center gap-2 pointer-events-none">
          <div className="w-2 h-2 rounded-full bg-gradient-to-tr from-purple-500 to-pink-500 animate-pulse"></div>
          <span className="text-[10px] font-mono font-bold tracking-wider text-text-muted">SUPPSALES AGENT CONTROL PANEL</span>
        </div>
        
        {/* Right Side: Window Control Buttons */}
        <div className="flex items-center gap-1.5 z-50">
          <button 
            onClick={() => (window as any).pywebview?.api?.minimize()} 
            title="Minimalizuj"
            className="p-1 rounded hover:bg-white/10 text-text-muted hover:text-text-main transition-colors cursor-pointer"
          >
            <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
          </button>
          <button 
            onClick={() => (window as any).pywebview?.api?.maximize()} 
            title="Maksymalizuj"
            className="p-1 rounded hover:bg-white/10 text-text-muted hover:text-text-main transition-colors cursor-pointer"
          >
            <svg className="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <rect x="3" y="3" width="18" height="18" rx="2" />
            </svg>
          </button>
          <button 
            onClick={() => (window as any).pywebview?.api?.close()} 
            title="Ukryj w zasobniku"
            className="p-1 rounded hover:bg-red-500/20 text-text-muted hover:text-red-400 transition-colors cursor-pointer"
          >
            <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
      </header>

      {/* --- APP WORKSPACE --- */}
      <div className="flex flex-1 overflow-hidden z-10">
        
        {/* --- SIDEBAR --- */}
        <aside className="w-72 bg-slate-900/40 border-r border-white/5 backdrop-blur-xl shrink-0 flex flex-col justify-between p-6 relative">
        <div className="space-y-8">
          
          {/* Brand Logo Header */}
          <div className="flex items-center gap-3 relative px-2">
            <div className="absolute -inset-1 bg-primary/20 blur-md rounded-xl opacity-75"></div>
            
            {/* Elegant SVG Conector Logo */}
            <div className="relative p-2.5 bg-slate-950/80 border border-white/10 rounded-xl flex items-center justify-center">
              <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none">
                <path d="M12 2C6.477 2 2 6.477 2 12s4.477 10 10 10 10-4.477 10-10S17.523 2 12 2z" stroke="url(#logoGrad)" strokeWidth="2" />
                <path d="M8 12c2.5-3.5 5.5-3.5 8 0" stroke="url(#logoGrad)" strokeWidth="2.5" strokeLinecap="round" />
                <path d="M8 15c2.5-1.5 5.5-1.5 8 0" stroke="url(#logoGrad)" strokeWidth="2.5" strokeLinecap="round" />
                <path d="M8 9c2.5 1.5 5.5 1.5 8 0" stroke="url(#logoGrad)" strokeWidth="2.5" strokeLinecap="round" />
                <defs>
                  <linearGradient id="logoGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stopColor="#a855f7" />
                    <stop offset="100%" stopColor="#ec4899" />
                  </linearGradient>
                </defs>
              </svg>
            </div>
            
            <div className="flex flex-col">
              <div className="flex items-center gap-1">
                <span className="text-base font-extrabold tracking-tight text-text-main">Subiekt</span>
                <span className="text-base font-extrabold tracking-tight text-primary">Agent</span>
              </div>
              <span className="text-[10px] font-mono text-text-muted">SuppSales Connector</span>
            </div>
          </div>

          {/* Navigation Links */}
          <nav className="space-y-1">
            <button
              onClick={() => setActiveSection('dashboard')}
              className={`w-full flex items-center gap-3.5 px-4.5 py-3 rounded-xl text-sm font-bold tracking-tight transition-all cursor-pointer ${
                activeSection === 'dashboard'
                  ? 'bg-gradient-to-r from-primary/15 to-purple-500/5 border border-primary/20 text-text-main shadow-inner'
                  : 'border border-transparent text-text-muted hover:text-text-main hover:bg-white/[0.02]'
              }`}
            >
              <LayoutDashboard className="w-5 h-5" />
              Panel Główny
            </button>
            
            <button
              onClick={() => setActiveSection('config')}
              className={`w-full flex items-center gap-3.5 px-4.5 py-3 rounded-xl text-sm font-bold tracking-tight transition-all cursor-pointer ${
                activeSection === 'config'
                  ? 'bg-gradient-to-r from-primary/15 to-purple-500/5 border border-primary/20 text-text-main shadow-inner'
                  : 'border border-transparent text-text-muted hover:text-text-main hover:bg-white/[0.02]'
              }`}
            >
              <Settings className="w-5 h-5" />
              Ustawienia Agenta
            </button>

            <button
              onClick={() => setActiveSection('logs')}
              className={`w-full flex items-center gap-3.5 px-4.5 py-3 rounded-xl text-sm font-bold tracking-tight transition-all cursor-pointer ${
                activeSection === 'logs'
                  ? 'bg-gradient-to-r from-primary/15 to-purple-500/5 border border-primary/20 text-text-main shadow-inner'
                  : 'border border-transparent text-text-muted hover:text-text-main hover:bg-white/[0.02]'
              }`}
            >
              <Terminal className="w-5 h-5" />
              Logi Systemowe
            </button>

            <button
              onClick={() => setActiveSection('endpoints')}
              className={`w-full flex items-center gap-3.5 px-4.5 py-3 rounded-xl text-sm font-bold tracking-tight transition-all cursor-pointer ${
                activeSection === 'endpoints'
                  ? 'bg-gradient-to-r from-primary/15 to-purple-500/5 border border-primary/20 text-text-main shadow-inner'
                  : 'border border-transparent text-text-muted hover:text-text-main hover:bg-white/[0.02]'
              }`}
            >
              <BookOpen className="w-5 h-5" />
              Dokumentacja API
            </button>
          </nav>

        </div>

        {/* Sidebar Footer Controls */}
        <div className="pt-6 border-t border-white/5 space-y-4">
          <div className="flex items-center justify-between px-2">
            <span className="text-[10px] font-bold text-text-muted uppercase tracking-wider">Serwer lokalny</span>
            <div className="flex items-center gap-1.5 bg-emerald-500/10 border border-emerald-500/20 rounded-full px-2 py-0.5">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
              <span className="text-[9px] font-bold text-emerald-400">AKTYWNY</span>
            </div>
          </div>
          
          <button
            onClick={handleRestartAgent}
            disabled={restarting}
            className="w-full flex items-center justify-center gap-2 text-xs font-bold uppercase tracking-wider py-2.5 rounded-xl border border-white/10 hover:border-white/20 bg-slate-950/40 hover:bg-slate-950/80 text-text-main transition-colors cursor-pointer"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${restarting ? 'animate-spin' : ''}`} />
            {restarting ? 'Restart...' : 'Zrestartuj serwer'}
          </button>
        </div>

      </aside>

      {/* --- MAIN CONTENT PANEL --- */}
      <main className="flex-1 h-full overflow-y-auto p-8 z-10 relative flex flex-col justify-between">
        
        <div>
          {/* Header Bar */}
          <header className="flex justify-between items-center mb-8 pb-4 border-b border-white/5">
            <div>
              <h1 className="text-xl font-extrabold tracking-tight text-text-main">
                {activeSection === 'dashboard' && 'Panel Kontrolny'}
                {activeSection === 'config' && 'Modyfikacja Ustawień'}
                {activeSection === 'logs' && 'Terminal Logów'}
                {activeSection === 'endpoints' && 'Swagger-Lite Dokumentacja'}
              </h1>
              <p className="text-xs text-text-muted">
                {activeSection === 'dashboard' && 'Monitorowanie statusu połączeń i aktywności API'}
                {activeSection === 'config' && 'Zarządzanie parametrami bazy danych, tunelu i systemowymi'}
                {activeSection === 'logs' && 'Śledzenie operacji lokalnych i komunikatów o błędach'}
                {activeSection === 'endpoints' && 'Interaktywny panel weryfikacji i testowania zapytań HTTP'}
              </p>
            </div>
            
            {/* Quick stats indicator */}
            <div className="flex gap-4">
              <div className="bg-slate-900/40 border border-white/5 rounded-xl px-4 py-2 flex items-center gap-3">
                <Server className={`w-5 h-5 ${sferaConnected ? 'text-emerald-400' : 'text-red-400'}`} />
                <div className="flex flex-col">
                  <span className="text-[9px] font-bold text-text-muted uppercase">Sfera GT</span>
                  <span className="text-xs font-extrabold text-text-main">{sferaConnected ? 'POŁĄCZONA' : 'ROZŁĄCZONA'}</span>
                </div>
              </div>
              
              <div className="bg-slate-900/40 border border-white/5 rounded-xl px-4 py-2 flex items-center gap-3" title={cfUrl || undefined}>
                <Activity className={`w-5 h-5 ${cfConnected ? 'text-emerald-400' : 'text-red-400'}`} />
                <div className="flex flex-col">
                  <span className="text-[9px] font-bold text-text-muted uppercase">Tunel CF</span>
                  <span className="text-xs font-extrabold text-text-main">{cfConnected ? 'AKTYWNY' : 'NIEAKTYWNY'}</span>
                  {cfUrl && <span className="text-[9px] text-text-muted truncate max-w-[120px]">{cfUrl}</span>}
                </div>
              </div>

              {(ngrokConnected || config.ngrok_enabled) && (
                <div className="bg-slate-900/40 border border-white/5 rounded-xl px-4 py-2 flex items-center gap-3" title={ngrokUrl || undefined}>
                  <Activity className={`w-5 h-5 ${ngrokConnected ? 'text-emerald-400' : 'text-yellow-400'}`} />
                  <div className="flex flex-col">
                    <span className="text-[9px] font-bold text-text-muted uppercase">Tunel ngrok</span>
                    <span className="text-xs font-extrabold text-text-main">{ngrokConnected ? 'AKTYWNY' : 'ŁĄCZENIE...'}</span>
                    {ngrokUrl && <span className="text-[9px] text-text-muted truncate max-w-[120px]">{ngrokUrl}</span>}
                  </div>
                </div>
              )}
            </div>
          </header>

          {/* Section Renderers */}
          {activeSection === 'dashboard' && (
            <div className="animate-fadeIn">
              <ConnectorFlow sferaConnected={sferaConnected} cfConnected={cfConnected} ngrokConnected={ngrokConnected} ngrokUrl={ngrokUrl} />
              
              {/* Prominent Tunnel URL alert with Copy button */}
              {(cfConnected || ngrokConnected) && (
                <div className="bg-gradient-to-r from-violet-500/10 via-purple-500/10 to-pink-500/10 border border-white/10 rounded-2xl p-5 mb-8 flex flex-col sm:flex-row justify-between items-center gap-4 backdrop-blur-xl relative overflow-hidden group">
                  <div className="absolute top-0 left-0 w-full h-0.5 bg-gradient-to-r from-violet-500 via-purple-400 to-pink-500"></div>
                  <div className="flex items-center gap-4 w-full">
                    <div className="w-10 h-10 rounded-xl bg-violet-500/20 flex items-center justify-center text-violet-400 shrink-0">
                      <Activity className="w-5 h-5 animate-pulse" />
                    </div>
                    <div className="overflow-hidden w-full">
                      <h4 className="text-[10px] font-bold text-text-muted uppercase tracking-wider">Publiczny adres tunelu HTTP (dla SuppSales)</h4>
                      <p className="text-sm font-extrabold text-text-main mt-0.5 font-mono select-all truncate">
                        {cfConnected ? cfUrl : ngrokUrl}
                      </p>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => handleCopyUrl(cfConnected ? cfUrl : ngrokUrl)}
                    className="w-full sm:w-auto px-5 py-2.5 rounded-xl bg-primary hover:bg-violet-600 text-white text-xs font-bold tracking-wider uppercase transition-all duration-300 flex items-center justify-center gap-2 hover:scale-[1.02] cursor-pointer shadow-lg shadow-violet-500/20 shrink-0"
                  >
                    {copied ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
                    {copied ? 'Skopiowano!' : 'Kopiuj adres'}
                  </button>
                </div>
              )}

              <StatusGrid 
                sferaConnected={sferaConnected} 
                cfConnected={cfConnected} 
                stats={stats} 
                onTestSfera={handleTestSfera} 
              />
            </div>
          )}

          {activeSection === 'config' && (
            <div className="animate-fadeIn">
              <ConfigPanel config={config} onSave={handleSaveConfig} onReset={handleResetConfig} />
            </div>
          )}

          {activeSection === 'logs' && (
            <div className="animate-fadeIn">
              <LogTerminal logs={logs} onClear={onClear} wsConnected={wsConnected} />
            </div>
          )}

          {activeSection === 'endpoints' && (
            <div className="animate-fadeIn">
              <EndpointDoc apiKey={config.agent_api_key} />
            </div>
          )}
        </div>

        {/* Footer */}
        <footer className="mt-12 pt-6 border-t border-white/5 flex justify-between items-center text-[10px] text-text-muted font-mono">
          <span>&copy; {new Date().getFullYear()} SuppSales. Wszystkie prawa zastrzeżone.</span>
          <div className="flex gap-4">
            <span>Subiekt Agent HTTP v0.5.1</span>
            <span>Uptime: {stats.last_stock_time || '00:00:00'}</span>
          </div>
        </footer>

      </main>

      </div> {/* Close App Workspace */}

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

      <style>{`
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(8px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .animate-fadeIn {
          animation: fadeIn 0.3s cubic-bezier(0.16, 1, 0.3, 1) forwards;
        }
      `}</style>
    </div>
  );
  
  function onClear() {
    setLogs([]);
    try {
      fetch('/gui/logs/clear', { method: 'POST' });
    } catch (err) {}
  }
}
