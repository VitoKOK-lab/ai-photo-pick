// JewelryDB — Shared Components  →  window.JDB
// Requires React on window before loading.

const { useState, useEffect, useRef, useCallback, useMemo } = React;

// ─── Mock Data ────────────────────────────────────────────────────────────────
const MOCK_ITEMS = [
  { id:1,  category:'戒指', color:'黃金',  material:'18K金', gem:'鑽石',  price:45000,  confidence:94, favorited:false, locked:false, date:'2024-01-15', tags:['主石0.5ct','H色','VS1'] },
  { id:2,  category:'項鍊', color:'玫瑰金',material:'14K金', gem:'紅寶石',price:32000,  confidence:87, favorited:true,  locked:false, date:'2024-01-18', tags:['緬甸產','1.2ct','無加熱'] },
  { id:3,  category:'耳環', color:'白金',  material:'鉑金',  gem:'藍寶石',price:68000,  confidence:92, favorited:false, locked:true,  date:'2024-01-20', tags:['斯里蘭卡','一對','喀什米爾色'] },
  { id:4,  category:'手環', color:'黃金',  material:'18K金', gem:'翡翠',  price:28000,  confidence:78, favorited:false, locked:false, date:'2024-01-22', tags:['A貨','冰種','飄花'] },
  { id:5,  category:'胸針', color:'玫瑰金',material:'玫瑰金',gem:'珍珠',  price:15000,  confidence:85, favorited:true,  locked:false, date:'2024-01-25', tags:['南洋珠','11mm','正圓'] },
  { id:6,  category:'戒指', color:'白金',  material:'鉑金',  gem:'鑽石',  price:120000, confidence:96, favorited:false, locked:true,  date:'2024-01-28', tags:['主石1.2ct','D色','IF'] },
  { id:7,  category:'項鍊', color:'黃金',  material:'18K金', gem:'無',    price:22000,  confidence:89, favorited:false, locked:false, date:'2024-02-01', tags:['威尼斯鍊','45cm','1.2mm'] },
  { id:8,  category:'耳環', color:'玫瑰金',material:'14K金', gem:'紅寶石',price:18000,  confidence:82, favorited:true,  locked:false, date:'2024-02-05', tags:['懸掛式','2.4ct','緬甸'] },
  { id:9,  category:'戒指', color:'黃金',  material:'18K金', gem:'翡翠',  price:55000,  confidence:91, favorited:false, locked:false, date:'2024-02-08', tags:['玻璃種','帝王綠','18K鑲嵌'] },
  { id:10, category:'手環', color:'銀',    material:'925銀', gem:'藍寶石',price:8500,   confidence:76, favorited:false, locked:false, date:'2024-02-10', tags:['鍍白金','0.8ct','橢圓'] },
  { id:11, category:'項鍊', color:'玫瑰金',material:'玫瑰金',gem:'珍珠',  price:35000,  confidence:88, favorited:true,  locked:false, date:'2024-02-12', tags:['akoya珍珠','8-8.5mm','日本產'] },
  { id:12, category:'胸針', color:'黃金',  material:'18K金', gem:'鑽石',  price:42000,  confidence:93, favorited:false, locked:false, date:'2024-02-15', tags:['花型','碎鑽0.8ct','立體工藝'] },
];

// ─── 客戶檔案 ─────────────────────────────────────────────────────────────────
const MOCK_CLIENTS = [
  { id:'C001', name:'陳太太', lineId:'@chen_tai_tai', phone:'',        date:'2024-01-15', sessions:3,
    tags:['大主石','鉑金','求婚款','預算12萬'],  notes:'山平簡大器，不喜歡強調裝飾感',  favItemIds:[6,1,12] },
  { id:'C002', name:'林小姐', lineId:'@lin_gem',      phone:'0933-456-789', date:'2024-02-15', sessions:1,
    tags:['藍寶石','斯里蘭卡','無燒','張陽證書'], notes:'對產地小心，需GRS/GIA證數',      favItemIds:[3,8] },
  { id:'C003', name:'王太太', lineId:'@wang_ruby',    phone:'',        date:'2024-02-14', sessions:2,
    tags:['紅寶石','玫瑰金','珍珠','預算4萬'],  notes:'喜歡玫瑰金系，緬甸無燒特別有興趣',  favItemIds:[2,11,5] },
  { id:'C004', name:'張先生', lineId:'@zhang_gift',  phone:'0955-678-901', date:'2024-02-12', sessions:1,
    tags:['送礼','男士款','黃金','預算4萬'],   notes:'為太太選購生日礼物，需精裝礼盒',    favItemIds:[12,7] },
  { id:'C005', name:'劉太太', lineId:'@liu_luxury',  phone:'',        date:'2024-02-10', sessions:2,
    tags:['鉑金','大鑽石','高端藏家'],          notes:'比較鉑金vs白K金差異，預算12萬+',  favItemIds:[6,3,1] },
];

// ─── 頖品風格檔案 ───────────────────────────────────────────────────────────────
const STYLE_PROFILES = [
  { id:'classic', label:'古典璊燦', desc:'鉑金 · 大鑽石 · 精工錒嵌',  bg:'#EAF0F8',
    match: i => i.gem==='鑽石' || i.material==='鉑金' },
  { id:'nature',  label:'自然靈動', desc:'翡翠 · 彩寶 · 有機線條',  bg:'#EBF5EC',
    match: i => ['翡翠','藍寶石','紅寶石'].includes(i.gem) },
  { id:'romance', label:'浪漫玫瑰', desc:'玫瑰金 · 珍珠 · 曲線設計', bg:'#F5EAE8',
    match: i => i.color==='玫瑰金' || i.gem==='珍珠' },
  { id:'modern',  label:'現代簡約', desc:'黃金鍊 · 幾何造型 · 日常配戴', bg:'#F2EAD5',
    match: i => i.gem==='無' || ['項鍊','手環'].includes(i.category) },
];

// ─── 客戶偏好庫 ──────────────────────────────────────────────────────────────
const MOCK_FAVORITES_DB = [
  { id:1,  itemId:6,  type:'customer', name:'陳太太', clientId:'C001', date:'2024-02-16', note:'求婚款，大主石，預算12萬，鉑金首選' },
  { id:2,  itemId:1,  type:'customer', name:'陳太太', clientId:'C001', date:'2024-02-14', note:'黃金也可考慮，主石H色以上，預算5萬' },
  { id:3,  itemId:3,  type:'customer', name:'林小姐', clientId:'C002', date:'2024-02-15', note:'藍色系耳環，喀什米爾色最喜歡' },
  { id:4,  itemId:2,  type:'customer', name:'王太太', clientId:'C003', date:'2024-02-14', note:'緬甸無燒紅寶，預算3.5萬，附GRS更好' },
  { id:5,  itemId:11, type:'customer', name:'王太太', clientId:'C003', date:'2024-02-13', note:'南洋珠有興趣，玫瑰金鑲嵌' },
  { id:6,  itemId:9,  type:'staff',    name:'小雅',  staffId:'S001',  date:'2024-02-15', note:'帝王綠翡翠，高端藏家款，建議定價5.5萬' },
  { id:7,  itemId:4,  type:'staff',    name:'小雅',  staffId:'S001',  date:'2024-02-14', note:'飄花冰種CP值高，適合首購客人' },
  { id:8,  itemId:12, type:'customer', name:'張先生', clientId:'C004', date:'2024-02-12', note:'送禮，需精裝盒，預算4萬' },
  { id:9,  itemId:5,  type:'staff',    name:'大明',  staffId:'S002',  date:'2024-02-11', note:'南洋珠胸針稀有款，建議備貨2件' },
  { id:10, itemId:6,  type:'customer', name:'劉太太', clientId:'C005', date:'2024-02-10', note:'在比較鉑金vs白K金，預算12萬' },
  { id:11, itemId:7,  type:'customer', name:'張先生', clientId:'C004', date:'2024-02-09', note:'男士義大利鍊，45cm款' },
  { id:12, itemId:3,  type:'customer', name:'蘇小姐', clientId:'C006', date:'2024-02-08', note:'藍寶石耳環，斯里蘭卡産，預算6萬' },
  { id:13, itemId:8,  type:'customer', name:'蘇小姐', clientId:'C006', date:'2024-02-07', note:'玫瑰金紅寶耳環也有興趣' },
  { id:14, itemId:3,  type:'staff',    name:'大明',  staffId:'S002',  date:'2024-02-06', note:'藍寶石耳環詢問度極高，建議補貨' },
];

