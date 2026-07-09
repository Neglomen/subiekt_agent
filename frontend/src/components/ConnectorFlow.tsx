import React from 'react';
import { Database, Cpu, CloudLightning } from 'lucide-react';

interface ConnectorFlowProps {
  sferaConnected: boolean;
  cfConnected: boolean;
  ngrokConnected?: boolean;
  ngrokUrl?: string;
}

export const ConnectorFlow: React.FC<ConnectorFlowProps> = ({
  sferaConnected,
  cfConnected,
  ngrokConnected = false,
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  ngrokUrl: _ngrokUrl = '',
}) => {
  const tunnelConnected = cfConnected || ngrokConnected;
  const tunnelLabel = cfConnected ? 'CF' : ngrokConnected ? 'ngrok' : '';
  return (
    <div className="relative w-full max-w-4xl mx-auto py-8 px-4 bg-slate-900/20 rounded-2xl border border-white/5 backdrop-blur-md overflow-hidden mb-8">
      {/* Background glow effects */}
      <div className="absolute top-1/2 left-1/4 -translate-y-1/2 w-48 h-48 bg-primary/10 blur-3xl rounded-full pointer-events-none"></div>
      <div className="absolute top-1/2 left-3/4 -translate-y-1/2 w-48 h-48 bg-emerald-500/5 blur-3xl rounded-full pointer-events-none"></div>

      <div className="relative flex justify-between items-center max-w-3xl mx-auto z-10">
        
        {/* Node 1: Subiekt GT */}
        <div className="flex flex-col items-center group">
          <div className={`relative p-5 rounded-2xl border transition-all duration-500 flex items-center justify-center ${
            sferaConnected 
              ? 'bg-emerald-500/10 border-emerald-500/30 shadow-lg shadow-emerald-500/10' 
              : 'bg-red-500/10 border-red-500/20'
          }`}>
            <div className={`absolute inset-0 rounded-2xl blur-md opacity-50 transition-all duration-500 ${
              sferaConnected ? 'bg-emerald-500/20 group-hover:opacity-100' : 'bg-red-500/10'
            }`}></div>
            <Database className={`w-8 h-8 relative z-10 transition-colors ${
              sferaConnected ? 'text-emerald-400' : 'text-red-400'
            }`} />
          </div>
          <span className="mt-3 text-sm font-bold tracking-tight text-text-main">Subiekt GT ERP</span>
          <span className={`text-xs mt-1 font-mono ${
            sferaConnected ? 'text-emerald-400' : 'text-red-400'
          }`}>
            {sferaConnected ? 'POŁĄCZONO' : 'BŁĄD SFERY'}
          </span>
        </div>

        {/* Connection Line 1 */}
        <div className="flex-1 px-4 relative h-12">
          <svg className="w-full h-full" overflow="visible">
            <defs>
              <linearGradient id="grad1" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stopColor={sferaConnected ? '#10b981' : '#f43f5e'} />
                <stop offset="100%" stopColor="#818cf8" />
              </linearGradient>
            </defs>
            {/* Base Line */}
            <line 
              x1="0%" y1="50%" x2="100%" y2="50%" 
              stroke={sferaConnected ? 'rgba(16, 185, 129, 0.1)' : 'rgba(244, 63, 94, 0.1)'} 
              strokeWidth="4" 
              strokeLinecap="round"
            />
            {/* Flowing Line */}
            {sferaConnected && (
              <line 
                x1="0%" y1="50%" x2="100%" y2="50%" 
                stroke="url(#grad1)" 
                strokeWidth="4" 
                strokeLinecap="round"
                strokeDasharray="8 8"
                style={{
                  animation: 'flowRight 1.5s linear infinite'
                }}
              />
            )}
          </svg>
          <style>{`
            @keyframes flowRight {
              to {
                stroke-dashoffset: -16;
              }
            }
          `}</style>
        </div>

        {/* Node 2: Subiekt Agent */}
        <div className="flex flex-col items-center group">
          <div className="relative p-6 rounded-2xl border bg-primary/10 border-primary/30 shadow-lg shadow-primary/20 flex items-center justify-center">
            <div className="absolute inset-0 rounded-2xl bg-primary/20 blur-md opacity-60 group-hover:opacity-100 transition-opacity duration-300"></div>
            <Cpu className="w-10 h-10 text-violet-400 relative z-10 animate-pulse" />
          </div>
          <div className="mt-3 flex items-center gap-1.5">
            <span className="text-sm font-bold text-text-main">Subiekt</span>
            <span className="text-sm font-bold text-primary">Agent</span>
          </div>
          <span className="text-xs text-text-muted mt-1 font-mono">v0.5.1-web</span>
        </div>

        {/* Connection Line 2 */}
        <div className="flex-1 px-4 relative h-12">
          <svg className="w-full h-full" overflow="visible">
            <defs>
              <linearGradient id="grad2" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="#818cf8" stopOpacity="0.8" />
                <stop offset="100%" stopColor={tunnelConnected ? '#10b981' : '#f43f5e'} stopOpacity="0.8" />
              </linearGradient>
            </defs>
            {/* Base Line */}
            <line 
              x1="0%" y1="50%" x2="100%" y2="50%" 
              stroke={tunnelConnected ? 'rgba(16, 185, 129, 0.1)' : 'rgba(244, 63, 94, 0.1)'} 
              strokeWidth="4" 
              strokeLinecap="round"
            />
            {/* Flowing Line */}
            {tunnelConnected && (
              <line 
                x1="0%" y1="50%" x2="100%" y2="50%" 
                stroke="url(#grad2)" 
                strokeWidth="4" 
                strokeLinecap="round"
                strokeDasharray="8 8"
                style={{
                  animation: 'flowRight 1.5s linear infinite'
                }}
              />
            )}
          </svg>
        </div>

        {/* Node 3: SuppSales */}
        <div className="flex flex-col items-center group">
          <div className={`relative p-5 rounded-2xl border transition-all duration-500 flex items-center justify-center ${
            tunnelConnected 
              ? 'bg-emerald-500/10 border-emerald-500/30 shadow-lg shadow-emerald-500/10' 
              : 'bg-red-500/10 border-red-500/20'
          }`}>
            <div className={`absolute inset-0 rounded-2xl blur-md opacity-50 transition-all duration-500 ${
              tunnelConnected ? 'bg-emerald-500/20 group-hover:opacity-100' : 'bg-red-500/10'
            }`}></div>
            <CloudLightning className={`w-8 h-8 relative z-10 transition-colors ${
              tunnelConnected ? 'text-emerald-400' : 'text-red-400'
            }`} />
          </div>
          <span className="mt-3 text-sm font-bold tracking-tight text-text-main">SuppSales Cloud</span>
          <span className={`text-xs mt-1 font-mono max-w-[120px] truncate text-center ${
            tunnelConnected ? 'text-emerald-400' : 'text-red-400'
          }`}>
            {tunnelConnected ? `TUNEL ${tunnelLabel} AKTYWNY` : 'TUNEL NIEAKTYWNY'}
          </span>
        </div>

      </div>
    </div>
  );
};
