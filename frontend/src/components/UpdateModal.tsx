import React, { useState } from 'react';
import { Download, Sparkles, AlertCircle, X } from 'lucide-react';

interface UpdateInfo {
  current_version: string;
  latest_version: string;
  is_newer: boolean;
  changelog: string;
  download_url: string;
}

interface UpdateModalProps {
  updateInfo: UpdateInfo;
  onClose: () => void;
  apiKey: string | null;
}

export const UpdateModal: React.FC<UpdateModalProps> = ({ updateInfo, onClose, apiKey }) => {
  const [downloadStatus, setDownloadStatus] = useState<'idle' | 'downloading' | 'finished' | 'error'>('idle');
  const [progress, setProgress] = useState(0);
  const [errorMsg, setErrorMsg] = useState('');

  const handleUpdate = async () => {
    setDownloadStatus('downloading');
    setProgress(0);
    setErrorMsg('');

    try {
      // Serwer sam ponownie ustala i weryfikuje URL najnowszego wydania — nie
      // przekazujemy download_url z klienta (patrz subiekt_agent/CLAUDE.md).
      const res = await fetch('/gui/update/download', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-API-Key': apiKey || '' },
      });

      if (!res.ok) {
        throw new Error('Nie udało się rozpocząć pobierania.');
      }

      // Rozpocznij odpytywanie o postęp
      pollProgress();
    } catch (err: any) {
      setDownloadStatus('error');
      setErrorMsg(err.message || 'Wystąpił nieznany błąd.');
    }
  };

  const pollProgress = () => {
    const interval = setInterval(async () => {
      try {
        const res = await fetch('/gui/update/progress', { headers: { 'X-API-Key': apiKey || '' } });
        if (res.ok) {
          const data = await res.json();
          setDownloadStatus(data.status);
          setProgress(data.progress);
          
          if (data.status === 'finished') {
            clearInterval(interval);
          } else if (data.status === 'error') {
            clearInterval(interval);
            setErrorMsg(data.error || 'Błąd pobierania pliku.');
          }
        }
      } catch (err) {
        console.error('Błąd odpytywania o postęp aktualizacji:', err);
      }
    }, 500);

    return () => clearInterval(interval);
  };

  return (
    <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm z-50 flex items-center justify-center p-4 animate-fadeIn">
      <div className="bg-slate-900 border border-white/10 rounded-2xl w-full max-w-lg shadow-2xl overflow-hidden relative flex flex-col max-h-[90vh]">
        
        {/* Header */}
        <div className="p-6 border-b border-white/5 flex justify-between items-start">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center text-primary">
              <Sparkles className="w-5 h-5 animate-pulse" />
            </div>
            <div>
              <h3 className="text-base font-bold text-text-main">Dostępna nowa wersja!</h3>
              <p className="text-xs text-text-muted">
                Zainstalowana: <span className="font-mono text-white">{updateInfo.current_version}</span> → Najnowsza: <span className="font-mono text-green-400 font-bold">{updateInfo.latest_version}</span>
              </p>
            </div>
          </div>
          {downloadStatus !== 'downloading' && (
            <button 
              onClick={onClose}
              className="text-text-muted hover:text-text-main p-1 hover:bg-white/5 rounded-lg transition-colors cursor-pointer"
            >
              <X className="w-5 h-5" />
            </button>
          )}
        </div>

        {/* Content (Changelog) */}
        <div className="p-6 overflow-y-auto flex-1 bg-slate-950/40 text-sm text-text-main space-y-4">
          <div className="space-y-2">
            <h4 className="text-xs font-bold uppercase tracking-wider text-text-muted">Co nowego w tej wersji:</h4>
            <div className="bg-slate-950/60 border border-white/5 rounded-xl p-4 font-sans text-xs text-text-muted leading-relaxed whitespace-pre-wrap max-h-48 overflow-y-auto">
              {updateInfo.changelog || 'Brak opisu zmian dla tej wersji.'}
            </div>
          </div>

          {downloadStatus === 'downloading' && (
            <div className="space-y-2 pt-2">
              <div className="flex justify-between text-xs font-bold">
                <span className="text-primary animate-pulse">Pobieranie aktualizacji...</span>
                <span>{progress}%</span>
              </div>
              <div className="w-full bg-white/5 h-2 rounded-full overflow-hidden">
                <div 
                  className="bg-gradient-to-r from-primary to-purple-600 h-full transition-all duration-300"
                  style={{ width: `${progress}%` }}
                ></div>
              </div>
              <span className="text-[10px] text-text-muted block text-center">
                Po zakończeniu pobierania instalator uruchomi się automatycznie, a ta aplikacja zostanie zamknięta.
              </span>
            </div>
          )}

          {downloadStatus === 'finished' && (
            <div className="bg-green-500/10 border border-green-500/20 text-green-400 p-4 rounded-xl flex items-start gap-3 text-xs">
              <Sparkles className="w-5 h-5 shrink-0" />
              <div>
                <p className="font-bold">Pobieranie zakończone!</p>
                <p className="opacity-90">Uruchamianie instalatora... Aplikacja zostanie za chwilę wyłączona.</p>
              </div>
            </div>
          )}

          {downloadStatus === 'error' && (
            <div className="bg-red-500/10 border border-red-500/20 text-red-400 p-4 rounded-xl flex items-start gap-3 text-xs">
              <AlertCircle className="w-5 h-5 shrink-0" />
              <div>
                <p className="font-bold">Błąd pobierania aktualizacji</p>
                <p className="opacity-90">{errorMsg}</p>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-6 border-t border-white/5 bg-slate-900/50 flex justify-end gap-3 shrink-0">
          {downloadStatus !== 'downloading' && downloadStatus !== 'finished' && (
            <>
              <button
                onClick={onClose}
                className="px-5 py-2.5 rounded-xl border border-white/10 hover:bg-white/5 text-xs font-bold uppercase tracking-wider text-text-muted hover:text-text-main transition-all cursor-pointer"
              >
                Pomiń
              </button>
              <button
                onClick={handleUpdate}
                className="flex items-center gap-2 px-6 py-2.5 rounded-xl bg-gradient-to-r from-primary to-purple-600 hover:from-primary/95 hover:to-purple-600/95 text-white text-xs font-bold uppercase tracking-wider shadow-lg shadow-primary/20 hover:scale-[1.01] active:scale-[0.99] transition-all cursor-pointer"
              >
                <Download className="w-4 h-4" />
                Aktualizuj teraz
              </button>
            </>
          )}
          {(downloadStatus === 'downloading' || downloadStatus === 'finished') && (
            <button
              disabled
              className="px-6 py-2.5 rounded-xl bg-white/5 text-white/40 text-xs font-bold uppercase tracking-wider transition-all cursor-not-allowed w-full text-center"
            >
              Trwa aktualizacja...
            </button>
          )}
        </div>

      </div>
    </div>
  );
};