// ─── 近期成交記錄 ──────────────────────────────────────────────────────────────
const MOCK_TRANSACTIONS = [
  { id:1, item:'18K金 鑽石戒指',     category:'戒指', material:'18K金', gem:'鑽石',
    stoneSpec:'0.5ct H/VS1',           metalWeight:3.2,  price:45000,  date:'2024-01-15', notes:'附GIA證書', client:'陳先生' },
  { id:2, item:'鉑金 藍寶石耳環一對', category:'耳環', material:'鉑金',  gem:'藍寶石',
    stoneSpec:'各1.2ct 無加熱',        metalWeight:5.8,  price:68000,  date:'2024-01-20', notes:'斯里蘭卡喀什米爾色', client:'劉太太' },
  { id:3, item:'鉑金 大鑽石戒指',    category:'戒指', material:'鉑金',  gem:'鑽石',
    stoneSpec:'1.2ct D/IF',            metalWeight:6.1,  price:120000, date:'2024-01-28', notes:'GIA認證，求婚款', client:'王先生' },
  { id:4, item:'18K金 帝王翡翠戒',   category:'戒指', material:'18K金', gem:'翡翠',
    stoneSpec:'6.2×8.4mm 玻璃種帝王綠',metalWeight:4.5,  price:55000,  date:'2024-02-08', notes:'A貨無裂附鑑定', client:'趙先生' },
  { id:5, item:'玫瑰金 南洋珠項鍊',  category:'項鍊', material:'玫瑰金',gem:'珍珠',
    stoneSpec:'11mm 正圓強光',         metalWeight:4.2,  price:35000,  date:'2024-02-12', notes:'日本産附證書', client:'陳太太' },
  { id:6, item:'14K金 緬甸紅寶耳環', category:'耳環', material:'14K金', gem:'紅寶石',
    stoneSpec:'各0.6ct 無燒緬甸',      metalWeight:3.8,  price:18000,  date:'2024-02-05', notes:'附GRS證書', client:'林小姐' },
];

// ─── Helpers ──────────────────────────────────────────────────────────────────
function getMetalColors(color) {
  const map = {
    '黃金':  { s:'#F0D090', m:'#C9943E', d:'#8B6820', bg1:'#F2EAD5', bg2:'#E8D5B5' },
    '玫瑰金':{ s:'#F0C0A0', m:'#C4856A', d:'#884040', bg1:'#F2E2D8', bg2:'#E8CAB8' },
    '白金':  { s:'#D8E8F8', m:'#8898C0', d:'#507098', bg1:'#EAF0F8', bg2:'#D8E4F0' },
    '銀':    { s:'#D8DDE8', m:'#8890A8', d:'#505870', bg1:'#ECEEF2', bg2:'#D8DCE4' },
  };
  return map[color] || map['黃金'];
}
function getGemColor(gem) {
  const map = { '鑽石':'#E0F0FF','紅寶石':'#E02830','藍寶石':'#2048C0','翡翠':'#3A8850','珍珠':'#F8EEE8','無':null };
  return map[gem] ?? null;
}

// ─── useLongPress ─────────────────────────────────────────────────────────────
function useLongPress(cb, ms = 580) {
  const t = useRef(null);
  const fired = useRef(false);
  const start = useCallback((e) => {
    fired.current = false;
    t.current = setTimeout(() => { fired.current = true; cb(e); }, ms);
  }, [cb, ms]);
  const stop = useCallback(() => { clearTimeout(t.current); }, []);
  return {
    onMouseDown: start, onMouseUp: stop, onMouseLeave: stop,
    onTouchStart: (e) => start(e.touches[0]),
    onTouchEnd: stop, onTouchCancel: stop,
    onContextMenu: (e) => { e.preventDefault(); cb(e); },
  };
}

// ─── JewelryPhoto ─────────────────────────────────────────────────────────────
function JewelryPhoto({ item }) {
  const id = `jp${item.id}`;
  const m = getMetalColors(item.color);
  const gc = getGemColor(item.gem);
  return (
    <svg viewBox="0 0 200 200" style={{ width:'100%', height:'100%', display:'block' }} xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id={`bg${id}`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor={m.bg1}/><stop offset="100%" stopColor={m.bg2}/>
        </linearGradient>
        <linearGradient id={`mt${id}`} x1="0.15" y1="0" x2="0.85" y2="1">
          <stop offset="0%" stopColor={m.s}/><stop offset="50%" stopColor={m.m}/><stop offset="100%" stopColor={m.d}/>
        </linearGradient>
        <radialGradient id={`sh${id}`} cx="30%" cy="25%">
          <stop offset="0%" stopColor="white" stopOpacity="0.4"/><stop offset="100%" stopColor="white" stopOpacity="0"/>
        </radialGradient>
      </defs>
      <rect width="200" height="200" fill={`url(#bg${id})`}/>
      {item.category === '戒指' && <>
        <circle cx="100" cy="108" r="50" fill="none" stroke={`url(#mt${id})`} strokeWidth="20"/>
        <circle cx="100" cy="108" r="50" fill="none" stroke={m.d} strokeWidth="1" opacity="0.2"/>
        {gc ? <><polygon points="100,44 116,57 113,73 87,73 84,57" fill={gc}/>
               <polygon points="100,44 116,57 100,58" fill="white" opacity="0.4"/></> :
               <rect x="88" y="44" width="24" height="18" rx="3" fill={m.m} opacity="0.55"/>}
        <path d="M65,88 Q100,72 135,88" stroke="white" strokeWidth="2.5" fill="none" opacity="0.3" strokeLinecap="round"/>
      </>}
      {item.category === '項鍊' && <>
        {[0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9].map((t,i) => {
          const x=30+140*t, y=52+60*4*t*(1-t);
          return <circle key={i} cx={x} cy={y} r="3" fill={m.m} opacity="0.75"/>;
        })}
        <path d="M30,52 Q100,112 170,52" fill="none" stroke={m.m} strokeWidth="2" opacity="0.45"/>
        {gc ? <><polygon points="100,106 114,124 100,140 86,124" fill={gc}/>
               <polygon points="100,106 114,124 100,119" fill="white" opacity="0.3"/></> :
               <ellipse cx="100" cy="122" rx="12" ry="18" fill={`url(#mt${id})`} opacity="0.8"/>}
        <circle cx="100" cy="104" r="5" fill={m.m}/>
        <line x1="100" y1="95" x2="100" y2="104" stroke={m.m} strokeWidth="3" strokeLinecap="round"/>
      </>}
      {item.category === '耳環' && <>
        {gc ? <><polygon points="65,56 74,73 65,90 56,73" fill={gc}/>
               <polygon points="65,56 74,73 65,68" fill="white" opacity="0.3"/>
               <polygon points="135,56 144,73 135,90 126,73" fill={gc}/>
               <polygon points="135,56 144,73 135,68" fill="white" opacity="0.3"/></> :
              <><ellipse cx="65" cy="74" rx="11" ry="15" fill={`url(#mt${id})`} opacity="0.8"/>
               <ellipse cx="135" cy="74" rx="11" ry="15" fill={`url(#mt${id})`} opacity="0.8"/></>}
        {[65,135].map(cx => <g key={cx}>
          <circle cx={cx} cy="53" r="5" fill={m.m}/>
          <line x1={cx} y1="48" x2={cx} y2="57" stroke={m.m} strokeWidth="2.5" strokeLinecap="round"/>
          <line x1={cx-7} y1="43" x2={cx+7} y2="43" stroke={m.m} strokeWidth="2.5" strokeLinecap="round"/>
        </g>)}
      </>}
      {item.category === '手環' && <>
        <path d="M55,148 A58,58 0 1,1 145,148" fill="none" stroke={`url(#mt${id})`} strokeWidth="18" strokeLinecap="round"/>
        <path d="M55,148 A58,58 0 1,1 145,148" fill="none" stroke={m.d} strokeWidth="1" opacity="0.15" strokeLinecap="round"/>
        {gc && <><circle cx="100" cy="42" r="11" fill={gc}/><circle cx="100" cy="42" r="5" fill="white" opacity="0.3"/></>}
        <path d="M68,90 Q100,74 132,90" stroke="white" strokeWidth="2" fill="none" opacity="0.3" strokeLinecap="round"/>
      </>}
      {item.category === '胸針' && <>
        {[0,45,90,135,180,225,270,315].map((angle,i) => {
          const r=angle*Math.PI/180, x1=100+22*Math.cos(r), y1=100+22*Math.sin(r), x2=100+46*Math.cos(r), y2=100+46*Math.sin(r);
          return <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} stroke={`url(#mt${id})`} strokeWidth="6" strokeLinecap="round"/>;
        })}
        <circle cx="100" cy="100" r="24" fill={gc||`url(#mt${id})`}/>
        {gc && <circle cx="100" cy="100" r="12" fill="white" opacity="0.2"/>}
        {[0,90,180,270].map((angle,i) => {
          const r=angle*Math.PI/180;
          return <circle key={i} cx={100+46*Math.cos(r)} cy={100+46*Math.sin(r)} r="7" fill={gc||m.m}/>;
        })}
      </>}
      <rect width="200" height="200" fill={`url(#sh${id})`}/>
    </svg>
  );
}

