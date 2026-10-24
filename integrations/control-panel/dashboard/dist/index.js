(() => {
  /* GraMem 控制台 2.0 — 记忆档案馆式界面。全部接口与 1.8.1 相同。 */
  const sdk = window.__HERMES_PLUGIN_SDK__;
  const R = sdk.React, h = R.createElement, Frag = R.Fragment;
  const {useState, useEffect, useRef, useMemo} = sdk.hooks;
  const VERSION = '2.0.0';
  const BASE = () => window.__HERMES_BASE_PATH__ || '';
  const json = v => JSON.stringify(v, null, 2);
  const cx = (...a) => a.filter(Boolean).join(' ');
  const date = value => value ? new Date(Number(value) * 1000).toLocaleString('zh-CN', {hour12: false}) : '—';
  const day = value => value ? new Date(Number(value) * 1000).toLocaleDateString('zh-CN') : '—';
  const num = v => v == null ? '—' : Number(v).toLocaleString('zh-CN');
  const kb = n => n == null ? '—' : n < 1024 * 1024 ? (n / 1024).toFixed(1) + ' KB' : (n / 1048576).toFixed(1) + ' MB';
  const pct = v => v == null ? '未评估' : (v * 100).toFixed(1) + '%';

  /* ---------- 词表 ---------- */
  const typeNames = {identity:'身份特征',occupation:'职业',health:'健康',current_location:'当前位置',preference:'偏好',interests:'兴趣',skill:'技能',technical_environment:'技术环境',project:'项目',relationship:'关系',episodic:'经历',knowledge:'知识',temporary:'临时情境',communication:'沟通习惯',capabilities:'能力',projects:'项目',stable_patterns:'长期习惯',uncertainties:'待确认'};
  const typeOptions = Object.entries(typeNames).filter(([k]) => !['communication','capabilities','projects','stable_patterns','uncertainties'].includes(k));
  const lifecycleNames = {temporary:'临时', normal:'普通', permanent:'长期保留'};
  const statusNames = {active:'有效', candidate:'审核中', superseded:'历史版本', archived:'归档', rejected:'已拒绝', forgotten:'已遗忘'};
  const jobNames = {pending:'待处理', processing:'处理中', completed:'已完成', done:'已完成', failed:'失败', redacted:'已脱敏'};
  const fieldNames = {id:'记录编号',content:'内容',fact:'事实',slot:'主题标识',type:'类型',class:'分类',status:'状态',lifecycle:'生命周期',strength:'强度',confidence:'置信度',importance:'重要性',created:'创建时间',updated:'更新时间',source:'来源',source_ids:'来源记录',metadata:'来源信息',relations:'事实关系',subject:'主体',predicate:'关系',object:'对象',version:'版本',tokens:'Token 数',ok:'完成',processed:'已处理',graph_synced:'图同步条数',sources:'来源任务',graph:'图同步任务',attempts:'重试次数',retry_at:'下次重试',principal:'记忆身份',action:'操作',path:'保存位置',count:'数量',graph_backup_required:'需要独立备份图服务',valid_from:'生效时间',valid_until:'失效时间',access_count:'交付次数',session:'会话',kind:'类别',error:'错误',lifecycle_changes:'生命周期变更',knowledge_processed:'文件解析',embedding_processed:'向量生成',review_processed:'自动审核',consolidated:'整理结果',profile:'画像',imported:'已导入',skipped:'已跳过'};
  const names = {
    recall_tokens:'召回 Token 预算',always_limit:'Always 最大条数',relevant_limit:'Relevant 最大条数',historical_limit:'历史最大条数',
    graph_recall_enabled:'自动关联图召回',graph_recall_hops:'自动图召回跳数',graph_recall_limit:'图补充事实最多条数',graph_recall_tokens:'图补充事实 Token 子预算',
    extraction_tokens:'提取输出预算',extraction_input_tokens:'提取证据预算',max_items:'每次提取最大条数',
    model:'提取 / 控制分类 / 画像模型',base_url:'供应商兼容 API 地址',api_key_env:'模型密钥变量名',embedding_model:'Embedding 模型',
    provider_preference:'文本路由偏好',embedding_provider_preference:'向量路由偏好',embedding_dimensions:'向量维度',embedding_revision:'向量空间版本',timeout:'模型请求超时（秒）',
    min_confidence:'最低置信度',min_future_use:'最低未来价值',min_stability:'最低稳定性',activate_threshold:'自动激活门槛',
    temporary_activate_threshold:'临时情境激活门槛',review_threshold:'候选审核门槛',archive_threshold:'归档强度门槛',permanent_threshold:'永久记忆强度门槛',
    permanent_access_count:'永久记忆交付次数',reinforcement:'每次交付强化值',decay_rates:'各类每日衰减率',
    graph_url:'FalkorDB 地址',graph_name:'图命名空间前缀',graph_password_env:'图密码变量名',owner_id:'Owner 稳定身份',
    aliases:'已核实账号身份绑定',trusted_cli_owner:'信任本机 CLI 为 Owner',auto_approve:'由模型自动审核所有候选',confirmation_types:'需要确认的事实类型',timezone:'记忆维护时区',capture_owner_in_groups:'记录群内所有者证据',chat_auto_archive:'自动归档并整理聊天记录',knowledge_auto_archive:'自动归档已授权所有者的附件',knowledge_ocr_languages:'OCR 语言（Tesseract）'
  };
  const settingGroups = [
    ['召回', '每次对话最多带入多少记忆。', ['recall_tokens','always_limit','relevant_limit','historical_limit']],
    ['关联图召回', '沿关系图补充相关事实。', ['graph_recall_enabled','graph_recall_hops','graph_recall_limit','graph_recall_tokens']],
    ['提取', '从对话里提炼事实的预算与门槛。', ['extraction_tokens','extraction_input_tokens','max_items','min_confidence','min_future_use','min_stability']],
    ['审核与生命周期', '候选如何生效，记忆如何强化、淡化与长期保留。', ['auto_approve','confirmation_types','activate_threshold','temporary_activate_threshold','review_threshold','archive_threshold','permanent_threshold','permanent_access_count','reinforcement','decay_rates','timezone']],
    ['聊天与附件', '自动归档的范围。', ['chat_auto_archive','knowledge_auto_archive','knowledge_ocr_languages']],
    ['图服务连接', '更换命名空间需要单独迁移。', ['graph_url','graph_name','graph_password_env']],
  ];
  const modelKeys = ['model','base_url','api_key_env','provider_preference','embedding_provider_preference','embedding_model','embedding_dimensions','embedding_revision','timeout'];
  const identityKeys = ['owner_id','aliases','trusted_cli_owner','capture_owner_in_groups'];
  const platforms = {telegram:['Telegram','填写数字用户 ID，例如 1000000001。不要填 @用户名或群组 ID。'],email:['邮件','填写完整邮箱地址，系统会忽略大小写。'],slack:['Slack','填写成员 ID（U 开头），可在成员资料的更多菜单中复制。'],teams:['Teams','填写用户的 Microsoft Entra 对象 ID，通常为 UUID。'],photon:['Photon','填写渠道事件中的发送者账号 ID。'],discord:['Discord','开启开发者模式，在用户资料中复制用户 ID。'],whatsapp:['WhatsApp','填写渠道识别的完整发送者 ID。'],signal:['Signal','填写渠道识别的发送者 ID。'],matrix:['Matrix','填写完整用户 ID，例如 @name:example.org。']};
  const scopeParts = s => { const p = String(s).split('\x1f'); return {kind: p[1], name: p[2] || s}; };
  const scopeKind = k => ({owner:'所有者', contact:'联系人', group:'群组'})[k] || k || '身份';
  const prettyScope = s => { const p = scopeParts(s); return scopeKind(p.kind) + '：' + p.name; };
  const prettySlot = s => String(s).startsWith('document:') ? '文件 ' + s.slice(9, 21) : s;

  /* ---------- 图标 ---------- */
  const paths = {
    overview:'M4 13h6V4H4z M14 20h6v-9h-6z M14 4h6v4h-6z M4 20h6v-4H4z',
    memory:'M7 3h10a2 2 0 0 1 2 2v15l-7-3.5L5 20V5a2 2 0 0 1 2-2z',
    profile:'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8z M4 21a8 8 0 0 1 16 0',
    book:'M5 4h9l5 5v11H5z M14 4v5h5 M8 13h8 M8 17h5',
    chat:'M4 5h16v11H10l-4 4v-4H4z',
    network:'M6 6m-2 0a2 2 0 1 0 4 0a2 2 0 1 0-4 0 M18 7m-2 0a2 2 0 1 0 4 0a2 2 0 1 0-4 0 M12 18m-2 0a2 2 0 1 0 4 0a2 2 0 1 0-4 0 M7.8 7l3.4 9 M16.3 8.4l-3.4 7.8 M8 6.3l8 .5',
    graph:'M5 18L12 5l7 13z M12 5v8 M5 18l7-5 7 5',
    identity:'M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z M2.5 20a6.5 6.5 0 0 1 13 0 M16 4.3a3.5 3.5 0 0 1 0 6.4 M18 14.5a6.5 6.5 0 0 1 3.5 5.5',
    sliders:'M4 6h10 M18 6h2 M4 12h4 M12 12h8 M4 18h12 M20 18h0 M14 4v4 M8 10v4 M16 16v4',
    tools:'M12 3v11 M8 10l4 4 4-4 M4 15v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4',
    palette:'M12 3a9 9 0 1 0 0 18c1 0 1.5-.7 1.5-1.5 0-1.2-1-1.5-1-2.5s.8-1.5 2-1.5H17a4 4 0 0 0 4-4c0-4.7-4-8.5-9-8.5z M7.5 11.5h0 M10 7.5h0 M14.5 7.5h0',
    logout:'M15 4h4v16h-4 M10 8l-4 4 4 4 M6 12h10',
    search:'M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14z M20 20l-4-4',
    refresh:'M20 11a8 8 0 0 0-14.6-4.5L4 8 M4 4v4h4 M4 13a8 8 0 0 0 14.6 4.5L20 16 M20 20v-4h-4',
    close:'M6 6l12 12 M18 6L6 18',
    plus:'M12 5v14 M5 12h14',
    upload:'M12 16V4 M7 9l5-5 5 5 M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3',
    download:'M12 4v12 M7 11l5 5 5-5 M4 20h16',
    check:'M5 12l5 5 9-10',
    left:'M15 6l-6 6 6 6', right:'M9 6l6 6-6 6',
    zoomin:'M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14z M20 20l-4-4 M8 11h6 M11 8v6',
    zoomout:'M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14z M20 20l-4-4 M8 11h6',
    target:'M12 20a8 8 0 1 0 0-16 8 8 0 0 0 0 16z M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z',
    light:'M12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8z M12 2v2 M12 20v2 M2 12h2 M20 12h2 M5 5l1.5 1.5 M17.5 17.5L19 19 M5 19l1.5-1.5 M17.5 6.5L19 5',
    dark:'M20 14.5A8 8 0 0 1 9.5 4 8.5 8.5 0 1 0 20 14.5z',
    system:'M3 5h18v11H3z M8 20h8 M12 16v4',
    edit:'M4 20h4L19 9l-4-4L4 16z M13 7l4 4',
    pause:'M8 5v14 M16 5v14',
    trash:'M4 7h16 M9 7V4h6v3 M6 7l1 13h10l1-13',
    spark:'M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z M19 16l.7 2 2 .7-2 .7-.7 2-.7-2-2-.7 2-.7z',
    menu:'M4 7h16 M4 12h16 M4 17h16',
    play:'M7 5l12 7-12 7z',
    expand:'M4 9V4h5 M20 9V4h-5 M4 15v5h5 M20 15v5h-5',
    alert:'M12 4l9 16H3z M12 10v4 M12 17h0'
  };
  const icon = (name, cls) => h('svg', {viewBox:'0 0 24 24', className:cx('gm-icon', cls), 'aria-hidden':true, fill:'none', stroke:'currentColor', strokeWidth:1.6, strokeLinecap:'round', strokeLinejoin:'round'}, h('path', {d: paths[name] || paths.overview}));

  /* ---------- 基础组件 ---------- */
  const btn = (label, onClick, o = {}) => {
    const {kind = 'tonal', icon: ic, small, className, ...rest} = o;
    return h('button', {type:'button', onClick, className:cx('gm-btn', 'gm-btn-' + kind, small && 'gm-sm', !label && 'gm-icon-only', className), ...rest}, ic ? icon(ic) : null, label ? h('span', null, label) : null);
  };
  const submit = (label, o = {}) => h('button', {type:'submit', className:cx('gm-btn', 'gm-btn-' + (o.kind || 'primary')), disabled:o.disabled}, o.icon ? icon(o.icon) : null, h('span', null, label));
  const input = (value, onChange, more = {}) => h('input', {className:'gm-input', value: value ?? '', onChange: e => onChange(e.target.value), ...more});
  const select = (value, onChange, opts, more = {}) => h('select', {className:'gm-input gm-select', value, onChange: e => onChange(e.target.value), ...more}, opts.map(o => h('option', {value:o[0], key:o[0]}, o[1])));
  const textarea = (value, onChange, more = {}) => h('textarea', {className:'gm-input', value: value ?? '', onChange: e => onChange(e.target.value), ...more});
  const field = (label, control, hint, more = {}) => h('label', {className:cx('gm-field', more.className), key: more.key}, h('span', {className:'gm-label'}, label), control, hint ? h('small', {className:'gm-hint'}, hint) : null);
  const check = (checked, onChange, label, more = {}) => h('label', {className:'gm-check', key: more.key}, h('input', {type:'checkbox', checked: !!checked, onChange: e => onChange(e.target.checked), disabled: more.disabled}), h('span', null, label));
  const note = (text, more = {}) => text ? h('p', {className:cx('gm-note', more.className), key: more.key}, text) : null;
  const badge = (text, tone = 'neutral', more = {}) => h('span', {className:'gm-badge gm-tone-' + tone, key: more.key, title: more.title}, text);
  const row = (...children) => h('div', {className:'gm-row'}, ...children);
  const empty = (text, action) => h('div', {className:'gm-empty'}, h('p', null, text), action || null);
  const panel = ({title, sub, actions, className, key, flat, id}, ...children) => h('section', {className:cx('gm-panel', flat && 'gm-flat', className), key: key || title, id},
    title || actions ? h('header', {className:'gm-panel-head'}, h('div', null, title ? h('h3', null, title) : null, sub ? h('p', {className:'gm-note'}, sub) : null), actions ? h('div', {className:'gm-row gm-tight'}, actions) : null) : null,
    ...children);
  const metric = (label, value, more = {}) => h('div', {className:cx('gm-metric', more.tone && 'gm-tone-' + more.tone), key: more.key || label}, h('span', null, label), h('strong', null, value));
  function Pager({page, size, total, onPage}) {
    const pages = Math.max(1, Math.ceil(total / size));
    if (!total) return null;
    return h('div', {className:'gm-pager'}, btn('', () => onPage(page - 1), {kind:'ghost', icon:'left', disabled: page <= 1, 'aria-label':'上一页'}),
      h('span', null, `第 ${page} / ${pages} 页，共 ${num(total)} 条`),
      btn('', () => onPage(page + 1), {kind:'ghost', icon:'right', disabled: page >= pages, 'aria-label':'下一页'}));
  }
  function Segmented({value, onChange, options, label}) {
    return h('div', {className:'gm-seg', role:'radiogroup', 'aria-label': label}, options.map(([k, text]) => h('button', {type:'button', key:k, role:'radio', 'aria-checked': value === k, className: value === k ? 'gm-on' : '', onClick: () => onChange(k)}, text)));
  }
  function Readable({value}) {
    if (value === null || value === undefined) return h('span', {className:'gm-note'}, '未设置');
    if (Array.isArray(value)) return value.length ? h('ul', {className:'gm-readable-list'}, value.map((v, i) => h('li', {key:i}, h(Readable, {value:v})))) : h('span', {className:'gm-note'}, '暂无记录');
    if (typeof value === 'object') return h('dl', {className:'gm-readable'}, Object.entries(value).map(([k, v]) => h('div', {key:k}, h('dt', null, fieldNames[k] || typeNames[k] || names[k] || k), h('dd', null, h(Readable, {value: ['created','updated','retry_at','valid_from','valid_until'].includes(k) && typeof v === 'number' ? date(v) : v})))));
    return h('span', null, typeof value === 'boolean' ? (value ? '是' : '否') : String(value));
  }
  const inspect = value => h('div', {className:'gm-inspect'}, h(Readable, {value}), h('details', {className:'gm-disclose'}, h('summary', null, '原始 JSON'), h('pre', {className:'gm-pre'}, json(value))));

  function Drawer({title, sub, onClose, children, wide}) {
    const closeRef = useRef(null), last = useRef(onClose); last.current = onClose;
    useEffect(() => {
      const prev = document.activeElement; closeRef.current?.focus();
      const k = e => { if (e.key === 'Escape') last.current(); };
      addEventListener('keydown', k);
      return () => { removeEventListener('keydown', k); prev?.focus?.(); };
    }, []);
    return h('div', {className:'gm-layer'}, h('div', {className:'gm-scrim', onClick: () => last.current()}),
      h('aside', {className:cx('gm-drawer', wide && 'gm-wide'), role:'dialog', 'aria-modal':true, 'aria-label': title},
        h('header', null, h('div', null, h('h3', null, title), sub ? h('p', {className:'gm-note'}, sub) : null), btn('', () => last.current(), {kind:'ghost', icon:'close', 'aria-label':'关闭', ref: closeRef})),
        h('div', {className:'gm-drawer-body'}, children)));
  }
  function Dialog({d, close}) {
    const ok = useRef(null);
    useEffect(() => { ok.current?.focus(); const k = e => { if (e.key === 'Escape') close(false); }; addEventListener('keydown', k); return () => removeEventListener('keydown', k); }, []);
    return h('div', {className:'gm-layer gm-center'}, h('div', {className:'gm-scrim', onClick: () => close(false)}),
      h('div', {className:'gm-dialog', role:'alertdialog', 'aria-modal':true, 'aria-labelledby':'gm-dialog-title'},
        h('h3', {id:'gm-dialog-title'}, d.title || (d.danger ? '这一步不能轻易撤回' : '请确认')),
        h('p', null, d.message),
        h('div', {className:'gm-row gm-end'}, btn(d.cancel || '取消', () => close(false), {kind:'ghost'}), btn(d.confirm || '继续', () => close(true), {kind: d.danger ? 'danger' : 'primary', ref: ok}))));
  }

  /* ---------- 力导向布局与画布交互 ---------- */
  function forceLayout(items, edges, {w = 1000, ht = 600, rep = 2000, len = 125, k = .012} = {}) {
    const n = items.map((it, i) => ({...it, x: w / 2 + ht * .42 * Math.cos(i * 2 * Math.PI / Math.max(1, items.length)), y: ht / 2 + ht * .36 * Math.sin(i * 2 * Math.PI / Math.max(1, items.length)), vx: 0, vy: 0}));
    const by = new Map(n.map(x => [x.id, x]));
    for (let it = 0; it < 200; it++) {
      n.forEach(a => { a.vx += (w / 2 - a.x) * .006; a.vy += (ht / 2 - a.y) * .006; });
      for (let i = 0; i < n.length; i++) for (let j = i + 1; j < n.length; j++) {
        const a = n[i], c = n[j], dx = a.x - c.x, dy = a.y - c.y, d = Math.max(10, Math.hypot(dx, dy)), f = rep / (d * d);
        a.vx += dx / d * f; c.vx -= dx / d * f; a.vy += dy / d * f; c.vy -= dy / d * f;
      }
      edges.forEach(([s, t]) => { const a = by.get(s), c = by.get(t); if (!a || !c || a === c) return; const dx = c.x - a.x, dy = c.y - a.y, d = Math.max(1, Math.hypot(dx, dy)), f = (d - len) * k; a.vx += dx / d * f; c.vx -= dx / d * f; a.vy += dy / d * f; c.vy -= dy / d * f; });
      n.forEach(a => { a.vx *= .65; a.vy *= .65; a.x = Math.min(w - 50, Math.max(50, a.x + a.vx)); a.y = Math.min(ht - 45, Math.max(45, a.y + a.vy)); });
    }
    return n;
  }
  function usePanZoom(onNodeMove) {
    const [zoom, setZoom] = useState(1), [pan, setPan] = useState({x:0, y:0});
    const svg = useRef(null), drag = useRef(null), st = useRef({});
    st.current = {zoom, pan, onNodeMove};
    const point = ev => { const p = svg.current.createSVGPoint(); p.x = ev.clientX; p.y = ev.clientY; return p.matrixTransform(svg.current.getScreenCTM().inverse()); };
    useEffect(() => {
      const el = svg.current; if (!el) return;
      const w = e => { e.preventDefault(); setZoom(z => Math.max(.3, Math.min(4, z * (e.deltaY > 0 ? .9 : 1.1)))); };
      el.addEventListener('wheel', w, {passive:false});
      return () => el.removeEventListener('wheel', w);
    }, []);
    const handlers = {
      onPointerDown: e => { if (e.target === e.currentTarget || e.target.getAttribute('data-bg')) { drag.current = {kind:'pan', start: point(e), pan: st.current.pan}; e.currentTarget.setPointerCapture(e.pointerId); } },
      onPointerMove: e => { const d = drag.current; if (!d) return; const p = point(e); if (d.kind === 'pan') setPan({x: d.pan.x + p.x - d.start.x, y: d.pan.y + p.y - d.start.y}); else { const s = st.current; s.onNodeMove(d.id, (p.x - s.pan.x) / s.zoom, (p.y - s.pan.y) / s.zoom); } },
      onPointerUp: () => { drag.current = null; }, onPointerCancel: () => { drag.current = null; },
    };
    const grab = (id, e) => { e.stopPropagation(); drag.current = {kind:'node', id}; svg.current.setPointerCapture(e.pointerId); };
    const reset = () => { setZoom(1); setPan({x:0, y:0}); };
    const controls = h('div', {className:'gm-canvas-tools'}, btn('', () => setZoom(z => Math.min(4, z * 1.2)), {kind:'ghost', small:true, icon:'zoomin', 'aria-label':'放大'}), btn('', () => setZoom(z => Math.max(.3, z / 1.2)), {kind:'ghost', small:true, icon:'zoomout', 'aria-label':'缩小'}), btn('', reset, {kind:'ghost', small:true, icon:'target', 'aria-label':'复位视图'}));
    return {svg, handlers, grab, reset, controls, transform: `translate(${pan.x},${pan.y}) scale(${zoom})`};
  }

  /* ---------- 主题 ---------- */
  function tonalTheme(seed, dark) {
    const c = /^#[0-9a-f]{6}$/i.test(seed) ? seed.slice(1) : '2e5e55';
    const r = parseInt(c.slice(0, 2), 16) / 255, g = parseInt(c.slice(2, 4), 16) / 255, bv = parseInt(c.slice(4, 6), 16) / 255;
    const max = Math.max(r, g, bv), min = Math.min(r, g, bv), d = max - min, l = (max + min) / 2;
    let hue = 0; if (d) hue = max === r ? ((g - bv) / d + (g < bv ? 6 : 0)) * 60 : max === g ? ((bv - r) / d + 2) * 60 : ((r - g) / d + 4) * 60;
    const sat = d ? d / (1 - Math.abs(2 * l - 1)) * 100 : 0;
    const t = (light, s) => `hsl(${hue.toFixed(1)} ${Math.min(80, s).toFixed(1)}% ${light}%)`;
    const a = Math.max(28, sat);
    return dark ? {
      '--gm-bg': t(8, 12), '--gm-rail': t(10, 12), '--gm-panel': t(12, 11), '--gm-sunk': t(9.5, 12), '--gm-raise': t(16, 11),
      '--gm-ink': t(91, 12), '--gm-ink-2': t(66, 8), '--gm-ink-3': t(50, 7), '--gm-line': t(22, 9), '--gm-line-2': t(17, 10),
      '--gm-accent': t(74, a * .8), '--gm-on-accent': t(12, 40), '--gm-accent-soft': t(21, a * .45), '--gm-on-soft': t(86, a * .6), '--gm-accent-line': t(40, a * .5),
      '--gm-ok': '#86c99d', '--gm-ok-soft': '#1c3325', '--gm-warn': '#e2bb6a', '--gm-warn-soft': '#3a2f17', '--gm-danger': '#f0a299', '--gm-danger-soft': '#3d1d1a', '--gm-shadow': '0 18px 50px rgba(0,0,0,.45)'
    } : {
      '--gm-bg': t(95.5, 14), '--gm-rail': t(92.5, 14), '--gm-panel': t(99.3, 20), '--gm-sunk': t(96.5, 14), '--gm-raise': t(90, 14),
      '--gm-ink': t(14, 22), '--gm-ink-2': t(37, 10), '--gm-ink-3': t(54, 8), '--gm-line': t(84, 12), '--gm-line-2': t(90.5, 13),
      '--gm-accent': t(30, a * .85), '--gm-on-accent': t(98, 30), '--gm-accent-soft': t(90, a * .45), '--gm-on-soft': t(22, a * .7), '--gm-accent-line': t(70, a * .45),
      '--gm-ok': '#24693f', '--gm-ok-soft': '#dcefe2', '--gm-warn': '#86590a', '--gm-warn-soft': '#f6ead0', '--gm-danger': '#a8281e', '--gm-danger-soft': '#f8e0dc', '--gm-shadow': '0 18px 50px rgba(20,30,28,.16)'
    };
  }
  const DEFAULT_SEED = '#2E5E55';
  const themePresets = [['#2E5E55','松针'], ['#34548C','靛青'], ['#7A4E2D','胡桃'], ['#5E4A86','暮紫'], ['#8C3B4A','茜红']];

  /* ---------- 总览 ---------- */
  function Overview({overview, scope, go, switchScope, refresh, pending}) {
    if (!overview) return empty('正在读取工作空间…');
    const s = overview.status || {}, mem = Object.fromEntries((s.memories || []).map(r => [r.status, r.count]));
    const order = ['active', 'candidate', 'superseded', 'archived', 'rejected'];
    const total = order.reduce((n, k) => n + (mem[k] || 0), 0);
    const jobs = s.jobs || [], recent = s.recent_jobs || [], usage = s.durable_usage || {};
    return h('div', {className:'gm-stack'},
      h('section', {className:'gm-ledger'},
        h('div', {className:'gm-ledger-text'},
          h('p', {className:'gm-ledger-title'}, total ? `这个工作空间保存了 ${num(total)} 条记忆，其中 ${num(mem.active || 0)} 条正在使用。` : '这个工作空间还没有记忆。'),
          note(total ? '下方色带是全部记忆的状态分布；新对话会在后台继续提炼、审核并写入。' : '与助手对话、上传文件或导入旧记忆后，记忆会出现在这里。')),
        total ? h('div', {className:'gm-dist', role:'img', 'aria-label':'记忆状态分布'}, order.filter(k => mem[k]).map(k => h('span', {key:k, className:'gm-dist-' + k, style:{flexGrow: mem[k]}, title: statusNames[k] + ' ' + mem[k]}))) : null,
        h('div', {className:'gm-dist-legend'}, order.map(k => h('button', {type:'button', key:k, className:'gm-legend-item', onClick: () => go('memories', {status:k})}, h('i', {className:'gm-dist-' + k}), h('span', null, statusNames[k]), h('strong', null, num(mem[k] || 0)))))),
      h('div', {className:'gm-grid-2'},
        panel({title:'运行状态', actions: btn('刷新', refresh, {kind:'ghost', small:true, icon:'refresh', disabled: pending})},
          h('dl', {className:'gm-facts'},
            h('div', null, h('dt', null, '模型处理'), h('dd', null, s.processor_available ? badge('可用', 'ok') : badge('未配置或不可用', 'warn'))),
            h('div', null, h('dt', null, '候选审核'), h('dd', null, s.automatic_approval ? '由模型自动审核' : '按类型人工确认')),
            h('div', null, h('dt', null, '图待同步'), h('dd', null, num(s.graph_pending))),
            h('div', null, h('dt', null, '后台累计 Token'), h('dd', null, `输入 ${num(usage.input_tokens)} · 输出 ${num(usage.output_tokens)}`)),
            h('div', null, h('dt', null, '数据目录'), h('dd', null, h('code', null, overview.home)))),
          note(overview.usage_note)),
        panel({title:'记忆身份', sub:'每个身份的记忆互相隔离。点选即可切换当前查看的身份。'},
          h('ul', {className:'gm-scope-list'}, (overview.scopes || []).map(x => { const p = scopeParts(x.principal), on = x.principal === scope; return h('li', {key:x.principal}, h('button', {type:'button', className:cx('gm-scope', on && 'gm-on'), onClick: () => switchScope(x.principal), 'aria-pressed': on},
            h('span', {className:'gm-scope-kind'}, scopeKind(p.kind)), h('span', {className:'gm-scope-name'}, p.name), h('span', {className:'gm-scope-count'}, num(x.count) + ' 条'))); })))),
      panel({title:'后台任务', sub:'对话提炼任务的持久队列。失败的任务会按计划自动重试。', actions: btn('查看全部队列', () => go('operations'), {kind:'ghost', small:true})},
        jobs.length ? h('div', {className:'gm-metrics'}, jobs.map(j => metric(jobNames[j.status] || j.status, num(j.count), {key:j.status, tone: j.status === 'failed' ? 'danger' : null}))) : note('队列为空。新的对话会在后台自动整理。'),
        recent.length ? h('div', {className:'gm-table-wrap'}, h('table', {className:'gm-table'}, h('thead', null, h('tr', null, ['创建', '会话', '状态', '重试', '说明'].map(v => h('th', {key:v}, v)))),
          h('tbody', null, recent.slice(0, 8).map(j => h('tr', {key:j.id}, h('td', {className:'gm-nowrap'}, date(j.created)), h('td', null, h('code', null, String(j.session || '—').slice(0, 28))), h('td', null, badge(jobNames[j.status] || j.status, j.status === 'failed' ? 'danger' : j.status === 'pending' ? 'warn' : 'neutral')), h('td', null, j.attempts), h('td', {className:'gm-note-cell'}, j.error ? String(j.error).slice(0, 120) : '—')))))) : null));
  }

  /* ---------- 记忆 ---------- */
  function Memories({api, scope, run, notify, ask, initial}) {
    const blank = {content:'', type:'knowledge', slot:'', action:'remember', relations:[]};
    const [q, setQ] = useState(''), [term, setTerm] = useState(''), [status, setStatus] = useState(initial?.status || 'active'), [page, setPage] = useState(1), [size, setSize] = useState(30);
    const [data, setData] = useState({items:[], total:0}), [loaded, setLoaded] = useState(false);
    const [chosen, setChosen] = useState([]), [form, setForm] = useState(blank), [details, setDetails] = useState(null), [semantic, setSemantic] = useState(null);
    const seq = useRef(0), editor = useRef(null);
    const load = async () => { const n = ++seq.current; const v = await api('/memories', {scope, q: term, status, page, size}); if (n === seq.current) { setData(v); setLoaded(true); } };
    useEffect(() => { setChosen([]); setDetails(null); setSemantic(null); setForm(blank); }, [scope]);
    useEffect(() => { run(load); return () => { seq.current++; }; }, [scope, term, status, page, size]);
    const op = (action, r) => run(async () => {
      if (['forget', 'suppress'].includes(action) && !await ask(`${action === 'forget' ? '永久遗忘' : '停用'}主题「${r.slot}」的所有版本与派生内容？${action === 'forget' ? '如果它来自导入的文档，整份文档的分块和派生事实也会一起遗忘。遗忘后旧内容无法恢复。' : '停用后可以在“画像与偏好”中解除。'}`, {danger: action === 'forget', confirm: action === 'forget' ? '遗忘' : '停用'})) return;
      await api('/operation', {}, {action, scope, id: r.id, authorization: true});
      notify(({forget:'已遗忘这个主题及其派生内容', suppress:'已停用这个主题', reject:'已拒绝这条候选', confirm:'已通过这条候选，它现在是有效记忆'})[action] || '操作完成');
      setDetails(null); await load();
    });
    const edit = (k, v) => setForm(prev => ({...prev, [k]: v}));
    const startEdit = r => { setChosen([r.id]); setForm({content: r.content, type: r.type, slot: r.slot, action:'update', relations: r.metadata?.relations || []}); setDetails(null); requestAnimationFrame(() => editor.current?.scrollIntoView({behavior:'smooth', block:'start'})); };
    const startMerge = () => { setForm(f => ({...f, action:'merge'})); requestAnimationFrame(() => editor.current?.scrollIntoView({behavior:'smooth', block:'start'})); };
    const saveFact = () => run(async () => {
      if (!form.content.trim()) throw Error('请填写事实内容。');
      if (form.action !== 'remember' && !chosen.length) throw Error('请先在列表中勾选要更新或合并的记忆。');
      if (form.action === 'merge' && chosen.length < 2) throw Error('合并至少需要勾选两条记忆。');
      if (form.relations.some(r => ['subject','predicate','object'].some(k => !r[k]?.trim()))) throw Error('请补全每条关系的主体、关系和对象，或移除空行。');
      await api('/operation', {}, {action: form.action, scope, content: form.content, type: form.type, slot: form.slot, targets: form.action === 'remember' ? [] : chosen, relations: form.relations});
      notify(({remember:'已保存新事实', update:'已保存新版本，旧版本保留在历史中', merge:'已合并为一条新事实'})[form.action]);
      setForm(blank); setChosen([]); await load();
    });
    const toggle = (id, on) => setChosen(v => on ? [...new Set([...v, id])] : v.filter(x => x !== id));
    const allOn = data.items.length > 0 && data.items.every(r => chosen.includes(r.id));
    const strength = v => Math.max(0, Math.min(1, Number(v) || 0));
    return h('div', {className:'gm-stack'},
      h('section', {className:'gm-panel'},
        h('form', {className:'gm-search', onSubmit: e => { e.preventDefault(); setPage(1); setTerm(q.trim()); setSemantic(null); }},
          h('div', {className:'gm-search-box'}, icon('search'), input(q, setQ, {placeholder:'按内容、主题标识、类型或编号查找', 'aria-label':'搜索记忆', maxLength:2000})),
          submit('查找'),
          btn('语义召回', () => run(async () => { if (!q.trim()) throw Error('请先在搜索框写下想召回的问题。'); setSemantic(await api('/recall', {scope, q, historical: ['superseded','archived'].includes(status)})); }), {icon:'spark', title:'按含义召回，模拟助手在对话中会看到的上下文'})),
        h('div', {className:'gm-filter-row'}, h(Segmented, {label:'记忆状态', value: status, onChange: v => { setStatus(v); setPage(1); setChosen([]); }, options: Object.entries(statusNames)}),
          h('div', {className:'gm-row gm-tight'}, term ? badge('筛选：' + term, 'accent') : null, term ? btn('清除', () => { setQ(''); setTerm(''); setPage(1); }, {kind:'link', small:true}) : null,
            select(String(size), v => { setSize(Number(v)); setPage(1); }, [['30','每页 30'],['50','每页 50'],['100','每页 100']], {'aria-label':'每页条数', className:'gm-input gm-select gm-compact'}),
            btn('', () => run(load), {kind:'ghost', icon:'refresh', 'aria-label':'刷新'}))),
        status === 'forgotten' ? note('已遗忘的内容受排除规则保护，不会出现在列表中。') : null),
      semantic ? panel({title:'语义召回预览', sub:`助手在对话中会收到约 ${num(semantic.tokens)} 个 Token 的以下内容。`, actions: btn('', () => setSemantic(null), {kind:'ghost', icon:'close', 'aria-label':'关闭召回预览'})},
        h('pre', {className:'gm-pre gm-recall'}, semantic.context || '没有召回到匹配的记忆。'),
        (semantic.memories || []).length ? h('details', {className:'gm-disclose'}, h('summary', null, `召回的 ${semantic.memories.length} 条记忆`), h('ul', {className:'gm-plain-list'}, semantic.memories.map((m, i) => h('li', {key: m.id || i}, h('span', null, m.content), ' ', badge(typeNames[m.type] || m.type || '记忆'))))) : null) : null,
      chosen.length ? h('div', {className:'gm-selection', role:'status'}, h('span', null, `已勾选 ${chosen.length} 条`),
        chosen.length === 1 ? btn('更新这条', () => { const r = data.items.find(x => x.id === chosen[0]); if (r) startEdit(r); else startMerge(); }, {small:true, icon:'edit'}) : btn('合并为一条', startMerge, {small:true, icon:'expand'}),
        btn('清除勾选', () => setChosen([]), {kind:'link', small:true})) : null,
      h('section', {className:'gm-panel gm-list-panel'},
        data.items.length ? h('div', {className:'gm-list-head'}, check(allOn, on => setChosen(v => on ? [...new Set([...v, ...data.items.map(r => r.id)])] : v.filter(id => !data.items.some(r => r.id === id))), '本页全选'), h('span', null, '强度 / 置信度')) : null,
        h('ol', {className:'gm-mem-list'}, data.items.map(r => h('li', {key:r.id, className:cx('gm-mem', chosen.includes(r.id) && 'gm-picked'), style:{'--s': strength(r.strength)}},
          h('span', {className:'gm-mem-bar', title:'强度 ' + Number(r.strength).toFixed(3), 'aria-hidden':true}),
          h('input', {type:'checkbox', checked: chosen.includes(r.id), onChange: e => toggle(r.id, e.target.checked), 'aria-label':'勾选这条记忆'}),
          h('div', {className:'gm-mem-main'},
            h('p', {className:'gm-mem-text'}, r.content),
            h('div', {className:'gm-mem-meta'}, badge(typeNames[r.type] || r.type), r.lifecycle && r.lifecycle !== 'normal' ? badge(lifecycleNames[r.lifecycle] || r.lifecycle, r.lifecycle === 'permanent' ? 'accent' : 'warn') : null, h('code', {title:'主题标识'}, r.slot), h('span', null, '更新于 ' + day(r.updated)), (r.metadata?.relations || []).length ? h('span', null, r.metadata.relations.length + ' 条关系') : null)),
          h('div', {className:'gm-mem-side'},
            h('span', {className:'gm-mem-num'}, Number(r.strength).toFixed(2), h('small', null, ' / ' + Number(r.confidence).toFixed(2))),
            h('div', {className:'gm-row gm-tight'},
              status === 'candidate' ? btn('通过', () => op('confirm', r), {small:true, kind:'primary', icon:'check'}) : null,
              status === 'candidate' ? btn('拒绝', () => op('reject', r), {small:true}) : null,
              status === 'active' ? btn('', () => startEdit(r), {small:true, kind:'ghost', icon:'edit', 'aria-label':'编辑', title:'编辑'}) : null,
              btn('', () => setDetails(r), {small:true, kind:'ghost', icon:'expand', 'aria-label':'详情', title:'来源与版本详情'})))))),
        !data.items.length ? empty(loaded ? (term ? `没有找到包含「${term}」的${statusNames[status]}记忆。` : `没有${statusNames[status]}记忆。`) : '正在读取…', status === 'active' && !term && loaded ? btn('写下第一条事实', () => editor.current?.scrollIntoView({behavior:'smooth'}), {small:true}) : null) : null,
        h(Pager, {page, size, total: data.total, onPage: p => { setPage(p); window.scrollTo?.({top:0, behavior:'smooth'}); }})),
      h('section', {className:'gm-panel', ref: editor},
        h('header', {className:'gm-panel-head'}, h('div', null, h('h3', null, ({remember:'写入新事实', update:'更新所选记忆', merge:'合并所选记忆'})[form.action]), h('p', {className:'gm-note'}, form.action === 'remember' ? '明确、可长期成立的一句话效果最好。' : `将基于勾选的 ${chosen.length} 条记忆生成新版本，旧版本和来源都会保留。`)),
          h(Segmented, {label:'写入方式', value: form.action, onChange: v => edit('action', v), options:[['remember','新增'],['update','更新'],['merge','合并']]})),
        textarea(form.content, v => edit('content', v), {maxLength:2000, rows:4, placeholder:'例如：我在新加坡工作，时区为 UTC+8。', 'aria-label':'事实内容'}),
        h('div', {className:'gm-form-grid'},
          field('类型', select(form.type, v => edit('type', v), typeOptions.some(([k]) => k === form.type) ? typeOptions : [...typeOptions, [form.type, form.type]])),
          field('主题标识', input(form.slot, v => edit('slot', v), {maxLength:200, placeholder:'留空自动生成'}), '同一主题的新事实会替换旧版本。')),
        h('details', {className:'gm-disclose', open: form.relations.length > 0 || undefined}, h('summary', null, `事实关系（${form.relations.length}）`), note('按“主体 / 关系 / 对象”填写，例如：我 / 使用 / Telegram。关系需要有这条事实支持。'), h(Relations, {value: form.relations, onChange: v => edit('relations', v)})),
        h('div', {className:'gm-row gm-end'}, form.content || form.action !== 'remember' ? btn('清空', () => { setForm(blank); setChosen([]); }, {kind:'ghost'}) : null, btn('保存事实', saveFact, {kind:'primary', disabled: !form.content.trim()}))),
      details ? h(Drawer, {title:'记忆详情', sub: statusNames[status] + ' · ' + (typeNames[details.type] || details.type), onClose: () => setDetails(null)},
        h('blockquote', {className:'gm-quote'}, details.content),
        h('div', {className:'gm-metrics'}, metric('强度', Number(details.strength).toFixed(3)), metric('置信度', Number(details.confidence).toFixed(2)), details.importance != null ? metric('重要性', Number(details.importance).toFixed(2)) : null),
        h('div', {className:'gm-row'}, status === 'active' ? btn('编辑', () => startEdit(details), {icon:'edit'}) : null, status === 'candidate' ? btn('通过', () => op('confirm', details), {kind:'primary', icon:'check'}) : null, status === 'candidate' ? btn('拒绝', () => op('reject', details)) : null,
          btn('停用主题', () => op('suppress', details), {icon:'pause'}), btn('遗忘主题', () => op('forget', details), {kind:'danger', icon:'trash'})),
        inspect(details)) : null);
  }
  function Relations({value, onChange}) {
    const edit = (i, k, v) => onChange(value.map((r, n) => n === i ? {...r, [k]: v} : r));
    return h('div', {className:'gm-relations'}, value.map((r, i) => h('div', {className:'gm-relation', key:i},
      ['subject','predicate','object'].map(k => input(r[k] || '', v => edit(i, k, v), {key:k, maxLength:500, placeholder: fieldNames[k], 'aria-label': `第 ${i + 1} 条关系的${fieldNames[k]}`})),
      btn('', () => onChange(value.filter((_, n) => n !== i)), {kind:'ghost', small:true, icon:'close', 'aria-label':`移除第 ${i + 1} 条关系`}))),
      btn('添加关系', () => onChange([...value, {subject:'', predicate:'', object:''}]), {disabled: value.length >= 50, small:true, icon:'plus'}));
  }

  /* ---------- 画像与偏好 ---------- */
  function Profiles({api, scope, run, notify, ask}) {
    const [data, setData] = useState({profile:{}, exclusions:[]}), [source, setSource] = useState(null), [form, setForm] = useState({content:'', type:'preference'}), [saving, setSaving] = useState(false), [loaded, setLoaded] = useState(false), seq = useRef(0);
    const load = async () => { const n = ++seq.current, v = await api('/profile', {scope}); if (n === seq.current) { setData(v); setLoaded(true); } };
    useEffect(() => { setData({profile:{}, exclusions:[]}); setSource(null); setForm({content:'', type:'preference'}); run(load); return () => { seq.current++; }; }, [scope]);
    const showSource = id => { const n = seq.current; run(async () => { const v = await api('/memories', {scope, q:id}); if (n !== seq.current) return; const r = v.items.find(x => x.id === id); if (!r) throw Error('这条来源已不可用，请刷新画像。'); setSource({...r, draft: r.content}); }); };
    const submitFact = (action, r) => run(async () => {
      setSaving(true);
      try {
        if (action === 'remember') { if (!form.content.trim()) throw Error('请填写你希望记住的事实或偏好。'); await api('/operation', {}, {action, scope, content: form.content.trim(), type: form.type}); setForm(v => ({...v, content:''})); }
        else if (action === 'update') { if (!r.draft.trim()) throw Error('事实内容不能为空。'); await api('/operation', {}, {action, scope, content: r.draft.trim(), type: r.type, slot: r.slot, targets:[r.id], relations: r.metadata?.relations || []}); setSource(null); }
        else { if (!await ask(`停用「${r.content}」所在主题的全部版本与派生内容？原记录会保留，可以在本页下方解除停用。`, {confirm:'停用'})) return; await api('/operation', {}, {action:'suppress', scope, id: r.id, authorization: true}); setSource(null); }
        notify(action === 'suppress' ? '已停用这个主题，画像已重新整理。' : action === 'remember' ? '已保存，画像会依据有效记忆更新。' : '已保存来源修改，画像已依据有效记忆更新。'); await load();
      } finally { setSaving(false); }
    });
    const entries = Object.entries(data.profile || {}).filter(([, items]) => Array.isArray(items) && items.length);
    const exState = {suppressed:['已停用','warn'], deleted:['已遗忘','danger'], active:['已授权','ok']};
    return h('div', {className:'gm-stack'},
      panel({title:'画像', sub:'由有效记忆归纳而成。每条结论都能追溯到来源，修改来源即可修正画像。', actions:[btn('刷新', () => run(load), {key:'r', kind:'ghost', small:true, icon:'refresh'}), btn('用模型重新归纳', () => run(async () => { if (!await ask('调用模型重新归纳当前身份的画像？这会产生模型费用。', {confirm:'重新归纳'})) return; await api('/operation', {}, {action:'reflect', scope}); notify('画像已重新归纳'); await load(); }), {key:'m', small:true, icon:'spark'})]},
        entries.length ? h('div', {className:'gm-portrait'}, entries.map(([cat, items]) => h('section', {className:'gm-portrait-col', key:cat}, h('h4', null, typeNames[cat] || cat, h('span', null, items.length)),
          h('ul', null, items.map((item, i) => { const ids = (item.source_ids || [item.id]).filter(Boolean); return h('li', {key:i}, h('p', null, item.fact || String(item)), ids.length ? h('div', {className:'gm-row gm-tight'}, ids.map((id, n) => btn(ids.length > 1 ? `来源 ${n + 1}` : '查看来源', () => showSource(id), {key:id, kind:'link', small:true}))) : null); }))))) : empty(loaded ? '还没有可以归纳画像的有效记忆。可以在下方写下第一条偏好。' : '正在读取画像…'),
        h('details', {className:'gm-disclose'}, h('summary', null, '画像原始 JSON'), h('pre', {className:'gm-pre'}, json(data.profile)))),
      h('div', {className:'gm-grid-2'},
        panel({title:'补充身份特征与偏好', sub:'用一句明确的话描述自己，保存到当前记忆身份。'},
          h('form', {className:'gm-stack-sm', onSubmit: e => { e.preventDefault(); submitFact('remember'); }},
            field('类型', select(form.type, v => setForm(f => ({...f, type:v})), typeOptions.filter(([k]) => ['identity','occupation','preference','interests','skill','project','relationship'].includes(k)))),
            field('内容', textarea(form.content, v => setForm(f => ({...f, content:v})), {rows:3, maxLength:2000, placeholder:'例如：回答时我偏好先给结论，再解释细节。'})),
            h('div', {className:'gm-row gm-end'}, submit('保存这条事实', {disabled: saving || !form.content.trim()})))),
        panel({title:'遗忘、停用与重新授权', sub:'停用可以解除；遗忘不会恢复旧内容，重新授权只允许记录新的事实。'},
          data.exclusions.length ? h('ul', {className:'gm-ex-list'}, data.exclusions.map(x => h('li', {key:x.slot},
            h('div', null, h('code', null, prettySlot(x.slot)), h('small', null, '更新于 ' + date(x.updated))),
            badge(...(exState[x.state] || [x.state, 'neutral'])),
            x.state === 'suppressed' ? btn('解除停用', () => run(async () => { await api('/operation', {}, {action:'reactivate', scope, slot: x.slot}); notify('已解除停用'); await load(); }), {small:true}) :
            x.state === 'deleted' ? btn('允许记录新事实', () => run(async () => { if (!await ask(`明确授权重新记住「${prettySlot(x.slot)}」的新事实？旧值不会恢复。`, {confirm:'授权'})) return; await api('/operation', {}, {action:'reauthorize', scope, slot: x.slot, authorization: true}); notify('已授权记录新事实'); await load(); }), {small:true}) : h('span')))) : empty('没有遗忘或停用记录。'))),
      source ? h(Drawer, {title:'编辑来源事实', sub:(typeNames[source.type] || source.type) + '，修改会生成新版本并保留旧版本。', onClose: () => setSource(null)},
        field('事实内容', textarea(source.draft, v => setSource(s => ({...s, draft:v})), {rows:5, maxLength:2000})),
        h('div', {className:'gm-row'}, btn('保存修改', () => submitFact('update', source), {kind:'primary', disabled: saving || source.draft.trim() === source.content}), btn('停用此主题', () => submitFact('suppress', source), {kind:'danger', disabled: saving, icon:'pause'})),
        h('details', {className:'gm-disclose'}, h('summary', null, '来源与版本信息'), inspect(source))) : null);
  }

  /* ---------- 知识库 ---------- */
  const docStatus = {queued:['等待解析','warn'], processing:['正在解析','warn'], ready:['可检索','ok'], partial:['部分已解析','warn'], needs_parser:['需要解析组件','danger'], failed:['解析失败','danger'], empty:['没有提取到文字','neutral']};
  const ACCEPT = '.txt,.md,.csv,.json,.pdf,.docx,.png,.jpg,.jpeg,.webp,.gif,.tif,.tiff,.bmp';
  function Knowledge({api, scope, run, notify, ask, download}) {
    const [q, setQ] = useState(''), [term, setTerm] = useState(''), [page, setPage] = useState(1), [history, setHistory] = useState(false);
    const [data, setData] = useState({items:[], total:0}), [loaded, setLoaded] = useState(false), [hits, setHits] = useState(null), [detail, setDetail] = useState(null);
    const [description, setDescription] = useState(''), [title, setTitle] = useState(''), [uploads, setUploads] = useState([]), [over, setOver] = useState(false), seq = useRef(0), fileRef = useRef(null);
    const load = async () => { const n = ++seq.current, v = await api('/knowledge', {scope, q: term, page, historical: history}); if (n === seq.current) { setData(v); setLoaded(true); } };
    useEffect(() => { run(load); return () => { seq.current++; }; }, [scope, term, page, history]);
    useEffect(() => { if (!data.items.some(r => ['queued','processing'].includes(r.status))) return; const t = setTimeout(() => run(load), 3000); return () => clearTimeout(t); }, [data]);
    const open = (id, start = 0, append = false) => run(async () => { const v = await api('/knowledge/' + id, {scope, start}); setDetail(d => append && d && d.document.id === v.document.id ? {...v, items:[...d.items, ...v.items]} : v); });
    const control = (action, r) => run(async () => {
      if (action === 'forget' && !await ask(`永久遗忘「${r.name}」的这个版本？原件、文本分块和派生事实都会删除；已有备份和渠道历史需要另行处理。`, {danger:true, confirm:'遗忘'})) return;
      if (action === 'suppress' && !await ask(`暂停使用「${r.name}」的这个版本？可以在“画像与偏好”中解除停用。`, {confirm:'停用'})) return;
      await api('/knowledge/control', {}, {scope, id: r.id, action}); setDetail(null); setHits(null); await load();
      notify(({retry:'已重新排队解析', forget:'已遗忘这个文件版本', suppress:'已停用这个文件版本'})[action]);
    });
    const send = files => {
      files = [...files]; if (!files.length) return;
      const list = files.map((f, i) => ({id: Date.now() + '-' + i, name: f.name, size: f.size, state: f.size > 20000000 ? 'error' : 'waiting', msg: f.size > 20000000 ? '超过 20 MB' : ''}));
      setUploads(list);
      run(async () => {
        let ok = 0;
        for (let i = 0; i < files.length; i++) {
          if (list[i].state === 'error') continue;
          setUploads(u => u.map((x, n) => n === i ? {...x, state:'uploading'} : x));
          try {
            const encoded = await new Promise((resolve, reject) => { const rd = new FileReader(); rd.onload = () => resolve(String(rd.result).split(',')[1] || ''); rd.onerror = () => reject(Error('文件读取失败')); rd.readAsDataURL(files[i]); });
            await api('/knowledge/upload', {}, {scope, filename: files[i].name, data: encoded, description, ...(files.length === 1 && title.trim() ? {title: title.trim()} : {})});
            ok++; setUploads(u => u.map((x, n) => n === i ? {...x, state:'done'} : x));
          } catch (e) { setUploads(u => u.map((x, n) => n === i ? {...x, state:'error', msg: e.message || String(e)} : x)); }
        }
        if (ok) { notify(`已保存 ${ok} 个文件，后台正在解析`); setDescription(''); setTitle(''); }
        setPage(1); await load();
      });
    };
    return h('div', {className:'gm-stack'},
      h('section', {className:'gm-panel'},
        h('div', {className:'gm-upload-grid'},
          h('label', {className:cx('gm-drop', over && 'gm-over'), onDragOver: e => { e.preventDefault(); setOver(true); }, onDragLeave: () => setOver(false), onDrop: e => { e.preventDefault(); setOver(false); send(e.dataTransfer.files); }},
            icon('upload', 'gm-drop-icon'), h('strong', null, '拖入文件，或点击选择'), h('small', null, 'TXT、MD、CSV、JSON、PDF、DOCX 与常见图片，单个不超过 20 MB。原件长期保存，文字在后台提取。'),
            h('input', {ref: fileRef, type:'file', multiple:true, accept: ACCEPT, className:'gm-visually-hidden', onChange: e => { const f = [...(e.target.files || [])]; e.target.value = ''; send(f); }})),
          h('div', {className:'gm-stack-sm'},
            field('标题', input(title, setTitle, {maxLength:200, placeholder:'可选，仅在上传单个文件时使用'})),
            field('说明', textarea(description, setDescription, {rows:3, maxLength:2000, placeholder:'例如：角色设定参考图，以后绘图时使用'}), '说明会和文件一起被检索，图片尤其需要。'))),
        uploads.length ? h('ul', {className:'gm-upload-list'}, uploads.map(u => h('li', {key:u.id}, h('span', null, u.name), h('small', null, kb(u.size)), badge(({waiting:'等待', uploading:'上传中', done:'已保存', error:'失败'})[u.state], ({done:'ok', error:'danger', uploading:'accent'})[u.state] || 'neutral'), u.msg ? h('small', {className:'gm-danger-text'}, u.msg) : null))) : null),
      h('section', {className:'gm-panel'},
        h('form', {className:'gm-search', onSubmit: e => { e.preventDefault(); setPage(1); setTerm(q.trim()); setHits(null); }},
          h('div', {className:'gm-search-box'}, icon('search'), input(q, setQ, {placeholder:'文件名、标题，或想在正文里找的内容', 'aria-label':'搜索知识库', maxLength:2000})),
          submit('查找文件'),
          btn('搜索正文', () => run(async () => { if (!q.trim()) throw Error('请先输入要在正文中搜索的内容。'); setHits(await api('/knowledge/search', {scope, q, historical: history})); }), {icon:'book'})),
        h('div', {className:'gm-filter-row'}, check(history, v => { setHistory(v); setPage(1); setHits(null); }, '包含旧版本'), h('div', {className:'gm-row gm-tight'}, term ? badge('筛选：' + term, 'accent') : null, term ? btn('清除', () => { setQ(''); setTerm(''); setPage(1); }, {kind:'link', small:true}) : null, btn('', () => run(load), {kind:'ghost', icon:'refresh', 'aria-label':'刷新'})))),
      hits ? panel({title:`正文搜索：${hits.items.length} 处匹配`, sub:'结果来自原文或 OCR 识别，OCR 可能有误，请对照原件。', actions: btn('', () => setHits(null), {kind:'ghost', icon:'close', 'aria-label':'关闭搜索结果'})},
        hits.items.length ? h('ol', {className:'gm-hits'}, hits.items.map((x, i) => h('li', {key: x.memory_id + '-' + i}, h('div', {className:'gm-hit-head'}, h('strong', null, x.name), h('small', null, `v${x.version}，${x.page ? '第 ' + x.page + ' 页' : '正文或说明'}，分块 ${x.chunk}`), btn('打开', () => open(x.document_id, x.chunk), {kind:'link', small:true})), h('p', null, x.text)))) : empty('没有匹配的已索引内容。')) : null,
      h('section', {className:'gm-panel gm-list-panel'},
        data.items.length ? h('ul', {className:'gm-docs'}, data.items.map(r => { const st = docStatus[r.status] || [r.status, 'neutral']; return h('li', {key:r.id, className:'gm-doc'},
          h('div', {className:'gm-doc-ext', 'aria-hidden':true}, (r.name.split('.').pop() || '').slice(0, 4).toUpperCase()),
          h('div', {className:'gm-doc-main'}, h('button', {type:'button', className:'gm-doc-title', onClick: () => open(r.id)}, r.title || r.name), r.description ? h('p', null, r.description) : null,
            h('div', {className:'gm-mem-meta'}, badge(st[0], st[1]), h('span', null, `v${r.version}`), h('span', null, kb(r.size)), h('span', null, `${r.chunks} 个分块`), h('span', null, day(r.created))), r.error ? h('small', {className:'gm-danger-text'}, r.error) : null),
          h('div', {className:'gm-row gm-tight'},
            ['failed','needs_parser','empty'].includes(r.status) ? btn('重试解析', () => control('retry', r), {small:true, icon:'refresh'}) : null,
            h('a', {href: download(r.id), download:'', className:'gm-btn gm-btn-ghost gm-sm gm-icon-only', 'aria-label':'下载原件', title:'下载原件'}, icon('download')),
            btn('', () => control('suppress', r), {small:true, kind:'ghost', icon:'pause', 'aria-label':'停用', title:'停用'}),
            btn('', () => control('forget', r), {small:true, kind:'ghost', icon:'trash', className:'gm-danger-hover', 'aria-label':'遗忘', title:'遗忘'}))); })) :
          empty(loaded ? (term ? `没有找到与「${term}」相关的文件。` : '还没有文件。拖入第一个文件开始建立知识库。') : '正在读取…'),
        h(Pager, {page, size:30, total: data.total, onPage: setPage})),
      detail ? h(Drawer, {wide:true, title: detail.document.title || detail.document.name, sub:`v${detail.document.version} · ${detail.document.name}`, onClose: () => setDetail(null)},
        h('div', {className:'gm-row'}, h('a', {href: download(detail.document.id), download:'', className:'gm-btn gm-btn-tonal'}, icon('download'), h('span', null, '下载原件')), detail.document.previous ? btn('阅读上个版本', () => open(detail.document.previous), {kind:'ghost'}) : null),
        detail.items.length ? h('ol', {className:'gm-reader'}, detail.items.map(it => h('li', {key: it.memory_id}, h('small', null, `${it.page ? '第 ' + it.page + ' 页' : '正文或说明'} · 分块 ${it.chunk} · ${it.method}`), h('p', null, it.text)))) : empty('原件已保存，目前没有可阅读的文字。'),
        detail.next !== null && detail.next !== undefined ? btn('继续阅读', () => open(detail.document.id, detail.next, true), {className:'gm-block'}) : null) : null);
  }

  /* ---------- 聊天档案 ---------- */
  function ChatsView({api, scope, run, download}) {
    const [overview, setOverview] = useState(null), [q, setQ] = useState(''), [platform, setPlatform] = useState(''), [session, setSession] = useState(''), [after, setAfter] = useState(''), [before, setBefore] = useState('');
    const [data, setData] = useState({items:[], total:0, next:null}), [detail, setDetail] = useState(null), [start, setStart] = useState(0);
    const [processing, setProcessing] = useState(null), [submitting, setSubmitting] = useState(false);
    const polling = useRef(0), lastJob = useRef(null), reloadResult = useRef(null), jobRequests = useRef(0), filt = useRef({});
    filt.current = {q, platform, session, after, before};
    const filters = (o = {}) => { const f = {...filt.current, ...o}; return {scope, q: f.q, platform: f.platform, session: f.session, ...(f.after ? {after: Date.parse(f.after) / 1000} : {}), ...(f.before ? {before: Date.parse(f.before) / 1000} : {})}; };
    const load = (offset = 0, o) => run(async () => { setStart(offset); const [ov, list] = await Promise.all([api('/chats/overview', filters(o)), api('/chats', {...filters(o), start: offset})]); setOverview(ov); setData(list); });
    reloadResult.current = () => load(start);
    useEffect(() => {
      load(); setProcessing(null); setSubmitting(false); lastJob.current = null; let closed = false, timer; const n = ++polling.current;
      const poll = async () => {
        const stamp = jobRequests.current;
        try {
          const result = await api('/chats/process', {scope}); if (closed || n !== polling.current) return;
          if (stamp === jobRequests.current) { setProcessing(result); const wasActive = ['importing','processing'].includes(lastJob.current?.state); lastJob.current = result.job; if (result.job?.state === 'completed' && wasActive) reloadResult.current(); }
        } catch (e) { if (!closed && n === polling.current && stamp === jobRequests.current) setProcessing(v => ({...v, poll_error:'暂时无法读取进度，稍后会自动重试。'})); }
        if (!closed) timer = setTimeout(poll, 3000);
      };
      poll(); return () => { closed = true; clearTimeout(timer); polling.current++; };
    }, [scope]);
    const processAll = (retry = false) => { const n = polling.current; setSubmitting(true); jobRequests.current++; run(async () => { try { const result = await api(retry ? '/chats/process/retry' : '/chats/process', {}, {scope}, 'POST'); if (n === polling.current) { lastJob.current = result.job; setProcessing(result); } } finally { jobRequests.current++; if (n === polling.current) setSubmitting(false); } }); };
    const job = processing?.job, active = ['importing','processing'].includes(job?.state);
    const open = id => run(async () => setDetail(await api('/chats/' + id, {scope})));
    const applyFilter = o => { if (o.q !== undefined) setQ(o.q); if (o.platform !== undefined) setPlatform(o.platform); if (o.session !== undefined) setSession(o.session); load(0, o); };
    const clearFilters = () => { setQ(''); setPlatform(''); setSession(''); setAfter(''); setBefore(''); load(0, {q:'', platform:'', session:'', after:'', before:''}); };
    const platformKeys = Object.keys(overview?.platforms || {});
    const sessions = (overview?.sessions || []).map(s => typeof s === 'string' ? {id:s} : {id: s.session || s.id, count: s.count, platform: s.platform}).filter(s => s.id);
    const jobTitle = job ? ({importing:'正在补齐历史原话', processing: job.error === 'model_unavailable' ? '等待模型配置' : job.retrying ? '正在整理，部分记录等待重试' : '正在整理历史', completed:'历史整理已完成', failed:'整理遇到问题，可以重试'})[job.state] : '';
    const filtered = q || platform || session || after || before;
    return h('div', {className:'gm-stack'},
      h('div', {className:'gm-grid-2 gm-grid-wide-left'},
        panel({title:'整理进度', sub:'处理当前身份在任务启动前的所有可验证历史：补齐原件，生成摘要、主题和记忆网连接。关闭页面后仍会继续。'},
          job ? h('div', {className:'gm-job', role:'status'},
            h('div', {className:'gm-job-head'}, h('strong', null, jobTitle), h('span', null, `${num(job.done)} / ${num(job.total)}`)),
            h('progress', {max: Math.max(1, job.total), value: job.state === 'completed' ? Math.max(1, job.total) : job.done, 'aria-label':'历史聊天整理进度'}),
            h('div', {className:'gm-metrics gm-metrics-sm'}, Object.entries({working:'处理中', retrying:'等待重试', remaining:'未完成', imported:'补齐原话'}).map(([k, n]) => metric(n, num(job[k] ?? 0), {key:k}))),
            note('范围截至 ' + date(job.cutoff) + (job.state === 'completed' && job.total === 0 ? '，没有需要补处理的记录。' : '。')),
            job.protected > 0 ? note(`已完成的记录中有 ${job.protected} 条按禁提或删除规则不展示。`) : null,
            job.error === 'history_processing_failed' ? note('读取历史时遇到问题，已有原件和进度都已保留。') : null,
            job.error === 'history_unavailable' ? note('没有找到宿主历史数据库，本次只处理现有聊天档案。') : null) : note(`当前档案有 ${processing?.pending ?? '—'} 条待整理记录；提交后会同时扫描更早的历史。`),
          processing?.archive_enabled === false ? note('聊天自动归档已关闭。在“行为与模型”中开启后才能提交整理任务。', {className:'gm-warn-text'}) : null,
          processing?.model_available === false ? note('整理需要可用的 Chat 模型，模型恢复后会自动继续。', {className:'gm-warn-text'}) : null,
          processing?.poll_error ? note(processing.poll_error, {className:'gm-warn-text'}) : null,
          h('div', {className:'gm-row'}, btn(active ? '正在处理全部历史' : '处理全部未整理记录', () => processAll(), {kind:'primary', icon:'play', disabled: submitting || active || processing?.archive_enabled === false}),
            job && (job.state === 'failed' || job.retrying > 0 || job.error === 'model_unavailable') ? btn('重试未完成部分', () => processAll(true), {disabled: submitting, icon:'refresh'}) : null)),
        panel({title:'档案概况', sub:'点选平台、会话或主题即可筛选。'},
          h('div', {className:'gm-metrics gm-metrics-sm'}, metric('对话', num(overview?.turns)), metric('会话', num(overview?.sessions?.length)), ...(overview?.jobs || []).map(j => metric(({ready:'已归档', pending:'等待整理', working:'整理中', silent:'已禁提', redacted:'已删除'})[j.status] || j.status, num(j.count), {key:'j' + j.status}))),
          platformKeys.length ? h('div', {className:'gm-chips'}, platformKeys.map(p => h('button', {type:'button', key:p, className:cx('gm-chip', platform === p && 'gm-on'), onClick: () => applyFilter({platform: platform === p ? '' : p})}, p, h('span', null, overview.platforms[p])))) : null,
          (overview?.topics || []).length ? h(Frag, null, h('h4', {className:'gm-subhead'}, '主题'), h('div', {className:'gm-chips'}, overview.topics.map(t => h('button', {type:'button', key:t.topic, className:cx('gm-chip', q === t.topic && 'gm-on'), onClick: () => applyFilter({q: q === t.topic ? '' : t.topic})}, t.topic, h('span', null, t.count))))) : null)),
      (overview?.timeline || []).length ? panel({title:'最近的主题时间线', sub:'每条摘要都能追溯到双方原话。'},
        h('ol', {className:'gm-timeline'}, overview.timeline.slice(-12).reverse().map((it, i) => h('li', {key: it.summary_id + '-' + i},
          h('time', null, day(it.created)), h('div', null, h('div', {className:'gm-hit-head'}, h('strong', null, it.topic), h('small', null, it.platform + '，' + (it.speaker === 'assistant' ? '助手的讨论或建议' : '用户陈述')), btn('原话', () => open(it.turn_id), {kind:'link', small:true})), h('p', null, it.text)))))) : null,
      h('section', {className:'gm-panel'},
        h('form', {className:'gm-search', onSubmit: e => { e.preventDefault(); load(); }},
          h('div', {className:'gm-search-box'}, icon('search'), input(q, setQ, {placeholder:'查找过去讨论过的内容', 'aria-label':'搜索聊天'})), submit('查询')),
        h('div', {className:'gm-form-grid gm-form-grid-4'},
          field('平台', select(platform, setPlatform, [['', '全部平台'], ...[...new Set([...platformKeys, ...(platform ? [platform] : [])])].map(p => [p, p])])),
          field('会话', input(session, setSession, {placeholder:'会话 ID，可选', list:'gm-sessions'}), null),
          field('开始', input(after, setAfter, {type:'datetime-local'})),
          field('结束', input(before, setBefore, {type:'datetime-local'}))),
        h('datalist', {id:'gm-sessions'}, sessions.slice(0, 200).map(s => h('option', {key:s.id, value:s.id}))),
        filtered ? h('div', {className:'gm-row'}, btn('清除筛选', clearFilters, {kind:'link', small:true})) : null,
        data.items.length ? h('ol', {className:'gm-turns'}, data.items.map(it => h('li', {key: it.id},
          h('div', {className:'gm-hit-head'}, badge(it.platform, 'accent'), h('small', null, date(it.created)), h('code', {title:'会话'}, String(it.session).slice(0, 40)), it.audio_count ? badge(`语音 ${it.audio_count}`) : null, btn('查看原话', () => open(it.id), {kind:'link', small:true})),
          h('p', {className:'gm-turn-user'}, it.user), it.assistant ? h('p', {className:'gm-turn-bot'}, it.assistant) : null))) : empty('没有可展示的记录。正在整理、禁提或已删除的内容不会出现。'),
        data.total ? h('div', {className:'gm-pager'}, btn('', () => load(Math.max(0, start - 20)), {kind:'ghost', icon:'left', disabled: start === 0, 'aria-label':'上一页'}), h('span', null, `第 ${num(start + 1)}–${num(start + data.items.length)} 条，共 ${num(data.total)} 条`), btn('', () => load(data.next), {kind:'ghost', icon:'right', disabled: data.next === null || data.next === undefined, 'aria-label':'下一页'})) : null),
      detail ? h(Drawer, {wide:true, title:'原话', sub: detail.platform + ' · ' + date(detail.created), onClose: () => setDetail(null)},
        h('div', {className:'gm-row'}, h('a', {className:'gm-btn gm-btn-tonal', href: download(detail.id), download:''}, icon('download'), h('span', null, detail.original_export_filtered ? '下载原话副本' : '下载原件 JSON')),
          detail.audio?.length ? h('a', {className:'gm-btn gm-btn-ghost', href: download(detail.id, 'bundle'), download:''}, icon('download'), h('span', null, '聊天与语音原件包')) : null),
        h('div', {className:'gm-convo'}, h('div', {className:'gm-say gm-say-user'}, h('small', null, '用户'), h('p', null, detail.user)), h('div', {className:'gm-say gm-say-bot'}, h('small', null, '助手'), h('p', null, detail.assistant))),
        ...(detail.audio || []).map(a => h('article', {className:'gm-audio', key:a.id}, h('h4', null, '助手语音 · ' + a.name),
          note(a.state === 'stored' ? `原件已长期保留 · ${a.mime} · ${kb(a.size)}` : '音频原件尚未保存：' + (({missing_source:'原缓存已缺失', unsupported_path:'来源不在本身份的音频缓存内', invalid_audio:'音频格式无法验证', invalid_size:'音频大小不符合保留限制', unavailable_source:'来源暂时无法读取'})[a.error] || a.error || '原因未知')),
          a.state === 'stored' ? h('audio', {controls:true, preload:'none', src: download(detail.id, 'audio/' + a.id + '/original'), 'aria-label':'播放助手语音原件'}) : null,
          a.state === 'stored' ? h('a', {className:'gm-btn gm-btn-link gm-sm', href: download(detail.id, 'audio/' + a.id + '/original'), download: a.name}, '下载语音原件') : null,
          note(a.transcript ? '合成文案来自' + (a.transcript_basis === 'tts_spoken_text' ? '合成工具返回的文本' : '原始 TTS 调用输入') + '，不是语音识别结果或投递回执。' : '没有可靠的合成文案，不推测语音内容。'),
          a.sha256 ? h('code', {className:'gm-hash'}, 'SHA-256 ' + a.sha256) : null)),
        h('dl', {className:'gm-facts'}, h('div', null, h('dt', null, '会话'), h('dd', null, h('code', null, detail.session))), h('div', null, h('dt', null, '原件 SHA-256'), h('dd', null, h('code', {className:'gm-hash'}, detail.sha256))))) : null);
  }

  /* ---------- 记忆网 ---------- */
  const netKinds = {chat:'原话', summary:'摘要', memory:'记忆', document:'文件', topic:'主题', entity:'实体', context:'会话', event:'事件', audio:'助手语音'};
  const netColors = {chat:'#4579bc', summary:'#8a5fc0', memory:'#c0743a', document:'#3f8a69', topic:'#b8507f', entity:'#4f8394', context:'#7a8090', event:'#8d7440', audio:'#4a6fb4'};
  const netStates = {active:'有效', reinforced:'已强化', decaying:'衰减中', permanent:'永久', archived:'已归档', superseded:'已被更新', candidate:'待审核', rejected:'未通过', ready:'已整理', queued:'等待解析', indexed:'已索引', stored:'原件已保留', missing:'原件缺失'};
  const netRel = {SUPPORTED_BY:'原文支持', DERIVED_FROM:'派生自', CONTAINS:'包含', ABOUT:'共同主题', MENTIONS:'提及', RECORDED_FOR:'记忆事件', NEXT:'时间先后', HAS_AUDIO:'关联语音'};
  function NetworkView({api, scope, run}) {
    const [q, setQ] = useState(''), [data, setData] = useState({nodes:[], edges:[]}), [selected, setSelected] = useState(null), [hops, setHops] = useState('2'), [historical, setHistorical] = useState(true), [metricKey, setMetric] = useState('effective_strength');
    const [hidden, setHidden] = useState([]), [pos, setPos] = useState([]), seq = useRef(0);
    const load = (id = '', query = q) => { const n = ++seq.current; run(async () => { const r = await api('/network', {scope, q: query, id, hops, historical}); if (n === seq.current) { setData(r); setSelected(null); } }); };
    useEffect(() => { load(); return () => { seq.current++; }; }, [scope, historical]);
    useEffect(() => { setPos(forceLayout(data.nodes, data.edges.map(e => [e.source, e.target]), {rep:2600, len:150, k:.01})); }, [data]);
    const pz = usePanZoom((id, x, y) => setPos(p => p.map(n => n.id === id ? {...n, x, y} : n)));
    useEffect(() => pz.reset(), [data]);
    const visible = pos.filter(n => !hidden.includes(n.kind)), by = new Map(visible.map(n => [n.id, n]));
    const linked = new Set(selected ? [selected.id, ...data.edges.filter(e => e.source === selected.id || e.target === selected.id).flatMap(e => [e.source, e.target])] : visible.map(n => n.id));
    const kindsPresent = [...new Set(data.nodes.map(n => n.kind))];
    return h('div', {className:'gm-stack'},
      h('section', {className:'gm-panel'},
        h('form', {className:'gm-search', onSubmit: e => { e.preventDefault(); load(); }},
          h('div', {className:'gm-search-box'}, icon('search'), input(q, setQ, {placeholder:'主题、项目或内容', 'aria-label':'搜索记忆网'})),
          select(hops, setHops, [['1','1 跳'],['2','2 跳'],['3','3 跳']], {'aria-label':'展开跳数', className:'gm-input gm-select gm-compact'}), submit('探索'), btn('全部', () => { setQ(''); load('', ''); }, {kind:'ghost'})),
        h('div', {className:'gm-filter-row'},
          h('div', {className:'gm-chips'}, kindsPresent.map(k => h('button', {type:'button', key:k, className:cx('gm-chip', !hidden.includes(k) && 'gm-on'), 'aria-pressed': !hidden.includes(k), onClick: () => setHidden(v => v.includes(k) ? v.filter(x => x !== k) : [...v, k])}, h('i', {className:'gm-dot', style:{background: netColors[k]}}), netKinds[k] || k))),
          h('div', {className:'gm-row gm-tight'}, check(historical, setHistorical, '含历史与待审核'), select(metricKey, setMetric, [['effective_strength','大小：当前强度'],['confidence','大小：置信度'],['importance','大小：重要性']], {'aria-label':'节点大小依据', className:'gm-input gm-select gm-compact'})))),
      h('div', {className:'gm-canvas-layout'},
        h('section', {className:'gm-canvas'},
          pz.controls,
          h('svg', {ref: pz.svg, viewBox:'0 0 1000 600', className:'gm-svg', 'aria-label':'聊天、文件、事件与记忆的记忆网', ...pz.handlers},
            h('rect', {x:-5000, y:-5000, width:10000, height:10000, fill:'transparent', 'data-bg':'1'}),
            h('g', {transform: pz.transform},
              data.edges.map(e => { const a = by.get(e.source), c = by.get(e.target); if (!a || !c) return null; return h('line', {key:e.id, x1:a.x, y1:a.y, x2:c.x, y2:c.y, className:'gm-edge', strokeDasharray: ['SUPPORTED_BY','DERIVED_FROM'].includes(e.relation) ? undefined : '4 5', opacity: linked.has(a.id) && linked.has(c.id) ? .85 : .12}); }),
              visible.map(n => { const r = n[metricKey] == null ? 6 : 6 + 12 * Math.sqrt(Math.max(0, Math.min(1, n[metricKey]))), on = selected?.id === n.id; return h('g', {key:n.id, transform:`translate(${n.x},${n.y})`, className:'gm-node', role:'button', tabIndex:0, 'aria-label': (netKinds[n.kind] || n.kind) + ' ' + n.label, opacity: linked.has(n.id) ? 1 : .22,
                onClick: () => setSelected(s => s?.id === n.id ? null : n), onKeyDown: e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSelected(n); } }, onPointerDown: e => pz.grab(n.id, e)},
                h('title', null, (netKinds[n.kind] || n.kind) + '：' + n.label + '\n置信度 ' + pct(n.confidence) + '，当前强度 ' + pct(n.effective_strength)),
                h('circle', {r, fill: netColors[n.kind] || '#888', fillOpacity: n.confidence == null ? .7 : .35 + .65 * n.confidence, stroke: on ? 'var(--gm-ink)' : netColors[n.kind], strokeWidth: on ? 3 : 1.2, strokeDasharray: ['archived','superseded','candidate','rejected'].includes(n.status) ? '3 3' : undefined}),
                visible.length <= 40 || n.kind !== 'event' || on ? h('text', {y: r + 14, textAnchor:'middle', className:'gm-node-label'}, n.label.length > 14 ? n.label.slice(0, 14) + '…' : n.label) : null); }))),
          !data.nodes.length ? h('div', {className:'gm-canvas-empty'}, '这里还没有可连接的内容。换个关键词，或点“全部”。') : null,
          h('p', {className:'gm-canvas-foot'}, `${data.nodes.length} / ${data.total_nodes ?? 0} 个节点，${data.edges.length} 条连接，权重更新于 ${date(data.as_of)}${data.truncated ? '。内容较多，可通过搜索或沿节点展开查看更多。' : ''}`)),
        h('aside', {className:'gm-panel gm-inspector'},
          selected ? h(Frag, null,
            h('div', {className:'gm-row gm-tight'}, h('i', {className:'gm-dot', style:{background: netColors[selected.kind]}}), h('strong', null, netKinds[selected.kind] || selected.kind), badge(netStates[selected.status] || selected.status || '记录')),
            h('p', {className:'gm-inspector-label'}, selected.label), note(selected.session || selected.slot || ''),
            h('div', {className:'gm-metrics gm-metrics-sm'}, ...Object.entries({confidence:'置信度', strength:'本体强度', effective_strength:'当前强度', importance:'重要性'}).map(([k, n]) => metric(n, pct(selected[k]), {key:k}))),
            note(({memory:'权重直接来自记忆本体。', memory_reference:'事件引用对应记忆的当前权重，不代表事件发生时的权重。', related_memories:'权重汇总自关联记忆，不代表这条记录中所有说法的可信度。', unassessed:'已有原始记录，尚无可关联的记忆权重。'})[selected.weight_basis]),
            note(`生命周期 ${netStates[selected.lifecycle] || selected.lifecycle || '—'}，${selected.support_count ?? 0} 条关联记忆${selected.created ? '，记录于 ' + date(selected.created) : ''}${selected.valid_until ? '，有效期至 ' + date(selected.valid_until) : ''}`),
            btn('沿此节点展开', () => load(selected.id), {kind:'primary', icon:'expand', className:'gm-block'}),
            h('ul', {className:'gm-plain-list gm-links'}, data.edges.filter(e => e.source === selected.id || e.target === selected.id).map(e => { const other = data.nodes.find(n => n.id === (e.source === selected.id ? e.target : e.source)); return h('li', {key:e.id}, h('small', null, netRel[e.relation] || e.relation), other ? h('button', {type:'button', className:'gm-linklike', onClick: () => setSelected(other)}, other.label) : null); })))
          : h(Frag, null, h('h3', null, '读图方式'), note('节点大小表示所选权重，颜色深浅表示置信度，虚线轮廓是历史或待审核内容。实线连接是来源与派生，虚线连接包括时间先后，不代表因果。'), note('拖动节点调整位置，拖动空白处平移，滚轮缩放。点一个节点查看详情并沿它继续展开。')))));
  }

  /* ---------- 关系图 ---------- */
  function Graph({api, scope, run}) {
    const [q, setQ] = useState(''), [filter, setFilter] = useState(''), [hops, setHops] = useState('1'), [historical, setHistorical] = useState(false);
    const [data, setData] = useState({items:[]}), [selected, setSelected] = useState(null), [source, setSource] = useState(null), [pos, setPos] = useState([]), seq = useRef(0);
    const load = () => { const n = ++seq.current; run(async () => { const r = await api('/graph', {q, hops, historical, scope}); if (n === seq.current) { setData(r); setSelected(null); setSource(null); } }); };
    useEffect(() => { load(); return () => { seq.current++; }; }, [scope]);
    useEffect(() => { const labels = [...new Set(data.items.flatMap(e => [e.subject, e.object]))]; setPos(forceLayout(labels.map(id => ({id})), data.items.map(e => [e.subject, e.object]), {rep:2600, len:170, k:.014})); }, [data.items]);
    const pz = usePanZoom((id, x, y) => setPos(p => p.map(n => n.id === id ? {...n, x, y} : n)));
    useEffect(() => pz.reset(), [data.items]);
    const by = new Map(pos.map(n => [n.id, n]));
    const matches = name => !filter || name.toLocaleLowerCase().includes(filter.toLocaleLowerCase());
    const edges = data.items.filter(e => !selected || e.subject === selected || e.object === selected);
    const showSource = e => run(async () => { const v = await api('/memories', {scope, q: e.memory_id, status: e.valid_until ? 'superseded' : 'active'}); if (!v.items.length && historical) { const old = await api('/memories', {scope, q: e.memory_id, status:'archived'}); setSource({edge:e, items: old.items}); } else setSource({edge:e, items: v.items}); });
    return h('div', {className:'gm-stack'},
      h('section', {className:'gm-panel'},
        h('form', {className:'gm-search', onSubmit: e => { e.preventDefault(); load(); }},
          h('div', {className:'gm-search-box'}, icon('search'), input(q, setQ, {placeholder:'从一个实体出发，例如 GraMem', maxLength:2000, 'aria-label':'搜索图实体'})),
          select(hops, setHops, [['1','1 跳'],['2','2 跳'],['3','3 跳']], {'aria-label':'跳数', className:'gm-input gm-select gm-compact'}), submit('搜索关系')),
        h('div', {className:'gm-filter-row'}, check(historical, setHistorical, '包含已失效的历史关系'), h('div', {className:'gm-search-box gm-search-sm'}, icon('target'), input(filter, setFilter, {placeholder:'在当前图中高亮', 'aria-label':'高亮实体'}))),
        data.healthy === false ? h('p', {className:'gm-alert gm-tone-danger'}, icon('alert'), '图服务无法连接。空结果不代表没有关系，请检查“行为与模型”中的图服务连接。') : null,
        data.truncated ? note('结果达到单次显示上限（199 条关系），请搜索更具体的实体。') : null),
      h('section', {className:'gm-canvas'},
        pz.controls,
        h('svg', {ref: pz.svg, viewBox:'0 0 1000 600', className:'gm-svg', role:'img', 'aria-label':'可拖动的记忆关系图', ...pz.handlers},
          h('defs', null, h('marker', {id:'gm-arrow', viewBox:'0 0 10 10', refX:9, refY:5, markerWidth:6, markerHeight:6, orient:'auto-start-reverse'}, h('path', {d:'M 0 0 L 10 5 L 0 10 z', fill:'var(--gm-accent)'}))),
          h('rect', {x:-5000, y:-5000, width:10000, height:10000, fill:'transparent', 'data-bg':'1'}),
          h('g', {transform: pz.transform},
            data.items.map((e, i) => { const a = by.get(e.subject), c = by.get(e.object); if (!a || !c) return null; const dx = c.x - a.x, dy = c.y - a.y, d = Math.max(1, Math.hypot(dx, dy)), x1 = a.x + dx / d * 21, y1 = a.y + dy / d * 21, x2 = c.x - dx / d * 24, y2 = c.y - dy / d * 24;
              const related = !selected || e.subject === selected || e.object === selected;
              const sib = data.items.filter(x => (x.subject === e.subject && x.object === e.object) || (x.subject === e.object && x.object === e.subject)), off = (sib.indexOf(e) - (sib.length - 1) / 2) * 30;
              const mx = (x1 + x2) / 2 - dy / d * off, my = (y1 + y2) / 2 + dx / d * off;
              return h('g', {key:`${e.id || 'edge'}-${i}`, opacity: related ? .9 : .1, className:'gm-rel', onClick: () => showSource(e)},
                h('path', {d: a === c ? `M ${a.x - 12} ${a.y - 18} C ${a.x - 75} ${a.y - 95},${a.x + 75} ${a.y - 95},${a.x + 12} ${a.y - 18}` : `M ${x1} ${y1} Q ${mx} ${my} ${x2} ${y2}`, className: e.valid_until ? 'gm-rel-old' : 'gm-rel-line', strokeDasharray: e.valid_until ? '5 4' : undefined, fill:'none', markerEnd:'url(#gm-arrow)'}, h('title', null, `${e.subject} → ${e.predicate} → ${e.object}\n点击查看来源记忆`)),
                h('text', {x: mx, y: my - 5, textAnchor:'middle', className:'gm-edge-label'}, e.predicate)); }),
            pos.map(n => { const on = selected === n.id; return h('g', {key:n.id, transform:`translate(${n.x},${n.y})`, className:'gm-node', opacity: matches(n.id) ? 1 : .18, tabIndex:0, role:'button', 'aria-label': n.id, 'aria-pressed': on,
              onKeyDown: e => { if (e.key === 'Enter') setSelected(s => s === n.id ? null : n.id); }, onClick: () => setSelected(s => s === n.id ? null : n.id), onPointerDown: e => pz.grab(n.id, e)},
              h('circle', {r: on ? 24 : 19, className: on ? 'gm-ent gm-on' : 'gm-ent'}), h('text', {y:36, textAnchor:'middle', className:'gm-node-label'}, n.id.length > 20 ? n.id.slice(0, 20) + '…' : n.id), h('title', null, n.id)); }))),
        !pos.length ? h('div', {className:'gm-canvas-empty'}, '没有找到关系。换一个实体、增加跳数，或包含历史关系。') : null,
        h('p', {className:'gm-canvas-foot'}, `${pos.length} 个实体，${data.items.length} 条关系。箭头表示方向，虚线是已失效的历史关系；点击连线查看来源。`)),
      panel({title: selected ? `与「${selected}」相关的关系` : '全部关系', sub: selected ? null : '点选图中的实体，只看与它相连的关系。', actions: selected ? btn('显示全部', () => setSelected(null), {kind:'ghost', small:true}) : null},
        edges.length ? h('div', {className:'gm-table-wrap'}, h('table', {className:'gm-table'}, h('thead', null, h('tr', null, ['主体', '关系', '对象', '有效时间', ''].map((v, i) => h('th', {key:i}, v)))),
          h('tbody', null, edges.map((e, i) => h('tr', {key:`${e.id || 'edge'}-${i}`, className: e.valid_until ? 'gm-muted-row' : ''}, h('td', null, e.subject), h('td', null, h('strong', null, e.predicate)), h('td', null, e.object), h('td', {className:'gm-nowrap'}, `${day(e.valid_from)} → ${e.valid_until ? day(e.valid_until) : '至今'}`), h('td', null, btn('来源', () => showSource(e), {kind:'link', small:true}))))))) : empty('没有关系可显示。')),
      source ? h(Drawer, {title:'来源记忆', sub:`${source.edge.subject} → ${source.edge.predicate} → ${source.edge.object}`, onClose: () => setSource(null)},
        source.items.length ? source.items.map((m, i) => h('div', {key: m.id || i, className:'gm-stack-sm'}, h('blockquote', {className:'gm-quote'}, m.content), inspect(m))) : empty('来源记忆不可见：它可能已被停用、遗忘或归档。')) : null);
  }

  /* ---------- 账号与身份 ---------- */
  function Identities({data, save, onDirty, ask}) {
    const [values, setValues] = useState(data.values), [form, setForm] = useState({platform:'telegram', account:'', target: data.values.owner_id, verified:false}), [editing, setEditing] = useState(null), [problem, setProblem] = useState(''), [saving, setSaving] = useState(false);
    useEffect(() => { setValues(data.values); }, [data]);
    const aliases = values.aliases || {}, dirty = json(values) !== json(data.values);
    useEffect(() => { onDirty?.(dirty || !!form.account.trim()); }, [dirty, form.account]);
    useEffect(() => () => onDirty?.(false), []);
    const targets = [...new Set([values.owner_id, ...Object.values(aliases)])];
    const edit = (k, v) => { setForm(f => ({...f, [k]: v})); setProblem(''); };
    const resetForm = () => { setEditing(null); setForm(f => ({...f, account:'', verified:false})); setProblem(''); };
    const stage = e => {
      e.preventDefault();
      const account = form.account.trim(), platform = form.platform.trim().toLowerCase(), target = (form.target === '__new__' ? form.newTarget || '' : form.target).trim();
      if (!platform || !account || !target) return setProblem('请填写平台、账号和共用身份。');
      if (platform === 'telegram' && !/^[1-9]\d*$/.test(account)) return setProblem('Telegram 请填写正整数用户 ID，例如 1000000001；@用户名和群组 ID 不能用于身份关联。');
      if (platform === 'email' && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(account)) return setProblem('请填写完整邮箱地址。');
      const key = platform + ':' + (platform === 'email' ? account.toLowerCase() : account);
      if (key !== editing && Object.hasOwn(aliases, key)) return setProblem('这个账号已经关联过了，请直接编辑已有条目。');
      if (!form.verified) return setProblem('请先确认你已核实这个账号属于所选身份。');
      const next = {...aliases}; if (editing) delete next[editing]; next[key] = target;
      setValues(v => ({...v, aliases: next})); resetForm();
    };
    const label = t => t === values.owner_id ? `我（${t}）` : t;
    const groups = {}; Object.entries(aliases).forEach(([k, t]) => { (groups[t] = groups[t] || []).push(k); });
    return h('div', {className:'gm-stack'},
      h('section', {className:'gm-panel gm-identity-hero'},
        h('div', null, h('h3', null, '同一个人，同一份记忆'), note('把同一个人在不同平台上已核实的账号关联起来，他们会共用一份记忆。未关联的账号按独立联系人处理；关联只影响以后的识别，旧的独立记忆不会自动搬移。')),
        h('div', {className:'gm-owner-card'}, h('small', null, '我的稳定身份'), h('code', null, values.owner_id), h('small', null, '用于定位已有记忆，修改需要单独迁移。'))),
      h('div', {className:'gm-grid-2 gm-grid-wide-left'},
        panel({title:'已关联账号', sub:`${Object.keys(aliases).length} 个账号，按共用身份分组`},
          Object.keys(groups).length ? Object.entries(groups).map(([t, keys]) => h('div', {key:t, className:'gm-id-group'}, h('h4', null, label(t)),
            h('ul', {className:'gm-accounts'}, keys.map(key => { const i = key.indexOf(':'), p = key.slice(0, i), acc = key.slice(i + 1); return h('li', {key, className: editing === key ? 'gm-on' : ''},
              h('span', {className:'gm-platform'}, platforms[p]?.[0] || p), h('code', null, acc),
              h('div', {className:'gm-row gm-tight'}, btn('', () => { setEditing(key); setForm({platform: p, account: acc, target: t, verified:false}); setProblem(''); }, {kind:'ghost', small:true, icon:'edit', 'aria-label':'编辑 ' + acc}),
                btn('', async () => { if (!await ask(`解除 ${platforms[p]?.[0] || p} 账号 ${acc} 的关联？保存并重启后，它会作为独立联系人处理；已有记忆会保留。`, {confirm:'解除关联'})) return; setValues(v => ({...v, aliases: Object.fromEntries(Object.entries(v.aliases).filter(([k]) => k !== key))})); if (editing === key) resetForm(); }, {kind:'ghost', small:true, icon:'close', className:'gm-danger-hover', 'aria-label':'解除关联 ' + acc}))); })))) : empty('还没有关联账号。用右侧表单添加第一个。')),
        panel({title: editing ? '编辑账号关联' : '添加账号关联', sub:'加入列表后，记得在页面底部保存。'},
          h('form', {className:'gm-stack-sm', onSubmit: stage},
            field('平台', select(form.platform, v => edit('platform', v), [...new Set([...Object.keys(platforms), ...Object.keys(aliases).map(k => k.split(':')[0])])].map(k => [k, platforms[k]?.[0] || k]))),
            field('账号标识', input(form.account, v => edit('account', v), {placeholder: form.platform === 'telegram' ? '例如 1000000001' : '平台账号 ID', maxLength:500}), platforms[form.platform]?.[1] || '使用渠道提供的真实发送者 ID。'),
            field('共用身份', select(form.target, v => edit('target', v), [...targets.map(t => [t, label(t)]), ['__new__', '另一位联系人（新身份）']])),
            form.target === '__new__' ? field('新身份标识', input(form.newTarget || '', v => edit('newTarget', v), {placeholder:'例如 friend-alex', maxLength:200})) : null,
            check(form.verified, v => edit('verified', v), '我已核实这个账号属于所选身份'),
            problem ? h('p', {className:'gm-alert gm-tone-danger', role:'alert'}, problem) : null,
            h('div', {className:'gm-row gm-end'}, editing ? btn('取消编辑', resetForm, {kind:'ghost'}) : null, submit(editing ? '应用修改' : '加入列表', {kind:'tonal', disabled: saving}))))),
      panel({title:'信任与群聊', sub:'群聊始终使用群组记忆空间，不会向其他成员开放私人记忆。'},
        h('div', {className:'gm-stack-sm'}, check(values.trusted_cli_owner, v => setValues(x => ({...x, trusted_cli_owner: v})), '把本机命令行操作视为我本人'), check(values.capture_owner_in_groups, v => setValues(x => ({...x, capture_owner_in_groups: v})), '允许把我在群聊中的发言记录为证据'))),
      h(SaveBar, {dirty, saving, label:'保存身份设置', hint:'保存前会自动备份，重启宿主服务后生效。',
        onSave: async () => { if (form.account.trim()) { setProblem('表单里还有未加入列表的账号，请先加入或取消编辑。'); return; } setSaving(true); await save(values); setSaving(false); },
        onRevert: () => { setValues(data.values); resetForm(); }}));
  }
  function SaveBar({dirty, saving, label, hint, onSave, onRevert}) {
    return h('div', {className:cx('gm-savebar', dirty && 'gm-dirty'), role:'status'},
      h('span', null, dirty ? '有尚未保存的修改' : '已与服务器一致', hint ? h('small', null, hint) : null),
      h('div', {className:'gm-row gm-tight'}, btn('撤销修改', onRevert, {kind:'ghost', disabled: !dirty || saving}), btn(saving ? '正在保存…' : label, onSave, {kind:'primary', disabled: !dirty || saving})));
  }

  /* ---------- 行为与模型 ---------- */
  function ModelManager({api, run, notify, onSaved, onDirty, beforeSave, ask}) {
    const [data, setData] = useState(null), [form, setForm] = useState(null), [baseline, setBaseline] = useState(null);
    const fetchModels = async () => { const v = await api('/models'); const f = {model: v.chat.model || '', embedding_model: v.embedding.model || '', embedding_dimensions: v.embedding.dimensions || 0, embedding_revision: v.embedding.revision || '1', timeout: v.timeout, revision: v.revision}; setData(v); setForm(f); setBaseline(f); };
    const load = () => run(fetchModels);
    useEffect(() => { load(); return () => onDirty?.(false); }, []);
    const dirty = !!form && json(form) !== json(baseline);
    useEffect(() => { onDirty?.(dirty); }, [dirty]);
    if (!data || !form) return panel({title:'模型'}, empty('正在读取模型配置…', btn('重试', load, {small:true})));
    const edit = (k, v) => setForm(f => ({...f, [k]: v}));
    const embedChanged = form.embedding_model !== baseline.embedding_model || form.embedding_dimensions !== baseline.embedding_dimensions;
    const save = () => run(async () => {
      if (form.embedding_dimensions === '' || form.timeout === '') throw Error('请填写向量维度和请求超时。');
      if (beforeSave && !await beforeSave()) return;
      if (embedChanged && !await ask('更换向量模型或维度后，旧向量不再参与检索，知识库会在后台逐步重建向量。继续保存吗？', {confirm:'保存并切换'})) return;
      await api('/models', {}, form, 'PUT'); await fetchModels(); await onSaved(); notify('模型配置已保存。重启宿主服务后生效。');
    });
    const official = data.base_url === 'https://dashscope.aliyuncs.com/compatible-mode/v1' && data.api_key_env === 'DASHSCOPE_API_KEY';
    const modelField = (k, title, kind, list, hint) => field(title, h(Frag, null, input(form[k], v => edit(k, v), {list, maxLength:200, placeholder: kind === 'chat' ? '留空则停用模型处理' : '留空则停用向量'}), h('datalist', {id: list}, data.catalog.filter(x => x.kind === kind).map(x => h('option', {key:x.id, value:x.id}, x.name)))), hint);
    return panel({title:'模型', sub:'GraMem 独立使用的模型，与 Hermes 主模型无关。', actions: [badge(official ? '阿里 DashScope 官方接口' : '保存后切换到官方接口', official ? 'ok' : 'warn', {key:'b', title:'https://dashscope.aliyuncs.com/compatible-mode/v1 · DASHSCOPE_API_KEY'})]},
      h('div', {className:'gm-model-grid'},
        h('div', {className:'gm-model-card'}, h('h4', null, 'Chat'), note(data.chat.role), modelField('model', '模型 ID', 'chat', 'gm-chat-models', '可从推荐中选择，或填写阿里官方模型 ID。')),
        h('div', {className:'gm-model-card'}, h('h4', null, 'Embedding'), note(data.embedding.role), modelField('embedding_model', '模型 ID', 'embedding', 'gm-embedding-models'),
          h('div', {className:'gm-form-grid'}, field('向量维度', input(form.embedding_dimensions, v => edit('embedding_dimensions', v === '' ? '' : Number(v)), {type:'number', min:0, step:1}), '0 表示模型默认值'),
            field('向量空间版本', input(form.embedding_revision, v => edit('embedding_revision', v), {maxLength:100}), embedChanged ? '模型或维度已变，保存时会自动更新。' : null)))),
      h('div', {className:'gm-row gm-between'}, field('请求超时（秒）', input(form.timeout, v => edit('timeout', v === '' ? '' : Number(v)), {type:'number', min:1, max:120, step:1}), null, {className:'gm-narrow'}),
        h('div', {className:'gm-row gm-tight'}, btn('重新读取', async () => { if (!dirty || await ask('放弃未保存的模型修改并重新读取？', {confirm:'放弃并读取'})) load(); }, {kind:'ghost', icon:'refresh'}), btn('保存模型配置', save, {kind:'primary', disabled: !dirty}))));
  }
  function Settings({data, save, api, run, notify, onDirty, reload, ask}) {
    const [values, setValues] = useState(data.values), [keys, setKeys] = useState({}), [credential, setCredential] = useState({kind:'model', value:''}), [modelDirty, setModelDirty] = useState(false), [saving, setSaving] = useState(false);
    useEffect(() => { run(async () => setKeys(await api('/credentials'))); }, [data]);
    useEffect(() => { setValues(data.values); }, [data]);
    const edit = (k, v) => setValues(p => ({...p, [k]: v}));
    const dirty = json(values) !== json(data.values);
    useEffect(() => { onDirty?.(modelDirty || dirty); }, [values, data, modelDirty]);
    useEffect(() => () => onDirty?.(false), []);
    const known = settingGroups.flatMap(g => g[2]);
    const extra = Object.keys(values).filter(k => !known.includes(k) && !modelKeys.includes(k) && !identityKeys.includes(k));
    const groups = extra.length ? [...settingGroups, ['其他设置', '暂未归类的 GraMem 配置项。', extra]] : settingGroups;
    const fieldFor = k => {
      const v = values[k];
      if (typeof v === 'boolean') return h('div', {key:k, className:'gm-setting gm-setting-wide'}, check(v, x => edit(k, x), names[k] || k));
      if (k === 'decay_rates') return h('div', {key:k, className:'gm-setting gm-setting-wide'}, h('span', {className:'gm-label'}, names[k]), note('每天的衰减率。数值越大，记忆淡化越快；0 表示不衰减。'),
        h('div', {className:'gm-decay'}, Object.entries(v).map(([kind, rate]) => field(typeNames[kind] || kind, input(rate, x => edit(k, {...v, [kind]: x === '' ? '' : Number(x)}), {type:'number', min:0, step:.001}), null, {key:kind}))));
      if (k === 'confirmation_types') return h('div', {key:k, className:'gm-setting gm-setting-wide'}, h('span', {className:'gm-label'}, names[k]), note(values.auto_approve ? '自动审核已开启，此项在关闭自动审核后才生效。' : '关闭自动审核时，以下类型需要你确认后才生效。'),
        h('div', {className:'gm-check-grid'}, [...new Set([...typeOptions.map(x => x[0]), ...v])].map(kind => check(v.includes(kind), on => edit(k, on ? [...v, kind] : v.filter(x => x !== kind)), typeNames[kind] || kind, {key:kind}))));
      if (v !== null && typeof v === 'object') return h('div', {key:k, className:'gm-setting gm-setting-wide'}, h('span', {className:'gm-label'}, names[k] || k), h(Readable, {value: v}));
      return h('div', {key:k, className:'gm-setting'}, field(names[k] || k, input(v, x => edit(k, typeof v === 'number' ? (x === '' ? '' : Number(x)) : x), {type: typeof v === 'number' ? 'number' : 'text', step:'any', 'aria-label': names[k] || k}), h('code', null, k)));
    };
    const [open, setOpen] = useState(groups[0][0]);
    return h('div', {className:'gm-stack'},
      h(ModelManager, {key: data.revision, api, run, notify, ask, onSaved: reload, onDirty: setModelDirty, beforeSave: async () => !dirty || await ask('保存模型会重新读取行为配置，尚未保存的行为修改将被放弃。继续吗？', {confirm:'继续'})}),
      h('section', {className:'gm-panel gm-settings'},
        h('header', {className:'gm-panel-head'}, h('div', null, h('h3', null, '记忆行为'), h('p', {className:'gm-note'}, '保存前会校验并备份，重启宿主服务后生效。更换 Owner 或图命名空间需要单独迁移。'))),
        h('div', {className:'gm-settings-body'},
          h('nav', {className:'gm-settings-nav', 'aria-label':'设置分组'}, groups.map(([t, , ks]) => { const changed = ks.some(k => json(values[k]) !== json(data.values[k])); return h('button', {type:'button', key:t, className: open === t ? 'gm-on' : '', onClick: () => setOpen(t), 'aria-current': open === t ? 'true' : undefined}, t, changed ? h('i', {className:'gm-changed', 'aria-label':'有修改'}) : null); })),
          h('div', {className:'gm-settings-pane'}, groups.filter(g => g[0] === open).map(([t, sub, ks]) => h('div', {key:t}, h('h4', null, t), note(sub), h('div', {className:'gm-settings-grid'}, ks.filter(k => k in values).map(fieldFor))))))),
      panel({title:'连接凭据', sub:'密钥只写入宿主的保密存储，页面不会读回原值。若变量被其他组件复用，更换会同时影响它们。'},
        h('div', {className:'gm-cred'}, ['model', 'graph'].map(kind => h('div', {key:kind, className:'gm-cred-item'}, h('strong', null, kind === 'model' ? '模型 API 密钥' : 'FalkorDB 密码'), h('code', null, keys[kind]?.env || '—'), badge(keys[kind]?.is_set ? '已配置' : '未配置', keys[kind]?.is_set ? 'ok' : 'warn')))),
        h('form', {className:'gm-search', onSubmit: e => { e.preventDefault(); run(async () => { await api('/credentials', {}, credential, 'PUT'); setCredential(c => ({...c, value:''})); setKeys(await api('/credentials')); notify('凭据已保存。重启宿主服务后生效。'); }); }},
          select(credential.kind, v => setCredential(c => ({...c, kind: v, value:''})), [['model', '模型 API 密钥'], ['graph', 'FalkorDB 密码']], {'aria-label':'凭据类型', className:'gm-input gm-select gm-compact'}),
          input(credential.value, v => setCredential(c => ({...c, value: v})), {type:'password', autoComplete:'new-password', placeholder:'输入新的值', maxLength:10000, 'aria-label':'新凭据'}),
          submit('保存凭据', {disabled: !credential.value.trim()}))),
      h(SaveBar, {dirty, saving, label:'保存行为设置', hint:'保存会自动备份。',
        onSave: async () => { if (modelDirty && !await ask('保存行为设置会重新读取模型配置，尚未保存的模型修改将被放弃。继续吗？', {confirm:'继续'})) return; setSaving(true); try { await save(values); } finally { setSaving(false); } },
        onRevert: () => setValues(data.values)}));
  }

  /* ---------- 导入与维护 ---------- */
  function QueueTable({rows, cols}) {
    if (!rows?.length) return empty('队列为空。');
    return h('div', {className:'gm-table-wrap'}, h('table', {className:'gm-table'}, h('thead', null, h('tr', null, cols.map(c => h('th', {key:c[0]}, c[1])))),
      h('tbody', null, rows.map((r, i) => h('tr', {key: r.id ?? i}, cols.map(([k]) => h('td', {key:k, className: ['created','retry_at'].includes(k) ? 'gm-nowrap' : ''}, k === 'principal' ? prettyScope(r[k]) : ['created','retry_at'].includes(k) ? date(r[k]) : k === 'status' ? badge(jobNames[r[k]] || r[k], r[k] === 'failed' ? 'danger' : 'neutral') : h('code', null, String(r[k] ?? '—').slice(0, 36)))))))));
  }
  function Operations({api, scope, run, notify, ask}) {
    const [records, setRecords] = useState([]), [exclusions, setExclusions] = useState([]), [activate, setActivate] = useState(false), [queues, setQueues] = useState(null), [result, setResult] = useState(null), [raw, setRaw] = useState({records:'[]', exclusions:'[]'}), [busy, setBusy] = useState('');
    const actions = [
      ['maintain', '生命周期维护', '按衰减与门槛更新所有身份的记忆状态，并同步图。', 'refresh'],
      ['sync_graph', '同步图队列', '把待同步的事实写入 FalkorDB。', 'graph'],
      ['worker', '处理一个后台任务', '解析一个文件、生成一批向量、提炼一段对话并审核一条候选。', 'play'],
      ['consolidate', '整理同主题事实', '用模型整理当前身份的兼容事实并重新生成画像，会产生费用。', 'spark'],
      ['backup', '创建一致性备份', '打包 SQLite、知识库原件与校验清单。FalkorDB 需要另行备份。', 'download'],
    ];
    const op = (action, label) => run(async () => {
      if (action === 'consolidate' && !await ask('调用模型整理当前身份的兼容事实并生成画像？这会产生模型费用。', {confirm:'开始整理'})) return;
      setBusy(action);
      try { const v = await api('/operation', {}, {action, scope}); setResult({label, value: v}); notify(label + '已完成'); } finally { setBusy(''); }
    });
    const loadQueues = () => run(async () => setQueues(await api('/queues')));
    useEffect(() => { loadQueues(); }, []);
    const prepare = (value, kind) => { const rows = Array.isArray(value) ? value : value?.items || value?.memories; if (!Array.isArray(rows) || rows.some(r => !r || typeof r !== 'object' || Array.isArray(r))) throw Error('文件应包含记录对象数组，或带 items / memories 数组的导出文件。'); if (rows.length > 10000) throw Error('一次最多导入 10000 条记录。'); const normalized = rows.map(r => kind === 'records' ? {...r, content: r.content ?? r.text ?? '', type: r.type || 'knowledge', slot: r.slot || ''} : {...r, slot: r.slot || r.key || '', state: r.state || r.status || 'suppressed'}); if (kind === 'records') setRecords(normalized); else setExclusions(normalized); };
    const upload = (e, kind) => { const file = e.target.files?.[0]; e.target.value = ''; if (!file) return; run(async () => { if (file.size > 20_000_000) throw Error('文件最大 20 MB。'); const text = await file.text(); let parsed; try { parsed = JSON.parse(text); } catch { try { parsed = text.split(/\r?\n/).filter(s => s.trim()).map(s => JSON.parse(s)); } catch { throw Error('无法读取这个文件，请上传有效的 JSON 或 JSONL 导出。'); } } prepare(parsed, kind); notify('已读取文件，请检查预览后再导入。'); }); };
    const rowEdit = (kind, i, k, v) => (kind === 'records' ? setRecords : setExclusions)(rows => rows.map((r, n) => n === i ? {...r, [k]: v} : r));
    const invalid = records.filter(r => !r.content?.trim() || r.content.length > 2000).length;
    return h('div', {className:'gm-stack'},
      panel({title:'维护', sub:'“生命周期维护”和“图同步”覆盖当前工作空间的所有身份；其余操作只作用于当前身份。'},
        h('ul', {className:'gm-ops'}, actions.map(([k, label, desc, ic]) => h('li', {key:k}, h('span', {className:'gm-op-icon'}, icon(ic)), h('div', null, h('strong', null, label), h('p', null, desc)), btn(busy === k ? '执行中…' : '执行', () => op(k, label), {small:true, disabled: !!busy})))),
        result ? h('div', {className:'gm-result'}, h('div', {className:'gm-hit-head'}, h('strong', null, result.label + '：结果'), btn('', () => setResult(null), {kind:'ghost', small:true, icon:'close', 'aria-label':'关闭结果'})), inspect(result.value)) : null),
      panel({title:'持久队列', sub:'最近 100 个来源任务和待同步的图任务。', actions: btn('刷新', loadQueues, {kind:'ghost', small:true, icon:'refresh'})},
        queues ? h('div', {className:'gm-stack-sm'}, h('h4', {className:'gm-subhead'}, `来源任务（${queues.sources.length}）`), h(QueueTable, {rows: queues.sources, cols:[['created','创建'],['kind','类别'],['status','状态'],['attempts','重试'],['retry_at','下次重试'],['principal','身份']]}),
          h('h4', {className:'gm-subhead'}, `图同步（${queues.graph.length}）`), h(QueueTable, {rows: queues.graph, cols:[['action','操作'],['memory_id','记忆'],['attempts','重试'],['retry_at','下次重试'],['principal','身份']]})) : empty('正在读取队列…')),
      panel({title:'导入旧记忆', sub:'导入前可以逐条修改内容和类型。默认进入自动审核；排除记录会先导入，以保留原来的遗忘和停用边界。'},
        h('div', {className:'gm-form-grid'},
          h('label', {className:'gm-drop gm-drop-sm'}, icon('upload', 'gm-drop-icon'), h('strong', null, '记忆文件'), h('small', null, 'JSON 或 JSONL'), h('input', {type:'file', accept:'.json,.jsonl,application/json', className:'gm-visually-hidden', onChange: e => upload(e, 'records')})),
          h('label', {className:'gm-drop gm-drop-sm'}, icon('upload', 'gm-drop-icon'), h('strong', null, '遗忘与停用文件'), h('small', null, '可选'), h('input', {type:'file', accept:'.json,.jsonl,application/json', className:'gm-visually-hidden', onChange: e => upload(e, 'exclusions')}))),
        h('div', {className:'gm-row gm-between'}, h('span', {className:'gm-note'}, `待导入：${records.length} 条记忆，${exclusions.length} 条排除${invalid ? `，其中 ${invalid} 条内容需要补全` : ''}`),
          h('div', {className:'gm-row gm-tight'}, btn('添加记忆', () => setRecords(v => [...v, {content:'', type:'knowledge', slot:''}]), {small:true, kind:'ghost', icon:'plus'}), btn('添加排除', () => setExclusions(v => [...v, {slot:'', state:'suppressed'}]), {small:true, kind:'ghost', icon:'plus'}), records.length || exclusions.length ? btn('全部清空', () => { setRecords([]); setExclusions([]); }, {small:true, kind:'link'}) : null)),
        records.length || exclusions.length ? h('ol', {className:'gm-import'}, records.slice(0, 100).map((r, i) => h('li', {key:'r' + i, className: !r.content?.trim() ? 'gm-invalid' : ''},
          textarea(r.content, v => rowEdit('records', i, 'content', v), {rows:2, maxLength:2000, 'aria-label':`第 ${i + 1} 条记忆`}),
          select(r.type, v => rowEdit('records', i, 'type', v), typeOptions.some(([k]) => k === r.type) ? typeOptions : [...typeOptions, [r.type, r.type]], {'aria-label':'类型'}),
          input(r.slot, v => rowEdit('records', i, 'slot', v), {maxLength:200, placeholder:'主题标识（可选）', 'aria-label':'主题标识'}),
          btn('', () => setRecords(v => v.filter((_, n) => n !== i)), {kind:'ghost', small:true, icon:'close', 'aria-label':`移除第 ${i + 1} 条`}))),
          exclusions.slice(0, 100).map((r, i) => h('li', {key:'x' + i, className:'gm-import-ex'}, badge('排除'), input(r.slot, v => rowEdit('exclusions', i, 'slot', v), {maxLength:200, placeholder:'主题标识', 'aria-label':'排除主题标识'}), select(r.state, v => rowEdit('exclusions', i, 'state', v), [['suppressed','停用'],['deleted','遗忘']], {'aria-label':'状态'}), btn('', () => setExclusions(v => v.filter((_, n) => n !== i)), {kind:'ghost', small:true, icon:'close', 'aria-label':'移除排除记录'})))) : null,
        records.length > 100 || exclusions.length > 100 ? note('预览只显示每类前 100 条，导入时包含全部记录。') : null,
        h('details', {className:'gm-disclose'}, h('summary', null, '粘贴 JSON'), note('读取后进入上面的预览，不会立即导入。'), ...['records', 'exclusions'].map(kind => h('div', {key:kind, className:'gm-stack-sm'}, field(kind === 'records' ? '记忆 JSON' : '排除 JSON', textarea(raw[kind], v => setRaw(x => ({...x, [kind]: v})), {rows:4, spellCheck:false, className:'gm-input gm-mono'})), btn('读取到预览', () => run(async () => prepare(JSON.parse(raw[kind]), kind)), {small:true})))),
        h('div', {className:'gm-row gm-between'}, check(activate, setActivate, '这些事实已经由我审核，直接导入为有效记忆'),
          btn('导入', () => run(async () => {
            if (invalid) throw Error('每条记忆都需要 1–2000 字的内容，请补全或移除空记录。');
            if (exclusions.some(r => !r.slot?.trim() || !['deleted','suppressed'].includes(r.state))) throw Error('排除记录需要主题标识和有效状态。');
            if (activate && !await ask('确认这些迁移事实均已人工审核，可以直接成为有效记忆？', {confirm:'直接激活'})) return;
            setResult({label:'导入', value: await api('/import', {}, {records, exclusions, activate, scope})}); setRecords([]); setExclusions([]); notify('导入完成，结果见上方“维护”区域。');
          }), {kind:'primary', icon:'upload', disabled: !records.length && !exclusions.length}))));
  }

  /* ---------- 面板设置 ---------- */
  function PanelSettings({appearance, setAppearance, dark}) {
    return h('div', {className:'gm-grid-2 gm-grid-wide-left'},
      h('div', {className:'gm-stack'},
        panel({title:'显示模式'}, h('div', {className:'gm-mode-grid'}, [['system','跟随系统','随设备外观自动切换'], ['light','明亮','适合白天和明亮环境'], ['dark','深色','适合暗光环境']].map(([m, label, desc]) =>
          h('button', {type:'button', key:m, className:cx('gm-mode', appearance.mode === m && 'gm-on'), 'aria-pressed': appearance.mode === m, onClick: () => setAppearance(v => ({...v, mode: m}))}, icon(m), h('strong', null, label), h('small', null, desc))))),
        panel({title:'主题色', sub:'从一个颜色推导整套界面色调，明暗模式各自调整。'},
          h('div', {className:'gm-swatches'}, themePresets.map(([seed, label]) => h('button', {type:'button', key:seed, className:cx('gm-swatch', appearance.seed.toLowerCase() === seed.toLowerCase() && 'gm-on'), 'aria-pressed': appearance.seed.toLowerCase() === seed.toLowerCase(), onClick: () => setAppearance(v => ({...v, seed}))}, h('i', {style:{background: seed}}), h('span', null, label)))),
          h('label', {className:'gm-custom-color'}, h('input', {type:'color', value: appearance.seed, onChange: e => setAppearance(v => ({...v, seed: e.target.value})), 'aria-label':'自定义主题色'}), h('span', null, '自定义颜色'), h('code', null, appearance.seed.toUpperCase())),
          h('div', {className:'gm-row'}, btn('恢复默认外观', () => setAppearance({mode:'system', seed: DEFAULT_SEED}), {kind:'ghost', icon:'refresh'})))),
      h('div', {className:'gm-stack'},
        panel({title:'预览', sub:`当前为${dark ? '深色' : '明亮'}模式，设置只保存在这个浏览器中。`},
          h('div', {className:'gm-preview'},
            h('div', {className:'gm-mem', style:{'--s': .82}}, h('span', {className:'gm-mem-bar'}), h('span'), h('div', {className:'gm-mem-main'}, h('p', {className:'gm-mem-text'}, '回答时我偏好先给结论，再解释细节。'), h('div', {className:'gm-mem-meta'}, badge('偏好'), badge('长期保留', 'accent'), h('code', null, 'answer-style'))), h('div', {className:'gm-mem-side'}, h('span', {className:'gm-mem-num'}, '0.82'))),
            h('div', {className:'gm-row'}, btn('主要操作', null, {kind:'primary', tabIndex:-1}), btn('次要操作', null, {tabIndex:-1}), btn('文字操作', null, {kind:'link', tabIndex:-1})),
            h('div', {className:'gm-row'}, badge('可检索', 'ok'), badge('审核中', 'warn'), badge('解析失败', 'danger')))),
        panel({title:'关于'}, h('dl', {className:'gm-facts'}, h('div', null, h('dt', null, '控制台'), h('dd', null, VERSION)), h('div', null, h('dt', null, '范围'), h('dd', null, '只管理 GraMem。Hermes 主模型、渠道、工具与会话请使用官方面板。'))))));
  }

  /* ---------- 应用外壳 ---------- */
  const NAV = [
    [null, [['overview', '总览', 'overview']]],
    ['记忆', [['memories', '记忆条目', 'memory'], ['preferences', '画像与偏好', 'profile'], ['knowledge', '知识库', 'book'], ['chats', '聊天档案', 'chat']]],
    ['探索', [['network', '记忆网', 'network'], ['graph', '关系图', 'graph']]],
    ['管理', [['identities', '账号与身份', 'identity'], ['settings', '行为与模型', 'sliders'], ['operations', '导入与维护', 'tools']]],
  ];
  const PAGES = Object.fromEntries([...NAV.flatMap(g => g[1]), ['panel', '外观', 'palette']].map(x => [x[0], x]));
  const INTRO = {
    overview:'所选工作空间的记忆状态、身份与后台任务。',
    memories:'查找事实，审核候选，管理每条记忆的版本。',
    preferences:'查看有来源的画像，维护身份特征、兴趣和长期偏好。',
    knowledge:'长期保存原件，检索文档与图片中的文字。',
    chats:'跨平台查找原话，查看自动整理的主题与时间线。',
    network:'把原话、文件、事件和记忆串成一张网，权重与记忆本体同步。',
    graph:'沿着实体与关系，探索有来源的事实网络。',
    identities:'关联已核实的账号，让同一个人跨平台共用一份记忆。',
    settings:'调整记忆如何召回、生长和淡化，以及模型与图服务的连接。',
    operations:'维护生命周期，查看持久队列，导入旧记忆和备份。',
    panel:'调整控制台的明暗与色调。'
  };
  const Brandmark = () => h('svg', {viewBox:'0 0 32 32', className:'gm-mark', 'aria-hidden':true},
    h('path', {d:'M8 9 L24 11 L16 25 Z M8 9 L16 17 L24 11 M16 17 V25', fill:'none', stroke:'currentColor', strokeWidth:1.5, strokeLinejoin:'round'}),
    [[8, 9, 3.2], [24, 11, 3.2], [16, 25, 3.2], [16, 17, 2.2]].map(([x, y, r], i) => h('circle', {key:i, cx:x, cy:y, r, fill:'currentColor'})));

  function App() {
    const [tab, setTab] = useState('overview'), [tabArgs, setTabArgs] = useState(null), [profile, setProfile] = useState('default'), [profiles, setProfiles] = useState([]), [scope, setScope] = useState('');
    const [overview, setOverview] = useState(null), [overviewError, setOverviewError] = useState(''), [settings, setSettings] = useState(null), [pending, setPending] = useState(0), [dirty, setDirty] = useState(false);
    const [toasts, setToasts] = useState([]), [dialog, setDialog] = useState(null), [navOpen, setNavOpen] = useState(false);
    const toast = (text, tone = 'ok') => { const id = Math.random().toString(36).slice(2); setToasts(t => [...t.slice(-3), {id, text, tone}]); if (tone !== 'error') setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), 5200); };
    const notify = text => toast(text, 'ok');
    const ask = (message, o = {}) => new Promise(resolve => setDialog({message, ...o, resolve}));
    const closeDialog = v => { dialog?.resolve(v); setDialog(null); };
    useEffect(() => { if (!dirty) return; const warn = e => { e.preventDefault(); e.returnValue = ''; }; addEventListener('beforeunload', warn); return () => removeEventListener('beforeunload', warn); }, [dirty]);
    const guard = async msg => !dirty || await ask(msg, {confirm:'放弃修改', title:'有尚未保存的修改'});
    const go = async (next, args = null) => { if (next !== tab && !await guard('离开这个页面会放弃尚未保存的配置修改。')) return; setDirty(false); setTabArgs(args); setTab(next); setNavOpen(false); document.querySelector('.gm-main')?.scrollTo?.(0, 0); };
    const changeProfile = async next => { if (!await guard('切换工作空间会放弃尚未保存的配置修改。')) return; setDirty(false); setProfile(next); };
    const [appearance, setAppearance] = useState(() => { try { const v = JSON.parse(localStorage.getItem('gramem-appearance')); return v && v.seed ? v : {mode:'system', seed: DEFAULT_SEED}; } catch { return {mode:'system', seed: DEFAULT_SEED}; } });
    const [systemDark, setSystemDark] = useState(() => matchMedia('(prefers-color-scheme: dark)').matches);
    useEffect(() => { const m = matchMedia('(prefers-color-scheme: dark)'), u = e => setSystemDark(e.matches); m.addEventListener('change', u); return () => m.removeEventListener('change', u); }, []);
    useEffect(() => { try { localStorage.setItem('gramem-appearance', JSON.stringify(appearance)); } catch {} }, [appearance]);
    const dark = appearance.mode === 'dark' || (appearance.mode === 'system' && systemDark);
    const theme = useMemo(() => tonalTheme(appearance.seed, dark), [appearance.seed, dark]);
    useEffect(() => { const root = document.documentElement; root.style.setProperty('--gramem-shell-surface', theme['--gm-bg']); root.style.setProperty('--gramem-shell-text', theme['--gm-ink']); return () => { root.style.removeProperty('--gramem-shell-surface'); root.style.removeProperty('--gramem-shell-text'); }; }, [theme]);
    const seq = useRef(0);
    const run = async fn => { setPending(n => n + 1); try { await fn(); } catch (e) { toast(e.message || String(e), 'error'); } finally { setPending(n => n - 1); } };
    const api = async (path, params = {}, body, method) => {
      const qs = new URLSearchParams({profile, ...Object.fromEntries(Object.entries(params).map(([k, v]) => [k, String(v)]))});
      return sdk.fetchJSON(`/api/plugins/hermes-control${path}?${qs}`, body === undefined ? undefined : {method: method || 'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
    };
    useEffect(() => { run(async () => { const v = await sdk.api.getProfiles(); setProfiles(v.profiles); }); }, []);
    useEffect(() => {
      const n = ++seq.current; setOverview(null); setOverviewError(''); setSettings(null); setScope('');
      api('/overview').then(v => { if (n === seq.current) { setOverview(v); setScope(v.owner); } }).catch(e => { if (n === seq.current) setOverviewError(e.message || String(e)); });
      api('/settings').then(v => { if (n === seq.current) setSettings(v); }).catch(() => {});
      return () => { seq.current++; };
    }, [profile]);
    const refreshOverview = () => run(async () => { const n = seq.current, v = await api('/overview'); if (n === seq.current) setOverview(v); });
    const saveSettings = values => run(async () => { await api('/settings', {}, {values, revision: settings.revision}, 'PUT'); setSettings(await api('/settings')); notify('配置已保存并备份。重启宿主服务后生效。'); });
    const download = kind => (id, resource = 'original') => BASE() + `/api/plugins/hermes-control/${kind}/${id}/${resource}?${new URLSearchParams({profile, scope})}`;
    const notReady = overviewError ? empty('这个工作空间暂时无法读取 GraMem：' + overviewError) : empty(overview === null ? '正在读取工作空间…' : '这个工作空间尚未启用 GraMem。');
    const props = {api, scope, run, notify, ask};
    const content = {
      overview: () => overviewError ? notReady : h(Overview, {overview, scope, go, pending: pending > 0, refresh: refreshOverview, switchScope: s => { setScope(s); notify('已切换到' + prettyScope(s)); }}),
      memories: () => overview && scope ? h(Memories, {key: profile + scope + (tabArgs?.status || ''), ...props, initial: tabArgs}) : notReady,
      knowledge: () => overview && scope ? h(Knowledge, {key: profile + scope, ...props, download: id => download('knowledge')(id)}) : notReady,
      chats: () => overview && scope ? h(ChatsView, {key: profile + scope, ...props, download: download('chats')}) : notReady,
      network: () => overview && scope ? h(NetworkView, {key: profile + scope, ...props}) : notReady,
      graph: () => overview && scope ? h(Graph, {key: profile + scope, ...props}) : notReady,
      preferences: () => overview && scope ? h(Profiles, {key: profile + scope, ...props}) : notReady,
      identities: () => settings ? h(Identities, {key: profile, data: settings, save: saveSettings, onDirty: setDirty, ask}) : empty('这个工作空间尚未配置 GraMem。'),
      settings: () => settings ? h(Settings, {key: profile, data: settings, save: saveSettings, ...props, onDirty: setDirty, reload: async () => setSettings(await api('/settings'))}) : empty('这个工作空间尚未配置 GraMem。'),
      operations: () => overview && scope ? h(Operations, {key: profile + scope, ...props}) : notReady,
      panel: () => h(PanelSettings, {appearance, setAppearance, dark}),
    };
    const scoped = !['overview', 'identities', 'settings', 'panel'].includes(tab);
    const navItem = ([key, label, ic]) => h('li', {key}, h('button', {type:'button', className: tab === key ? 'gm-on' : '', 'aria-current': tab === key ? 'page' : undefined, onClick: () => go(key)}, icon(ic), h('span', null, label)));
    return h('div', {className:cx('gm-root', navOpen && 'gm-nav-open'), 'data-mode': dark ? 'dark' : 'light', style: theme, 'aria-busy': pending > 0},
      h('aside', {className:'gm-rail'},
        h('div', {className:'gm-brand'}, h(Brandmark), h('div', null, h('strong', null, 'GraMem'), h('small', null, '记忆控制台')), btn('', () => setNavOpen(v => !v), {kind:'ghost', icon: navOpen ? 'close' : 'menu', className:'gm-nav-toggle', 'aria-label':'切换导航', 'aria-expanded': navOpen})),
        h('div', {className:'gm-context'},
          field('工作空间', select(profile, changeProfile, profiles.length ? profiles.map(p => [p.name, p.name]) : [['default', 'default']], {disabled: pending > 0})),
          overview ? field('记忆身份', select(scope, setScope, overview.scopes.map(s => [s.principal, prettyScope(s.principal)]), {disabled: pending > 0})) : null),
        h('nav', {className:'gm-nav', 'aria-label':'控制台导航'}, NAV.map(([group, items], i) => h('div', {key: i, className:'gm-nav-group'}, group ? h('span', {className:'gm-nav-title'}, group) : null, h('ul', null, items.map(navItem))))),
        h('div', {className:'gm-rail-foot'}, h('ul', null, navItem(['panel', '外观', 'palette']), h('li', null, h('button', {type:'button', onClick: () => run(async () => { await sdk.authedFetch('/auth/logout', {method:'POST'}); location.href = BASE() + '/login'; })}, icon('logout'), h('span', null, '退出登录')))))),
      h('main', {className:'gm-main'},
        h('div', {className:cx('gm-progress', pending > 0 && 'gm-on'), 'aria-hidden':true}),
        h('header', {className:'gm-page-head'},
          h('div', null, h('h1', null, PAGES[tab][1]), h('p', null, INTRO[tab])),
          scoped && scope ? h('div', {className:'gm-scope-pill', title:'当前记忆身份，可在左侧切换'}, icon('profile'), h('span', null, prettyScope(scope))) : null),
        h('div', {className:'gm-page'}, content[tab]())),
      h('div', {className:'gm-toasts', 'aria-live':'polite'}, toasts.map(t => h('div', {key:t.id, className:'gm-toast gm-tone-' + (t.tone === 'error' ? 'danger' : 'ok'), role: t.tone === 'error' ? 'alert' : 'status'}, icon(t.tone === 'error' ? 'alert' : 'check'), h('span', null, t.text), btn('', () => setToasts(x => x.filter(y => y.id !== t.id)), {kind:'ghost', small:true, icon:'close', 'aria-label':'关闭提示'})))),
      dialog ? h(Dialog, {d: dialog, close: closeDialog}) : null);
  }
  window.__HERMES_PLUGINS__.register('hermes-control', App);
})();
