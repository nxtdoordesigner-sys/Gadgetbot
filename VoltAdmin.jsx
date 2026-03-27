import { useState, useRef, useEffect } from "react";

// ── Supabase project is fixed — only anon key needed ──
const SUPA_URL = "https://qgubvwirrspidiuleram.supabase.co";

const CATEGORIES = ["Smartphones","Laptops","Tablets","Accessories","Audio","Wearables","Gaming","Other"];
const CONDITIONS  = ["Brand New","Nigeria Used","UK Used","Refurbished"];

const defaultForm = {
  title:"", author:"", category:"Smartphones", price:"",
  list_price:"", base_price:"", condition:"Nigeria Used",
  stock_qty:1, negotiable:true, in_stock:true, specs:"", image_url:"",
};

// ── Palette ──────────────────────────────────────────────
const C = {
  bg:     "#F7F8FA",
  bg2:    "#FFFFFF",
  bg3:    "#F0F2F5",
  bg4:    "#E8EBEF",
  border: "#E2E6EC",
  text:   "#111827",
  text2:  "#6B7280",
  text3:  "#9CA3AF",
  accent: "#16A34A",        // green — VoltStore brand
  accentL:"#DCFCE7",
  accentD:"#15803D",
  red:    "#DC2626",
  redL:   "#FEF2F2",
  amber:  "#D97706",
  amberL: "#FFFBEB",
  blue:   "#2563EB",
  blueL:  "#EFF6FF",
};

const G = {
  root: { minHeight:"100vh", background:C.bg, fontFamily:"'Inter',system-ui,sans-serif", color:C.text },
  layout: { display:"flex", height:"100vh", overflow:"hidden" },

  sidebar: {
    width:220, background:C.bg2,
    borderRight:`1px solid ${C.border}`,
    display:"flex", flexDirection:"column",
    padding:"0", position:"sticky", top:0, height:"100vh", flexShrink:0,
  },
  logoWrap: {
    padding:"20px 20px 16px",
    borderBottom:`1px solid ${C.border}`,
    display:"flex", alignItems:"center", gap:10,
  },
  logoBolt: {
    width:32, height:32, background:C.accent, borderRadius:8,
    display:"flex", alignItems:"center", justifyContent:"center", flexShrink:0,
  },
  logoText: { fontWeight:700, fontSize:15, color:C.text, letterSpacing:"-0.01em" },
  logoSub:  { fontSize:10, color:C.text3, marginTop:1 },

  navSection: { padding:"16px 12px 8px", fontSize:10, fontWeight:600,
    color:C.text3, textTransform:"uppercase", letterSpacing:"0.08em" },
  navItem: { display:"flex", alignItems:"center", gap:9, padding:"9px 12px",
    marginInline:8, borderRadius:8, fontSize:13, cursor:"pointer",
    transition:"all 0.12s", color:C.text2, fontWeight:500 },

  main: { flex:1, display:"flex", flexDirection:"column", overflow:"hidden" },
  topbar: {
    padding:"14px 28px", borderBottom:`1px solid ${C.border}`,
    display:"flex", alignItems:"center", justifyContent:"space-between",
    background:C.bg2, flexShrink:0,
  },
  pageTitle: { fontWeight:700, fontSize:17, color:C.text, letterSpacing:"-0.01em" },
  pageSub:   { fontSize:12, color:C.text3, marginTop:2 },

  content: { padding:"24px 28px", flex:1, overflowY:"auto" },

  statGrid: { display:"grid", gridTemplateColumns:"repeat(4,1fr)", gap:14, marginBottom:24 },
  stat: { background:C.bg2, border:`1px solid ${C.border}`, borderRadius:12, padding:"16px 20px" },
  statLabel: { fontSize:11, color:C.text3, marginBottom:6 },
  statVal: { fontSize:26, fontWeight:700, color:C.text, letterSpacing:"-0.02em" },
  statSub: { fontSize:11, color:C.text3, marginTop:4 },

  toolbar: { display:"flex", gap:10, marginBottom:18, alignItems:"center" },
  searchWrap: { flex:1, position:"relative" },
  searchIcon: { position:"absolute", left:11, top:"50%", transform:"translateY(-50%)", color:C.text3 },

  grid: { display:"grid", gridTemplateColumns:"repeat(auto-fill,minmax(210px,1fr))", gap:14 },

  card: {
    background:C.bg2, border:`1px solid ${C.border}`, borderRadius:14,
    overflow:"hidden", display:"flex", flexDirection:"column",
    transition:"all 0.15s", boxShadow:"0 1px 3px rgba(0,0,0,0.04)",
  },
  cardImg: { height:160, background:C.bg3, display:"flex", alignItems:"center",
    justifyContent:"center", position:"relative", overflow:"hidden" },
  cardBadgesTR: { position:"absolute", top:9, right:9, display:"flex", flexDirection:"column", gap:4, alignItems:"flex-end" },
  cardBadgesTL: { position:"absolute", top:9, left:9 },
  cardBody: { padding:"13px 15px", flex:1, display:"flex", flexDirection:"column", gap:6 },
  cardTitle: { fontSize:13, fontWeight:600, color:C.text, lineHeight:1.4 },
  cardMeta: { display:"flex", gap:4, flexWrap:"wrap" },
  cardSpecs: { fontSize:11, color:C.text3, lineHeight:1.5 },
  cardPrice: { fontSize:16, fontWeight:700, color:C.accent, marginTop:"auto" },
  cardFloor: { fontSize:10, color:C.text3, marginTop:2 },
  cardActions: { display:"flex", borderTop:`1px solid ${C.border}` },

  formWrap: { maxWidth:580, background:C.bg2, border:`1px solid ${C.border}`,
    borderRadius:16, overflow:"hidden", boxShadow:"0 1px 4px rgba(0,0,0,0.05)" },
  formHeader: { padding:"18px 24px", borderBottom:`1px solid ${C.border}`,
    display:"flex", alignItems:"center", gap:12 },
  formHeaderIcon: { width:36, height:36, background:C.accentL, borderRadius:9,
    display:"flex", alignItems:"center", justifyContent:"center" },
  formBody: { padding:"24px", display:"flex", flexDirection:"column", gap:20 },
  sectionLabel: { fontSize:10, textTransform:"uppercase", letterSpacing:"0.1em",
    color:C.text3, fontWeight:600, paddingBottom:8,
    borderBottom:`1px solid ${C.border}`, marginBottom:4 },
  formFooter: { padding:"14px 24px", borderTop:`1px solid ${C.border}`, display:"flex", gap:9 },

  setupWrap: { minHeight:"100vh", display:"flex", alignItems:"center",
    justifyContent:"center", background:C.bg },
  setupCard: { background:C.bg2, border:`1px solid ${C.border}`, borderRadius:20,
    padding:36, width:"100%", maxWidth:400,
    boxShadow:"0 4px 16px rgba(0,0,0,0.06)" },

  empty: { textAlign:"center", padding:"60px 20px" },
  toast: { position:"fixed", bottom:22, right:22, zIndex:9999,
    padding:"12px 18px", borderRadius:10, fontSize:13, fontWeight:500,
    boxShadow:"0 4px 16px rgba(0,0,0,0.12)" },
};