// ─── TabBar ───────────────────────────────────────────────────────────────────
function TabIcon({ id, active }) {
  const c = active ? 'var(--gold)' : 'var(--ink-4)';
  const fill = active ? c : 'none';
  if (id === 'home') return <svg width="22" height="22" viewBox="0 0 22 22" fill="none">
    <rect x="2" y="9"  width="7" height="11" rx="1.5" fill={fill} stroke={c} strokeWidth="1.5"/>
    <rect x="11" y="2" width="9" height="8"  rx="1.5" fill={fill} stroke={c} strokeWidth="1.5"/>
    <rect x="11" y="12" width="9" height="8" rx="1.5" fill={fill} stroke={c} strokeWidth="1.5"/>
    <rect x="2" y="2"  width="7" height="5"  rx="1.5" fill={fill} stroke={c} strokeWidth="1.5"/>
  </svg>;
  if (id === 'stats') return <svg width="22" height="22" viewBox="0 0 22 22" fill="none">
    <rect x="2"  y="13" width="4" height="7"  rx="1" fill={c} opacity={active?1:0.45}/>
    <rect x="9"  y="8"  width="4" height="12" rx="1" fill={c} opacity={active?1:0.45}/>
    <rect x="16" y="3"  width="4" height="17" rx="1" fill={c} opacity={active?1:0.45}/>
  </svg>;
  if (id === 'quotes') return <svg width="22" height="22" viewBox="0 0 22 22" fill="none">
    <path d="M5 2h9l4 4v14a1 1 0 01-1 1H5a1 1 0 01-1-1V3a1 1 0 011-1z" stroke={c} strokeWidth="1.5" fill={active?'var(--gold-tint)':'none'}/>
    <path d="M13 2v4h4" stroke={c} strokeWidth="1.5" strokeLinecap="round"/>
    <line x1="7" y1="11" x2="15" y2="11" stroke={c} strokeWidth="1.5" strokeLinecap="round"/>
    <line x1="7" y1="15" x2="12" y2="15" stroke={c} strokeWidth="1.5" strokeLinecap="round"/>
  </svg>;
  if (id === 'favorites') return <svg width="22" height="22" viewBox="0 0 22 22" fill="none">
    <path d="M11 19C11 19 2 13 2 7.5a4.5 4.5 0 019-1 4.5 4.5 0 019 1C20 13 11 19 11 19z"
      fill={active?c:'none'} stroke={c} strokeWidth="1.5"/>
  </svg>;
  return null;
}

function TabBar({ activePage, navigate }) {
  const tabs = [
    { id:'home',      label:'首頁' },
    { id:'stats',     label:'洞察' },
    { id:'quotes',    label:'成交' },
    { id:'favorites', label:'偏好' },
  ];
  return (
    <div style={{ height:83, background:'rgba(250,249,247,0.96)', backdropFilter:'blur(20px)',
      WebkitBackdropFilter:'blur(20px)', borderTop:'0.5px solid var(--line)',
      display:'flex', alignItems:'flex-start', paddingTop:8, flexShrink:0 }}>
      {tabs.map(tab => {
        const active = activePage === tab.id;
        return (
          <button key={tab.id} onClick={() => navigate(tab.id)} style={{
            flex:1, display:'flex', flexDirection:'column', alignItems:'center', gap:3,
            background:'none', border:'none', cursor:'pointer', padding:'4px 0',
            color: active ? 'var(--gold)' : 'var(--ink-4)',
          }}>
            <TabIcon id={tab.id} active={active}/>
            <span style={{ fontSize:10, fontFamily:'var(--font-body)', fontWeight: active ? 500 : 400, letterSpacing:'0.02em' }}>
              {tab.label}
            </span>
          </button>
        );
      })}
    </div>
  );
}

// ─── FilterPills ──────────────────────────────────────────────────────────────
function FilterPills({ active, onSelect }) {
  const pills = ['全部','戒指','項鍊','耳環','手環','胸針','黃金','玫瑰金','白金','鑽石','翡翠','珍珠'];
  return (
    <div className="hide-scrollbar" style={{ display:'flex', gap:6, padding:'6px 12px 8px',
      overflowX:'auto', flexShrink:0 }}>
      {pills.map(p => {
        const on = active === p;
        return <button key={p} onClick={() => onSelect(p)} style={{
          height:28, padding:'0 11px', borderRadius:'var(--r-pill)', whiteSpace:'nowrap', cursor:'pointer',
          border: on ? '1.5px solid var(--gold)' : '1px solid var(--line)',
          background: on ? 'var(--gold-tint)' : 'var(--card)',
          color: on ? 'var(--gold)' : 'var(--ink-2)',
          fontSize:12, fontFamily:'var(--font-body)', fontWeight: on ? 500 : 400,
          transition:'all 0.15s ease',
        }}>{p}</button>;
      })}
    </div>
  );
}

// ─── PhotoCard ────────────────────────────────────────────────────────────────
function PhotoCard({ item, onPress, onLongPress }) {
  const lp = useLongPress((e) => onLongPress && onLongPress(item), 580);
  return (
    <div onClick={() => onPress && onPress(item)} {...lp}
      style={{ position:'relative', borderRadius:'var(--r-card)', overflow:'hidden',
        aspectRatio:'1', cursor:'pointer', userSelect:'none', WebkitUserSelect:'none',
        boxShadow:'var(--shadow)', background:'var(--card)' }}>
      <div style={{ position:'absolute', inset:0 }}><JewelryPhoto item={item}/></div>
      <div style={{ position:'absolute', inset:0, bottom:0,
        background:'linear-gradient(to top, rgba(20,16,12,0.72) 0%, rgba(20,16,12,0.25) 55%, transparent 100%)' }}/>
      <div style={{ position:'absolute', bottom:0, left:0, right:0, padding:'14px 8px 7px' }}>
        <div style={{ fontSize:11, color:'white', lineHeight:1.5, letterSpacing:'0.02em' }}>
          <span style={{ fontWeight:600 }}>{item.category}</span>
          <span style={{ opacity:0.8 }}> · {item.color} · {item.material}</span>
        </div>
      </div>
      <div style={{ position:'absolute', top:6, right:6, display:'flex', flexDirection:'column', gap:3 }}>
        {item.favorited && <Badge bg="rgba(255,255,255,0.92)" text="♥" color="var(--danger)"/>}
        {item.locked && <Badge bg="rgba(20,16,12,0.65)" text="🔒" color="white"/>}
      </div>
    </div>
  );
}
function Badge({ bg, text, color }) {
  return <div style={{ width:20, height:20, borderRadius:'50%', background:bg,
    display:'flex', alignItems:'center', justifyContent:'center', fontSize:10, color }}>{text}</div>;
}

