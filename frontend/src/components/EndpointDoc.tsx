import React, { useState } from 'react';
import { Play, X, Send, HelpCircle } from 'lucide-react';

interface Endpoint {
  method: 'GET' | 'POST';
  path: string;
  description: string;
  group: 'products' | 'invoices' | 'sales-invoices' | 'config' | 'status';
  samplePayload?: string;
  queryParams?: { name: string; placeholder: string; value: string }[];
}

const ENDPOINTS: Endpoint[] = [
  {
    method: 'GET',
    path: '/status',
    description: 'Sprawdza ogólny stan agenta oraz status aktywnego połączenia ze Sferą Subiekta GT.',
    group: 'status',
  },
  {
    method: 'GET',
    path: '/products',
    description: 'Wyszukuje produkty w kartotece Subiekta GT po symbolu lub nazwie.',
    group: 'products',
    queryParams: [
      { name: 'q', placeholder: 'np. TOSHIBA', value: '' }
    ]
  },
  {
    method: 'POST',
    path: '/products/stock/bulk',
    description: 'Masowo pobiera aktualne stany magazynowe (stan wolny = stan - rezerwacje) dla listy symboli.',
    group: 'products',
    samplePayload: JSON.stringify({
      symbols: ["MWP-MM20P(BK) CZARNA", "DFM 66B8EOQBH", "NIEISTNIEJACY-SYMBOL"]
    }, null, 2),
  },
  {
    method: 'POST',
    path: '/products/components/bulk',
    description: 'Pobiera składniki i ich ilości dla podanej listy symboli kompletów.',
    group: 'products',
    samplePayload: JSON.stringify({
      symbols: ["KOMPLET-TOWAROWY-1"]
    }, null, 2),
  },
  {
    method: 'POST',
    path: '/sales-invoices/create',
    description: 'Tworzy Fakturę Sprzedaży (FS) w Subiekcie GT dla zamówienia SuppSales wraz z opcją rezerwacji lub zakładania kontrahenta.',
    group: 'sales-invoices',
    samplePayload: JSON.stringify({
      original_order_number: "Zamówienie : 3fcd5fb0-76dd-11f1",
      customer: {
        nip: "7361748232",
        name: "Górska Grupa Hotelowa Sp. z o.o.",
        street: "Chyców Potok 26 lok. P.II",
        postal_code: "34-500",
        city: "Zakopane"
      },
      issue_date: new Date().toISOString().slice(0, 10),
      sale_date: new Date().toISOString().slice(0, 10),
      payment_due_date: new Date().toISOString().slice(0, 10),
      payment_type: "ONLINE",
      is_paid_in_advance: true,
      line_items: [
        {
          product_symbol: "MWP-MM20P(BK) CZARNA",
          quantity: "1",
          gross_price: "239.97",
          vat_rate: "23.0"
        }
      ]
    }, null, 2),
  },
  {
    method: 'GET',
    path: '/sales-invoices/pdf',
    description: 'Generuje i pobiera plik PDF z wydrukiem Faktury Sprzedaży (FS) bezpośrednio z Subiekta GT.',
    group: 'sales-invoices',
    queryParams: [
      { name: 'doc_number', placeholder: 'np. FS 12/2026', value: '' }
    ]
  },
  {
    method: 'POST',
    path: '/invoices/check',
    description: 'Sprawdza czy Faktura Zakupu (FZ) o podanym numerze oryginalnym dostawcy już istnieje w bazie Subiekta.',
    group: 'invoices',
    samplePayload: JSON.stringify({
      original_invoice_number: "FV/98765/2026"
    }, null, 2),
  },
  {
    method: 'POST',
    path: '/invoices/create',
    description: 'Tworzy Fakturę Zakupu (FZ) w Subiekcie GT na podstawie dokumentu zakupu dostawcy.',
    group: 'invoices',
    samplePayload: JSON.stringify({
      original_invoice_number: "FV/98765/2026",
      supplier: {
        nip: "7361748232",
        name: "Górska Grupa Hotelowa Sp. z o.o.",
        street: "Chyców Potok 26",
        postal_code: "34-500",
        city: "Zakopane"
      },
      issue_date: new Date().toISOString().slice(0, 10),
      line_items: [
        {
          product_symbol: "MWP-MM20P(BK) CZARNA",
          quantity: "2",
          gross_price: "185.00",
          vat_rate: "23.0"
        }
      ]
    }, null, 2),
  },
  {
    method: 'GET',
    path: '/payment-forms',
    description: 'Pobiera słownik dostępnych form płatności zdefiniowanych w Subiekcie GT.',
    group: 'config',
  },
  {
    method: 'GET',
    path: '/config/mappings',
    description: 'Pobiera aktualne mapowania płatności, KSeF, fiskalizacji i produktów.',
    group: 'config',
  }
];

interface EndpointDocProps {
  apiKey: string;
}

