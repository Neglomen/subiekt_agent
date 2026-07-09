import React, { useState, useEffect } from 'react';
import { Database, Activity, Package, FileText, RefreshCw } from 'lucide-react';
import canvasConfetti from 'canvas-confetti';

// --- ANIMATED COUNTER ---
export const AnimatedCounter: React.FC<{ value: number }> = ({ value }) => {
  const [count, setCount] = useState(0);

  useEffect(() => {
    let start = count;
    const end = value;
    if (start === end) return;

    const duration = 800; // 800ms
    const startTime = performance.now();

    const updateCount = (now: number) => {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const ease = progress * (2 - progress); // Ease out quad
      const current = Math.floor(ease * (end - start) + start);
      setCount(current);

      if (progress < 1) {
        requestAnimationFrame(updateCount);
      } else {
        setCount(end);
      }
    };

    requestAnimationFrame(updateCount);
  }, [value]);

  return <span>{count}</span>;
};

// --- MINI SPARKLINE ---
const Sparkline: React.FC<{ history: number[] }> = ({ history }) => {
  if (!history || history.length === 0) {
    history = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0];
  }
  
  const paddedHistory = [...history];
  while (paddedHistory.length < 20) {
    paddedHistory.unshift(0);
  }
  if (paddedHistory.length > 20) {
    paddedHistory.splice(0, paddedHistory.length - 20);
  }

  const maxVal = Math.max(...paddedHistory, 1);
  const points = paddedHistory.map((val, index) => {
    const x = (index / 19) * 100;
    const y = 28 - (val / maxVal) * 24; // map 0..max -> 28..4
    return `${x},${y}`;
  });

  const pathD = `M 0,30 L ${points.join(' L ')} L 100,30 Z`;
  const lineD = `M ${points.join(' L ')}`;

  return (
    <div className="w-full h-12 mt-2">
      <svg className="w-full h-full" viewBox="0 0 100 30" preserveAspectRatio="none">
        <defs>
          <linearGradient id="sparklineGrad" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#c084fc" stopOpacity="0.4" />
            <stop offset="100%" stopColor="#c084fc" stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={pathD} fill="url(#sparklineGrad)" />
        <path d={lineD} fill="none" stroke="#c084fc" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    </div>
  );
};

// --- COMPONENT PROPS & MAIN ---
interface StatusGridProps {
  sferaConnected: boolean;
  cfConnected: boolean;
  stats: {
    requests_last_60s: number;
    request_history: number[];
    avg_latency_ms: number;
    products_checked_today: number;
    bulk_stock_queries: number;
    invoices_created_today: number;
    last_invoice_number: string;
    last_invoice_status: string;
    last_invoice_time: string;
    last_stock_status: string;
    last_stock_time: string;
    ksef_enabled: boolean;
    fiscalization_enabled: boolean;
  };
  onTestSfera: () => Promise<boolean>;
}