// ─── PhotoDetailModal ─────────────────────────────────────────────────────────
function PhotoDetailModal({ item, allItems, onClose, onFavorite, onLock }) {
  const [closing, setClosing] = useState(false);
  const [dragY, setDragY]     = useState(0);
  const [dragging, setDragging] = useState(false);
  const sy = useRef(0);
  const close = () => { setClosing(true); setTimeout(onClose, 300); };
  const similar = allItems.filter(i => i.id !== item.id && (i.category === item.category || i.color === item.color)).slice(0,5);
  return (
    <div onClick={close} style={{ position:'absolute', inset:0, zIndex:50, display:'flex',
      flexDirection:'column', justifyContent:'flex-end',
      background:'rgba(0,0,0,0.45)',
      animation: closing ? 'fadeOut 0.28s ease forwards' : 'fadeIn 0.28s ease forwards' }}>
      <div onClick={e => e.stopPropagation()} style={{ background:'var(--card)',
        borderRadius:'20px 20px 0 0', maxHeight:'88%',
        transform:`translateY(${dragY}px)`,
        transition: dragging ? 'none' : 'transform 0.18s ease',
        animation: closing ? 'slideDown 0.3s ease forwards' : 'slideUp 0.36s cubic-bezier(0.32,0.72,0,1) forwards',
        display:'flex', flexDirection:'column', overflow:'hidden' }}
        onTouchStart={e => { sy.current = e.touches[0].clientY; setDragging(true); }}
        onTouchMove={e => { const d = e.touches[0].clientY - sy.current; if(d>0) setDragY(d); }}
        onTouchEnd={e => { setDragging(false); if(e.changedTouches[0].clientY - sy.current > 90) close(); else setDragY(0); }}>
        {/* Handle */}
        <div style={{ display:'flex', justifyContent:'center', padding:'10px 0 6px', flexShrink:0 }}>
          <div style={{ width:36, height:4, borderRadius:2, background:'var(--line)' }}/>
        </div>
        {/* Photo */}
        <div style={{ height:220, flexShrink:0 }}><JewelryPhoto item={item}/></div>
        {/* Info */}
        <div className="hide-scrollbar" style={{ overflowY:'auto', flex:1, padding:'14px 16px 0' }}>
          <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:10 }}>
            <div>
              <div style={{ fontSize:20, fontFamily:'var(--font-display)', fontWeight:500, color:'var(--ink)', marginBottom:3 }}>
                {item.category} · {item.color}
              </div>
              <div style={{ fontSize:12, color:'var(--ink-2)' }}>{item.material} · {item.gem}</div>
            </div>
            <div style={{ fontSize:18, fontFamily:'var(--font-display)', fontWeight:600, color:'var(--gold-deep)' }}>
              NT${item.price.toLocaleString()}
            </div>
          </div>
          <div style={{ display:'flex', gap:5, flexWrap:'wrap', marginBottom:12 }}>
            {item.tags.map((t,i) => <span key={i} style={{ fontSize:11, padding:'3px 8px',
              borderRadius:'var(--r-pill)', background:'var(--gold-tint)', color:'var(--gold-deep)', fontWeight:500 }}>{t}</span>)}
          </div>
          <div style={{ marginBottom:14 }}>
            <div style={{ display:'flex', justifyContent:'space-between', marginBottom:5 }}>
              <span style={{ fontSize:11, color:'var(--ink-3)', letterSpacing:'0.06em', textTransform:'uppercase' }}>AI 信心度</span>
              <span style={{ fontSize:12, color:'var(--gold)', fontWeight:600 }}>{item.confidence}%</span>
            </div>
            <div style={{ height:4, borderRadius:2, background:'var(--line)', overflow:'hidden' }}>
              <div style={{ height:'100%', width:`${item.confidence}%`,
                background:'linear-gradient(to right,var(--gold-dim),var(--gold))', borderRadius:2, transition:'width 0.6s ease' }}/>
            </div>
          </div>
          {similar.length > 0 && <div style={{ marginBottom:14 }}>
            <div style={{ fontSize:11, color:'var(--ink-3)', letterSpacing:'0.06em', textTransform:'uppercase', marginBottom:8 }}>相似珠寶</div>
            <div style={{ display:'flex', gap:7 }}>
              {similar.map(s => <div key={s.id} style={{ width:58, height:58, borderRadius:8, overflow:'hidden', flexShrink:0 }}>
                <JewelryPhoto item={s}/>
              </div>)}
            </div>
          </div>}
        </div>
        {/* Actions */}
        <div style={{ display:'flex', gap:8, padding:'12px 16px 22px', borderTop:'0.5px solid var(--line)', flexShrink:0 }}>
          {[
            { icon: item.favorited?'♥':'♡', label: item.favorited?'已收藏':'收藏', act:()=>onFavorite(item.id),
              active: item.favorited, activeColor:'var(--danger)' },
            { icon: item.locked?'🔒':'🔓', label: item.locked?'已鎖定':'鎖定', act:()=>onLock(item.id),
              active: item.locked, activeColor:'var(--ink)' },
            { icon:'⊕', label:'查看原圖', act:()=>{}, active:false },
          ].map((a,i) => <button key={i} onClick={a.act} style={{
            flex:1, height:42, borderRadius:'var(--r-btn)', cursor:'pointer',
            border:`1.5px solid ${a.active ? a.activeColor : 'var(--line)'}`,
            background: a.active ? (i===0?'#FEF0F0':i===1?'var(--ink)':'none') : 'none',
            color: a.active ? (i===0?a.activeColor:'white') : 'var(--ink-2)',
            fontSize:13, fontFamily:'var(--font-body)',
            display:'flex', alignItems:'center', justifyContent:'center', gap:5,
          }}><span>{a.icon}</span><span>{a.label}</span></button>)}
        </div>
      </div>
    </div>
  );
}

// ─── LongPressMenu ────────────────────────────────────────────────────────────
function LongPressMenu({ item, onClose, onFavorite, onLock, showToast }) {
  const actions = [
    { icon: item.favorited?'♥':'♡', label: item.favorited?'取消收藏':'加入收藏',
      action:()=>{ onFavorite(item.id); showToast(item.favorited?'已取消收藏':'已加入收藏'); onClose(); }},
    { icon: item.locked?'🔓':'🔒', label: item.locked?'取消鎖定':'鎖定照片',
      action:()=>{ onLock(item.id); showToast(item.locked?'已解除鎖定':'已鎖定照片'); onClose(); }},
    { icon:'↗', label:'分享', action: onClose },
    { icon:'✕', label:'取消', action: onClose, danger:true },
  ];
  return (
    <div onClick={onClose} style={{ position:'absolute', inset:0, zIndex:60,
      background:'rgba(0,0,0,0.3)', backdropFilter:'blur(6px)', WebkitBackdropFilter:'blur(6px)',
      display:'flex', alignItems:'center', justifyContent:'center' }}>
      <div onClick={e=>e.stopPropagation()} style={{ background:'var(--card)',
        borderRadius:16, overflow:'hidden', width:230, boxShadow:'var(--shadow-float)' }}>
        <div style={{ height:140 }}><JewelryPhoto item={item}/></div>
        <div style={{ padding:'10px 14px 8px', borderBottom:'0.5px solid var(--line)' }}>
          <div style={{ fontSize:13, fontWeight:600, color:'var(--ink)' }}>{item.category} · {item.color}</div>
          <div style={{ fontSize:11, color:'var(--ink-3)' }}>{item.material} · {item.gem}</div>
        </div>
        {actions.map((a,i) => <button key={i} onClick={a.action} style={{
          width:'100%', padding:'11px 14px', background:'none', border:'none', cursor:'pointer',
          borderBottom: i<3?'0.5px solid var(--line)':'none', textAlign:'left',
          display:'flex', alignItems:'center', gap:10, fontSize:13, fontFamily:'var(--font-body)',
          color: a.danger?'var(--danger)':'var(--ink)',
        }}><span style={{ fontSize:15, width:20, textAlign:'center' }}>{a.icon}</span><span>{a.label}</span></button>)}
      </div>
    </div>
  );
}

// ─── StatCard ─────────────────────────────────────────────────────────────────
function StatCard({ title, value, sub, accent }) {
  return (
    <div style={{ background:'var(--card)', borderRadius:'var(--r-card)', padding:'14px 16px',
      boxShadow:'var(--shadow)', flex:1, minWidth:0 }}>
      <div style={{ fontSize:10, color:'var(--ink-3)', letterSpacing:'0.08em', textTransform:'uppercase', marginBottom:6 }}>{title}</div>
      <div style={{ fontSize:24, fontFamily:'var(--font-display)', fontWeight:500, color: accent||'var(--ink)', lineHeight:1.1, marginBottom:3 }}>{value}</div>
      <div style={{ fontSize:11, color:'var(--ink-3)' }}>{sub}</div>
    </div>
  );
}