const styles = `
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: ${C.bg}; }
  input, select, textarea {
    background: ${C.bg3}; border: 1.5px solid ${C.border};
    border-radius: 8px; padding: 9px 12px; font-size: 13px;
    color: ${C.text}; outline: none; font-family: inherit;
    transition: border 0.15s; width: 100%;
  }
  input::placeholder, textarea::placeholder { color: ${C.text3}; }
  input:focus, select:focus, textarea:focus { border-color: ${C.accent}; background: #fff; }
  select { appearance: none; cursor: pointer; }
  textarea { resize: vertical; min-height: 72px; }
  button { font-family: inherit; cursor: pointer; }
  .vs-card:hover { border-color: ${C.accent}33 !important; transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.08) !important; }
  .vs-ca:hover { background: ${C.bg3} !important; color: ${C.text} !important; }
  .vs-ca.danger:hover { color: ${C.red} !important; background: ${C.redL} !important; }
  .vs-nav-item:hover { background: ${C.bg3} !important; color: ${C.text} !important; }
  .vs-nav-item.active { background: ${C.accentL} !important; color: ${C.accent} !important; font-weight: 600 !important; }
  @keyframes slideUp { from { opacity:0; transform:translateY(8px); } to { opacity:1; transform:translateY(0); } }
  ::-webkit-scrollbar { width: 5px; } ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: ${C.border}; border-radius: 99px; }
`;

// ── Tiny components ──────────────────────────────────────

const Badge = ({ children, color="gray" }) => {
  const map = {
    green: { bg:C.accentL, c:C.accentD, b:`${C.accent}40` },
    red:   { bg:C.redL,    c:C.red,     b:`${C.red}30` },
    amber: { bg:C.amberL,  c:C.amber,   b:`${C.amber}40` },
    blue:  { bg:C.blueL,   c:C.blue,    b:`${C.blue}30` },
    gray:  { bg:C.bg3,     c:C.text2,   b:C.border },
  }[color] || { bg:C.bg3, c:C.text3, b:C.border };
  return (
    <span style={{ fontSize:10, fontWeight:600, padding:"3px 8px", borderRadius:20,
      background:map.bg, color:map.c, border:`1px solid ${map.b}` }}>
      {children}
    </span>
  );
};

