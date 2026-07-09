import React, { useEffect, useState } from 'react';
import { CheckCircle, AlertCircle, X } from 'lucide-react';

interface ToastProps {
  type: 'success' | 'error';
  message: string;
  onClose: () => void;
  duration?: number;
}

export const Toast: React.FC<ToastProps> = ({
  type,
  message,
  onClose,
  duration = 4000,
}) => {
  const [progress, setProgress] = useState(100);

  useEffect(() => {
    const startTime = Date.now();
    const interval = setInterval(() => {
      const elapsed = Date.now() - startTime;
      const remaining = Math.max(0, 100 - (elapsed / duration) * 100);
      setProgress(remaining);
      
      if (elapsed >= duration) {
        clearInterval(interval);
        onClose();
      }
    }, 16);

    return () => clearInterval(interval);
  }, [duration, onClose]);

  return (
    <div className="relative overflow-hidden min-w-[300px] max-w-[400px] bg-slate-950/80 backdrop-blur-xl border border-white/10 rounded-xl p-4 shadow-2xl flex items-start gap-3 animate-slideIn">
      {type === 'success' ? (
        <CheckCircle className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />
      ) : (
        <AlertCircle className="w-5 h-5 text-red-400 shrink-0 mt-0.5" />
      )}
      
      <div className="flex-1">
        <p className="text-xs font-bold text-text-main">
          {type === 'success' ? 'Sukces' : 'Błąd'}
        </p>
        <p className="text-[11px] text-text-muted mt-1 leading-relaxed">{message}</p>
      </div>

      <button 
        onClick={onClose}
        className="text-text-muted hover:text-text-main transition-colors cursor-pointer"
      >
        <X className="w-4 h-4" />
      </button>

      {/* Progress Bar */}
      <div className="absolute bottom-0 left-0 w-full h-[3px] bg-white/5">
        <div 
          className={`h-full transition-all duration-[16ms] linear ${
            type === 'success' ? 'bg-emerald-500' : 'bg-red-500'
          }`}
          style={{ width: `${progress}%` }}
        ></div>
      </div>

      <style>{`
        @keyframes slideIn {
          from {
            transform: translateY(20px);
            opacity: 0;
          }
          to {
            transform: translateY(0);
            opacity: 1;
          }
        }
        .animate-slideIn {
          animation: slideIn 0.3s cubic-bezier(0.16, 1, 0.3, 1) forwards;
        }
      `}</style>
    </div>
  );
};