// ─── BarChart ─────────────────────────────────────────────────────────────────
function BarChart({ title, data }) {
  const max = Math.max(...data.map(d=>d.value));
  return (
    <div style={{ background:'var(--card)', borderRadius:'var(--r-card)', padding:'14px 16px', boxShadow:'var(--shadow)' }}>
      <div style={{ fontSize:13, fontWeight:600, color:'var(--ink)', marginBottom:12 }}>{title}</div>
      <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
        {data.map((d,i) => <div key={i} style={{ display:'flex', alignItems:'center', gap:8 }}>
          <div style={{ fontSize:11, color:'var(--ink-2)', width:38, textAlign:'right', flexShrink:0 }}>{d.label}</div>
          <div style={{ flex:1, height:16, background:'var(--gold-tint)', borderRadius:3, overflow:'hidden' }}>
            <div style={{ height:'100%', width:`${(d.value/max)*100}%`,
              background: d.color||'linear-gradient(to right,var(--gold-dim),var(--gold))',
              borderRadius:3, transition:'width 0.6s ease', display:'flex', alignItems:'center', paddingRight:5, justifyContent:'flex-end' }}>
              {d.value > max*0.3 && <span style={{ fontSize:10, color:'white', fontWeight:600 }}>{d.value}</span>}
            </div>
          </div>
          {d.value <= max*0.3 && <span style={{ fontSize:10, color:'var(--ink-3)', minWidth:14 }}>{d.value}</span>}
        </div>)}
      </div>
    </div>
  );
}

// ─── QuoteRow ─────────────────────────────────────────────────────────────────
function QuoteRow({ quote, onPress }) {
  const status = { '成交':{ bg:'#EBF7EF', c:'#2A7A50' }, '議價中':{ bg:'var(--gold-tint)', c:'var(--gold-deep)' }, '未成交':{ bg:'#FEF0F0', c:'var(--danger)' } };
  const s = status[quote.status] || status['議價中'];
  return (
    <div onClick={() => onPress&&onPress(quote)} style={{ background:'var(--card)', borderRadius:10,
      padding:'12px 14px', boxShadow:'var(--shadow)', cursor:'pointer', display:'flex', flexDirection:'column', gap:7 }}>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start' }}>
        <div style={{ flex:1, marginRight:8 }}>
          <div style={{ fontSize:13, fontWeight:600, color:'var(--ink)', marginBottom:2 }}>{quote.item}</div>
          <div style={{ fontSize:11, color:'var(--ink-3)' }}>{quote.material} · {quote.gem} · {quote.client}</div>
        </div>
        <div style={{ textAlign:'right', flexShrink:0 }}>
          <div style={{ fontSize:15, fontFamily:'var(--font-display)', fontWeight:600, color:'var(--gold-deep)', marginBottom:4 }}>
            NT${quote.price.toLocaleString()}
          </div>
          <span style={{ fontSize:10, padding:'2px 7px', borderRadius:'var(--r-pill)',
            background:s.bg, color:s.c, fontWeight:500 }}>{quote.status}</span>
        </div>
      </div>
      <div style={{ fontSize:11, color:'var(--ink-4)' }}>{quote.date}</div>
    </div>
  );
}

// ─── QuoteFormModal ───────────────────────────────────────────────────────────
function QuoteFormModal({ onClose, onSave }) {
  const [closing, setClosing] = useState(false);
  const [form, setForm] = useState({ item:'', material:'18K金', gem:'鑽石', price:'', client:'', status:'議價中' });
  const close = () => { setClosing(true); setTimeout(onClose, 290); };
  const set = (k,v) => setForm(p=>({...p,[k]:v}));
  const fieldStyle = { width:'100%', height:40, padding:'0 10px', borderRadius:'var(--r-input)',
    border:'1px solid var(--line)', fontSize:13, fontFamily:'var(--font-body)', color:'var(--ink)',
    background:'var(--bg)', outline:'none' };
  const labelStyle = { fontSize:11, color:'var(--ink-3)', letterSpacing:'0.05em', textTransform:'uppercase', marginBottom:5, display:'block' };
  return (
    <div onClick={close} style={{ position:'absolute', inset:0, zIndex:50, display:'flex',
      flexDirection:'column', justifyContent:'flex-end',
      background:'rgba(0,0,0,0.4)',
      animation: closing ? 'fadeOut 0.28s ease forwards' : 'fadeIn 0.28s ease forwards' }}>
      <div onClick={e=>e.stopPropagation()} style={{ background:'var(--card)', borderRadius:'20px 20px 0 0',
        animation: closing ? 'slideDown 0.29s ease forwards' : 'slideUp 0.36s cubic-bezier(0.32,0.72,0,1) forwards',
        maxHeight:'85%', display:'flex', flexDirection:'column' }}>
        <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between',
          padding:'14px 16px 12px', borderBottom:'0.5px solid var(--line)', flexShrink:0 }}>
          <div style={{ fontSize:16, fontFamily:'var(--font-display)', fontWeight:500 }}>新增報價</div>
          <button onClick={close} style={{ background:'none', border:'none', fontSize:18, cursor:'pointer', color:'var(--ink-3)', padding:4 }}>✕</button>
        </div>
        <div className="hide-scrollbar" style={{ overflowY:'auto', flex:1, padding:'16px' }}>
          <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
            <div><label style={labelStyle}>品項描述</label>
              <input style={fieldStyle} placeholder="例：18K金 主石1ct 鑽石戒指" value={form.item} onChange={e=>set('item',e.target.value)}/></div>
            <div style={{ display:'flex', gap:10 }}>
              <div style={{ flex:1 }}><label style={labelStyle}>材質</label>
                <select style={fieldStyle} value={form.material} onChange={e=>set('material',e.target.value)}>
                  {['18K金','14K金','鉑金','925銀','玫瑰金'].map(v=><option key={v}>{v}</option>)}</select></div>
              <div style={{ flex:1 }}><label style={labelStyle}>寶石</label>
                <select style={fieldStyle} value={form.gem} onChange={e=>set('gem',e.target.value)}>
                  {['鑽石','紅寶石','藍寶石','翡翠','珍珠','無'].map(v=><option key={v}>{v}</option>)}</select></div>
            </div>
            <div style={{ display:'flex', gap:10 }}>
              <div style={{ flex:1 }}><label style={labelStyle}>成交金額（NT$）</label>
                <input style={fieldStyle} type="number" placeholder="0" value={form.price} onChange={e=>set('price',e.target.value)}/></div>
              <div style={{ flex:1 }}><label style={labelStyle}>狀態</label>
                <select style={fieldStyle} value={form.status} onChange={e=>set('status',e.target.value)}>
                  {['議價中','成交','未成交'].map(v=><option key={v}>{v}</option>)}</select></div>
            </div>
            <div><label style={labelStyle}>客戶</label>
              <input style={fieldStyle} placeholder="客戶姓名" value={form.client} onChange={e=>set('client',e.target.value)}/></div>
          </div>
        </div>
        <div style={{ padding:'12px 16px 28px', flexShrink:0 }}>
          <button onClick={() => { if(!form.item||!form.price) return;
            onSave({...form, id:Date.now(), price:Number(form.price), date:new Date().toISOString().slice(0,10)});
            close(); }}
            style={{ width:'100%', height:46, borderRadius:'var(--r-btn)', background:'var(--gold)',
              border:'none', color:'white', fontSize:15, fontFamily:'var(--font-body)', fontWeight:600,
              cursor:'pointer', letterSpacing:'0.04em' }}>
            確認新增
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Toast ────────────────────────────────────────────────────────────────────
function Toast({ message }) {
  const [v, setV] = useState(false);
  useEffect(() => { requestAnimationFrame(()=>setV(true)); return ()=>setV(false); }, []);
  return (
    <div style={{ position:'absolute', bottom:96, left:'50%',
      transform:`translateX(-50%) translateY(${v?0:12}px)`, opacity:v?1:0,
      transition:'all 0.25s ease', zIndex:90, background:'rgba(26,22,18,0.88)',
      backdropFilter:'blur(10px)', color:'white', fontSize:13, padding:'8px 16px',
      borderRadius:'var(--r-pill)', whiteSpace:'nowrap', fontFamily:'var(--font-body)', fontWeight:400 }}>
      {message}
    </div>
  );
}

// ─── EmptyState ───────────────────────────────────────────────────────────────
function EmptyState({ title='找不到符合的珠寶', sub='試試調整篩選條件' }) {
  return (
    <div style={{ display:'flex', flexDirection:'column', alignItems:'center',
      justifyContent:'center', padding:'50px 30px', gap:10 }}>
      <svg width="60" height="60" viewBox="0 0 60 60" fill="none">
        <polygon points="30,6 48,22 30,54 12,22" fill="none" stroke="var(--gold-dim)" strokeWidth="1.5"/>
        <polygon points="12,22 48,22 30,54" fill="var(--gold-tint)"/>
        <polygon points="30,6 12,22 48,22" fill="var(--gold-bg)"/>
        <line x1="12" y1="22" x2="30" y2="6" stroke="var(--line-gold)" strokeWidth="1"/>
        <line x1="48" y1="22" x2="30" y2="6" stroke="var(--line-gold)" strokeWidth="1"/>
      </svg>
      <div style={{ fontSize:14, fontWeight:500, color:'var(--ink-2)', textAlign:'center' }}>{title}</div>
      <div style={{ fontSize:12, color:'var(--ink-3)', textAlign:'center' }}>{sub}</div>
    </div>
  );
}