export const EndpointDoc: React.FC<EndpointDocProps> = ({ apiKey }) => {
  const [activeGroup, setActiveGroup] = useState<'all' | 'products' | 'invoices' | 'sales-invoices' | 'config' | 'status'>('all');
  const [modalEndpoint, setModalEndpoint] = useState<Endpoint | null>(null);
  
  // Test modal state
  const [payloadText, setPayloadText] = useState('');
  const [queryParams, setQueryParams] = useState<{ name: string; value: string }[]>([]);
  const [testResult, setTestResult] = useState<{ status: number; data: any } | null>(null);
  const [testing, setTesting] = useState(false);

  const openTestModal = (endpoint: Endpoint) => {
    setModalEndpoint(endpoint);
    setPayloadText(endpoint.samplePayload || '');
    setQueryParams(endpoint.queryParams?.map(q => ({ name: q.name, value: '' })) || []);
    setTestResult(null);
  };

  const handleQueryParamChange = (index: number, val: string) => {
    setQueryParams(prev => {
      const copy = [...prev];
      copy[index].value = val;
      return copy;
    });
  };

  const runApiTest = async () => {
    if (!modalEndpoint) return;
    setTesting(true);
    setTestResult(null);
    
    try {
      // Budujemy query string
      let url = modalEndpoint.path;
      if (queryParams.length > 0) {
        const queryStrings = queryParams
          .filter(q => q.value)
          .map(q => `${encodeURIComponent(q.name)}=${encodeURIComponent(q.value)}`);
        if (queryStrings.length > 0) {
          url += `?${queryStrings.join('&')}`;
        }
      }

      const options: RequestInit = {
        method: modalEndpoint.method,
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': apiKey,
        },
      };

      if (modalEndpoint.method === 'POST' && payloadText) {
        options.body = payloadText;
      }

      const res = await fetch(url, options);
      const isJson = res.headers.get('content-type')?.includes('application/json');
      let data;
      if (isJson) {
        data = await res.json();
      } else {
        data = { response: 'Pomyślnie pobrano plik/dane (non-JSON)' };
      }
      
      setTestResult({
        status: res.status,
        data,
      });
    } catch (err: any) {
      setTestResult({
        status: 500,
        data: { error: err.message || 'Wystąpił błąd sieci.' },
      });
    } finally {
      setTesting(false);
    }
  };

  const filteredEndpoints = activeGroup === 'all'
    ? ENDPOINTS
    : ENDPOINTS.filter(e => e.group === activeGroup);

  return (
    <div className="bg-slate-900/40 backdrop-blur-xl border border-white/5 rounded-2xl p-6 relative">
      <div className="absolute -bottom-10 -right-10 w-24 h-24 bg-primary/5 blur-2xl rounded-full"></div>

      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6 pb-4 border-b border-white/5">
        <div>
          <h2 className="text-sm font-extrabold text-text-main">Interaktywna Dokumentacja API</h2>
          <p className="text-[10px] text-text-muted">Lista endpointów HTTP agenta z możliwością bezpośredniego testowania</p>
        </div>
      </div>

      {/* Tab select group */}
      <div className="flex flex-wrap gap-2 mb-6">
        {['all', 'status', 'products', 'sales-invoices', 'invoices', 'config'].map((grp) => (
          <button
            key={grp}
            onClick={() => setActiveGroup(grp as any)}
            className={`text-[10px] font-bold px-3 py-1.5 rounded-lg border transition-all cursor-pointer ${
              activeGroup === grp
                ? 'bg-primary/20 border-primary/45 text-violet-300'
                : 'bg-slate-950/20 border-white/5 text-text-muted hover:text-text-main'
            }`}
          >
            {grp === 'all' ? 'WSZYSTKIE' : grp.toUpperCase()}
          </button>
        ))}
      </div>

      {/* Grid of endpoints */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {filteredEndpoints.map((ep) => (
          <div
            key={ep.path}
            className="group bg-slate-950/40 border border-white/5 hover:border-primary/20 rounded-xl p-4 flex flex-col justify-between transition-all duration-300 hover:scale-[1.005]"
          >
            <div>
              <div className="flex items-center gap-2 mb-2">
                <span className={`text-[9px] font-extrabold px-2 py-0.5 rounded font-mono ${
                  ep.method === 'GET' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-violet-500/10 text-violet-400 border border-violet-500/20'
                }`}>
                  {ep.method}
                </span>
                <span className="text-xs font-mono font-bold text-text-main group-hover:text-primary transition-colors">{ep.path}</span>
              </div>
              <p className="text-[11px] text-text-muted leading-relaxed mb-4">{ep.description}</p>
            </div>
            
            <button
              onClick={() => openTestModal(ep)}
              className="flex items-center gap-1.5 text-[10px] font-bold tracking-wide uppercase px-3 py-1.5 rounded-lg border border-white/10 hover:border-white/20 bg-slate-900/40 hover:bg-slate-900/80 text-text-main transition-colors cursor-pointer self-start"
            >
              <Play className="w-3.5 h-3.5 text-primary" />
              Testuj Endpoint
            </button>
          </div>
        ))}
      </div>

      {/* Modal testowy */}
      {modalEndpoint && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4 animate-fadeIn">
          <div className="bg-slate-900 border border-white/10 rounded-2xl max-w-3xl w-full max-h-[90vh] overflow-hidden flex flex-col shadow-2xl relative">
            <div className="absolute top-0 right-0 w-48 h-48 bg-primary/5 blur-3xl rounded-full pointer-events-none"></div>
            
            {/* Modal Header */}
            <div className="p-5 border-b border-white/5 flex justify-between items-center bg-slate-950/40">
              <div className="flex items-center gap-2">
                <span className={`text-[10px] font-extrabold px-2 py-0.5 rounded font-mono ${
                  modalEndpoint.method === 'GET' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-violet-500/10 text-violet-400 border border-violet-500/20'
                }`}>
                  {modalEndpoint.method}
                </span>
                <span className="text-sm font-mono font-bold text-text-main">{modalEndpoint.path}</span>
              </div>
              <button
                onClick={() => setModalEndpoint(null)}
                className="text-text-muted hover:text-text-main transition-colors cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-6 overflow-y-auto flex-1 grid grid-cols-1 md:grid-cols-2 gap-6">
              
              {/* Left Column: Request */}
              <div className="flex flex-col gap-4">
                <h3 className="text-xs font-bold text-text-muted tracking-wider uppercase">Konfiguracja Zapytania</h3>
                
                {/* Headers indication */}
                <div className="bg-slate-950/40 p-3 rounded-lg border border-white/5 text-[10px] font-mono text-text-muted">
                  <div className="flex justify-between">
                    <span>Content-Type:</span>
                    <span className="text-text-main font-bold">application/json</span>
                  </div>
                  <div className="flex justify-between mt-1">
                    <span>X-API-Key:</span>
                    <span className="text-primary font-bold truncate max-w-[150px]">{apiKey || 'Brak klucza!'}</span>
                  </div>
                </div>

                {/* Query parameters */}
                {queryParams.length > 0 && (
                  <div className="space-y-3">
                    <label className="block text-[10px] font-bold text-text-muted tracking-wider uppercase">Parametry URL (?)</label>
                    {queryParams.map((q, idx) => (
                      <div key={q.name} className="flex flex-col gap-1">
                        <span className="text-[10px] font-mono text-text-main">{q.name}</span>
                        <input
                          type="text"
                          value={q.value}
                          onChange={(e) => handleQueryParamChange(idx, e.target.value)}
                          placeholder={modalEndpoint.queryParams?.[idx].placeholder}
                          className="w-full bg-slate-950/60 border border-white/10 rounded-lg px-3 py-1.5 text-text-main font-mono text-xs focus:outline-none focus:border-primary/50"
                        />
                      </div>
                    ))}
                  </div>
                )}

                {/* JSON Body */}
                {modalEndpoint.method === 'POST' && (
                  <div className="flex-1 flex flex-col min-h-[220px]">
                    <label className="block text-[10px] font-bold text-text-muted tracking-wider uppercase mb-2">Treść Zapytania (JSON Body)</label>
                    <textarea
                      value={payloadText}
                      onChange={(e) => setPayloadText(e.target.value)}
                      className="w-full flex-1 bg-slate-950/60 border border-white/10 rounded-xl p-3 text-text-main font-mono text-xs focus:outline-none focus:border-primary/50 resize-none min-h-[180px]"
                    />
                  </div>
                )}
                
                <button
                  onClick={runApiTest}
                  disabled={testing}
                  className="flex items-center justify-center gap-2 text-xs font-bold uppercase tracking-wider py-2.5 rounded-xl bg-gradient-to-r from-primary to-purple-600 hover:from-primary/95 hover:to-purple-600/95 text-white shadow-lg shadow-primary/20 hover:scale-[1.01] active:scale-[0.99] transition-all cursor-pointer disabled:opacity-50 mt-auto"
                >
                  <Send className="w-4 h-4" />
                  {testing ? 'Wysyłanie...' : 'Wyślij Żądanie'}
                </button>
              </div>

              {/* Right Column: Response */}
              <div className="flex flex-col gap-4">
                <div className="flex justify-between items-center">
                  <h3 className="text-xs font-bold text-text-muted tracking-wider uppercase">Odpowiedź Serwera</h3>
                  {testResult && (
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                      testResult.status >= 200 && testResult.status < 300 
                        ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' 
                        : 'bg-red-500/10 text-red-400 border border-red-500/20'
                    }`}>
                      KOD: {testResult.status}
                    </span>
                  )}
                </div>

                <div className="flex-1 bg-slate-950/70 border border-white/5 rounded-xl p-4 overflow-auto font-mono text-xs min-h-[280px] max-h-[380px] relative">
                  {testResult ? (
                    <pre className="text-text-main">{JSON.stringify(testResult.data, null, 2)}</pre>
                  ) : (
                    <div className="absolute inset-0 flex flex-col items-center justify-center text-center p-6 select-none">
                      <HelpCircle className="w-8 h-8 text-slate-700 mb-2 animate-bounce" />
                      <p className="text-[10px] text-text-muted">Skonfiguruj żądanie i kliknij przycisk po lewej stronie, aby otrzymać odpowiedź.</p>
                    </div>
                  )}
                </div>
              </div>

            </div>
          </div>
        </div>
      )}
    </div>
  );
};