const Btn = ({ children, variant="ghost", onClick, disabled, style={} }) => {
  const base = { display:"inline-flex", alignItems:"center", gap:6, padding:"8px 16px",
    borderRadius:8, fontSize:13, fontWeight:500, transition:"all 0.15s", border:"none" };
  const v = {
    primary: { background:C.accent, color:"#fff" },
    ghost:   { background:C.bg3, color:C.text2, border:`1px solid ${C.border}` },
    danger:  { background:C.redL, color:C.red, border:`1px solid ${C.red}30` },
  }[variant];
  return (
    <button onClick={onClick} disabled={disabled}
      style={{ ...base, ...v, opacity:disabled?.4:1, ...style }}
      onMouseEnter={e => { if (!disabled && variant==="primary") e.currentTarget.style.background=C.accentD; }}
      onMouseLeave={e => { if (!disabled && variant==="primary") e.currentTarget.style.background=C.accent; }}>
      {children}
    </button>
  );
};

const Icon = ({ n, s=15 }) => {
  const icons = {
    bolt:    <svg width={s} height={s} viewBox="0 0 16 16" fill="none"><path d="M9 1L2 9h6l-1 6 7-8H8l1-6z" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round"/></svg>,
    grid:    <svg width={s} height={s} viewBox="0 0 16 16" fill="none"><rect x="1" y="1" width="6" height="6" rx="1.5" stroke="currentColor" strokeWidth="1.2"/><rect x="9" y="1" width="6" height="6" rx="1.5" stroke="currentColor" strokeWidth="1.2"/><rect x="1" y="9" width="6" height="6" rx="1.5" stroke="currentColor" strokeWidth="1.2"/><rect x="9" y="9" width="6" height="6" rx="1.5" stroke="currentColor" strokeWidth="1.2"/></svg>,
    plus:    <svg width={s} height={s} viewBox="0 0 16 16" fill="none"><path d="M8 2v12M2 8h12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>,
    search:  <svg width={s} height={s} viewBox="0 0 16 16" fill="none"><circle cx="6.5" cy="6.5" r="5" stroke="currentColor" strokeWidth="1.2"/><path d="M10.5 10.5l3.5 3.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/></svg>,
    refresh: <svg width={s} height={s} viewBox="0 0 16 16" fill="none"><path d="M13.5 8a5.5 5.5 0 11-1.5-3.77" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/><path d="M10 4.5h3V1.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/></svg>,
    back:    <svg width={s} height={s} viewBox="0 0 16 16" fill="none"><path d="M10 12L6 8l4-4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/></svg>,
    photo:   <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.3"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>,
    cog:     <svg width={s} height={s} viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="2.5" stroke="currentColor" strokeWidth="1.2"/><path d="M8 1v2M8 13v2M1 8h2M13 8h2M3.05 3.05l1.41 1.41M11.54 11.54l1.41 1.41M3.05 12.95l1.41-1.41M11.54 4.46l1.41-1.41" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/></svg>,
    check:   <svg width={s} height={s} viewBox="0 0 16 16" fill="none"><path d="M2 8l4 4 8-8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>,
    tag:     <svg width={s} height={s} viewBox="0 0 16 16" fill="none"><path d="M9.5 1.5h4v4L7 12a1.5 1.5 0 01-2.12 0l-2.88-2.88A1.5 1.5 0 012 8l6.5-6.5z" stroke="currentColor" strokeWidth="1.2"/><circle cx="11.5" cy="4.5" r="0.8" fill="currentColor"/></svg>,
    eye:     <svg width={s} height={s} viewBox="0 0 16 16" fill="none"><path d="M1 8s2.5-5 7-5 7 5 7 5-2.5 5-7 5-7-5-7-5z" stroke="currentColor" strokeWidth="1.2"/><circle cx="8" cy="8" r="2" stroke="currentColor" strokeWidth="1.2"/></svg>,
    info:    <svg width={s} height={s} viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeWidth="1.2"/><path d="M8 7v4M8 5.5v.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/></svg>,
  };
  return icons[n] || null;
};