// ─── AppHeader ────────────────────────────────────────────────────────────────
function AppHeader({ onSearch, searchActive, searchVal, onSearchChange, right }) {
  return (
    <div style={{ height:52, display:'flex', alignItems:'center', padding:'0 14px',
      background:'var(--card)', borderBottom:'0.5px solid var(--line)', flexShrink:0, gap:10 }}>
      {searchActive ? <>
        <input autoFocus value={searchVal} onChange={e=>onSearchChange(e.target.value)}
          placeholder="搜尋類別、顏色、材質…"
          style={{ flex:1, height:34, padding:'0 12px', borderRadius:'var(--r-pill)',
            border:'1.5px solid var(--gold)', background:'var(--gold-tint)',
            fontSize:13, fontFamily:'var(--font-body)', color:'var(--ink)', outline:'none' }}/>
        <button onClick={()=>{ onSearch(false); onSearchChange(''); }}
          style={{ background:'none', border:'none', color:'var(--ink-3)', fontSize:13, cursor:'pointer', flexShrink:0 }}>取消</button>
      </> : <>
        <div style={{ flex:1 }}>
          <div style={{ fontFamily:'var(--font-display)', fontSize:19, fontWeight:500, color:'var(--gold)', lineHeight:1 }}>
            ✦ JewelryDB
          </div>
          <div style={{ fontSize:9, color:'var(--ink-3)', letterSpacing:'0.08em', marginTop:1 }}>珠寶照片管理系統</div>
        </div>
        <button onClick={()=>onSearch(true)} style={{ background:'none', border:'none', cursor:'pointer', padding:6, color:'var(--ink-2)' }}>
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
            <circle cx="8" cy="8" r="5" stroke="currentColor" strokeWidth="1.5"/>
            <line x1="12" y1="12" x2="16" y2="16" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
          </svg>
        </button>
        {right}
      </>}
    </div>
  );
}

// ─── PrefChip ─────────────────────────────────────────────────────────────────
function PrefChip({ label, value, count }) {
  return (
    <div style={{ display:'flex', flexDirection:'column', alignItems:'center', gap:3,
      padding:'8px 14px', background:'var(--gold-tint)', borderRadius:10,
      border:'1px solid var(--line-gold)', minWidth:64 }}>
      <span style={{ fontSize:9, color:'var(--ink-3)', letterSpacing:'0.08em', textTransform:'uppercase' }}>{label}</span>
      <span style={{ fontSize:16, fontFamily:'var(--font-display)', fontWeight:600, color:'var(--gold-deep)' }}>{value}</span>
      <span style={{ fontSize:10, color:'var(--ink-3)' }}>{count} 次</span>
    </div>
  );
}

// ─── FavEntry ─────────────────────────────────────────────────────────────────
function FavEntry({ entry, item, onClick }) {
  const isCust = entry.type === 'customer';
  return (
    <div onClick={() => onClick && onClick(entry)} style={{ background:'var(--card)',
      borderRadius:'var(--r-card)', padding:'12px 13px', boxShadow:'var(--shadow)',
      cursor:'pointer', display:'flex', gap:11, alignItems:'flex-start' }}>
      <div style={{ width:38, height:38, borderRadius:'50%', flexShrink:0,
        background: isCust ? 'var(--gold-bg)' : '#EEF6F5',
        border:`1.5px solid ${isCust ? 'var(--gold)' : '#B0D8D4'}`,
        display:'flex', alignItems:'center', justifyContent:'center',
        fontSize:14, fontFamily:'var(--font-display)', fontWeight:500,
        color: isCust ? 'var(--gold-deep)' : '#3A8880' }}>{entry.name.slice(0,1)}</div>
      <div style={{ flex:1, minWidth:0 }}>
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:3 }}>
          <div style={{ display:'flex', alignItems:'center', gap:6 }}>
            <span style={{ fontSize:13, fontWeight:600, color:'var(--ink)' }}>{entry.name}</span>
            <span style={{ fontSize:10, padding:'1px 7px', borderRadius:'var(--r-pill)',
              background: isCust ? 'var(--gold-tint)' : '#EEF6F5',
              color: isCust ? 'var(--gold-deep)' : '#3A8880', fontWeight:500 }}>
              {isCust ? '客人' : '員工'}</span>
          </div>
          <span style={{ fontSize:11, color:'var(--ink-4)', flexShrink:0 }}>{entry.date.slice(5)}</span>
        </div>
        {item && <div style={{ fontSize:12, color:'var(--ink-2)', marginBottom:4 }}>
          {item.category} · {item.color} {item.material}{item.gem!=='無'?` · ${item.gem}`:''}
        </div>}
        {entry.note && <div style={{ fontSize:11, color:'var(--ink-3)', lineHeight:1.55,
          overflow:'hidden', display:'-webkit-box', WebkitLineClamp:2, WebkitBoxOrient:'vertical' }}>
          {entry.note}
        </div>}
        {item && <div style={{ display:'flex', gap:4, marginTop:5 }}>
          {[item.category, item.material, item.gem!=='無'?item.gem:null].filter(Boolean).map((t,i) =>
            <span key={i} style={{ fontSize:10, padding:'2px 6px', borderRadius:'var(--r-pill)',
              background:'var(--gold-tint)', color:'var(--gold-deep)' }}>{t}</span>)}
        </div>}
      </div>
      {item && <div style={{ width:50, height:50, borderRadius:8, overflow:'hidden', flexShrink:0 }}>
        <JewelryPhoto item={item}/>
      </div>}
    </div>
  );
}

