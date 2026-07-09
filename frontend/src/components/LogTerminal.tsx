import React, { useState, useEffect, useRef } from 'react';
import { Terminal, Download, Trash2 } from 'lucide-react';

interface LogLine {
  id: string;
  timestamp: string;
  level: 'INFO' | 'SUCCESS' | 'WARNING' | 'ERROR' | 'REQUEST' | 'DEBUG';
  message: string;
  raw: string;
}

interface LogTerminalProps {
  logs: string[];
  onClear: () => void;
  wsConnected: boolean;
}

export const LogTerminal: React.FC<LogTerminalProps> = ({
  logs,
  onClear,
  wsConnected,
}) => {
  const [filters, setFilters] = useState({
    DEBUG: false,
    INFO: true,
    SUCCESS: true,
    WARNING: true,
    ERROR: true,
    REQUEST: true,
  });

  const terminalEndRef = useRef<HTMLDivElement>(null);
  const [parsedLogs, setParsedLogs] = useState<LogLine[]>([]);

  // Parse raw logs whenever they change
  useEffect(() => {
    const parsed = logs.map((rawLine) => {
      // Extract timestamp (HH:MM:SS)
      let timestamp = '';
      const timeMatch = rawLine.match(/\d{2}:\d{2}:\d{2}/);
      if (timeMatch) {
        timestamp = timeMatch[0];
      } else {
        // Fallback: extract time from local Date if no match
        timestamp = new Date().toLocaleTimeString();
      }

      // Determine level
      let level: LogLine['level'] = 'INFO';
      if (rawLine.includes(' - ERROR - ') || rawLine.includes('com_error') || rawLine.includes('Traceback') || rawLine.includes('pywintypes.com_error')) {
        level = 'ERROR';
      } else if (rawLine.includes(' - WARNING - ') || rawLine.includes('WARNING')) {
        level = 'WARNING';
      } else if (rawLine.includes(' - DEBUG - ')) {
        level = 'DEBUG';
      } else if (rawLine.includes(' - INFO - ')) {
        level = 'INFO';
      } else if (rawLine.includes('Traceback') || rawLine.startsWith('  File "') || rawLine.includes('Error:')) {
        // Traceback lines take the last known level (usually ERROR)
        level = 'ERROR';
      }

      // Detect requests
      if (
        rawLine.includes('Otrzymano żądanie') || 
        rawLine.includes('POST /') || 
        rawLine.includes('GET /') || 
        rawLine.includes('HTTP/1.1') ||
        rawLine.includes('>>> [DEPENDENCY]')
      ) {
        level = 'REQUEST';
      }

      // Detect successes
      if (
        rawLine.includes('Pomyślnie') || 
        rawLine.includes('udał się') || 
        rawLine.includes('poprawny') || 
        rawLine.includes('gotowe') ||
        rawLine.includes('połączono')
      ) {
        level = 'SUCCESS';
      }

      // Extract message - strip dates, module name, line numbers to clean it up
      let message = rawLine;
      const parts = rawLine.split(' - ');
      if (parts.length >= 4) {
        message = parts.slice(3).join(' - ');
      } else if (parts.length >= 3) {
        message = parts.slice(2).join(' - ');
      }

      return {
        id: Math.random().toString(36).substring(2, 9),
        timestamp,
        level,
        message,
        raw: rawLine,
      };
    });

    setParsedLogs(parsed);
  }, [logs]);

  // Scroll to bottom
  useEffect(() => {
    terminalEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [parsedLogs]);

  const handleFilterToggle = (lvl: keyof typeof filters) => {
    setFilters((prev) => ({ ...prev, [lvl]: !prev[lvl] }));
  };

  const filteredLogs = parsedLogs.filter((log) => filters[log.level]);

  const exportLogs = () => {
    const text = logs.join('\n');
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `subiekt_agent_logs_${new Date().toISOString().slice(0, 10)}.txt`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const getLevelColor = (level: LogLine['level']) => {
    switch (level) {
      case 'DEBUG':
        return 'text-slate-500';
      case 'INFO':
        return 'text-indigo-400';
      case 'SUCCESS':
        return 'text-emerald-400 font-bold';
      case 'WARNING':
        return 'text-amber-400';
      case 'ERROR':
        return 'text-red-400 font-bold';
      case 'REQUEST':
        return 'text-cyan-400';
      default:
        return 'text-slate-300';
    }
  };

  return (
    <div className="bg-slate-900/40 backdrop-blur-xl border border-white/5 rounded-2xl p-6 mb-8 relative">
      <div className="absolute -bottom-10 -right-10 w-24 h-24 bg-primary/5 blur-2xl rounded-full"></div>

      {/* Terminal Title & Controls */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-4 pb-4 border-b border-white/5">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-slate-950/60 border border-white/5 rounded-lg">
            <Terminal className="w-5 h-5 text-primary" />
          </div>
          <div>
            <h2 className="text-sm font-extrabold text-text-main flex items-center gap-2">
              Logi Systemowe
              <span className={`text-[10px] px-2 py-0.5 rounded-full font-mono ${
                wsConnected ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-red-500/10 text-red-400 border border-red-500/20'
              }`}>
                {wsConnected ? 'STREAMING' : 'ROZŁĄCZONO'}
              </span>
            </h2>
            <p className="text-[10px] text-text-muted">Podgląd zdarzeń lokalnych w czasie rzeczywistym</p>
          </div>
        </div>

        <div className="flex items-center gap-3 w-full md:w-auto justify-end">
          <button
            onClick={onClear}
            className="flex items-center gap-1 text-[11px] font-bold uppercase tracking-wider text-text-muted hover:text-red-400 transition-colors cursor-pointer"
          >
            <Trash2 className="w-3.5 h-3.5" />
            Wyczyść
          </button>
          <button
            onClick={exportLogs}
            className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider border border-white/10 hover:border-white/20 bg-slate-950/40 hover:bg-slate-950/80 px-3.5 py-2 rounded-xl text-text-main transition-colors cursor-pointer"
          >
            <Download className="w-3.5 h-3.5" />
            Eksportuj (.txt)
          </button>
        </div>
      </div>

      {/* Filter pills */}
      <div className="flex flex-wrap gap-2 mb-4">
        {(Object.keys(filters) as Array<keyof typeof filters>).map((lvl) => (
          <button
            key={lvl}
            onClick={() => handleFilterToggle(lvl)}
            className={`text-[10px] font-bold px-3 py-1.5 rounded-lg border transition-all cursor-pointer ${
              filters[lvl]
                ? 'bg-primary/20 border-primary/40 text-violet-300 shadow-sm shadow-primary/10'
                : 'bg-slate-950/20 border-white/5 text-text-muted hover:text-text-main'
            }`}
          >
            {lvl}
          </button>
        ))}
        
        {/* Logs counter */}
        <span className="text-[10px] font-mono font-bold bg-slate-950/60 border border-white/5 text-text-muted px-2.5 py-1.5 rounded-lg ml-auto">
          Wpisy: {filteredLogs.length}
        </span>
      </div>

      {/* Terminal Display */}
      <div className="bg-slate-950/70 border border-white/5 rounded-xl p-4 h-[300px] overflow-y-auto font-mono text-[11px] leading-relaxed relative">
        <div className="space-y-1.5">
          {filteredLogs.length === 0 ? (
            <div className="text-center text-text-muted py-24 select-none">
              Brak logów pasujących do zaznaczonych filtrów.
            </div>
          ) : (
            filteredLogs.map((log) => (
              <div key={log.id} className="flex items-start gap-2 hover:bg-white/[0.01] py-0.5 px-1 rounded transition-colors">
                <span className="text-text-muted shrink-0">[{log.timestamp}]</span>
                <span className={`shrink-0 font-bold ${getLevelColor(log.level)}`}>
                  [{log.level}]
                </span>
                <span className="text-text-main whitespace-pre-wrap break-all">{log.message}</span>
              </div>
            ))
          )}
          <div ref={terminalEndRef} />
        </div>
      </div>
    </div>
  );
};