const Toggle = ({ checked, onChange }) => (
  <div onClick={() => onChange(!checked)}
    style={{ width:40, height:22, borderRadius:22, cursor:"pointer", position:"relative",
      background: checked ? C.accent : C.bg4,
      border: `1.5px solid ${checked ? C.accent : C.border}`,
      transition:"all 0.2s", flexShrink:0,
    }}>
    <div style={{
      position:"absolute", top:3, left: checked ? 19 : 3,
      width:14, height:14, borderRadius:"50%",
      background: checked ? "#fff" : C.text3,
      transition:"all 0.2s", boxShadow:"0 1px 3px rgba(0,0,0,0.2)",
    }} />
  </div>
);

const Field = ({ label, hint, required, children }) => (
  <div style={{ display:"flex", flexDirection:"column", gap:5 }}>
    <label style={{ fontSize:12, fontWeight:500, color:C.text2 }}>
      {label}{required && <span style={{ color:C.red, marginLeft:2 }}>*</span>}
    </label>
    {children}
    {hint && <div style={{ fontSize:11, color:C.text3 }}>{hint}</div>}
  </div>
);

// ── Product Card ─────────────────────────────────────────

const ProductCard = ({ product, onEdit, onDelete, onToggleStock }) => (
  <div className="vs-card" style={G.card}>
    <div style={G.cardImg}>
      {product.image_url
        ? <img src={product.image_url} alt={product.title}
            style={{ width:"100%", height:"100%", objectFit:"cover" }} />
        : <div style={{ color:C.text3, opacity:0.4 }}><Icon n="photo" s={36} /></div>
      }
      <div style={G.cardBadgesTR}>
        <Badge color={product.in_stock ? "green" : "red"}>
          {product.in_stock ? "in stock" : "out of stock"}
        </Badge>
      </div>
      {product.negotiable && (
        <div style={G.cardBadgesTL}><Badge color="amber">negotiable</Badge></div>
      )}
    </div>
    <div style={G.cardBody}>
      <div style={G.cardTitle}>{product.title}</div>
      <div style={G.cardMeta}>
        {product.category && <Badge color="blue">{product.category}</Badge>}
        {product.condition && <Badge color="gray">{product.condition}</Badge>}
        {product.stock_qty > 0 && <Badge color="gray">{product.stock_qty} units</Badge>}
      </div>
      {product.specs && <div style={G.cardSpecs}>{product.specs}</div>}
      <div style={{ marginTop:"auto", paddingTop:6 }}>
        <div style={G.cardPrice}>₦{Number(product.price).toLocaleString()}</div>
        {product.negotiable && product.base_price && (
          <div style={G.cardFloor}>floor ₦{Number(product.base_price).toLocaleString()}</div>
        )}
      </div>
    </div>
    <div style={G.cardActions}>
      {[
        { label:"edit",   fn:() => onEdit(product) },
        { label: product.in_stock ? "out of stock" : "restock", fn:() => onToggleStock(product) },
        { label:"delete", fn:() => onDelete(product), danger:true },
      ].map((a, i) => (
        <button key={i}
          className={`vs-ca${a.danger?" danger":""}`}
          onClick={a.fn}
          style={{ flex:1, padding:"9px 4px", fontSize:11, fontWeight:500,
            background:"transparent", border:"none",
            color: a.danger ? C.text3 : C.text2,
            borderLeft: i > 0 ? `1px solid ${C.border}` : "none",
            transition:"all 0.13s", textAlign:"center" }}>
          {a.label}
        </button>
      ))}
    </div>
  </div>
);

// ── Main App ─────────────────────────────────────────────