// ─── ClientProfileModal ───────────────────────────────────────────────────────
function ClientProfileModal({ clientEntries, allItems, isStaff, onClose }) {
  const [closing, setClosing] = useState(false);
  const close = () => { setClosing(true); setTimeout(onClose, 300); };
  const name = clientEntries[0]?.name || '';
  const id   = clientEntries[0]?.clientId || clientEntries[0]?.staffId || '';
  const favItems = clientEntries.map(e => allItems.find(i=>i.id===e.itemId)).filter(Boolean);
  // Infer preferences
  const tally = (key) => {
    const m={}; favItems.forEach(item=>{ const v=item[key]; if(v&&v!=='無') m[v]=(m[v]||0)+1; });
    return Object.entries(m).sort((a,b)=>b[1]-a[1]);
  };
  const topCat   = tally('category')[0];
  const topGem   = tally('gem')[0];
  const topColor = tally('color')[0];
  return (
    <div onClick={close} style={{ position:'absolute', inset:0, zIndex:60, display:'flex',
      flexDirection:'column', justifyContent:'flex-end', background:'rgba(0,0,0,0.45)',
      animation: closing?'fadeOut 0.28s ease forwards':'fadeIn 0.28s ease forwards' }}>
      <div onClick={e=>e.stopPropagation()} style={{ background:'var(--card)',
        borderRadius:'20px 20px 0 0', maxHeight:'82%',
        animation: closing?'slideDown 0.3s ease forwards':'slideUp 0.36s cubic-bezier(0.32,0.72,0,1) forwards',
        display:'flex', flexDirection:'column', overflow:'hidden' }}>
        <div style={{ display:'flex', justifyContent:'center', padding:'10px 0 0', flexShrink:0 }}>
          <div style={{ width:36, height:4, borderRadius:2, background:'var(--line)' }}/>
        </div>
        <div style={{ padding:'10px 16px 14px', borderBottom:'0.5px solid var(--line)', flexShrink:0,
          display:'flex', alignItems:'center', gap:12 }}>
          <div style={{ width:46, height:46, borderRadius:'50%', background:'var(--gold-bg)',
            border:'1.5px solid var(--gold)', display:'flex', alignItems:'center', justifyContent:'center',
            fontSize:20, fontFamily:'var(--font-display)', color:'var(--gold-deep)' }}>{name.slice(0,1)}</div>
          <div style={{ flex:1 }}>
            <div style={{ fontSize:17, fontFamily:'var(--font-display)', fontWeight:500 }}>{name}</div>
            <div style={{ fontSize:11, color:'var(--ink-3)' }}>
              {isStaff?'員工 · 選品專員':`客戶編號 ${id}`} · 共 {favItems.length} 件收藏
            </div>
          </div>
          <button onClick={close} style={{ background:'none',border:'none',fontSize:18,cursor:'pointer',color:'var(--ink-3)',padding:4 }}>✕</button>
        </div>
        <div className="hide-scrollbar" style={{ overflowY:'auto', flex:1, padding:'14px 16px' }}>
          {!isStaff && (topCat||topGem||topColor) && <div style={{ marginBottom:14 }}>
            <div style={{ fontSize:10, color:'var(--ink-3)', letterSpacing:'0.07em',
              textTransform:'uppercase', marginBottom:8 }}>偏好輪廓</div>
            <div style={{ display:'flex', gap:8 }}>
              {topCat   && <PrefChip label="類別" value={topCat[0]}   count={topCat[1]}/>}
              {topGem   && <PrefChip label="寶石" value={topGem[0]}   count={topGem[1]}/>}
              {topColor && <PrefChip label="金屬" value={topColor[0]} count={topColor[1]}/>}
            </div>
          </div>}
          <div style={{ fontSize:10, color:'var(--ink-3)', letterSpacing:'0.07em',
            textTransform:'uppercase', marginBottom:8 }}>{isStaff?'選品紀錄':'收藏紀錄'}</div>
          <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
            {clientEntries.map(entry => {
              const item = allItems.find(i=>i.id===entry.itemId);
              return (
                <div key={entry.id} style={{ display:'flex', gap:10, padding:'10px',
                  background:'var(--bg)', borderRadius:10 }}>
                  {item && <div style={{ width:54, height:54, borderRadius:8, overflow:'hidden', flexShrink:0 }}>
                    <JewelryPhoto item={item}/>
                  </div>}
                  <div style={{ flex:1, minWidth:0 }}>
                    {item && <div style={{ fontSize:13, fontWeight:600, color:'var(--ink)', marginBottom:2 }}>
                      {item.category} · {item.color} {item.material}
                    </div>}
                    <div style={{ fontSize:11, color:'var(--ink-4)', marginBottom:4 }}>{entry.date}</div>
                    {entry.note && <div style={{ fontSize:11, color:'var(--ink-2)', lineHeight:1.55 }}>{entry.note}</div>}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
        {!isStaff && <div style={{ padding:'12px 16px 24px', borderTop:'0.5px solid var(--line)', flexShrink:0 }}>
          <button style={{ width:'100%', height:44, borderRadius:'var(--r-btn)', background:'var(--gold)',
            border:'none', color:'white', fontSize:14, fontWeight:600, cursor:'pointer',
            fontFamily:'var(--font-body)', letterSpacing:'0.04em' }}>✦ 為此客戶推薦商品</button>
        </div>}
      </div>
    </div>
  );
}

// ─── TransactionRow ───────────────────────────────────────────────────────────
function TransactionRow({ tx, onEdit }) {
  const catBg = { '戒指':'#F2EAD5','項鍊':'#F2E2D8','耳環':'#EAF0F8','手環':'#EBF7EF','胸針':'#FEF0F0' };
  const ctMatch = tx.stoneSpec?.match(/([\d.]+)\s*ct/);
  const ct = ctMatch ? parseFloat(ctMatch[1]) : null;
  const ppc = ct ? Math.round(tx.price/ct) : null;
  const ppg = tx.metalWeight ? Math.round(tx.price/tx.metalWeight) : null;
  return (
    <div onClick={()=>onEdit&&onEdit(tx)} style={{ background:'var(--card)', borderRadius:'var(--r-card)',
      padding:'12px 14px', boxShadow:'var(--shadow)', cursor:'pointer' }}>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:7 }}>
        <div style={{ flex:1, marginRight:10 }}>
          <div style={{ display:'flex', alignItems:'center', gap:6, marginBottom:4 }}>
            <span style={{ fontSize:10, padding:'2px 7px', borderRadius:'var(--r-pill)',
              background:catBg[tx.category]||'var(--gold-tint)', color:'var(--ink-2)', fontWeight:500 }}>{tx.category}</span>
            <span style={{ fontSize:13, fontWeight:600, color:'var(--ink)' }}>{tx.item}</span>
          </div>
          <div style={{ fontSize:11, color:'var(--ink-3)', lineHeight:1.7 }}>
            {tx.material} · {tx.gem} · <span style={{ color:'var(--ink-2)' }}>{tx.stoneSpec}</span><br/>
            金屬 {tx.metalWeight}g · {tx.client}
          </div>
        </div>
        <div style={{ textAlign:'right', flexShrink:0 }}>
          <div style={{ fontSize:18, fontFamily:'var(--font-display)', fontWeight:600,
            color:'var(--gold-deep)', marginBottom:3 }}>NT${tx.price.toLocaleString()}</div>
          <div style={{ fontSize:11, color:'var(--ink-4)' }}>{tx.date}</div>
        </div>
      </div>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center',
        paddingTop:7, borderTop:'0.5px solid var(--line)' }}>
        <div style={{ display:'flex', gap:8 }}>
          {ppc && <span style={{ fontSize:10, color:'var(--gold-deep)' }}>每克拉 NT${ppc.toLocaleString()}</span>}
          {ppg && <span style={{ fontSize:10, color:'var(--ink-3)' }}>每克 NT${ppg.toLocaleString()}</span>}
          {tx.notes && <span style={{ fontSize:10, color:'var(--ink-3)' }}>· {tx.notes}</span>}
        </div>
        <button onClick={e=>{e.stopPropagation();onEdit&&onEdit(tx);}} style={{
          height:26, padding:'0 10px', borderRadius:'var(--r-pill)',
          border:'1px solid var(--line-gold)', background:'var(--gold-tint)',
          color:'var(--gold-deep)', fontSize:11, cursor:'pointer', fontFamily:'var(--font-body)' }}>修正</button>
      </div>
    </div>
  );
}

