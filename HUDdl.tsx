/**
 * HUDdl.tsx
 * ─────────────────────────────────────────────────────────────────────────────
 * Frontend for HUDdl.py — the combined Bay Area housing crawler + HUD data app.
 *
 * Features:
 *   • Tabbed view: All | Web Sites | HUD Official Data
 *   • Live search with debounce across all sources
 *   • Per-card VoIP call button and email inquiry modal
 *   • HUD layer badges (Multifamily, LIHTC, Public Housing, etc.)
 *   • CSV / JSON export button
 *   • Stats bar showing counts per source
 *
 * Setup:
 *   1. python HUDdl.py              (starts the API on port 8787)
 *   2. npm run dev                  (starts this frontend on port 5173)
 *   3. Open http://lcocalhost:5173
 *
 * Dependencies: React 18+, Tailwind CSS
 * ─────────────────────────────────────────────────────────────────────────────
 */

import { useState, useEffect, useCallback, useRef } from "react";

// ─── Logo component (inline SVG — no external file needed) ───────────────────
function HudLogo({ size = 40 }: { size?: number }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 520 520" width={size} height={size}>
      <defs>
        <linearGradient id="bodyGrad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" style={{stopColor:"#4a90d9",stopOpacity:1}} />
          <stop offset="100%" style={{stopColor:"#1a4fa0",stopOpacity:1}} />
        </linearGradient>
        <linearGradient id="roofGrad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" style={{stopColor:"#2563b0",stopOpacity:1}} />
          <stop offset="100%" style={{stopColor:"#0f3070",stopOpacity:1}} />
        </linearGradient>
        <linearGradient id="sideGrad" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" style={{stopColor:"#1a4fa0",stopOpacity:1}} />
          <stop offset="100%" style={{stopColor:"#3070c0",stopOpacity:1}} />
        </linearGradient>
        <linearGradient id="shimmer" x1="0%" y1="0%" x2="60%" y2="100%">
          <stop offset="0%" style={{stopColor:"#c8dff8",stopOpacity:0.45}} />
          <stop offset="100%" style={{stopColor:"#1a4fa0",stopOpacity:0}} />
        </linearGradient>
        <linearGradient id="windowGrad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" style={{stopColor:"#e8f3ff",stopOpacity:1}} />
          <stop offset="100%" style={{stopColor:"#b8d4f0",stopOpacity:1}} />
        </linearGradient>
      </defs>
      <ellipse cx="260" cy="490" rx="185" ry="14" fill="#1040a0" opacity="0.25"/>
      <rect x="135" y="148" width="38" height="70" rx="4" fill="#1a4fa0"/>
      <rect x="129" y="142" width="50" height="12" rx="3" fill="#2560b0"/>
      <rect x="135" y="148" width="12" height="60" rx="2" fill="#4a80d0" opacity="0.4"/>
      <rect x="338" y="155" width="34" height="62" rx="4" fill="#1a4fa0"/>
      <rect x="332" y="149" width="46" height="11" rx="3" fill="#2560b0"/>
      <rect x="338" y="155" width="10" height="55" rx="2" fill="#4a80d0" opacity="0.4"/>
      <rect x="78" y="295" width="364" height="185" rx="6" fill="url(#bodyGrad)"/>
      <polygon points="78,295 200,295 78,420" fill="url(#shimmer)" opacity="0.6"/>
      <polygon points="55,308 260,158 260,308" fill="url(#roofGrad)"/>
      <polygon points="260,158 465,308 260,308" fill="url(#sideGrad)"/>
      <polygon points="55,308 260,156 270,162 65,314" fill="white" opacity="0.85"/>
      <polygon points="455,308 260,156 250,162 445,314" fill="white" opacity="0.7"/>
      <line x1="260" y1="156" x2="260" y2="168" stroke="white" strokeWidth="3" opacity="0.6"/>
      <polygon points="80,306 160,230 160,306" fill="#6aaae0" opacity="0.18"/>
      <polygon points="215,225 260,190 305,225" fill="#1a4fa0"/>
      <rect x="227" y="216" width="66" height="52" rx="4" fill="url(#windowGrad)"/>
      <line x1="260" y1="216" x2="260" y2="268" stroke="#8ab8e0" strokeWidth="2.5"/>
      <line x1="227" y1="240" x2="293" y2="240" stroke="#8ab8e0" strokeWidth="2.5"/>
      <polygon points="229,218 248,218 229,238" fill="white" opacity="0.35"/>
      <rect x="104" y="330" width="88" height="80" rx="5" fill="url(#windowGrad)"/>
      <line x1="148" y1="330" x2="148" y2="410" stroke="#8ab8e0" strokeWidth="3"/>
      <line x1="104" y1="368" x2="192" y2="368" stroke="#8ab8e0" strokeWidth="3"/>
      <polygon points="106,332 128,332 106,356" fill="white" opacity="0.4"/>
      <rect x="328" y="330" width="88" height="80" rx="5" fill="url(#windowGrad)"/>
      <line x1="372" y1="330" x2="372" y2="410" stroke="#8ab8e0" strokeWidth="3"/>
      <line x1="328" y1="368" x2="416" y2="368" stroke="#8ab8e0" strokeWidth="3"/>
      <polygon points="330,332 352,332 330,356" fill="white" opacity="0.4"/>
      <rect x="222" y="358" width="76" height="122" rx="6" fill="#1040a0"/>
      <rect x="228" y="362" width="64" height="116" rx="5" fill="#1855b0"/>
      <polygon points="230,364 252,364 230,395" fill="#6090d8" opacity="0.35"/>
      <circle cx="280" cy="422" r="7" fill="#ddeeff" opacity="0.85"/>
      <circle cx="280" cy="422" r="4" fill="white" opacity="0.6"/>
      <rect x="65" y="476" width="390" height="12" rx="4" fill="#1648a0" opacity="0.7"/>
      <rect x="80" y="484" width="360" height="8" rx="3" fill="#1040a0" opacity="0.5"/>
    </svg>
  );
}