export default function VoltAdmin() {
  const [products, setProducts]   = useState([]);
  const [loading, setLoading]     = useState(false);
  const [fetched, setFetched]     = useState(false);
  const [view, setView]           = useState("grid");
  const [form, setForm]           = useState(defaultForm);
  const [editId, setEditId]       = useState(null);
  const [toast, setToast]         = useState(null);
  const [search, setSearch]       = useState("");
  const [cat, setCat]             = useState("all");
  const [saving, setSaving]       = useState(false);
  const [anonKey, setAnonKey]     = useState(() => localStorage.getItem("vs_key") || "");
  const [setup, setSetup]         = useState(() => !localStorage.getItem("vs_key"));
  const [tempKey, setTempKey]     = useState("");
  const tRef = useRef(null);

  const showToast = (msg, type="success") => {
    setToast({ msg, type });
    clearTimeout(tRef.current);
    tRef.current = setTimeout(() => setToast(null), 3200);
  };

  const api = async (path, method="GET", body=null) => {
    const r = await fetch(`${SUPA_URL}/rest/v1/${path}`, {
      method,
      headers: {
        "Content-Type": "application/json",
        "apikey": anonKey,
        "Authorization": `Bearer ${anonKey}`,
        ...(method === "POST" ? { "Prefer": "return=representation" } : {}),
        ...(method === "PATCH" ? { "Prefer": "return=representation" } : {}),
      },
      ...(body ? { body: JSON.stringify(body) } : {}),
    });
    if (!r.ok) throw new Error(await r.text());
    const txt = await r.text();
    return txt ? JSON.parse(txt) : null;
  };

  const load = async (key) => {
    setLoading(true);
    try {
      const data = await api("books?select=*&order=id.desc");
      setProducts(data || []);
      setFetched(true);
    } catch (e) {
      showToast("Connection failed: " + e.message, "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!setup && anonKey) load();
  }, []);

  const connect = async () => {
    if (!tempKey.trim()) return;
    const k = tempKey.trim();
    setAnonKey(k);
    localStorage.setItem("vs_key", k);
    setSetup(false);
    // load with fresh key
    setLoading(true);
    try {
      const r = await fetch(`${SUPA_URL}/rest/v1/books?select=*&order=id.desc&limit=1`, {
        headers: { "apikey": k, "Authorization": `Bearer ${k}` },
      });
      if (!r.ok) throw new Error("Invalid key");
      const data = await fetch(`${SUPA_URL}/rest/v1/books?select=*&order=id.desc`, {
        headers: { "apikey": k, "Authorization": `Bearer ${k}` },
      }).then(r2 => r2.json());
      setProducts(data || []);
      setFetched(true);
      showToast("Connected! " + (data?.length || 0) + " products loaded.");
    } catch (e) {
      showToast("Connection failed: " + e.message, "error");
      setSetup(true);
    } finally {
      setLoading(false);
    }
  };

  const save = async () => {
    if (!form.title.trim() || !form.price) { showToast("Title and price are required", "error"); return; }
    setSaving(true);
    try {
      const payload = {
        title: form.title.trim(),
        author: form.author.trim(),
        category: form.category,
        price: +form.price,
        list_price: form.list_price ? +form.list_price : +form.price,
        base_price: form.base_price ? +form.base_price : (+form.price * 0.88),
        condition: form.condition,
        stock_qty: +form.stock_qty || 1,
        negotiable: form.negotiable,
        in_stock: form.in_stock,
        specs: form.specs.trim() || null,
        image_url: form.image_url.trim() || null,
      };

      if (editId) {
        await api(`books?id=eq.${editId}`, "PATCH", payload);
        setProducts(ps => ps.map(p => p.id === editId ? { ...p, ...payload } : p));
        showToast("Product updated ✓");
      } else {
        const res = await api("books", "POST", payload);
        if (res?.[0]) setProducts(ps => [res[0], ...ps]);
        showToast("Product added ✓");
      }
      setForm(defaultForm);
      setEditId(null);
      setView("grid");
    } catch (e) {
      showToast("Save failed: " + e.message, "error");
    } finally {
      setSaving(false);
    }
  };

  const del = async (product) => {
    if (!confirm(`Delete "${product.title}"? This cannot be undone.`)) return;
    try {
      await api(`books?id=eq.${product.id}`, "DELETE");
      setProducts(ps => ps.filter(p => p.id !== product.id));
      showToast("Product deleted");
    } catch { showToast("Delete failed", "error"); }
  };

  const toggleStock = async (product) => {
    const nv = !product.in_stock;
    try {
      await api(`books?id=eq.${product.id}`, "PATCH", { in_stock: nv, stock_qty: nv ? 1 : 0 });
      setProducts(ps => ps.map(p => p.id === product.id
        ? { ...p, in_stock: nv, stock_qty: nv ? 1 : 0 } : p));
      showToast(nv ? "Back in stock ✓" : "Marked out of stock");
    } catch { showToast("Update failed", "error"); }
  };

  const openEdit = (product) => {
    setForm({
      title: product.title || "", author: product.author || "",
      category: product.category || "Smartphones", price: product.price || "",
      list_price: product.list_price || "", base_price: product.base_price || "",
      condition: product.condition || "Nigeria Used", stock_qty: product.stock_qty || 1,
      negotiable: product.negotiable ?? true, in_stock: product.in_stock ?? true,
      specs: product.specs || "", image_url: product.image_url || "",
    });
    setEditId(product.id);
    setView("form");
  };

  const f = k => val => setForm(p => ({ ...p, [k]: val }));
  const fe = k => e => setForm(p => ({ ...p, [k]: e.target.value }));

  const filtered = products.filter(p => {
    const q = search.toLowerCase();
    return (!q || p.title?.toLowerCase().includes(q) || p.author?.toLowerCase().includes(q)
      || p.category?.toLowerCase().includes(q))
      && (cat === "all" || p.category === cat);
  });

  const inStock       = products.filter(p => p.in_stock).length;
  const negotiable    = products.filter(p => p.negotiable).length;
  const outStock      = products.length - inStock;

  // ── Setup screen ─────────────────────────────────────
  if (setup) return (
    <>
      <style>{styles}</style>
      <div style={G.setupWrap}>
        <div style={G.setupCard}>
          <div style={{ display:"flex", alignItems:"center", gap:10, marginBottom:6 }}>
            <div style={G.logoBolt}><Icon n="bolt" s={16} /></div>
            <div>
              <div style={{ fontWeight:700, fontSize:16, color:C.text }}>VoltStore Admin</div>
              <div style={{ fontSize:11, color:C.text3 }}>inventory dashboard</div>
            </div>
          </div>

          <div style={{ height:1, background:C.border, margin:"18px 0" }} />

          <div style={{ background:C.blueL, border:`1px solid ${C.blue}30`,
            borderRadius:8, padding:"10px 13px", marginBottom:18,
            display:"flex", gap:8, fontSize:12, color:C.blue }}>
            <Icon n="info" s={14} />
            <div>Connected to <strong>qgubvwirrspidiuleram.supabase.co</strong><br/>
            Enter your anon key to get started.</div>
          </div>

          <div style={{ display:"flex", flexDirection:"column", gap:14 }}>
            <Field label="Supabase Anon Key" required hint="Project Settings → API → anon public">
              <input type="password" value={tempKey}
                onChange={e => setTempKey(e.target.value)}
                onKeyDown={e => e.key==="Enter" && connect()}
                placeholder="eyJhbGciOiJIUzI1NiIs..." />
            </Field>
            <button onClick={connect}
              style={{ background:C.accent, color:"#fff", border:"none", borderRadius:9,
                padding:"11px", fontSize:13, fontWeight:600, cursor:"pointer",
                display:"flex", alignItems:"center", justifyContent:"center", gap:7,
                fontFamily:"inherit" }}>
              <Icon n="bolt" s={14} /> Connect &amp; load inventory
            </button>
          </div>

          <div style={{ marginTop:18, padding:"12px", background:C.bg3,
            borderRadius:8, fontSize:11, color:C.text3, lineHeight:1.6 }}>
            💡 <strong>Also manageable via bot:</strong> Send product details to your admin
            Telegram bot to add products conversationally. Both methods sync to the same database.
          </div>
        </div>
      </div>
    </>
  );

  // ── Main Dashboard ────────────────────────────────────
  return (
    <>
      <style>{styles}</style>
      <div style={G.root}>
        <div style={G.layout}>

          {/* Sidebar */}
          <div style={G.sidebar}>
            <div style={G.logoWrap}>
              <div style={G.logoBolt}><Icon n="bolt" s={15} /></div>
              <div>
                <div style={G.logoText}>VoltStore</div>
                <div style={G.logoSub}>admin panel</div>
              </div>
            </div>

            <div style={{ padding:"12px 8px", flex:1 }}>
              <div style={G.navSection}>Manage</div>
              {[
                { k:"grid", label:"Inventory", icon:"grid" },
                { k:"form", label:"Add Product", icon:"plus" },
              ].map(item => (
                <div key={item.k}
                  className={`vs-nav-item${view === item.k && !(item.k==="form" && editId) ? " active" : ""}`}
                  onClick={() => {
                    if (item.k === "form") { setForm(defaultForm); setEditId(null); }
                    setView(item.k);
                  }}
                  style={G.navItem}>
                  <Icon n={item.icon} s={14} />
                  {item.label}
                </div>
              ))}
            </div>

            <div style={{ padding:"12px 16px", borderTop:`1px solid ${C.border}` }}>
              <div style={{ fontSize:11, color:C.text3, marginBottom:6 }}>
                {products.length} products · {inStock} in stock
              </div>
              <button onClick={() => { setSetup(true); setTempKey(anonKey); }}
                style={{ width:"100%", background:C.bg3, border:`1px solid ${C.border}`,
                  borderRadius:7, padding:"7px 12px", fontSize:11, color:C.text2,
                  cursor:"pointer", display:"flex", alignItems:"center", gap:6,
                  fontFamily:"inherit", fontWeight:500 }}>
                <Icon n="cog" s={12} /> settings / reconnect
              </button>
            </div>
          </div>

          {/* Main */}
          <div style={G.main}>
            <div style={G.topbar}>
              <div>
                <div style={G.pageTitle}>
                  {view === "form"
                    ? (editId ? "Edit Product" : "Add New Product")
                    : "Inventory"}
                </div>
                <div style={G.pageSub}>
                  {view === "grid"
                    ? `${filtered.length} products showing · ${inStock} in stock · ${outStock} out of stock`
                    : editId
                      ? `Editing: ${form.title || "product #" + editId}`
                      : "Add a new product to your catalog"}
                </div>
              </div>
              <div style={{ display:"flex", gap:8 }}>
                {view === "grid" ? (
                  <>
                    <Btn variant="ghost" onClick={load} disabled={loading}>
                      <Icon n="refresh" s={13} />{loading ? "loading…" : "refresh"}
                    </Btn>
                    <Btn variant="primary" onClick={() => { setForm(defaultForm); setEditId(null); setView("form"); }}>
                      <Icon n="plus" s={13} />add product
                    </Btn>
                  </>
                ) : (
                  <Btn variant="ghost" onClick={() => { setView("grid"); setEditId(null); setForm(defaultForm); }}>
                    <Icon n="back" s={13} />back to inventory
                  </Btn>
                )}
              </div>
            </div>

            <div style={G.content}>

              {/* ── Grid view ── */}
              {view === "grid" && <>
                <div style={G.statGrid}>
                  {[
                    { label:"Total Products", val:products.length },
                    { label:"In Stock", val:inStock, accent:true },
                    { label:"Out of Stock", val:outStock, sub:"needs restocking" },
                    { label:"Negotiable", val:negotiable, sub:"flexible pricing" },
                  ].map((s, i) => (
                    <div key={i} style={G.stat}>
                      <div style={G.statLabel}>{s.label}</div>
                      <div style={{ ...G.statVal, color: s.accent ? C.accent : C.text }}>{s.val}</div>
                      {s.sub && <div style={G.statSub}>{s.sub}</div>}
                    </div>
                  ))}
                </div>

                <div style={G.toolbar}>
                  <div style={G.searchWrap}>
                    <span style={G.searchIcon}><Icon n="search" s={14} /></span>
                    <input value={search} onChange={e => setSearch(e.target.value)}
                      placeholder="search by name, brand or category…"
                      style={{ paddingLeft:36 }} />
                  </div>
                  <select value={cat} onChange={e => setCat(e.target.value)}
                    style={{ width:170, color:C.text2 }}>
                    <option value="all">all categories</option>
                    {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>

                {loading && (
                  <div style={G.empty}>
                    <div style={{ fontSize:13, color:C.text3 }}>loading products…</div>
                  </div>
                )}

                {!loading && fetched && filtered.length === 0 && (
                  <div style={G.empty}>
                    <div style={{ opacity:0.2, marginBottom:12, color:C.text }}><Icon n="grid" s={40} /></div>
                    <div style={{ fontSize:14, fontWeight:500, color:C.text2, marginBottom:4 }}>
                      {search ? "No products found" : "No products yet"}
                    </div>
                    <div style={{ fontSize:12, color:C.text3, marginBottom:16 }}>
                      {search ? "Try a different search term" : "Add your first product using the button above or via the admin bot"}
                    </div>
                    {!search && (
                      <Btn variant="primary" onClick={() => setView("form")}>
                        <Icon n="plus" s={13} />add first product
                      </Btn>
                    )}
                  </div>
                )}

                <div style={G.grid}>
                  {filtered.map(p => (
                    <ProductCard key={p.id} product={p}
                      onEdit={openEdit} onDelete={del} onToggleStock={toggleStock} />
                  ))}
                </div>
              </>}

              {/* ── Form view ── */}
              {view === "form" && (
                <div style={G.formWrap}>
                  <div style={G.formHeader}>
                    <div style={G.formHeaderIcon}>
                      <Icon n="plus" s={16} />
                    </div>
                    <div>
                      <div style={{ fontSize:14, fontWeight:600, color:C.text }}>
                        {editId ? "Edit product" : "New product"}
                      </div>
                      <div style={{ fontSize:11, color:C.text3 }}>
                        You can also add products by chatting with the admin bot
                      </div>
                    </div>
                  </div>

                  <div style={G.formBody}>

                    {/* Product Info */}
                    <div>
                      <div style={G.sectionLabel}>product info</div>
                      <div style={{ display:"flex", flexDirection:"column", gap:13, marginTop:12 }}>
                        <Field label="Product title" required>
                          <input value={form.title} onChange={fe("title")}
                            placeholder="e.g. iPhone 15 Pro Max 256GB" />
                        </Field>
                        <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:12 }}>
                          <Field label="Brand / Make">
                            <input value={form.author} onChange={fe("author")}
                              placeholder="Apple, Samsung, Tecno…" />
                          </Field>
                          <Field label="Stock quantity">
                            <input type="number" min="0" value={form.stock_qty} onChange={fe("stock_qty")} />
                          </Field>
                        </div>
                        <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:12 }}>
                          <Field label="Category">
                            <select value={form.category} onChange={fe("category")}>
                              {CATEGORIES.map(c => <option key={c}>{c}</option>)}
                            </select>
                          </Field>
                          <Field label="Condition">
                            <select value={form.condition} onChange={fe("condition")}>
                              {CONDITIONS.map(c => <option key={c}>{c}</option>)}
                            </select>
                          </Field>
                        </div>
                        <Field label="Specs / description">
                          <textarea value={form.specs} onChange={fe("specs")}
                            placeholder="128GB storage, Face ID, midnight black, dual SIM…" />
                        </Field>
                      </div>
                    </div>

                    {/* Pricing */}
                    <div>
                      <div style={G.sectionLabel}>pricing (₦)</div>
                      <div style={{ background:C.bg3, border:`1px solid ${C.border}`,
                        borderRadius:8, padding:"10px 13px", marginBottom:12, marginTop:12,
                        fontSize:11, color:C.text2, display:"flex", gap:6, alignItems:"flex-start" }}>
                        <Icon n="info" s={13} />
                        <div><strong>Selling price</strong> is what customers see.
                        <strong> List price</strong> is the starting ask.
                        <strong> Floor price</strong> is the minimum — the bot will never go below this.</div>
                      </div>
                      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr 1fr", gap:12 }}>
                        <Field label="Selling price" required>
                          <input type="number" value={form.price} onChange={fe("price")} placeholder="0" />
                        </Field>
                        <Field label="List price" hint="starting ask">
                          <input type="number" value={form.list_price} onChange={fe("list_price")} placeholder="same as selling" />
                        </Field>
                        <Field label="Floor price" hint="bot minimum">
                          <input type="number" value={form.base_price} onChange={fe("base_price")} placeholder="auto (88%)" />
                        </Field>
                      </div>
                    </div>

                    {/* Photo */}
                    <div>
                      <div style={G.sectionLabel}>product photo</div>
                      <div style={{ marginTop:12 }}>
                        <Field label="Image URL" hint="Paste a public URL — or upload via the admin bot on Telegram">
                          <input value={form.image_url} onChange={fe("image_url")}
                            placeholder="https://example.com/photo.jpg" />
                        </Field>
                        {form.image_url && (
                          <img src={form.image_url} alt="preview"
                            style={{ width:"100%", height:160, objectFit:"cover",
                              borderRadius:9, border:`1px solid ${C.border}`, marginTop:10 }}
                            onError={e => e.currentTarget.style.display = "none"} />
                        )}
                      </div>
                    </div>

                    {/* Availability */}
                    <div>
                      <div style={G.sectionLabel}>availability</div>
                      <div style={{ display:"flex", gap:28, marginTop:14 }}>
                        {[
                          { k:"in_stock",   label:"In stock" },
                          { k:"negotiable", label:"Price negotiable" },
                        ].map(({ k, label }) => (
                          <label key={k} style={{ display:"flex", alignItems:"center", gap:10,
                            cursor:"pointer", fontSize:13, color:C.text2, userSelect:"none" }}>
                            <Toggle checked={form[k]} onChange={f(k)} />
                            {label}
                          </label>
                        ))}
                      </div>
                    </div>
                  </div>

                  <div style={G.formFooter}>
                    <Btn variant="primary" onClick={save} disabled={saving}
                      style={{ flex:1, justifyContent:"center", padding:"10px" }}>
                      {saving ? "saving…" : editId ? "save changes" : "add product"}
                    </Btn>
                    <Btn variant="ghost"
                      onClick={() => { setView("grid"); setForm(defaultForm); setEditId(null); }}>
                      cancel
                    </Btn>
                  </div>
                </div>
              )}

            </div>
          </div>
        </div>
      </div>

      {toast && (
        <div style={{
          ...G.toast,
          background: toast.type === "error" ? C.redL : C.accentL,
          color: toast.type === "error" ? C.red : C.accentD,
          border: `1px solid ${toast.type === "error" ? C.red + "40" : C.accent + "50"}`,
          animation: "slideUp 0.2s ease",
        }}>
          {toast.msg}
        </div>
      )}
    </>
  );
}