// ─── TransactionEditModal ─────────────────────────────────────────────────────
function TransactionEditModal({ tx, isNew, onClose, onSave }) {
  const [closing, setClosing] = useState(false);
  const [form, setForm] = useState(tx ? {...tx} : {
    item:'', category:'戒指', material:'18K金', gem:'鑽石',
    stoneSpec:'', metalWeight:'', price:'', date:new Date().toISOString().slice(0,10),
    notes:'', client:''
  });
  const close = () => { setClosing(true); setTimeout(onClose, 300); };
  const set = (k,v) => setForm(p=>({...p,[k]:v}));
  const ctMatch = String(form.stoneSpec).match(/([\d.]+)\s*ct/);
  const ct = ctMatch ? parseFloat(ctMatch[1]) : null;
  const ppc = ct && form.price ? Math.round(Number(form.price)/ct) : null;
  const ppg = form.metalWeight && form.price ? Math.round(Number(form.price)/Number(form.metalWeight)) : null;
  const fld = { width:'100%', height:40, padding:'0 10px', borderRadius:'var(--r-input)',
    border:'1px solid var(--line)', fontSize:13, fontFamily:'var(--font-body)',
    color:'var(--ink)', background:'var(--bg)', outline:'none' };
  const lbl = { fontSize:10, color:'var(--ink-3)', letterSpacing:'0.06em',
    textTransform:'uppercase', marginBottom:5, display:'block' };
  return (
    <div onClick={close} style={{ position:'absolute', inset:0, zIndex:50, display:'flex',
      flexDirection:'column', justifyContent:'flex-end', background:'rgba(0,0,0,0.4)',
      animation: closing?'fadeOut 0.28s ease forwards':'fadeIn 0.28s ease forwards' }}>
      <div onClick={e=>e.stopPropagation()} style={{ background:'var(--card)',
        borderRadius:'20px 20px 0 0', maxHeight:'88%', display:'flex', flexDirection:'column',
        animation: closing?'slideDown 0.3s ease forwards':'slideUp 0.36s cubic-bezier(0.32,0.72,0,1) forwards' }}>
        <div style={{ display:'flex', justifyContent:'center', padding:'10px 0 0', flexShrink:0 }}>
          <div style={{ width:36, height:4, borderRadius:2, background:'var(--line)' }}/>
        </div>
        <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between',
          padding:'10px 16px 12px', borderBottom:'0.5px solid var(--line)', flexShrink:0 }}>
          <div>
            <div style={{ fontSize:16, fontFamily:'var(--font-display)', fontWeight:500 }}>
              {isNew ? '新增成交記錄' : '修正成交記錄'}
            </div>
            <div style={{ fontSize:11, color:'var(--ink-3)', marginTop:2 }}>調整價格 · 規格 · 重量以優化未來報價</div>
          </div>
          <button onClick={close} style={{ background:'none',border:'none',fontSize:18,cursor:'pointer',color:'var(--ink-3)',padding:4 }}>✕</button>
        </div>
        <div className="hide-scrollbar" style={{ overflowY:'auto', flex:1, padding:'16px' }}>
          {(ppc||ppg) && <div style={{ background:'var(--gold-tint)', borderRadius:10,
            padding:'10px 14px', border:'1px solid var(--line-gold)', marginBottom:14 }}>
            <div style={{ fontSize:10, color:'var(--ink-3)', letterSpacing:'0.06em',
              textTransform:'uppercase', marginBottom:8 }}>即時基準換算</div>
            <div style={{ display:'flex', gap:20 }}>
              {ppc && <div><div style={{ fontSize:11, color:'var(--ink-2)' }}>每克拉</div>
                <div style={{ fontSize:17, fontFamily:'var(--font-display)', fontWeight:600,
                  color:'var(--gold-deep)' }}>NT${ppc.toLocaleString()}</div></div>}
              {ppg && <div><div style={{ fontSize:11, color:'var(--ink-2)' }}>每克（金屬）</div>
                <div style={{ fontSize:17, fontFamily:'var(--font-display)', fontWeight:600,
                  color:'var(--gold-deep)' }}>NT${ppg.toLocaleString()}</div></div>}
            </div>
          </div>}
          <div style={{ display:'flex', flexDirection:'column', gap:13 }}>
            {isNew && <div><label style={lbl}>品項描述</label>
              <input style={fld} placeholder="例：18K金 鑽石戒指" value={form.item} onChange={e=>set('item',e.target.value)}/></div>}
            <div><label style={lbl}>成交金額（NT$）</label>
              <input style={{...fld, fontSize:19, fontFamily:'var(--font-display)', fontWeight:600,
                borderColor:'var(--gold)', background:'var(--gold-tint)'}}
                type="number" value={form.price} onChange={e=>set('price',e.target.value)}/></div>
            <div><label style={lbl}>寶石規格（重量 / 尺寸 / 品質）</label>
              <input style={fld} placeholder="例：0.5ct H/VS1 或 6.2×8.4mm 帝王綠"
                value={form.stoneSpec} onChange={e=>set('stoneSpec',e.target.value)}/></div>
            <div><label style={lbl}>金屬重量（克）</label>
              <input style={fld} type="number" step="0.1" placeholder="例：3.2"
                value={form.metalWeight} onChange={e=>set('metalWeight',e.target.value)}/></div>
            <div><label style={lbl}>品質備注</label>
              <textarea style={{...fld, height:68, padding:'8px 10px', resize:'none', lineHeight:1.6}}
                placeholder="GIA/GRS證書、產地、特殊說明…" value={form.notes} onChange={e=>set('notes',e.target.value)}/></div>
            {isNew && <div><label style={lbl}>客戶</label>
              <input style={fld} placeholder="客戶姓名" value={form.client} onChange={e=>set('client',e.target.value)}/></div>}
          </div>
        </div>
        <div style={{ padding:'12px 16px 26px', flexShrink:0, borderTop:'0.5px solid var(--line)' }}>
          <button onClick={()=>{ onSave({...form, price:Number(form.price), metalWeight:Number(form.metalWeight)}); close(); }}
            style={{ width:'100%', height:46, borderRadius:'var(--r-btn)', background:'var(--gold)',
              border:'none', color:'white', fontSize:15, fontFamily:'var(--font-body)',
              fontWeight:600, cursor:'pointer' }}>
            {isNew ? '確認新增' : '確認修正'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── TagBadge ─────────────────────────────────────────────────────────────────
function TagBadge({ label, dim, onRemove }) {
  return (
    <span style={{ fontSize:11, padding:'3px 9px', borderRadius:'var(--r-pill)', fontWeight:500,
      background: dim?'var(--bg)':'var(--gold-tint)',
      color: dim?'var(--ink-3)':'var(--gold-deep)',
      border:`1px solid ${dim?'var(--line)':'var(--line-gold)'}`,
      display:'inline-flex', alignItems:'center', gap:4 }}>
      {label}
      {onRemove && <span onClick={e=>{e.stopPropagation();onRemove();}} style=
        {{ cursor:'pointer', opacity:0.5, fontSize:10 }}>✕</span>}
    </span>
  );
}

// ─── ClientCard ────────────────────────────────────────────────────────────────
function ClientCard({ client, items, onTap, onDiscover }) {
  const favItems = items.filter(i => (client.favItemIds||[]).includes(i.id)).slice(0,3);
  const extraCount = Math.max(0, (client.favItemIds||[]).length - 3);
  return (
    <div onClick={() => onTap(client)} style={{ background:'var(--card)', borderRadius:'var(--r-card)',
      padding:'13px 14px 11px', boxShadow:'var(--shadow)', cursor:'pointer' }}>
      <div style={{ display:'flex', alignItems:'flex-start', gap:11, marginBottom:9 }}>
        <div style={{ width:42, height:42, borderRadius:'50%', flexShrink:0,
          background:'var(--gold-bg)', border:'1.5px solid var(--gold)',
          display:'flex', alignItems:'center', justifyContent:'center',
          fontSize:17, fontFamily:'var(--font-display)', fontWeight:500,
          color:'var(--gold-deep)' }}>{client.name.slice(0,1)}</div>
        <div style={{ flex:1, minWidth:0 }}>
          <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start' }}>
            <div style={{ fontSize:15, fontWeight:600, color:'var(--ink)' }}>{client.name}</div>
            <div style={{ fontSize:10, color:'var(--ink-4)', flexShrink:0, marginLeft:8 }}>{client.date}</div>
          </div>
          <div style={{ fontSize:11, color:'var(--ink-3)', marginTop:2 }}>
            {client.lineId
              ? <span style={{ color:'#07B53B', fontWeight:500 }}>LINE 已記錄</span>
              : <span style={{ color:'var(--warning)' }}>LINE 未記錄</span>}
            {' · 共 '}{client.sessions}次選品
          </div>
        </div>
      </div>
      {client.tags.length > 0 && (
        <div style={{ display:'flex', gap:5, flexWrap:'wrap', marginBottom:9 }}>
          {client.tags.slice(0,5).map((t,i) => <TagBadge key={i} label={t}/>)}
          {client.tags.length > 5 && <span style={{ fontSize:10, color:'var(--ink-4)', alignSelf:'center' }}>+{client.tags.length-5}</span>}
        </div>
      )}
      <div style={{ display:'flex', alignItems:'center', gap:8,
        borderTop:'0.5px solid var(--line)', paddingTop:9 }}>
        <div style={{ display:'flex', gap:4, flex:1, alignItems:'center' }}>
          {favItems.map(item => (
            <div key={item.id} style={{ width:34, height:34, borderRadius:6, overflow:'hidden' }}>
              <JewelryPhoto item={item}/>
            </div>
          ))}
          {extraCount > 0 && (
            <div style={{ width:34, height:34, borderRadius:6, background:'var(--gold-tint)',
              display:'flex', alignItems:'center', justifyContent:'center',
              fontSize:10, color:'var(--gold-deep)', fontWeight:700 }}>+{extraCount}</div>
          )}
          {(client.favItemIds||[]).length === 0 && (
            <span style={{ fontSize:11, color:'var(--ink-4)' }}>尚無收藏</span>
          )}
        </div>
        <button onClick={e=>{e.stopPropagation();onDiscover(client);}} style={{
          height:32, padding:'0 14px', borderRadius:'var(--r-btn)', background:'var(--gold)',
          border:'none', color:'white', fontSize:12, fontFamily:'var(--font-body)',
          fontWeight:600, cursor:'pointer', flexShrink:0 }}>✦ 選品</button>
      </div>
    </div>
  );
}

// ─── Exports ──────────────────────────────────────────────────────────────────
window.JDB = {
  MOCK_ITEMS, MOCK_FAVORITES_DB, MOCK_TRANSACTIONS, MOCK_CLIENTS, STYLE_PROFILES,
  JewelryPhoto, TabBar, FilterPills, PhotoCard, PhotoDetailModal,
  LongPressMenu, StatCard, BarChart,
  Toast, EmptyState, AppHeader,
  PrefChip, FavEntry, TagBadge, ClientCard,
  TransactionRow, TransactionEditModal,
};