// ─── Config ───────────────────────────────────────────────────────────────────
const API_BASE = "https://huddl-backend.onrender.com";

// HUD layer color mapping
const HUD_LAYER_COLORS: Record<string, string> = {
  "Multifamily Properties (Assisted)": "bg-blue-100 text-blue-800",
  "Public Housing Authorities":        "bg-purple-100 text-purple-800",
  "Low Income Housing Tax Credits":    "bg-emerald-100 text-emerald-800",
  "USDA Rural Housing":                "bg-amber-100 text-amber-800",
  "Public Housing Buildings":          "bg-rose-100 text-rose-800",
  "Public Housing Developments":       "bg-teal-100 text-teal-800",
};

// ─── Types ────────────────────────────────────────────────────────────────────
interface Listing {
  source: "web" | "hud";
  url: string;
  title: string;
  address: string;
  city: string;
  state: string;
  zip_code: string;
  phone: string;
  email: string;
  price_range: string;
  bedrooms: string[];
  units: string;
  description: string;
  hud_layer: string;
  hud_program: string;
  status: "ok" | "error" | "timeout";
}

type TabKey = "all" | "web" | "hud";

interface EmailPayload {
  smtp_host: string;
  smtp_port: number;
  smtp_user: string;
  smtp_password: string;
  from: string;
  to: string;
  subject: string;
  body: string;
}

// ─── Hooks ────────────────────────────────────────────────────────────────────
function useDebounce<T>(value: T, delay = 350): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