export const StatusGrid: React.FC<StatusGridProps> = ({
  sferaConnected,
  cfConnected: _cfConnected,
  stats,
  onTestSfera,
}) => {
  const [testingSfera, setTestingSfera] = useState(false);
  const [sferaPing, setSferaPing] = useState<number | null>(null);

  const handleTestSfera = async () => {
    setTestingSfera(true);
    const start = performance.now();
    const success = await onTestSfera();
    const end = performance.now();
    setSferaPing(Math.round(end - start));
    setTestingSfera(false);
    
    if (success) {
      canvasConfetti({
        particleCount: 50,
        spread: 40,
        origin: { y: 0.8 },
        colors: ['#a855f7', '#10b981'],
      });
    }
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
      
      {/* KARTA 1: Sfera Connection */}
      <div className="relative group overflow-hidden bg-slate-900/40 backdrop-blur-xl border border-white/5 hover:border-primary/30 rounded-2xl p-6 transition-all duration-300 hover:scale-[1.01] hover:shadow-2xl hover:shadow-primary/5">
        <div className="absolute -bottom-10 -right-10 w-24 h-24 bg-primary/5 blur-2xl rounded-full"></div>
        
        <div className="flex justify-between items-start mb-4">
          <div className={`p-3 rounded-xl ${sferaConnected ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400'}`}>
            <Database className={`w-6 h-6 ${sferaConnected ? 'animate-pulse' : ''}`} />
          </div>
          <div className="flex items-center gap-1.5 bg-slate-950/40 border border-white/5 rounded-full px-2.5 py-0.5">
            <span className={`w-2 h-2 rounded-full ${sferaConnected ? 'bg-emerald-500 animate-ping' : 'bg-red-500'}`}></span>
            <span className={`text-[10px] font-bold ${sferaConnected ? 'text-emerald-400' : 'text-red-400'}`}>
              {sferaConnected ? 'ONLINE' : 'BŁĄD'}
            </span>
          </div>
        </div>

        <h3 className="text-sm font-bold text-text-muted">Połączenie ze Sferą GT</h3>
        <p className="text-lg font-bold text-text-main mt-1">
          {sferaConnected ? 'Sfera połączona' : 'Brak połączenia'}
        </p>
        
        <div className="mt-4 flex items-center justify-between">
          <span className="text-xs font-mono text-text-muted">
            {sferaPing !== null ? `ping: ${sferaPing}ms` : 'ping: --'}
          </span>
          <button
            onClick={handleTestSfera}
            disabled={testingSfera}
            className="flex items-center gap-1.5 text-[11px] font-bold tracking-wide uppercase px-3 py-1.5 rounded-lg border border-white/10 hover:border-white/20 bg-slate-950/40 hover:bg-slate-950/80 text-text-main transition-colors cursor-pointer disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${testingSfera ? 'animate-spin' : ''}`} />
            Testuj
          </button>
        </div>
      </div>

      {/* KARTA 2: API Activity */}
      <div className="relative group overflow-hidden bg-slate-900/40 backdrop-blur-xl border border-white/5 hover:border-primary/30 rounded-2xl p-6 transition-all duration-300 hover:scale-[1.01] hover:shadow-2xl hover:shadow-primary/5">
        <div className="absolute -bottom-10 -right-10 w-24 h-24 bg-primary/5 blur-2xl rounded-full"></div>
        
        <div className="flex justify-between items-start mb-2">
          <div className="p-3 rounded-xl bg-primary/10 text-primary">
            <Activity className="w-6 h-6" />
          </div>
          <div className="text-right">
            <span className="text-[10px] font-bold text-text-muted tracking-wider block">ŚR. ODPOWIEDŹ</span>
            <span className="text-xs font-mono font-bold text-violet-400">{stats.avg_latency_ms} ms</span>
          </div>
        </div>

        <h3 className="text-sm font-bold text-text-muted">Zapytania API (60s)</h3>
        <div className="text-2xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-primary via-purple-400 to-pink-500 font-mono">
          <AnimatedCounter value={stats.requests_last_60s} />
        </div>
        
        <Sparkline history={stats.request_history} />
      </div>

      {/* KARTA 3: Inventory Stats */}
      <div className="relative group overflow-hidden bg-slate-900/40 backdrop-blur-xl border border-white/5 hover:border-primary/30 rounded-2xl p-6 transition-all duration-300 hover:scale-[1.01] hover:shadow-2xl hover:shadow-primary/5">
        <div className="absolute -bottom-10 -right-10 w-24 h-24 bg-primary/5 blur-2xl rounded-full"></div>
        
        <div className="flex justify-between items-start mb-4">
          <div className="p-3 rounded-xl bg-cyan-500/10 text-cyan-400">
            <Package className="w-6 h-6" />
          </div>
          <div className="flex items-center gap-1.5 bg-slate-950/40 border border-white/5 rounded-full px-2.5 py-0.5">
            <span className="text-[10px] font-bold text-cyan-400">MAGAZYN</span>
          </div>
        </div>

        <h3 className="text-sm font-bold text-text-muted">Unikalne towary (dziś)</h3>
        <p className="text-2xl font-bold text-text-main font-mono">
          <AnimatedCounter value={stats.products_checked_today} />
        </p>

        <div className="mt-4 pt-3 border-t border-white/5 flex flex-col gap-1 text-[10px]">
          <div className="flex justify-between">
            <span className="text-text-muted">Zapytania bulk:</span>
            <span className="font-mono text-text-main font-bold">{stats.bulk_stock_queries}</span>
          </div>
          <div className="flex justify-between truncate">
            <span className="text-text-muted">Ostatnie:</span>
            <span className="font-mono text-text-muted truncate ml-2">
              {stats.last_stock_status === 'OK' ? '🟢 OK' : stats.last_stock_status === 'Brak' ? '--' : '🔴 ERR'}{' '}
              {stats.last_stock_time}
            </span>
          </div>
        </div>
      </div>

      {/* KARTA 4: Invoices & Docs */}
      <div className="relative group overflow-hidden bg-slate-900/40 backdrop-blur-xl border border-white/5 hover:border-primary/30 rounded-2xl p-6 transition-all duration-300 hover:scale-[1.01] hover:shadow-2xl hover:shadow-primary/5">
        <div className="absolute -bottom-10 -right-10 w-24 h-24 bg-primary/5 blur-2xl rounded-full"></div>
        
        <div className="flex justify-between items-start mb-4">
          <div className="p-3 rounded-xl bg-pink-500/10 text-pink-400">
            <FileText className="w-6 h-6" />
          </div>
          
          <div className="flex flex-col gap-1 items-end">
            {stats.ksef_enabled && (
              <span className="flex items-center gap-1 text-[9px] font-extrabold bg-blue-500/10 border border-blue-500/30 text-blue-400 rounded-full px-2 py-0.5">
                KSeF AKTYWNY
              </span>
            )}
            {stats.fiscalization_enabled && (
              <span className="flex items-center gap-1 text-[9px] font-extrabold bg-indigo-500/10 border border-indigo-500/30 text-indigo-400 rounded-full px-2 py-0.5">
                FISKALIZACJA
              </span>
            )}
          </div>
        </div>

        <h3 className="text-sm font-bold text-text-muted">Dokumenty dziś (WZ/FS/FZ)</h3>
        <p className="text-2xl font-bold text-text-main font-mono">
          <AnimatedCounter value={stats.invoices_created_today} />
        </p>

        <div className="mt-4 pt-3 border-t border-white/5 flex flex-col gap-1 text-[10px]">
          <div className="flex justify-between items-center truncate">
            <span className="text-text-muted">Ostatni dokument:</span>
            <span className="font-mono text-pink-400 font-bold max-w-[120px] truncate">
              {stats.last_invoice_number || '--'}
            </span>
          </div>
          <div className="flex justify-between truncate">
            <span className="text-text-muted">Status:</span>
            <span className="font-mono text-text-muted truncate ml-2">
              {stats.last_invoice_status === 'OK' ? '🟢 OK' : stats.last_invoice_status === 'Brak' ? '--' : '🔴 ERR'}{' '}
              {stats.last_invoice_time}
            </span>
          </div>
        </div>
      </div>

    </div>
  );
};