// ─── EmailModal ───────────────────────────────────────────────────────────────
function EmailModal({ listing, onClose }: { listing: Listing; onClose: () => void }) {
  const [form, setForm] = useState<EmailPayload>({
    smtp_host: "smtp.gmail.com",
    smtp_port: 587,
    smtp_user: "",
    smtp_password: "",
    from: "",
    to: listing.email,
    subject: `Housing Inquiry – ${listing.title}`,
    body: `Hello,\n\nI am interested in a unit at ${listing.title}${listing.address ? ` (${listing.address})` : ""}.\nCould you please share availability and pricing?\n\nThank you.`,
  });
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null);

  const update = (k: keyof EmailPayload, v: string | number) =>
    setForm((p) => ({ ...p, [k]: v }));

  const handleSend = async () => {
    setSending(true);
    setResult(null);
    try {
      const res = await fetch(`${API_BASE}/api/email`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      setResult(await res.json());
    } catch {
      setResult({ ok: false, message: "Network error — is HUDdl.py running?" });
    } finally {
      setSending(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <div>
            <h2 className="text-lg font-semibold text-slate-800">Send Inquiry</h2>
            <p className="text-xs text-slate-400 mt-0.5 truncate max-w-xs">{listing.title}</p>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-700 text-xl" aria-label="Close">✕</button>
        </div>

        <div className="px-6 py-4 space-y-3">
          <details>
            <summary className="cursor-pointer text-xs font-semibold text-slate-400 uppercase tracking-wide select-none">
              SMTP Settings ▸
            </summary>
            <div className="mt-2 space-y-2">
              {[
                { label: "SMTP Host", key: "smtp_host", type: "text" },
                { label: "SMTP Port", key: "smtp_port", type: "number" },
                { label: "Your Email", key: "smtp_user", type: "email", ph: "you@gmail.com" },
                { label: "App Password", key: "smtp_password", type: "password", ph: "Gmail App Password" },
              ].map(({ label, key, type, ph }) => (
                <Field key={key} label={label}>
                  <input
                    type={type}
                    value={(form as any)[key]}
                    onChange={(e) => update(key as keyof EmailPayload, type === "number" ? Number(e.target.value) : e.target.value)}
                    placeholder={ph}
                    className={iCls}
                  />
                </Field>
              ))}
            </div>
          </details>

          <Field label="From">
            <input type="email" value={form.from} onChange={(e) => update("from", e.target.value)} placeholder="your@email.com" className={iCls} />
          </Field>
          <Field label="To">
            <input type="email" value={form.to} onChange={(e) => update("to", e.target.value)} className={iCls} />
          </Field>
          <Field label="Subject">
            <input value={form.subject} onChange={(e) => update("subject", e.target.value)} className={iCls} />
          </Field>
          <Field label="Message">
            <textarea rows={5} value={form.body} onChange={(e) => update("body", e.target.value)} className={`${iCls} resize-none`} />
          </Field>
        </div>

        {result && (
          <div className={`mx-6 mb-2 rounded-lg px-4 py-2 text-sm border ${result.ok ? "bg-emerald-50 text-emerald-700 border-emerald-200" : "bg-red-50 text-red-700 border-red-200"}`}>
            {result.ok ? "✓ " : "✗ "}{result.message}
          </div>
        )}

        <div className="flex justify-end gap-3 px-6 py-4 border-t border-slate-100">
          <button onClick={onClose} className={btnSec}>Cancel</button>
          <button onClick={handleSend} disabled={sending || !form.to || !form.from} className={btnPri}>
            {sending ? "Sending…" : "Send Email"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── ListingCard ──────────────────────────────────────────────────────────────
function ListingCard({ listing, onEmail }: { listing: Listing; onEmail: (l: Listing) => void }) {
  const [callStatus, setCallStatus] = useState<string | null>(null);
  const isHUD = listing.source === "hud";
  const isError = listing.status !== "ok" && !isHUD;

  const handleVoIP = async () => {
    if (!listing.phone) return;
    try {
      const res = await fetch(`${API_BASE}/api/voip?phone=${encodeURIComponent(listing.phone)}`);
      const data = await res.json();
      if (data.ok && data.tel_uri) {
        window.location.href = data.tel_uri;
        setCallStatus("Dialing…");
      } else {
        setCallStatus(data.message || "Failed");
      }
    } catch {
      window.location.href = `tel:${listing.phone.replace(/\D/g, "")}`;
      setCallStatus("Dialing…");
    }
    setTimeout(() => setCallStatus(null), 3000);
  };

  const domain = listing.url
    ? new URL(listing.url.startsWith("http") ? listing.url : `https://${listing.url}`).hostname.replace(/^www\./, "")
    : null;

  const layerColor = listing.hud_layer
    ? HUD_LAYER_COLORS[listing.hud_layer] ?? "bg-slate-100 text-slate-600"
    : "";

  return (
    <article className={`bg-white rounded-2xl border transition-all duration-200 hover:shadow-lg hover:-translate-y-0.5 ${isError ? "opacity-60 border-slate-200" : "border-slate-200 shadow-sm"}`}>
      {/* Top bar */}
      <div className="flex items-start justify-between px-5 pt-4 pb-1 gap-2">
        <div className="flex flex-wrap gap-1.5">
          {/* Source badge */}
          <span className={`text-[10px] font-semibold rounded-full px-2 py-0.5 ${isHUD ? "bg-blue-600 text-white" : "bg-slate-100 text-slate-500"}`}>
            {isHUD ? "HUD" : "Web"}
          </span>
          {/* HUD layer badge */}
          {listing.hud_layer && (
            <span className={`text-[10px] font-medium rounded-full px-2 py-0.5 ${layerColor}`}>
              {listing.hud_layer}
            </span>
          )}
          {isError && (
            <span className="text-[10px] bg-amber-100 text-amber-700 rounded-full px-2 py-0.5 font-medium">
              Unavailable
            </span>
          )}
        </div>
        {listing.price_range && (
          <span className="shrink-0 text-xs bg-emerald-50 text-emerald-700 font-semibold rounded-full px-2 py-0.5">
            {listing.price_range}
          </span>
        )}
      </div>

      {/* Title + address */}
      <div className="px-5 pb-1">
        <h3 className="text-sm font-semibold text-slate-800 leading-snug line-clamp-2">
          {listing.title || domain || "Unknown Property"}
        </h3>
        {listing.address && (
          <p className="text-xs text-slate-400 mt-0.5 flex items-center gap-1 line-clamp-1">
            📍 {listing.address}
          </p>
        )}
      </div>

      {/* Metadata chips */}
      <div className="px-5 pt-1.5 flex flex-wrap gap-1.5">
        {listing.bedrooms.map((b) => (
          <span key={b} className="text-[11px] bg-indigo-50 text-indigo-600 rounded-md px-2 py-0.5 font-medium">{b}</span>
        ))}
        {listing.units && (
          <span className="text-[11px] bg-slate-100 text-slate-600 rounded-md px-2 py-0.5">{listing.units} units</span>
        )}
        {listing.hud_program && !listing.hud_program.includes(listing.hud_layer) && (
          <span className="text-[11px] bg-violet-50 text-violet-700 rounded-md px-2 py-0.5">{listing.hud_program}</span>
        )}
      </div>

      {/* Description */}
      {listing.description && (
        <p className="px-5 pt-2 text-xs text-slate-400 line-clamp-2 leading-relaxed">
          {listing.description}
        </p>
      )}

      {/* Actions */}
      <div className="px-5 py-3 mt-1 flex items-center gap-2 border-t border-slate-100">
        <button
          onClick={handleVoIP}
          disabled={!listing.phone}
          title={listing.phone || "No phone found"}
          className={`flex items-center gap-1 text-xs font-medium px-3 py-1.5 rounded-lg transition-all ${listing.phone ? "bg-sky-500 hover:bg-sky-600 text-white shadow-sm" : "bg-slate-100 text-slate-400 cursor-not-allowed"}`}
        >
          📞 {callStatus ?? (listing.phone ? "Call" : "No Phone")}
        </button>

        <button
          onClick={() => onEmail(listing)}
          disabled={!listing.email}
          title={listing.email || "No email found"}
          className={`flex items-center gap-1 text-xs font-medium px-3 py-1.5 rounded-lg transition-all ${listing.email ? "bg-indigo-500 hover:bg-indigo-600 text-white shadow-sm" : "bg-slate-100 text-slate-400 cursor-not-allowed"}`}
        >
          ✉ {listing.email ? "Email" : "No Email"}
        </button>

        {domain && (
          <a
            href={listing.url}
            target="_blank"
            rel="noopener noreferrer"
            className="ml-auto text-xs text-slate-300 hover:text-indigo-400 transition-colors truncate max-w-[100px]"
          >
            {domain} →
          </a>
        )}
      </div>
    </article>
  );
}

// ─── Helpers ──────────────────────────────────────────────────────────────────
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <label className="text-xs font-medium text-slate-500">{label}</label>
      {children}
    </div>
  );
}

const iCls = "w-full rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-300 transition";
const btnPri = "px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold transition disabled:opacity-50 disabled:cursor-not-allowed";
const btnSec = "px-4 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-700 text-sm font-semibold transition";

// ─── SearchingState ───────────────────────────────────────────────────────────
const SEARCH_PHRASES = [
  "Scanning available listings…",
  "Checking rental vacancies…",
  "Searching affordable housing programs…",
  "Looking up Section 8 properties…",
  "Finding LIHTC developments…",
  "Reviewing public housing availability…",
  "Locating HUD-assisted properties…",
  "Browsing Bay Area apartments…",
  "Discovering housing opportunities…",
  "Matching properties to your search…",
  "Connecting to housing databases…",
  "Pulling the latest listings…",
];

function SearchingState() {
  const [phraseIdx, setPhraseIdx] = useState(0);
  const [dot, setDot]             = useState(0);

  useEffect(() => {
    const phraseTimer = setInterval(() =>
      setPhraseIdx((i) => (i + 1) % SEARCH_PHRASES.length), 2200);
    const dotTimer = setInterval(() =>
      setDot((d) => (d + 1) % 4), 500);
    return () => { clearInterval(phraseTimer); clearInterval(dotTimer); };
  }, []);

  return (
    <div className="flex flex-col items-center justify-center py-28 gap-4">
      {/* Animated logo */}
      <div className="relative w-20 h-20">
        <div className="absolute inset-0 rounded-full border-4 border-blue-200 animate-ping opacity-20" />
        <div className="w-20 h-20 drop-shadow-md animate-bounce">
          <HudLogo size={80} />
        </div>
      </div>

      {/* Rotating real-estate phrase */}
      <div className="text-center">
        <p className="text-sm font-medium text-slate-600 transition-all duration-500 min-h-[1.5rem]">
          {SEARCH_PHRASES[phraseIdx]}{"·".repeat(dot)}
        </p>
        <p className="text-xs text-slate-300 mt-1">
          Searching over 25 sites + HUD databases · takes ~30 seconds
        </p>
      </div>

      {/* Progress bar */}
      <div className="w-64 h-1.5 bg-slate-100 rounded-full overflow-hidden">
        <div className="h-full bg-blue-400 rounded-full animate-[progress_30s_linear_forwards]"
             style={{ animation: "progress 30s linear forwards" }} />
      </div>

      <style>{`
        @keyframes progress {
          from { width: 2%; }
          to   { width: 98%; }
        }
      `}</style>
    </div>
  );
}

// ─── Main App ─────────────────────────────────────────────────────────────────
export default function HUDdl() {
  const [allListings, setAllListings] = useState<Listing[]>([]);
  const [loading, setLoading]         = useState(false);
  const [crawled, setCrawled]         = useState(false);
  const [query, setQuery]             = useState("");
  const [tab, setTab]                 = useState<TabKey>("all");
  const [emailTarget, setEmailTarget] = useState<Listing | null>(null);
  const [error, setError]             = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const debouncedQuery = useDebounce(query);

  const fetchListings = useCallback(async (q: string, source: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `${API_BASE}/api/listings?q=${encodeURIComponent(q)}&source=${source}`
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: Listing[] = await res.json();
      setAllListings(data);
      setCrawled(true);
    } catch {
      setError("Could not reach HUDdl.py — make sure it's running on port 8787.");
    } finally {
      setLoading(false);
    }
  }, []);

  // Re-filter from cache when query / tab changes after first load
  useEffect(() => {
    if (crawled) {
      fetchListings(debouncedQuery, tab === "all" ? "all" : tab);
    }
  }, [debouncedQuery, tab, crawled, fetchListings]);

  const handleExport = async (fmt: "csv" | "json") => {
    const src = tab === "all" ? "all" : tab;
    const url = `${API_BASE}/api/export?format=${fmt}&source=${src}&q=${encodeURIComponent(query)}`;
    const a = document.createElement("a");
    a.href = url;
    a.download = `huddl_export.${fmt}`;
    a.click();
  };

  // Stats
  const webListings = allListings.filter((l) => l.source === "web");
  const hudListings = allListings.filter((l) => l.source === "hud");
  const withPhone   = allListings.filter((l) => l.phone).length;
  const withEmail   = allListings.filter((l) => l.email).length;

  const TABS: { key: TabKey; label: string; count: number }[] = [
    { key: "all", label: "All Sources", count: allListings.length },
    { key: "web", label: "Web Sites",   count: webListings.length },
    { key: "hud", label: "HUD Data",    count: hudListings.length },
  ];

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50/20 to-indigo-50 font-sans">

      {/* ── Header ──────────────────────────────────────────────────────── */}
      <header className="sticky top-0 z-40 bg-white/90 backdrop-blur border-b border-slate-200/70 shadow-sm">
        <div className="max-w-6xl mx-auto px-4 py-3 flex flex-col sm:flex-row items-center gap-3">

          {/* Logo */}
          <div className="flex items-center gap-2 shrink-0">
            <div className="w-9 h-9">
              <HudLogo size={36} />
            </div>
            <div>
              <h1 className="text-sm font-bold text-slate-800 leading-none">HUDdl</h1>
              <p className="text-[10px] text-slate-400">Alameda County Housing Data</p>
            </div>
          </div>

          {/* Search */}
          <div className="flex-1 relative max-w-xl w-full">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 text-sm pointer-events-none">🔍</span>
            <input
              ref={inputRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search by city, zip, bedrooms, program, address…"
              className="w-full pl-9 pr-9 py-2 rounded-xl border border-slate-200 bg-white text-sm text-slate-800 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-300 transition"
              aria-label="Search listings"
            />
            {query && (
              <button
                onClick={() => { setQuery(""); inputRef.current?.focus(); }}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-700"
              >
                ✕
              </button>
            )}
          </div>

          {/* Actions */}
          <div className="flex items-center gap-2 shrink-0">
            {crawled && (
              <>
                <button onClick={() => handleExport("csv")} className="text-xs px-3 py-2 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-600 transition">
                  ↓ CSV
                </button>
                <button onClick={() => handleExport("json")} className="text-xs px-3 py-2 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-600 transition">
                  ↓ JSON
                </button>
              </>
            )}
            <button
              onClick={() => fetchListings(query, tab === "all" ? "all" : tab)}
              disabled={loading}
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold transition shadow disabled:opacity-60 disabled:cursor-wait"
            >
              {loading
                ? <><span className="animate-spin">⟳</span> Searching…</>
                : <>⟳ {crawled ? "Search Again" : "Start Search"}</>
              }
            </button>
          </div>
        </div>

        {/* Tabs */}
        {crawled && (
          <div className="max-w-6xl mx-auto px-4 pb-0 flex gap-1 border-t border-slate-100">
            {TABS.map(({ key, label, count }) => (
              <button
                key={key}
                onClick={() => setTab(key)}
                className={`px-4 py-2 text-xs font-medium transition border-b-2 ${
                  tab === key
                    ? "border-blue-600 text-blue-600"
                    : "border-transparent text-slate-500 hover:text-slate-700"
                }`}
              >
                {label}
                <span className={`ml-1.5 text-[10px] rounded-full px-1.5 py-0.5 ${tab === key ? "bg-blue-100 text-blue-600" : "bg-slate-100 text-slate-500"}`}>
                  {count}
                </span>
              </button>
            ))}
          </div>
        )}
      </header>

      {/* ── Main ────────────────────────────────────────────────────────── */}
      <main className="max-w-6xl mx-auto px-4 py-6">

        {/* Error */}
        {error && (
          <div className="mb-4 rounded-xl bg-red-50 border border-red-200 text-red-700 px-5 py-3 text-sm flex gap-2">
            <span>⚠</span> {error}
          </div>
        )}

        {/* Stats bar */}
        {crawled && !loading && (
          <div className="flex flex-wrap gap-3 mb-5">
            {[
              { label: "Total found",  value: allListings.length,   color: "text-blue-600" },
              { label: "Web sites",    value: webListings.length,   color: "text-indigo-600" },
              { label: "HUD records",  value: hudListings.length,   color: "text-blue-700" },
              { label: "Have phone",   value: withPhone,            color: "text-sky-600" },
              { label: "Have email",   value: withEmail,            color: "text-violet-600" },
            ].map(({ label, value, color }) => (
              <div key={label} className="bg-white rounded-xl border border-slate-200 px-4 py-2 shadow-sm text-center min-w-[90px]">
                <p className={`text-xl font-bold ${color}`}>{value}</p>
                <p className="text-[10px] text-slate-400">{label}</p>
              </div>
            ))}
          </div>
        )}

        {/* HUD layer legend (shown on HUD tab) */}
        {crawled && tab === "hud" && !loading && (
          <div className="mb-4 flex flex-wrap gap-2">
            {Object.entries(HUD_LAYER_COLORS).map(([layer, cls]) => (
              <span key={layer} className={`text-[11px] font-medium rounded-full px-2.5 py-1 ${cls}`}>
                {layer}
              </span>
            ))}
          </div>
        )}

        {/* Empty / loading state */}
        {!crawled && !loading && (
          <div className="flex flex-col items-center justify-center py-28 text-center">
            <div className="w-20 h-20 mb-4 drop-shadow-lg">
              <HudLogo size={80} />
            </div>
            <p className="text-lg font-semibold text-slate-700">HUDdl is ready</p>
            <p className="text-sm text-slate-400 mt-1 max-w-sm">
              Crawls over 25 Bay Area housing sites <em>and</em> HUD's official ArcGIS database — all in one search.
            </p>
            <p className="text-xs text-slate-300 mt-4">Press <strong>Start Search</strong> to begin · takes ~30 seconds</p>
          </div>
        )}

        {loading && <SearchingState />}

        {/* Results grid */}
        {!loading && crawled && (
          allListings.length === 0 ? (
            <p className="text-center text-slate-400 py-20">
              No results for <em>"{query}"</em> in {tab === "all" ? "any source" : tab === "web" ? "web sites" : "HUD data"}.
            </p>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {allListings.map((l, i) => (
                <ListingCard key={`${l.source}-${l.url || l.title}-${i}`} listing={l} onEmail={setEmailTarget} />
              ))}
            </div>
          )
        )}
      </main>

      {/* Email modal */}
      {emailTarget && (
        <EmailModal listing={emailTarget} onClose={() => setEmailTarget(null)} />
      )}
    </div>
  );
}
