(() => {
  const sdk = window.__HERMES_PLUGIN_SDK__;
  const R = sdk.React, h = R.createElement;
  const {useState, useEffect, useRef, useMemo} = sdk.hooks;
  const json = v => JSON.stringify(v, null, 2);
  const b = (label, onClick, more = {}) => h('button', {type:'button', onClick, ...more}, label);
  const input = (value, onChange, more = {}) => h('input', {value, onChange:e=>onChange(e.target.value), ...more});
  const select = (value, onChange, opts, more = {}) => h('select', {value, onChange:e=>onChange(e.target.value), ...more}, opts.map(o=>h('option',{value:o[0],key:o[0]},o[1])));
  const box = (title, ...children) => h('section',{className:'hc-card',key:title},h('h3',null,title),...children);
  const note = text => h('p',{className:'hc-muted'},text);
  const typeNames={identity:'身份特征',occupation:'职业',health:'健康',current_location:'当前位置',preference:'偏好',interests:'兴趣',skill:'技能',technical_environment:'技术环境',project:'项目',relationship:'关系',episodic:'经历',knowledge:'知识',temporary:'临时情境',communication:'沟通习惯',capabilities:'能力',projects:'项目',stable_patterns:'长期习惯',uncertainties:'待确认'};
  const typeOptions=Object.entries(typeNames).filter(([k])=>!['communication','capabilities','projects','stable_patterns','uncertainties'].includes(k));
  const fieldNames={id:'记录编号',content:'内容',fact:'事实',slot:'主题标识',type:'类型',class:'分类',status:'状态',lifecycle:'生命周期',strength:'强度',confidence:'置信度',importance:'重要性',created:'创建时间',updated:'更新时间',source:'来源',source_ids:'来源记录',metadata:'来源信息',relations:'事实关系',subject:'主体',predicate:'关系',object:'对象',version:'版本',tokens:'Token 数',ok:'完成',processed:'已处理',graph_synced:'图同步条数',sources:'来源任务',graph:'图同步任务',attempts:'重试次数',retry_at:'下次重试',principal:'记忆身份',action:'操作',path:'保存位置',count:'数量',graph_backup_required:'需要独立备份图服务'};
  function Readable({value}){
    if(value===null||value===undefined)return note('未设置');
    if(Array.isArray(value))return value.length?h('ul',{className:'hc-readable-list'},value.map((v,i)=>h('li',{key:i},h(Readable,{value:v})))):note('暂无记录');
    if(typeof value==='object')return h('dl',{className:'hc-readable'},Object.entries(value).map(([k,v])=>h('div',{key:k},h('dt',null,fieldNames[k]||typeNames[k]||names[k]||k),h('dd',null,h(Readable,{value:['created','updated','retry_at'].includes(k)&&typeof v==='number'?date(v):v})))));
    return h('span',{className:'hc-readable-value'},typeof value==='boolean'?(value?'是':'否'):String(value));
  }
  const inspect=value=>h('div',null,h(Readable,{value}),h('details',{className:'hc-advanced'},h('summary',null,'高级：查看原始 JSON'),h('pre',null,json(value))));
  function Relations({value,onChange}){
    const edit=(i,k,v)=>onChange(value.map((r,n)=>n===i?{...r,[k]:v}:r));
    return h('div',null,value.map((row,i)=>h('div',{className:'hc-relation-row',key:i},['subject','predicate','object'].map(k=>h('label',{key:k},fieldNames[k],input(row[k]||'',v=>edit(i,k,v),{maxLength:500}))),b('移除',()=>onChange(value.filter((_,n)=>n!==i)),{className:'hc-quiet','aria-label':`移除第 ${i+1} 条关系`}))),b('添加关系',()=>onChange([...value,{subject:'',predicate:'',object:''}]),{disabled:value.length>=50,className:'hc-secondary'}));
  }
  const platforms={telegram:['Telegram','填写数字用户 ID，例如 1000000001。不要填 @用户名或群组 ID。'],email:['邮件','填写完整邮箱地址，系统会忽略大小写。'],slack:['Slack','填写成员 ID（U 开头），可在成员资料的更多菜单中复制。'],teams:['Teams','填写用户的 Microsoft Entra 对象 ID，通常为 UUID。'],photon:['Photon','填写渠道事件中的发送者账号 ID。'],discord:['Discord','开启开发者模式，在用户资料中复制用户 ID。'],whatsapp:['WhatsApp','填写渠道识别的完整发送者 ID。'],signal:['Signal','填写渠道识别的发送者 ID。'],matrix:['Matrix','填写完整用户 ID，例如 @name:example.org。']};
  function Identities({data,save,onDirty}){
    const [values,setValues]=useState(data.values),[form,setForm]=useState({platform:'telegram',account:'',target:data.values.owner_id,verified:false}),[editing,setEditing]=useState(null),[problem,setProblem]=useState(''),[saving,setSaving]=useState(false);
    useEffect(()=>{setValues(data.values);},[data]);
    const aliases=values.aliases||{},dirty=json(values)!==json(data.values);
    useEffect(()=>{onDirty?.(dirty||!!form.account.trim());},[dirty,form.account]);
    useEffect(()=>()=>onDirty?.(false),[]);
    const targets=[...new Set([values.owner_id,...Object.values(aliases)])];
    const edit=(key,value)=>{setForm(v=>({...v,[key]:value}));setProblem('');};
    const stage=e=>{e.preventDefault();const account=form.account.trim(),platform=form.platform.trim().toLowerCase(),target=(form.target==='__new__'?form.newTarget||'':form.target).trim();
      if(!platform||!account||!target)return setProblem('请填写平台、账号和共用身份。');
      if(platform==='telegram'&&!/^[1-9]\d*$/.test(account))return setProblem('Telegram 请填写正整数用户 ID，例如 1000000001；@用户名和群组 ID 不能用于身份关联。');
      if(platform==='email'&&!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(account))return setProblem('请填写完整邮箱地址。');
      const key=platform+':'+(platform==='email'?account.toLowerCase():account);
      if(key!==editing&&Object.hasOwn(aliases,key))return setProblem('这个账号已经关联。请编辑已有账号。');
      if(!form.verified)return setProblem('请先确认你已核实这个账号属于所选身份。');
      const next={...aliases};if(editing)delete next[editing];next[key]=target;setValues(v=>({...v,aliases:next}));setEditing(null);setForm(v=>({...v,account:'',verified:false}));setProblem('');
    };
    return h('div',null,box('共用记忆身份',note('同一个人的已核实账号关联后，会使用同一份记忆。未关联的账号按独立联系人处理。'),h('div',{className:'hc-identity-summary'},h('div',null,h('strong',null,'我的身份'),note(values.owner_id)),h('span',{className:'hc-chip'},`${Object.keys(aliases).length} 个关联账号`)),note('关联影响后续身份识别；以前作为独立联系人保存的记忆不会自动搬移。'),h('details',{className:'hc-advanced'},h('summary',null,'高级：稳定身份标识'),note('此标识用于定位已有记忆。修改需要单独迁移，请勿为了改显示名而更换。'),h('code',null,values.owner_id))),
      box('已关联账号',Object.keys(aliases).length?h('div',{className:'hc-account-list'},Object.entries(aliases).map(([key,target])=>{const split=key.indexOf(':'),platform=key.slice(0,split),account=key.slice(split+1);return h('div',{className:'hc-account',key},h('div',null,h('strong',null,platforms[platform]?.[0]||platform),h('div',{className:'hc-account-id'},account),note(`共用身份：${target===values.owner_id?'我（'+target+'）':target}`)),h('div',{className:'hc-actions'},b('编辑',()=>{setEditing(key);setForm({platform,account,target,verified:false});setProblem('');}),b('解除关联',()=>{if(!confirm(`解除 ${platforms[platform]?.[0]||platform} 账号 ${account} 的关联？保存并重启后，这个账号将作为独立联系人处理；已有记忆会保留。`))return;setValues(v=>({...v,aliases:Object.fromEntries(Object.entries(v.aliases).filter(([k])=>k!==key))}));if(editing===key){setEditing(null);setForm(v=>({...v,account:'',verified:false}));}},{className:'hc-danger'})));})):note('还没有关联账号。从下面添加第一个账号。')),
      box(editing?'编辑账号关联':'添加账号关联',h('form',{onSubmit:stage},h('div',{className:'hc-form-grid'},h('label',null,'1. 选择平台',select(form.platform,v=>edit('platform',v),[...new Set([...Object.keys(platforms),...Object.keys(aliases).map(k=>k.split(':')[0])])].map(k=>[k,platforms[k]?.[0]||k]))),h('label',null,'2. 账号标识',input(form.account,v=>edit('account',v),{placeholder:form.platform==='telegram'?'例如 1000000001':'填写平台账号 ID',maxLength:500}),h('small',null,platforms[form.platform]?.[1]||'使用渠道提供的真实发送者 ID。')),h('label',null,'3. 共用身份',select(form.target,v=>edit('target',v),[...targets.map(t=>[t,t===values.owner_id?`我（${t}）`:t]),['__new__','另一位联系人（新身份）']]),form.target==='__new__'?input(form.newTarget||'',v=>edit('newTarget',v),{placeholder:'例如 friend-alex',maxLength:200,'aria-label':'新身份标识'}):null)),h('label',{className:'hc-check'},h('input',{type:'checkbox',checked:form.verified,onChange:e=>edit('verified',e.target.checked)}),'我已核实这个账号属于所选身份'),problem?h('p',{className:'hc-error',role:'alert'},problem):null,h('div',{className:'hc-toolbar'},h('button',{type:'submit',disabled:saving},editing?'应用编辑':'加入关联列表'),editing?b('取消编辑',()=>{setEditing(null);setForm(v=>({...v,account:'',verified:false}));setProblem('');}):null)),note('加入列表后，点击下方“保存身份设置”完成保存。')),
      box('信任与群聊',...['trusted_cli_owner','capture_owner_in_groups'].map(key=>h('label',{className:'hc-check',key},h('input',{type:'checkbox',checked:values[key],onChange:e=>setValues(v=>({...v,[key]:e.target.checked}))}),key==='trusted_cli_owner'?'把本机命令行操作视为我本人':'允许记录我在群聊中的发言作为证据')),note('群聊仍使用群组记忆空间，不会把私人记忆开放给其他成员。')),
      h('div',{className:'hc-save-bar'},h('span',{role:'status'},dirty?'有尚未保存的修改':'身份配置已与服务器一致'),b(saving?'正在保存…':'保存身份设置',async()=>{if(form.account.trim()){setProblem('填写中的账号尚未加入列表。请先加入列表或取消编辑。');return;}setSaving(true);await save(values);setSaving(false);},{disabled:!dirty||saving}),b('撤销未保存修改',()=>{setValues(data.values);setEditing(null);setForm(v=>({...v,account:'',verified:false}));setProblem('');},{disabled:!dirty||saving,className:'hc-secondary'})),note('保存会自动备份。需重新启动宿主实例后生效。'));
  }
  const date = value => value ? new Date(Number(value)*1000).toLocaleString('zh-CN') : '—';
  const prettyScope = s => {const parts=s.split('\x1f');return `${({owner:'所有者',contact:'联系人',group:'群组'})[parts[1]]||parts[1]} · ${parts[2]||s}`;};
  function tonalTheme(seed,dark){
    const c=seed.replace('#',''),r=parseInt(c.slice(0,2),16)/255,g=parseInt(c.slice(2,4),16)/255,bv=parseInt(c.slice(4,6),16)/255;
    const max=Math.max(r,g,bv),min=Math.min(r,g,bv),d=max-min,l=(max+min)/2;
    let hue=0;if(d){hue=max===r?((g-bv)/d+(g<bv?6:0))*60:max===g?((bv-r)/d+2)*60:((r-g)/d+4)*60;}
    const sat=d?d/(1-Math.abs(2*l-1))*100:0;
    const tone=(light,saturation=sat)=>`hsl(${hue} ${Math.min(75,saturation)}% ${light}%)`;
    return {'--hc-primary':tone(dark?82:35,Math.max(35,sat)),'--hc-on-primary':tone(dark?18:99,25),
      '--hc-primary-container':tone(dark?29:91,45),'--hc-on-primary-container':tone(dark?93:19,35),
      '--hc-secondary-container':tone(dark?27:92,19),'--hc-on-secondary-container':tone(dark?90:25,22),
      '--hc-surface':tone(dark?8:98,14),'--hc-surface-low':tone(dark?11:96,13),
      '--hc-surface-container':tone(dark?15:93,13),'--hc-surface-high':tone(dark?20:90,13),
      '--hc-on-surface':tone(dark?92:12,10),'--hc-on-surface-variant':tone(dark?76:35,10),
      '--hc-outline':tone(dark?44:57,8),'--hc-outline-variant':tone(dark?28:81,10),
      '--hc-accent':tone(dark?82:35,Math.max(35,sat)),'--hc-graph-bg':tone(dark?10:97,17),
      '--hc-error':dark?'#ffb4ab':'#ba1a1a','--hc-error-container':dark?'#55201d':'#ffdad6'};
  }
  const names = {
    recall_tokens:'召回 Token 预算',always_limit:'Always 最大条数',relevant_limit:'Relevant 最大条数',historical_limit:'历史最大条数',
    graph_recall_enabled:'自动关联图召回',graph_recall_hops:'自动图召回跳数',graph_recall_limit:'图补充事实最多条数',graph_recall_tokens:'图补充事实 Token 子预算',
    extraction_tokens:'提取输出预算',extraction_input_tokens:'提取证据预算',max_items:'每次提取最大条数',
    model:'提取 / 控制分类 / 画像模型',base_url:'供应商兼容 API 地址',api_key_env:'模型密钥变量名',embedding_model:'Embedding 模型',
    provider_preference:'文本路由偏好（price / throughput）',embedding_provider_preference:'向量路由偏好（price / throughput）',embedding_dimensions:'向量维度',embedding_revision:'向量空间版本',timeout:'模型请求超时（秒）',
    min_confidence:'最低置信度',min_future_use:'最低未来价值',min_stability:'最低稳定性',activate_threshold:'自动激活门槛',
    temporary_activate_threshold:'临时情境激活门槛',review_threshold:'候选审核门槛',archive_threshold:'归档强度门槛',permanent_threshold:'永久记忆强度门槛',
    permanent_access_count:'永久记忆交付次数',reinforcement:'每次交付强化值',decay_rates:'各类每日衰减率',
    graph_url:'FalkorDB 地址',graph_name:'图命名空间前缀',graph_password_env:'图密码变量名',owner_id:'Owner 稳定身份',
    aliases:'已核实账号身份绑定',trusted_cli_owner:'信任本机 CLI 为 Owner',auto_approve:'LLM 自动审核所有候选',confirmation_types:'传统确认模式的事实类型',timezone:'记忆维护时区',capture_owner_in_groups:'记录群内所有者证据',chat_auto_archive:'自动归档并整理聊天记录',knowledge_auto_archive:'自动归档已授权所有者的附件',knowledge_ocr_languages:'OCR 语言（Tesseract）'
  };
  const groups = {
    '自动关联图召回':['graph_recall_enabled','graph_recall_hops','graph_recall_limit','graph_recall_tokens'],
    '记忆行为与倾向':['recall_tokens','always_limit','relevant_limit','historical_limit','extraction_tokens','extraction_input_tokens','max_items','min_confidence','min_future_use','min_stability','activate_threshold','temporary_activate_threshold','review_threshold','archive_threshold','permanent_threshold','permanent_access_count','reinforcement','decay_rates','auto_approve','confirmation_types','timezone'],
    '图服务连接':['graph_url','graph_name','graph_password_env'],
    '附件整理':['knowledge_auto_archive','knowledge_ocr_languages']
  };
  const modelKeys=['model','base_url','api_key_env','provider_preference','embedding_provider_preference','embedding_model','embedding_dimensions','embedding_revision','timeout'];
  function ModelManager({api,run,notify,onSaved,onDirty,beforeSave}){
    const [data,setData]=useState(null),[form,setForm]=useState(null),[baseline,setBaseline]=useState(null);
    const fetchModels=async()=>{const v=await api('/models');const f={model:v.chat.model||'',embedding_model:v.embedding.model||'',embedding_dimensions:v.embedding.dimensions||0,embedding_revision:v.embedding.revision||'1',timeout:v.timeout,revision:v.revision};setData(v);setForm(f);setBaseline(f);};
    const load=()=>run(fetchModels);
    useEffect(()=>{load();return()=>onDirty?.(false);},[]);
    const dirty=!!form&&json(form)!==json(baseline);
    useEffect(()=>{onDirty?.(dirty);},[dirty]);
    if(!data||!form)return box('GraMem 模型管理',note('正在读取模型配置…'),b('重试',load));
    const edit=(key,value)=>setForm(v=>({...v,[key]:value}));
    const save=()=>{if(beforeSave&&!beforeSave())return;return run(async()=>{await api('/models',{},form,'PUT');await fetchModels();await onSaved();notify('GraMem 模型已保存。重新启动宿主实例后生效。');});};
    const modelField=(key,title,kind,list)=>h('label',null,h('span',null,title),input(form[key],v=>edit(key,v),{list,maxLength:200,placeholder:kind==='chat'?'留空停用模型处理':'留空停用向量'}),h('datalist',{id:list},data.catalog.filter(x=>x.kind===kind).map(x=>h('option',{key:x.id,value:x.id},x.name))));
    return box('GraMem 模型管理',note('提取、分类、画像和聊天整理共用 Chat 模型；知识库和语义检索使用 Embedding 模型。可选择推荐项或填写阿里官方模型 ID。'),
      h('div',{className:'hc-model-grid'},
        modelField('model','Chat 模型','chat','hc-chat-models'),
        modelField('embedding_model','Embedding 模型','embedding','hc-embedding-models'),
        h('label',null,h('span',null,'向量维度（0 使用模型默认值）'),input(form.embedding_dimensions,v=>edit('embedding_dimensions',v===''?'':Number(v)),{type:'number',min:0,step:1})),
        h('label',null,h('span',null,'向量空间版本'),input(form.embedding_revision,v=>edit('embedding_revision',v),{maxLength:100})),
        h('label',null,h('span',null,'请求超时（秒）'),input(form.timeout,v=>edit('timeout',v===''?'':Number(v)),{type:'number',min:1,max:120,step:1}))
      ),
      note('更换向量模型或维度时会自动更新空间版本。旧向量不再参与新空间检索；知识库向量由后台逐步重建。'),
      h('div',{className:'hc-model-endpoint'},h('strong',null,'阿里 DashScope 官方接口'),note('https://dashscope.aliyuncs.com/compatible-mode/v1 · DASHSCOPE_API_KEY'),data.base_url!=='https://dashscope.aliyuncs.com/compatible-mode/v1'||data.api_key_env!=='DASHSCOPE_API_KEY'?note('当前连接尚未切换，保存模型配置后将切换到官方接口。'):null),
      h('div',{className:'hc-toolbar'},b('刷新模型配置',()=>{if(!dirty||confirm('放弃未保存的模型修改并刷新？'))load();}),b('保存模型配置',save,{className:'hc-primary'}))
    );
  }
  function Settings({data, save, api, run, notify,onDirty,reload}){
    const [values,setValues]=useState(data.values),[keys,setKeys]=useState({}),[credential,setCredential]=useState({kind:'model',value:''}),[modelDirty,setModelDirty]=useState(false);
    useEffect(()=>{run(async()=>setKeys(await api('/credentials')));},[data]);
    useEffect(()=>{setValues(data.values);},[data]);
    const edit=(key,v)=>setValues(prev=>({...prev,[key]:v}));
    useEffect(()=>{onDirty?.(modelDirty||json(values)!==json(data.values));},[values,data,modelDirty]);
    useEffect(()=>()=>onDirty?.(false),[]);
    return h('div',null,h(ModelManager,{key:data.revision,api,run,notify,onSaved:reload,onDirty:setModelDirty,beforeSave:()=>json(values)===json(data.values)||confirm('保存模型将重新加载行为配置。放弃其他尚未保存的行为修改并继续吗？')}),note('保存前会校验并备份。配置保存后需要重新启动宿主实例才能应用。更换 owner_id 或图命名空间需要单独迁移；更换 embedding 模型时应调整向量空间版本。'),
      Object.entries({...groups,...(Object.keys(values).some(key=>!Object.values(groups).flat().includes(key)&&![...modelKeys,'owner_id','aliases','trusted_cli_owner','capture_owner_in_groups'].includes(key))?{'其他 GraMem 设置':Object.keys(values).filter(key=>!Object.values(groups).flat().includes(key)&&![...modelKeys,'owner_id','aliases','trusted_cli_owner','capture_owner_in_groups'].includes(key))}:{})}).map(([title,keys])=>box(title,h('div',{className:'hc-form-grid'},keys.filter(key=>key in values).map(key=>{
        const value=values[key];let field;
        if(typeof value==='boolean') field=h('label',{className:'hc-check'},h('input',{'aria-label':names[key]||key,type:'checkbox',checked:value,onChange:e=>edit(key,e.target.checked)}),'启用');
        else if(key==='decay_rates') field=h('div',{className:'hc-decay-grid'},note('每天的衰减率。数值越大，记忆淡化越快；0 表示不衰减。'),...Object.entries(value).map(([kind,rate])=>h('label',{key:kind},typeNames[kind]||kind,input(rate,v=>edit(key,{...value,[kind]:v===''?'':Number(v)}),{type:'number',min:0,step:.001}))));
        else if(key==='confirmation_types') field=h('div',null,note('关闭自动审核时，以下类型需要确认。'),...([...new Set([...typeOptions.map(x=>x[0]),...value])].map(kind=>h('label',{key:kind,className:'hc-check'},h('input',{type:'checkbox',checked:value.includes(kind),onChange:e=>edit(key,e.target.checked?[...value,kind]:value.filter(v=>v!==kind))}),typeNames[kind]||kind))));
        else if(typeof value==='object') field=h(Readable,{value});
        else field=input(value,v=>edit(key,typeof value==='number' ? (v===''?'':Number(v)):v),{'aria-label':names[key]||key,type:typeof value==='number'?'number':'text',step:'any'});
        return h('div',{key,className:'hc-setting-field'},h('span',null,names[key]||key),field);
      })),title==='模型与图供应商'?note('GraMem 2.0 的提取、语义排除分类和画像共享上面的 Chat 模型；Embedding 使用单独模型名和同一 API 地址。这里管理 GraMem 使用的模型和供应商连接，密钥通过下面的独立凭据表单保存。'):null)),
      box('GraMem 连接凭据',note('密钥只写入宿主的保密存储，不通过页面返回。若此变量也被其他组件复用，更换会同时影响它们。保存后需重新启动宿主实例。'),h('div',{className:'hc-toolbar'},select(credential.kind,v=>setCredential(c=>({...c,kind:v,value:''})),[['model','模型 API 密钥'],['graph','FalkorDB 密码']]),input(credential.value,v=>setCredential(c=>({...c,value:v})),{type:'password',autoComplete:'new-password',placeholder:'输入新的凭据',maxLength:10000}),b('保存凭据',()=>run(async()=>{await api('/credentials',{},credential,'PUT');setCredential(c=>({...c,value:''}));setKeys(await api('/credentials'));notify('GraMem 连接凭据已保存，需重新启动宿主实例。');}))),note(`${keys[credential.kind]?.env||'—'} · ${keys[credential.kind]?.is_set?'已配置':'未配置'}`)),
      b('保存行为设置',()=>{if(modelDirty&&!confirm('保存行为设置会重新读取模型配置。放弃尚未保存的模型修改并继续吗？'))return;return save(values);})
    );
  }
  function Graph({api,scope,run}){
    const [q,setQ]=useState(''),[filter,setFilter]=useState(''),[hops,setHops]=useState('1'),[historical,setHistorical]=useState(false);
    const [data,setData]=useState({items:[]}),[selected,setSelected]=useState(null),[zoom,setZoom]=useState(1),[pan,setPan]=useState({x:0,y:0}),[sourceDetails,setSourceDetails]=useState(null);
    const [nodes,setNodes]=useState([]);const drag=useRef(null),svg=useRef(null),seq=useRef(0);
    const load=()=>{const n=++seq.current;run(async()=>{const result=await api('/graph',{q,hops,historical,scope});if(n===seq.current){setData(result);setSelected(null);setSourceDetails(null);}});};
    useEffect(()=>{load();return()=>{seq.current++;};},[scope]);
    useEffect(()=>{
      const labels=[...new Set(data.items.flatMap(e=>[e.subject,e.object]))];
      const n=labels.map((name,i)=>({name,x:500+300*Math.cos(i*2*Math.PI/Math.max(1,labels.length)),y:300+220*Math.sin(i*2*Math.PI/Math.max(1,labels.length)),vx:0,vy:0}));
      const byName=new Map(n.map(x=>[x.name,x]));
      // Deterministic force relaxation yields a web rather than a hierarchy.
      for(let iteration=0;iteration<180;iteration++){
        n.forEach(a=>{a.vx+=(500-a.x)*.006;a.vy+=(300-a.y)*.006;});
        for(let i=0;i<n.length;i++)for(let j=i+1;j<n.length;j++){
          const a=n[i],c=n[j],dx=a.x-c.x,dy=a.y-c.y,d=Math.max(12,Math.hypot(dx,dy)),force=1900/(d*d);
          a.vx+=dx/d*force;c.vx-=dx/d*force;a.vy+=dy/d*force;c.vy-=dy/d*force;
        }
        data.items.forEach(e=>{const a=byName.get(e.subject),c=byName.get(e.object);if(a===c)return;const dx=c.x-a.x,dy=c.y-a.y,d=Math.max(1,Math.hypot(dx,dy)),f=(d-135)*.014;a.vx+=dx/d*f;c.vx-=dx/d*f;a.vy+=dy/d*f;c.vy-=dy/d*f;});
        n.forEach(a=>{a.vx*=.65;a.vy*=.65;a.x=Math.min(940,Math.max(60,a.x+a.vx));a.y=Math.min(550,Math.max(50,a.y+a.vy));});
      }
      setNodes(n);setZoom(1);setPan({x:0,y:0});
    },[data.items]);
    const byName=new Map(nodes.map(n=>[n.name,n]));
    const matches=name=>!filter||name.toLocaleLowerCase().includes(filter.toLocaleLowerCase());
    const visibleEdges=data.items.filter(e=>!selected||e.subject===selected||e.object===selected);
    function point(ev){const p=svg.current.createSVGPoint();p.x=ev.clientX;p.y=ev.clientY;const local=p.matrixTransform(svg.current.getScreenCTM().inverse());return {x:local.x,y:local.y};}
    return h('div',null,box('关系图 · 网状显示器',
      h('form',{className:'hc-toolbar',onSubmit:e=>{e.preventDefault();load();}},input(q,setQ,{placeholder:'搜索图实体，例如 GraMem',maxLength:2000}),select(hops,setHops,[['1','1 跳'],['2','2 跳'],['3','3 跳']]),h('label',{className:'hc-check'},h('input',{type:'checkbox',checked:historical,onChange:e=>setHistorical(e.target.checked)}),'历史关系'),h('button',{type:'submit'},'搜索关系')),
      h('div',{className:'hc-toolbar'},input(filter,setFilter,{placeholder:'在当前图中高亮实体'}),b('放大',()=>setZoom(z=>Math.min(4,z*1.2))),b('缩小',()=>setZoom(z=>Math.max(.3,z/1.2))),b('复位',()=>{setZoom(1);setPan({x:0,y:0});setSelected(null);}),h('span',{className:'hc-muted'},`${nodes.length} 实体 · ${data.items.length} 关系`)),
      data.healthy===false?h('p',{className:'hc-error'},'图服务不可达。空结果不表示图中没有关系。'):null,
      data.truncated?note('当前图达到显示上限（最多 199 条关系）；请搜索更具体的实体以缩小范围。'):null,
      h('div',{className:'hc-graph-wrap'},h('svg',{ref:svg,viewBox:'0 0 1000 600',className:'hc-graph',role:'img','aria-label':'可拖动的记忆关系网状图',
        onWheel:e=>{setZoom(z=>Math.max(.3,Math.min(4,z*(e.deltaY>0?.9:1.1))));},
        onPointerDown:e=>{if(e.target===e.currentTarget){drag.current={kind:'pan',start:point(e),pan};e.currentTarget.setPointerCapture(e.pointerId);}},
        onPointerMove:e=>{if(!drag.current)return;const p=point(e),d=drag.current;if(d.kind==='pan')setPan({x:d.pan.x+p.x-d.start.x,y:d.pan.y+p.y-d.start.y});else setNodes(prev=>prev.map(n=>n.name===d.name?{...n,x:(p.x-pan.x)/zoom,y:(p.y-pan.y)/zoom}:n));},
        onPointerUp:()=>drag.current=null,onPointerCancel:()=>drag.current=null},
        h('defs',null,h('marker',{id:'hc-arrow',viewBox:'0 0 10 10',refX:9,refY:5,markerWidth:6,markerHeight:6,orient:'auto-start-reverse'},h('path',{d:'M 0 0 L 10 5 L 0 10 z',fill:'var(--hc-primary)'}))),
        h('g',{transform:`translate(${pan.x},${pan.y}) scale(${zoom})`},
          data.items.map((e,i)=>{const a=byName.get(e.subject),c=byName.get(e.object);if(!a||!c)return null;const dx=c.x-a.x,dy=c.y-a.y,d=Math.max(1,Math.hypot(dx,dy)),x1=a.x+dx/d*21,y1=a.y+dy/d*21,x2=c.x-dx/d*24,y2=c.y-dy/d*24;
            const related=!selected||e.subject===selected||e.object===selected;
            const siblings=data.items.filter(x=>(x.subject===e.subject&&x.object===e.object)||(x.subject===e.object&&x.object===e.subject));
            const index=siblings.indexOf(e),offset=(index-(siblings.length-1)/2)*30;
            const cx=(x1+x2)/2-dy/d*offset,cy=(y1+y2)/2+dx/d*offset;
            return h('g',{key:`${e.id||'edge'}-${i}`,opacity:related?.8:.12},h('path',{d:a===c?`M ${a.x-12} ${a.y-18} C ${a.x-75} ${a.y-95},${a.x+75} ${a.y-95},${a.x+12} ${a.y-18}`:`M ${x1} ${y1} Q ${cx} ${cy} ${x2} ${y2}`,stroke:e.valid_until?'var(--hc-on-surface-variant)':'var(--hc-primary)',strokeWidth:1.5,strokeDasharray:e.valid_until?'5 4':undefined,fill:'none',markerEnd:'url(#hc-arrow)'},h('title',null,`${e.subject} → ${e.predicate} → ${e.object}\n来源 ${e.memory_id}`)),h('text',{x:cx,y:cy-5,textAnchor:'middle',className:'hc-edge-label'},e.predicate));}),
          nodes.map(n=>h('g',{key:n.name,transform:`translate(${n.x},${n.y})`,className:'hc-node',opacity:matches(n.name)?1:.18,tabIndex:0,role:'button','aria-label':n.name,onKeyDown:e=>{if(e.key==='Enter')setSelected(n.name);},onClick:()=>setSelected(s=>s===n.name?null:n.name),onPointerDown:e=>{e.stopPropagation();drag.current={kind:'node',name:n.name};svg.current.setPointerCapture(e.pointerId);}},h('circle',{r:selected===n.name?25:20,fill:selected===n.name?'var(--hc-primary)':'var(--hc-primary-container)',stroke:'var(--hc-primary)',strokeWidth:2}),h('text',{y:37,textAnchor:'middle',className:'hc-node-label'},n.name.length>23?n.name.slice(0,23)+'…':n.name),h('title',null,n.name)))
        )),!nodes.length? h('div',{className:'hc-graph-empty'},'未找到关系。尝试其他实体、更多跳数或历史关系。'):null),
      note('拖动节点调整网状结构；拖动背景平移；滚轮缩放。箭头表示关系方向，虚线表示历史失效关系。点击实体聚焦关联线。')),
      box(selected?`关系详情 · ${selected}`:'关系与来源',sourceDetails?box('来源记忆',b('关闭来源',()=>setSourceDetails(null)),inspect(sourceDetails)):null,h('div',{className:'hc-table-scroll'},h('table',null,h('thead',null,h('tr',null,['主体','关系','对象','来源记忆','有效时间'].map(v=>h('th',{key:v},v)))),h('tbody',null,visibleEdges.map((e,i)=>h('tr',{key:`${e.id||'edge'}-${i}`},h('td',null,e.subject),h('td',null,e.predicate),h('td',null,e.object),h('td',null,b(e.memory_id,()=>run(async()=>{const v=await api('/memories',{scope,q:e.memory_id,status:e.valid_until?'superseded':'active'});if(!v.items.length&&historical){const old=await api('/memories',{scope,q:e.memory_id,status:'archived'});setSourceDetails(old.items);}else setSourceDetails(v.items);}),{className:'hc-text-button'})),h('td',null,`${date(e.valid_from)} → ${e.valid_until?date(e.valid_until):'当前'}`)))))))
    );
  }
  function Memories({api,scope,run,notify}){
    const [q,setQ]=useState(''),[term,setTerm]=useState(''),[status,setStatus]=useState('active'),[page,setPage]=useState(1),[data,setData]=useState({items:[],total:0});
    const [chosen,setChosen]=useState([]),[form,setForm]=useState({content:'',type:'knowledge',slot:'',action:'remember',relations:[]}),[details,setDetails]=useState(null),[semantic,setSemantic]=useState(null),seq=useRef(0);
    const load=async()=>{const n=++seq.current;const v=await api('/memories',{scope,q:term,status,page});if(n===seq.current)setData(v);};
    useEffect(()=>{setChosen([]);setDetails(null);setSemantic(null);setForm({content:'',type:'knowledge',slot:'',action:'remember',relations:[]});},[scope]);
    useEffect(()=>{run(load);return()=>{seq.current++;};},[scope,term,status,page]);
    const op=(action,row)=>run(async()=>{if(['forget','suppress'].includes(action)&&!confirm(`确认${action==='forget'?'永久遗忘':'停用'}整个槽位 ${row.slot} 的所有版本与派生内容？${action==='forget'?' 如果关联导入文档，将同时遗忘整份文档来源的全部分块及派生事实。':''}`))return;const result=await api('/operation',{}, {action,scope,id:row.id,authorization:true});notify(({forget:'此主题及其派生内容已遗忘',suppress:'此主题已停用',reject:'候选记忆已拒绝'})[action]||'操作完成');await load();});
    const edit=(k,v)=>setForm(prev=>({...prev,[k]:v}));
    return h('div',null,box('记忆搜索与版本管理',
      h('form',{className:'hc-toolbar',onSubmit:e=>{e.preventDefault();setPage(1);setTerm(q);}},input(q,setQ,{placeholder:'中文关键词 / 内容 / 槽位 / 类型 / ID'}),h('button',{type:'submit'},'搜索全部记忆'),select(status,v=>{setStatus(v);setPage(1);setChosen([]);},[['active','有效'],['candidate','自动审核中'],['superseded','已替换历史'],['archived','归档'],['rejected','已拒绝'],['forgotten','已遗忘（排除隐藏）']]),b('语义召回',()=>run(async()=>{if(!q.trim())throw Error('请填写召回问题');setSemantic(await api('/recall',{scope,q,historical:['superseded','archived'].includes(status)}));}))),
      semantic?box('语义召回结果',note(`${semantic.tokens} 个估算 Tokens`),h('pre',null,semantic.context||'没有召回匹配')):null,
      h('div',{className:'hc-table-scroll'},h('table',null,h('thead',null,h('tr',null,['选择','事实 / 槽位','类型与生命周期','强度 / 置信度','操作'].map(v=>h('th',{key:v},v)))),h('tbody',null,data.items.map(row=>h('tr',{key:row.id},h('td',null,h('input',{type:'checkbox',checked:chosen.includes(row.id),onChange:e=>setChosen(v=>e.target.checked?[...v,row.id]:v.filter(id=>id!==row.id))})),h('td',null,h('p',null,row.content),h('small',null,row.slot),h('br'),h('small',null,row.id)),h('td',null,typeNames[row.type]||row.type,h('br'),h('span',{className:'hc-tag'},({temporary:'临时',normal:'普通',permanent:'长期保留'})[row.lifecycle]||row.lifecycle)),h('td',null,`${Number(row.strength).toFixed(3)} / ${Number(row.confidence).toFixed(2)}`),h('td',null,h('div',{className:'hc-actions'},b('详情',()=>setDetails(row)),status==='active'?b('编辑',()=>{setChosen([row.id]);setForm({content:row.content,type:row.type,slot:row.slot,action:'update',relations:row.metadata.relations||[]});}):null,status==='candidate'?h('span',{className:'hc-tag'},'后台自动审核'):null,status==='candidate'?b('拒绝',()=>op('reject',row)):null,b('停用槽位',()=>op('suppress',row)),b('遗忘槽位',()=>op('forget',row),{className:'hc-danger'})))))))),
      !data.items.length?note('没有符合条件的记忆。被遗忘或停用的内容不会出现在搜索结果中。'):null,
      h('div',{className:'hc-toolbar'},b('上一页',()=>setPage(p=>p-1),{disabled:page<=1}),h('span',null,`第 ${page} 页 · ${data.total} 条`),b('下一页',()=>setPage(p=>p+1),{disabled:page*30>=data.total}),b('刷新',()=>run(load)))),
      details?box('记忆来源与版本详情',b('关闭',()=>setDetails(null)),inspect(details)):null,
      box('新增 / 更新 / 合并',select(form.action,v=>edit('action',v),[['remember','新增事实'],['update','更新已选事实'],['merge','合并已选事实']]),note(`已选择 ${chosen.length} 条目标。更新和合并保留旧版本与派生来源。`),
        h('div',{className:'hc-form-grid'},h('label',null,'类型',select(form.type,v=>edit('type',v),typeOptions.some(([k])=>k===form.type)?typeOptions:[...typeOptions,[form.type,form.type]])),h('label',null,'主题标识（可选，留空自动生成）',input(form.slot,v=>edit('slot',v),{maxLength:200}))),
        h('textarea',{value:form.content,maxLength:2000,rows:4,placeholder:'明确事实（最多 2000 字）',onChange:e=>edit('content',e.target.value)}),
        h('details',null,h('summary',null,'有事实来源的关系（可选）'),note('填写主体、关系和对象，例如：王子睿 → 使用 → Telegram。关系应有当前事实支持。'),h(Relations,{value:form.relations,onChange:v=>edit('relations',v)})),
        b('保存事实',()=>run(async()=>{if(form.action!=='remember'&&!chosen.length)throw Error('请先选择目标记忆');const relations=form.relations;if(relations.some(r=>['subject','predicate','object'].some(k=>!r[k]?.trim())))throw Error('请补全每条关系的主体、关系和对象，或移除空行');await api('/operation',{}, {action:form.action,scope,content:form.content,type:form.type,slot:form.slot,targets:form.action==='remember'?[]:chosen,relations});setForm({content:'',type:'knowledge',slot:'',action:'remember',relations:[]});setChosen([]);notify('事实已保存');await load();})))
    );
  }
  function Profiles({api,scope,run,notify}){
    const [data,setData]=useState({profile:{},exclusions:[]}),[source,setSource]=useState(null),[form,setForm]=useState({content:'',type:'preference'}),[saving,setSaving]=useState(false),seq=useRef(0);
    const load=async()=>{const n=++seq.current,v=await api('/profile',{scope});if(n===seq.current)setData(v);};
    useEffect(()=>{setData({profile:{},exclusions:[]});setSource(null);setForm({content:'',type:'preference'});run(load);return()=>{seq.current++;};},[scope]);
    const showSource=id=>{const n=seq.current;run(async()=>{const v=await api('/memories',{scope,q:id});if(n!==seq.current)return;const row=v.items.find(r=>r.id===id);if(!row)throw Error('这条来源已不可用，请刷新画像。');setSource({...row,draft:row.content});});};
    const submit=(action,row)=>run(async()=>{setSaving(true);try{
      if(action==='remember'){if(!form.content.trim())throw Error('请填写你希望记住的事实或偏好。');await api('/operation',{}, {action,scope,content:form.content.trim(),type:form.type});setForm(v=>({...v,content:''}));}
      else if(action==='update'){if(!row.draft.trim())throw Error('事实内容不能为空。');await api('/operation',{}, {action,scope,content:row.draft.trim(),type:row.type,slot:row.slot,targets:[row.id],relations:row.metadata?.relations||[]});setSource(null);}
      else {if(!confirm(`停用「${row.content}」所在主题的全部版本与派生内容？保留原记录，可在下方解除停用。`))return;await api('/operation',{}, {action:'suppress',scope,id:row.id,authorization:true});setSource(null);}
      notify(action==='suppress'?'该主题已停用，画像已重新整理。':'来源事实已保存，画像已依据有效记忆更新。');await load();
    }finally{setSaving(false);}});
    const entries=Object.entries(data.profile).filter(([,items])=>Array.isArray(items)&&items.length);
    return h('div',null,box('记忆画像',note('画像依据有效记忆生成。点击“查看来源”可直接修改支撑结论的事实；修改后会重新整理画像。'),
      h('div',{className:'hc-toolbar'},b('刷新画像',()=>run(load)),b('用模型重新归纳',()=>run(async()=>{if(!confirm('调用配置模型重新归纳画像？会产生模型费用。'))return;await api('/operation',{}, {action:'reflect',scope});notify('画像已重新归纳');await load();}))),
      entries.length?h('div',{className:'hc-portrait-grid'},entries.map(([category,items])=>h('section',{className:'hc-portrait-category',key:category},h('h3',null,typeNames[category]||category),items.map((item,i)=>h('article',{className:'hc-portrait-fact',key:i},h('p',null,item.fact||String(item)),h('div',{className:'hc-actions'},(item.source_ids||[item.id]).filter(Boolean).map((id,n)=>b(`查看来源${(item.source_ids||[]).length>1?' '+(n+1):''}`,()=>showSource(id),{key:id})))))))):note('还没有可生成画像的有效事实。你可以在下面添加身份特征或偏好。'),
      h('details',{className:'hc-advanced'},h('summary',null,'高级：查看画像 JSON'),h('pre',null,json(data.profile)))),
      source?box('编辑来源事实',note(`${typeNames[source.type]||source.type} · 修改会保留旧版本和来源关系。`),h('label',null,'事实内容',h('textarea',{'aria-label':'事实内容',rows:4,value:source.draft,maxLength:2000,onChange:e=>setSource(v=>({...v,draft:e.target.value}))})),h('div',{className:'hc-toolbar'},b('保存来源修改',()=>submit('update',source),{disabled:saving}),b('停用此主题',()=>submit('suppress',source),{disabled:saving,className:'hc-danger'}),b('关闭来源',()=>setSource(null),{disabled:saving,className:'hc-secondary'})),h('details',{className:'hc-advanced'},h('summary',null,'查看来源与版本信息'),inspect(source))):null,
      box('补充身份特征与偏好',note('用一句明确事实描述自己，例如“回答时我偏好先给结论，再解释细节”。会保存到顶部所选记忆身份中。'),h('form',{onSubmit:e=>{e.preventDefault();submit('remember');}},h('label',null,'内容类型',select(form.type,v=>setForm(f=>({...f,type:v})),typeOptions.filter(([k])=>['identity','occupation','preference','interests','skill','project','relationship'].includes(k)))),h('label',null,'希望记住的事实',h('textarea',{'aria-label':'希望记住的事实',rows:3,value:form.content,maxLength:2000,onChange:e=>setForm(f=>({...f,content:e.target.value})),placeholder:'例如：我偏好简洁的中文回答'})),h('div',{className:'hc-toolbar'},h('button',{type:'submit',disabled:saving||!form.content.trim()},'保存这条事实')))),
      box('遗忘 / 停用与重新授权',note('遗忘不会恢复旧内容；重新授权仅允许记录新事实。临时停用解除后，可再次使用保留的原记录。'),
        data.exclusions.length?h('div',{className:'hc-table-scroll'},h('table',null,h('thead',null,h('tr',null,['主题标识','状态','更新时间','操作'].map(v=>h('th',{key:v},v)))),h('tbody',null,data.exclusions.map(row=>h('tr',{key:row.slot},h('td',null,row.slot),h('td',null,({suppressed:'已停用',deleted:'已遗忘',active:'已授权'})[row.state]||row.state),h('td',null,date(row.updated)),h('td',null,row.state==='suppressed'?b('解除停用',()=>run(async()=>{await api('/operation',{}, {action:'reactivate',scope,slot:row.slot});await load();})):row.state==='deleted'?b('授权重新记住新事实',()=>run(async()=>{if(!confirm(`明确授权重新记住 ${row.slot} 的新事实？旧值不会恢复。`))return;await api('/operation',{}, {action:'reauthorize',scope,slot:row.slot,authorization:true});await load();})):null)))))):note('没有遗忘或停用记录。'))
    );
  }
  function Operations({api,scope,run,notify}){
    const [records,setRecords]=useState([]),[exclusions,setExclusions]=useState([]),[activate,setActivate]=useState(false),[queues,setQueues]=useState(null),[result,setResult]=useState(null),[raw,setRaw]=useState({records:'[]',exclusions:'[]'});
    const op=action=>run(async()=>{const v=await api('/operation',{}, {action,scope});setResult(v);notify('操作完成');});
    const prepare=(value,kind)=>{const rows=Array.isArray(value)?value:value?.items||value?.memories;if(!Array.isArray(rows)||rows.some(r=>!r||typeof r!=='object'||Array.isArray(r)))throw Error('文件应包含记录对象数组，或带 items / memories 数组的导出文件。');if(rows.length>10000)throw Error('一次最多导入 10000 条记录。');const normalized=rows.map(r=>kind==='records'?{...r,content:r.content??r.text??'',type:r.type||'knowledge',slot:r.slot||''}:{...r,slot:r.slot||r.key||'',state:r.state||r.status||'suppressed'});if(kind==='records')setRecords(normalized);else setExclusions(normalized);};
    const upload=(e,kind)=>{const file=e.target.files?.[0];e.target.value='';if(!file)return;run(async()=>{if(file.size>20_000_000)throw Error('文件最大 20 MB。');const text=await file.text();let parsed;try{parsed=JSON.parse(text);}catch{try{parsed=text.split(/\r?\n/).filter(s=>s.trim()).map(s=>JSON.parse(s));}catch{throw Error('无法读取这个文件，请上传有效的 JSON 或 JSONL 导出。');}}prepare(parsed,kind);notify('文件已读取，请检查预览后执行导入。');});};
    const rowEdit=(kind,index,key,value)=>{const setter=kind==='records'?setRecords:setExclusions;setter(rows=>rows.map((row,n)=>n===index?{...row,[key]:value}:row));};
    return h('div',null,box('维护、持久队列与备份',note('手动处理一次只消费一个任务。维护覆盖当前工作空间所有身份。备份包含 SQLite 与知识库原件；独立 FalkorDB 需另行备份。'),
      h('div',{className:'hc-toolbar'},b('生命周期维护 + 图同步',()=>op('maintain')),b('整理同槽事实与画像',()=>{if(confirm('调用模型整理当前身份的兼容事实并生成画像？会产生模型费用。'))op('consolidate');}),b('同步图队列',()=>op('sync_graph')),b('处理一个后台任务',()=>op('worker')),b('创建一致性备份',()=>op('backup')),b('查看队列',()=>run(async()=>setQueues(await api('/queues'))))),
      result?inspect(result):null,queues?inspect(queues):null),
      box('导入旧记忆',note('上传导出文件，或逐条添加记录。导入前可修改内容和类型；默认进入自动审核。排除记录会先导入，以保留原来的遗忘和停用边界。'),
        h('div',{className:'hc-form-grid'},h('label',null,'读取记忆文件',h('input',{type:'file',accept:'.json,.jsonl,application/json',onChange:e=>upload(e,'records')})),h('label',null,'读取遗忘 / 停用文件（可选）',h('input',{type:'file',accept:'.json,.jsonl,application/json',onChange:e=>upload(e,'exclusions')}))),
        h('div',{className:'hc-toolbar'},b('添加记忆记录',()=>setRecords(v=>[...v,{content:'',type:'knowledge',slot:''}])),b('添加排除记录',()=>setExclusions(v=>[...v,{slot:'',state:'suppressed'}])),h('span',null,`${records.length} 条记忆 · ${exclusions.length} 条排除`)),
        h('div',{className:'hc-import-preview'},records.slice(0,100).map((row,i)=>h('div',{className:'hc-import-row',key:i},h('label',null,`第 ${i+1} 条记忆`,h('textarea',{'aria-label':`第 ${i+1} 条记忆`,rows:2,value:row.content,maxLength:2000,onChange:e=>rowEdit('records',i,'content',e.target.value)})),h('div',{className:'hc-form-grid'},h('label',null,'类型',select(row.type,v=>rowEdit('records',i,'type',v),typeOptions.some(([k])=>k===row.type)?typeOptions:[...typeOptions,[row.type,row.type]])),h('label',null,'主题标识（可选）',input(row.slot,v=>rowEdit('records',i,'slot',v),{maxLength:200}))),b('移除记录',()=>setRecords(v=>v.filter((_,n)=>n!==i)),{className:'hc-quiet'}))),exclusions.slice(0,100).map((row,i)=>h('div',{className:'hc-import-row',key:'exclusion-'+i},h('div',{className:'hc-form-grid'},h('label',null,'排除主题标识',input(row.slot,v=>rowEdit('exclusions',i,'slot',v),{maxLength:200})),h('label',null,'状态',select(row.state,v=>rowEdit('exclusions',i,'state',v),[['suppressed','停用'],['deleted','遗忘']]))),b('移除排除记录',()=>setExclusions(v=>v.filter((_,n)=>n!==i)),{className:'hc-quiet'})))),
        records.length>100||exclusions.length>100?note('预览显示每类的前 100 条，导入时包含文件中的全部记录。'):null,
        h('label',{className:'hc-check'},h('input',{type:'checkbox',checked:activate,onChange:e=>setActivate(e.target.checked)}),'这些事实已由我审核，直接导入为有效记忆'),
        h('div',{className:'hc-toolbar'},b('执行导入',()=>run(async()=>{if(records.some(r=>!r.content?.trim()||r.content.length>2000))throw Error('每条记忆都需要 1–2000 字的内容，请补全或移除空记录。');if(exclusions.some(r=>!r.slot?.trim()||!['deleted','suppressed'].includes(r.state)))throw Error('排除记录需要主题标识和有效状态。');if(activate&&!confirm('确认这些迁移事实均已人工审核，可直接激活？'))return;setResult(await api('/import',{}, {records,exclusions,activate,scope}));setRecords([]);setExclusions([]);notify('迁移导入完成，请查看导入结果。');}),{disabled:!records.length&&!exclusions.length})),
        h('details',{className:'hc-advanced'},h('summary',null,'高级：粘贴 JSON 导出'),note('读取后进入上面的预览列表，不会立即导入。'),...['records','exclusions'].map(kind=>h('div',{key:kind},h('label',null,kind==='records'?'记忆 JSON':'排除 JSON',h('textarea',{rows:4,value:raw[kind],onChange:e=>setRaw(v=>({...v,[kind]:e.target.value})),spellCheck:false})),b('读取到预览',()=>run(async()=>prepare(JSON.parse(raw[kind]),kind)))))))
    );
  }
  function Knowledge({api,scope,run,notify,download}){
    const [q,setQ]=useState(''),[term,setTerm]=useState(''),[page,setPage]=useState(1),[history,setHistory]=useState(false);
    const [data,setData]=useState({items:[],total:0}),[hits,setHits]=useState(null),[detail,setDetail]=useState(null),[description,setDescription]=useState(''),seq=useRef(0);
    const labels={queued:'等待解析',processing:'正在解析',ready:'可检索',partial:'部分已解析',needs_parser:'需要解析组件',failed:'解析失败',empty:'没有提取到文字'};
    const load=async()=>{const n=++seq.current,v=await api('/knowledge',{scope,q:term,page,historical:history});if(n===seq.current)setData(v);};
    useEffect(()=>{run(load);return()=>{seq.current++;};},[scope,term,page,history]);
    useEffect(()=>{if(!data.items.some(r=>['queued','processing'].includes(r.status)))return;const timer=setTimeout(()=>run(load),3000);return()=>clearTimeout(timer);},[data]);
    const open=(id,start=0)=>run(async()=>setDetail(await api('/knowledge/'+id,{scope,start})));
    const control=(action,row)=>run(async()=>{if(['forget','suppress'].includes(action)&&!confirm(action==='forget'?`永久遗忘 ${row.name} 的这个版本？会删除原件、文本分块及派生事实；已有备份和渠道历史需另行处理。`:`暂停使用 ${row.name} 的这个版本？可在画像与偏好页解除停用。`))return;await api('/knowledge/control',{}, {scope,id:row.id,action});setDetail(null);setHits(null);await load();notify(action==='retry'?'已重新排队':'知识库操作完成');});
    return h('div',null,
      box('保存图片与文档',note('原件长期留存。支持 TXT、MD、CSV、JSON、PDF、DOCX 及 PNG、JPEG、WebP、GIF、TIFF、BMP，单文件最大 20 MB。解析在后台完成；图片说明可帮助以后找回照片和插图。'),
        h('label',null,'说明（可选）',h('textarea',{value:description,maxLength:2000,rows:2,onChange:e=>setDescription(e.target.value),placeholder:'例如：agent 的银白参考图设定图，今后绘图时参考'})),
        h('input',{type:'file',multiple:true,accept:'.txt,.md,.csv,.json,.pdf,.docx,.png,.jpg,.jpeg,.webp,.gif,.tif,.tiff,.bmp',onChange:e=>{const files=[...(e.target.files||[])];e.target.value='';run(async()=>{for(const file of files){if(file.size>20000000)throw Error('文件最大 20 MB');const reader=new FileReader();const encoded=await new Promise((resolve,reject)=>{reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=()=>reject(Error('文件读取失败'));reader.readAsDataURL(file);});await api('/knowledge/upload',{}, {scope,filename:file.name,data:encoded,description});}notify(`已保存 ${files.length} 个文件，等待后台解析`);setPage(1);await load();});}})),
      box('知识库检索与原件',
        h('form',{className:'hc-toolbar',onSubmit:e=>{e.preventDefault();setPage(1);setTerm(q);setHits(null);}},input(q,setQ,{placeholder:'文件名 / 标题 / 检索问题'}),h('button',{type:'submit'},'查找文件'),b('搜索内容',()=>run(async()=>{if(!q.trim())throw Error('请输入检索问题');setHits(await api('/knowledge/search',{scope,q,historical:history}));})),h('label',{className:'hc-check'},h('input',{type:'checkbox',checked:history,onChange:e=>{setHistory(e.target.checked);setPage(1);setHits(null);}}),'显示历史版本'),b('刷新',()=>run(load))),
        h('div',{className:'hc-table-scroll'},h('table',null,h('thead',null,h('tr',null,['文件 / 说明','版本 / 大小','解析状态','操作'].map(v=>h('th',{key:v},v)))),h('tbody',null,data.items.map(row=>h('tr',{key:row.id},
          h('td',null,h('strong',null,row.title),h('p',null,row.description||row.name),h('small',null,date(row.created))),
          h('td',null,`v${row.version} · ${(row.size/1024).toFixed(1)} KB`,h('br'),`${row.chunks} 个分块`),
          h('td',null,h('span',{className:'hc-tag'},labels[row.status]||row.status),row.error?note(row.error):null),
          h('td',null,h('div',{className:'hc-actions'},b('阅读',()=>open(row.id)),h('a',{href:download(row.id),download:'',className:'hc-download'},'下载原件'),['failed','needs_parser','empty'].includes(row.status)?b('重试解析',()=>control('retry',row)):null,b('停用',()=>control('suppress',row)),b('遗忘',()=>control('forget',row),{className:'hc-danger'})))
        ))))),
        !data.items.length?note('没有可见文件。私人知识库按身份隔离；被停用或遗忘的文件不会显示。'):null,
        h('div',{className:'hc-toolbar'},b('上一页',()=>setPage(p=>p-1),{disabled:page<=1}),h('span',null,`第 ${page} 页 · ${data.total} 份文件`),b('下一页',()=>setPage(p=>p+1),{disabled:page*30>=data.total}))),
      hits?box('内容搜索结果',note('结果来自原文或 OCR。OCR 可能有误，请结合原件核对。'),...hits.items.map((hit,i)=>h('article',{className:'hc-card',key:hit.memory_id+'-'+i},h('strong',null,`${hit.name} · v${hit.version} · ${hit.page?'第 '+hit.page+' 页':'正文/说明'} · 分块 ${hit.chunk}`),h('pre',null,hit.text),b('查看来源',()=>open(hit.document_id,hit.chunk)))),!hits.items.length?note('没有匹配的已索引内容。'):null):null,
      detail?box(`${detail.document.name} · v${detail.document.version}`,b('关闭',()=>setDetail(null)),h('a',{href:download(detail.document.id),download:'',className:'hc-download'},'下载原件'),...detail.items.map(item=>h('article',{key:item.memory_id},note(`${item.page?'第 '+item.page+' 页':'正文/说明'} · 分块 ${item.chunk} · ${item.method}`),h('pre',null,item.text))),detail.next!==null?b('继续阅读',()=>open(detail.document.id,detail.next)):null,detail.document.previous?b('阅读上个版本',()=>open(detail.document.previous)):null,!detail.items.length?note('原件已保存，目前没有可阅读的文字。'):null):null
    );
  }
  function ChatsView({api,scope,run,download}){
    const [overview,setOverview]=useState(null),[q,setQ]=useState(''),[platform,setPlatform]=useState(''),[session,setSession]=useState(''),[after,setAfter]=useState(''),[before,setBefore]=useState('');
    const [data,setData]=useState({items:[],total:0,next:null}),[detail,setDetail]=useState(null),[start,setStart]=useState(0);
    const [processing,setProcessing]=useState(null),[submitting,setSubmitting]=useState(false);
    const polling=useRef(0),lastJob=useRef(null),reloadResult=useRef(null),jobRequests=useRef(0);
    const filters=()=>({scope,q,platform,session,...(after?{after:Date.parse(after)/1000}:{}),...(before?{before:Date.parse(before)/1000}:{})});
    const load=(offset=0)=>run(async()=>{setStart(offset);setOverview(await api('/chats/overview',filters()));setData(await api('/chats',{...filters(),start:offset}));setDetail(null);});
    reloadResult.current=()=>load(start);
    useEffect(()=>{load();setProcessing(null);setSubmitting(false);lastJob.current=null;let closed=false;let timer;const n=++polling.current;
      const poll=async()=>{const stamp=jobRequests.current;try{const result=await api('/chats/process',{scope});if(closed||n!==polling.current)return;if(stamp===jobRequests.current){setProcessing(result);
        const wasActive=['importing','processing'].includes(lastJob.current?.state);lastJob.current=result.job;if(result.job?.state==='completed'&&wasActive)reloadResult.current();
      }}catch(e){if(!closed&&n===polling.current&&stamp===jobRequests.current)setProcessing(v=>({...v,poll_error:'进度暂时无法读取，请刷新页面。'}));}
      if(!closed)timer=setTimeout(poll,3000);};poll();return()=>{closed=true;clearTimeout(timer);polling.current++;};},[scope]);
    const processAll=(retry=false)=>{const n=polling.current;setSubmitting(true);jobRequests.current++;run(async()=>{try{const result=await api(retry?'/chats/process/retry':'/chats/process',{}, {scope},'POST');if(n===polling.current){lastJob.current=result.job;setProcessing(result);}}finally{jobRequests.current++;if(n===polling.current)setSubmitting(false);}});};
    const job=processing?.job,active=['importing','processing'].includes(job?.state);
    const open=id=>run(async()=>setDetail(await api('/chats/'+id,{scope})));
    return h('div',null,
      box('聊天整体观',note('自动整理各平台与会话的主题和时间线。每条摘要都可追溯到双方原话。'),
        h('div',{className:'hc-toolbar'},b(active?'全部历史正在处理':'一键处理全部未整理记录',()=>processAll(),{disabled:submitting||active||processing?.archive_enabled===false}),
          job&&(job.state==='failed'||job.retrying>0||job.error==='model_unavailable')?b('重试未完成任务',()=>processAll(true),{disabled:submitting}):null,b('刷新整理结果',()=>load(start))),
        note('处理当前记忆身份在任务启动前的所有可验证历史，补齐原件并生成摘要、主题及记忆网连接。已完成记录跳过；关闭页面后继续处理。搜索筛选不会缩小这项任务的范围。'),
        processing?.archive_enabled===false?note('聊天自动归档已关闭，开启后可提交整理任务。'):null,
        processing?.model_available===false?note('整理任务需要可用的模型，配置恢复后会继续。'):null,
        job?h('div',{role:'status'},h('strong',null,({importing:'正在补齐历史原话',processing:job.error==='model_unavailable'?'等待模型配置':job.retrying?'正在处理，部分记录等待重试':'正在整理历史',completed:'历史整理已完成',failed:'任务遇到问题，可重试'})[job.state]),
          h('div',{className:'hc-job-summary'},...Object.entries({total:'本次记录',done:'已完成',working:'处理中',retrying:'等待重试',remaining:'未完成',imported:'补齐原话'}).map(([key,name])=>h('div',{className:'hc-job-row',key},h('span',null,name),h('strong',null,job[key]??0)))),
          h('progress',{max:Math.max(1,job.total),value:job.state==='completed'?Math.max(1,job.total):job.done,'aria-label':'历史聊天整理进度'}),
          note('范围截至 '+date(job.cutoff)+(job.state==='completed'&&job.total===0?' · 没有需要补处理的记录。':'')),
          job.protected>0?note('已完成中有 '+job.protected+' 条依照禁提或删除规则不展示。'):null,
          job.error==='history_processing_failed'?note('读取历史时遇到问题，已有原件和进度已保留。'):null,
          job.error==='history_unavailable'?note('未找到宿主历史数据库，本次处理现有聊天档案。'):null):note('当前档案有 '+(processing?.pending??'—')+' 条待整理记录，旧历史会在提交后扫描。'),
        processing?.poll_error?note(processing.poll_error):null,
        h('div',{className:'hc-job-summary'},h('div',{className:'hc-job-row'},h('span',null,'可查询对话'),h('strong',null,overview?.turns??'—')),h('div',{className:'hc-job-row'},h('span',null,'会话'),h('strong',null,overview?.sessions.length??'—')),...Object.entries(overview?.platforms||{}).map(([name,n])=>h('div',{className:'hc-job-row',key:name},h('span',null,name),h('strong',null,n)))),
        h('div',{className:'hc-toolbar'},...(overview?.topics||[]).map(t=>b(t.topic+' · '+t.count,()=>{setQ(t.topic);},{key:t.topic}))),
        h('div',{className:'hc-toolbar'},...(overview?.jobs||[]).map(j=>h('span',{className:'hc-tag',key:j.status},({ready:'已归档',pending:'等待整理',working:'整理中',silent:'已禁提',redacted:'已删除'})[j.status]+' '+j.count))),
        (overview?.timeline||[]).slice(-12).reverse().map((item,i)=>h('article',{key:item.summary_id+'-'+i,className:'hc-chat-event'},h('strong',null,item.topic),note(item.platform+' · '+date(item.created)),h('p',null,item.text),note(item.speaker==='assistant'?'助手讨论／建议':'用户陈述'),b('查看原话',()=>open(item.turn_id))))),
      box('跨平台与会话查询',
        h('form',{className:'hc-toolbar',onSubmit:e=>{e.preventDefault();load();}},input(q,setQ,{placeholder:'查找过去讨论的内容'}),input(platform,setPlatform,{placeholder:'平台，例如 slack'}),input(session,setSession,{placeholder:'会话 ID（可选）'}),h('label',null,'开始',input(after,setAfter,{type:'datetime-local'})),h('label',null,'结束',input(before,setBefore,{type:'datetime-local'})),h('button',{type:'submit'},'查询'),b('刷新',()=>load(start))),
        ...data.items.map(item=>h('article',{className:'hc-chat-event',key:item.id},h('strong',null,item.platform+' · '+date(item.created)),note(item.session),h('p',null,item.user),h('p',{className:'hc-muted'},item.assistant),item.audio_count?note('关联助手语音 '+item.audio_count+' 段'):null,b('查看原话',()=>open(item.id)))),
        !data.items.length?note('没有可展示的记录。正在整理、禁提或删除的内容不会出现在查询中。'):null,
        h('div',{className:'hc-toolbar'},b('上一页',()=>load(Math.max(0,start-20)),{disabled:start===0}),note('匹配 '+data.total+' 条'),b('下一页',()=>load(data.next),{disabled:data.next===null}))),
      detail?box('原话 · '+detail.platform+' · '+date(detail.created),b('关闭',()=>setDetail(null)),h('a',{className:'hc-download',href:download(detail.id),download:''},detail.original_export_filtered?'下载原话副本':'下载原件 JSON'),
        detail.audio?.length?h('a',{className:'hc-download',href:download(detail.id,'bundle'),download:''},'下载聊天与语音原件包'):null,
        h('h4',null,'用户'),h('pre',null,detail.user),h('h4',null,'助手'),h('pre',null,detail.assistant),
        ...(detail.audio||[]).map(a=>h('article',{className:'hc-chat-audio',key:a.id},h('h4',null,'助手语音 · '+a.name),
          note(a.state==='stored'?'音频原件已长期保留 · '+a.mime+' · '+(a.size/1024).toFixed(1)+' KB':'音频原件尚未保存 · '+({missing_source:'原缓存已缺失',unsupported_path:'来源不在本身份的音频缓存内',invalid_audio:'音频格式无法验证',invalid_size:'音频大小不符合保留限制',unavailable_source:'来源暂时无法读取'})[a.error]),
          a.state==='stored'?h('audio',{controls:true,preload:'none',src:download(detail.id,'audio/'+a.id+'/original'),'aria-label':'播放助手语音原件'}):null,
          a.state==='stored'?h('a',{className:'hc-download',href:download(detail.id,'audio/'+a.id+'/original'),download:a.name},'下载语音原件'):null,
          a.transcript?note('合成文案来自 '+(a.transcript_basis==='tts_spoken_text'?'合成工具返回文本':'原始 TTS 调用输入')+'，不作为语音识别转写或投递回执。'):note('没有可靠合成文案，不推测语音内容。'),
          a.sha256?note('语音 SHA-256 '+a.sha256):null)),
        note('会话 '+detail.session+' · 聊天原件 SHA-256 '+detail.sha256)):null);
  }
  function NetworkView({api,scope,run}){
    const [q,setQ]=useState(''),[data,setData]=useState({nodes:[],edges:[]}),[selected,setSelected]=useState(null),[hops,setHops]=useState('2'),[historical,setHistorical]=useState(true),[metric,setMetric]=useState('effective_strength');
    const seq=useRef(0);
    const load=(id='',query=q)=>{const n=++seq.current;run(async()=>{const result=await api('/network',{scope,q:query,id,hops,historical});if(n===seq.current){setData(result);setSelected(null);}});};
    useEffect(()=>{load();return()=>{seq.current++;};},[scope,historical]);
    const kinds={chat:'原话',summary:'摘要',memory:'记忆',document:'文件',topic:'主题',entity:'实体',context:'会话',event:'事件',audio:'助手语音'};
    const colors={chat:'#4579bc',summary:'#9063c5',memory:'#c57939',document:'#438d6e',topic:'#bd5483',entity:'#5b8290',context:'#7c8190',event:'#897242',audio:'#496eb5'};
    const percent=v=>v==null?'未评估':(v*100).toFixed(1)+'%';
    const states={active:'有效',reinforced:'已强化',decaying:'衰减中',permanent:'永久',archived:'已归档',superseded:'已被更新',candidate:'待审核',rejected:'未通过',ready:'已整理',queued:'等待解析',indexed:'已索引',stored:'原件已保留',missing:'原件缺失'};
    const nodes=useMemo(()=>{
      const points=data.nodes.map((n,i)=>({...n,x:500+250*Math.cos(i*2*Math.PI/Math.max(1,data.nodes.length)),y:310+210*Math.sin(i*2*Math.PI/Math.max(1,data.nodes.length)),vx:0,vy:0}));
      const by=new Map(points.map(n=>[n.id,n]));
      for(let step=0;step<180;step++){
        points.forEach(n=>{n.vx+=(500-n.x)*.006;n.vy+=(310-n.y)*.006;});
        for(let i=0;i<points.length;i++)for(let j=i+1;j<points.length;j++){const a=points[i],b=points[j],dx=a.x-b.x,dy=a.y-b.y,d=Math.max(10,Math.hypot(dx,dy)),f=2300/(d*d);a.vx+=dx/d*f;b.vx-=dx/d*f;a.vy+=dy/d*f;b.vy-=dy/d*f;}
        data.edges.forEach(e=>{const a=by.get(e.source),b=by.get(e.target);if(!a||!b)return;const dx=b.x-a.x,dy=b.y-a.y,d=Math.max(1,Math.hypot(dx,dy)),f=(d-110)*.008;a.vx+=dx/d*f;b.vx-=dx/d*f;a.vy+=dy/d*f;b.vy-=dy/d*f;});
        points.forEach(n=>{n.vx*=.65;n.vy*=.65;n.x=Math.min(940,Math.max(60,n.x+n.vx));n.y=Math.min(550,Math.max(60,n.y+n.vy));});
      }return points;
    },[data]);
    const by=new Map(nodes.map(n=>[n.id,n]));
    const linked=new Set(selected?[selected.id,...data.edges.filter(e=>e.source===selected.id||e.target===selected.id).flatMap(e=>[e.source,e.target])]:nodes.map(n=>n.id));
    return h('div',null,box('记忆网',note('把已记录的原话、文件、记忆与事件串成图。节点大小表示所选权重，颜色深浅表示置信度；虚线连接也包括时间先后，不表示因果。'),
      h('form',{className:'hc-toolbar',onSubmit:e=>{e.preventDefault();load();}},input(q,setQ,{placeholder:'主题、项目或内容'}),select(hops,setHops,[['1','1 跳'],['2','2 跳'],['3','3 跳']]),select(metric,setMetric,[['effective_strength','大小：当前强度'],['confidence','大小：置信度'],['importance','大小：重要性']]),h('label',null,h('input',{type:'checkbox',checked:historical,onChange:e=>setHistorical(e.target.checked)}),'包含历史与待审核记忆'),h('button',{type:'submit'},'探索'),b('全部',()=>{setQ('');load('','');}),b('刷新权重',()=>load())),
      h('div',{className:'hc-toolbar'},...Object.entries(kinds).map(([k,name])=>h('span',{key:k,className:'hc-tag',style:{borderLeft:'5px solid '+colors[k]}},name))),
      h('svg',{viewBox:'0 0 1000 610',className:'hc-network-svg','aria-label':'聊天、文件、事件与记忆的记忆网'},
        data.edges.map(e=>{const a=by.get(e.source),b=by.get(e.target);if(!a||!b)return null;return h('line',{key:e.id,x1:a.x,y1:a.y,x2:b.x,y2:b.y,stroke:'var(--hc-outline)',strokeWidth:1.3,strokeDasharray:['SUPPORTED_BY','DERIVED_FROM'].includes(e.relation)?undefined:'5 5',opacity:linked.has(a.id)&&linked.has(b.id)?.8:.15});}),
        nodes.map(n=>h('g',{key:n.id,role:'button',tabIndex:0,'aria-label':kinds[n.kind]+' '+n.label,onClick:()=>setSelected(n),onKeyDown:e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();setSelected(n);}},style:{cursor:'pointer'},opacity:linked.has(n.id)?1:.25},h('title',null,kinds[n.kind]+' · 置信度 '+percent(n.confidence)+' · 当前强度 '+percent(n.effective_strength)+(n.created?' · '+date(n.created):'')),h('circle',{cx:n.x,cy:n.y,r:n[metric]==null?7:7+12*Math.sqrt(Math.max(0,Math.min(1,n[metric]))),fill:colors[n.kind],fillOpacity:n.confidence==null?.7:.35+.65*n.confidence,stroke:selected?.id===n.id?'var(--hc-on-surface)':colors[n.kind],strokeWidth:selected?.id===n.id?3:1,strokeDasharray:['archived','superseded','candidate','rejected'].includes(n.status)?'3 3':undefined}),nodes.length<=40||n.kind!=='event'||selected?.id===n.id?h('text',{x:n.x,y:n.y+31,textAnchor:'middle',fontSize:11,fill:'var(--hc-on-surface)'},n.label.slice(0,12)):null))),
      note(`${data.nodes.length} / ${data.total_nodes??0} 个节点 · ${data.edges.length} 条连接 · 权重更新于 ${date(data.as_of)}${data.truncated?' · 可通过搜索或选择节点展开更多内容':''}`),note('记忆权重与本体同步；其他节点汇总关联记忆的最高权重。未评估的记录显示为空，聊天内容不会因此被判定为事实。')),
      selected?box(kinds[selected.kind],h('p',null,selected.label),note(selected.session||selected.slot||''),
        h('div',{className:'hc-job-summary'},...Object.entries({confidence:'置信度',strength:'本体强度',effective_strength:'当前强度（含衰减）',importance:'重要性'}).map(([key,name])=>h('div',{className:'hc-job-row',key},h('span',null,name),h('strong',null,percent(selected[key]))))),
        note('状态 '+(states[selected.status]||selected.status||'记录')+' · 生命周期 '+(states[selected.lifecycle]||selected.lifecycle||'—')+' · '+selected.support_count+' 条关联记忆'),
        note(({memory:'权重直接来自记忆本体。',memory_reference:'事件引用对应记忆的当前权重，不代表事件发生时的权重。',related_memories:'权重汇总自不同的关联记忆，不代表这条记录中所有说法的可信度。',unassessed:'已有原始记录，尚无可关联的记忆权重。'})[selected.weight_basis]),
        selected.created?note('记录时间 '+date(selected.created)):null,
        selected.valid_until?note('有效期结束 '+date(selected.valid_until)):null,
        b('沿此节点展开',()=>load(selected.id)),...data.edges.filter(e=>e.source===selected.id||e.target===selected.id).map(e=>h('p',{key:e.id},({SUPPORTED_BY:'原文支持',DERIVED_FROM:'派生自',CONTAINS:'包含',ABOUT:'共同主题',MENTIONS:'提及',RECORDED_FOR:'记忆事件',NEXT:'时间先后',HAS_AUDIO:'关联语音'})[e.relation]+' · '+(by.get(e.source===selected.id?e.target:e.source)?.label||'')))):null);
  }

  const themePresets = [
    ['#6750A4','鸢尾紫'], ['#006B5E','森林绿'], ['#0061A4','晴空蓝'],
    ['#A23864','玫瑰粉'], ['#805600','暖琥珀']
  ];
  const iconPaths = {
    overview:'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
    memories:'M6 3h12a2 2 0 0 1 2 2v16l-8-4-8 4V5a2 2 0 0 1 2-2z M8 8h8 M8 12h6',
    knowledge:'M4 3h11l5 5v13H4z M14 3v6h6 M7 13h10 M7 17h7',
    chats:'M4 4h16v12H9l-5 4V4z M7 8h10 M7 12h7',
    network:'M4 5l8 7 8-7 M4 19l8-7 8 7 M12 12V3',
    graph:'M6 6l12 2-6 11L6 6z M6 6l6 6 6-4 M12 12v7',
    identities:'M16 7a4 4 0 1 1-8 0a4 4 0 0 1 8 0z M4 21v-2a6 6 0 0 1 6-6h4a6 6 0 0 1 6 6v2',
    preferences:'M16 7a4 4 0 1 1-8 0a4 4 0 0 1 8 0z M4 21v-2a6 6 0 0 1 6-6h4a6 6 0 0 1 6 6v2',
    settings:'M4 7h16 M4 17h16 M9 4v6 M15 14v6',
    operations:'M12 3v12 M7 10l5 5 5-5 M4 16v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4',
    panel:'M12 3a9 9 0 1 0 9 9c0-5-4-9-9-9z M12 3v18 M12 7h4 M12 12h6 M12 17h4',
    light:'M12 3v2 M12 19v2 M3 12h2 M19 12h2 M5 5l2 2 M17 17l2 2 M5 19l2-2 M17 7l2-2 M16 12a4 4 0 1 1-8 0a4 4 0 0 1 8 0z',
    dark:'M20 14A8 8 0 0 1 10 4a9 9 0 1 0 10 10z',
    system:'M3 4h18v12H3z M8 21h8 M12 16v5'
  };
  const icon = name => h('svg',{viewBox:'0 0 24 24',className:'hc-icon','aria-hidden':true,fill:'none',stroke:'currentColor',strokeWidth:1.7,strokeLinecap:'round',strokeLinejoin:'round'},h('path',{d:iconPaths[name]||iconPaths.panel}));
  function PanelSettings({appearance,setAppearance,dark}){
    return h('div',{className:'hc-panel-settings'},
      h('div',{className:'hc-settings-main'},
        box('显示模式',note('选择适合当前环境的外观。跟随系统会自动切换明暗。'),
          h('div',{className:'hc-mode-options'},[['system','跟随系统','随设备外观自动变化'],['light','明亮','柔和的浅色背景'],['dark','深色','适合暗光环境']].map(([mode,label,description])=>b(
            h(R.Fragment,null,icon(mode),h('span',{className:'hc-option-label'},label),h('small',null,description),h('span',{className:'hc-option-check','aria-hidden':true},appearance.mode===mode?'✓':'')),
            ()=>setAppearance(v=>({...v,mode})),{key:mode,className:'hc-mode-option','aria-pressed':appearance.mode===mode,'aria-label':label})))),
        box('主题色',note('选择预设，或设置自己的颜色。按钮、卡片和关系图会同步调整。'),
          h('div',{className:'hc-preset-grid'},themePresets.map(([seed,label])=>b(
            h(R.Fragment,null,h('span',{className:'hc-color-dot',style:{background:seed}},appearance.seed.toLowerCase()===seed.toLowerCase()?'✓':''),h('span',null,label)),
            ()=>setAppearance(v=>({...v,seed})),{key:seed,className:'hc-color-option','aria-pressed':appearance.seed.toLowerCase()===seed.toLowerCase(),'aria-label':label}))),
          h('div',{className:'hc-custom-color'},h('label',null,'自定义颜色',h('div',{className:'hc-color-input'},h('input',{type:'color',value:appearance.seed,onChange:e=>setAppearance(v=>({...v,seed:e.target.value})),'aria-label':'自定义主题色'}),h('code',null,appearance.seed.toUpperCase()))),note('颜色会自动生成适合明亮和深色模式的配色。')))),
      h('aside',{className:'hc-settings-preview'},box('实时预览',
        h('div',{className:'hc-preview-scene'},h('div',{className:'hc-preview-toolbar'},h('span',{className:'hc-preview-symbol'},icon('graph')),h('strong',null,'记忆与关系'),h('span',{className:'hc-tag'},dark?'深色':'明亮')),
          h('div',{className:'hc-preview-stat'},note('示例记忆'),h('strong',null,'128'),h('span',null,'让重要的事实持续连接。')),
          h('div',{className:'hc-preview-chips'},h('span',null,'偏好'),h('span',null,'项目'),h('span',null,'知识')),
          h('div',{className:'hc-preview-actions'},h('span',{className:'hc-preview-filled'},'主要操作'),h('span',{className:'hc-preview-tonal'},'次要操作'))),
        note('设置实时生效，仅保存在当前浏览器中。')),
        b('恢复默认外观',()=>setAppearance({mode:'system',seed:'#6750A4'}),{className:'hc-secondary hc-reset-appearance'})))
  }
  function App(){
    const [tab,setTab]=useState('overview'),[profile,setProfile]=useState('default'),[profiles,setProfiles]=useState([]),[scope,setScope]=useState('');
    const [overview,setOverview]=useState(null),[settings,setSettings]=useState(null),[message,setMessage]=useState(''),[error,setError]=useState(''),[pending,setPending]=useState(0),[dirty,setDirty]=useState(false);
    useEffect(()=>{if(!dirty)return;const warn=e=>{e.preventDefault();e.returnValue='';};window.addEventListener('beforeunload',warn);return()=>window.removeEventListener('beforeunload',warn);},[dirty]);
    const navigate=next=>{if(next!==tab&&dirty&&!confirm('当前配置有尚未保存的修改。离开会放弃这些修改，仍要继续吗？'))return;setDirty(false);setTab(next);};
    const changeProfile=next=>{if(dirty&&!confirm('切换工作空间会放弃尚未保存的配置，仍要继续吗？'))return;setDirty(false);setProfile(next);};
    const [appearance,setAppearance]=useState(()=>{try{return JSON.parse(localStorage.getItem('gramem-appearance'))||{mode:'system',seed:'#6750A4'};}catch{return {mode:'system',seed:'#6750A4'};}});
    const [systemDark,setSystemDark]=useState(()=>matchMedia('(prefers-color-scheme: dark)').matches);
    useEffect(()=>{const media=matchMedia('(prefers-color-scheme: dark)');const update=e=>setSystemDark(e.matches);media.addEventListener('change',update);return()=>media.removeEventListener('change',update);},[]);
    useEffect(()=>{localStorage.setItem('gramem-appearance',JSON.stringify(appearance));},[appearance]);
    const dark=appearance.mode==='dark'||(appearance.mode==='system'&&systemDark);
    const theme=tonalTheme(appearance.seed,dark);
    useEffect(()=>{const root=document.documentElement;root.style.setProperty('--gramem-shell-surface',theme['--hc-surface']);root.style.setProperty('--gramem-shell-text',theme['--hc-on-surface']);return()=>{root.style.removeProperty('--gramem-shell-surface');root.style.removeProperty('--gramem-shell-text');};},[appearance.seed,dark]);
    const seq=useRef(0);
    const run=async fn=>{setPending(n=>n+1);setError('');try{await fn();}catch(e){setError(e.message||String(e));}finally{setPending(n=>n-1);}};
    const api=async(path,params={},body,method)=>{
      const qs=new URLSearchParams({profile,...Object.fromEntries(Object.entries(params).map(([k,v])=>[k,String(v)]))});
      return sdk.fetchJSON(`/api/plugins/hermes-control${path}?${qs}`,body===undefined?undefined:{method:method||'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    };
    useEffect(()=>{run(async()=>{const v=await sdk.api.getProfiles();setProfiles(v.profiles);});},[]);
    useEffect(()=>{
      const n=++seq.current;setOverview(null);setSettings(null);setScope('');setMessage('');setError('');
      api('/overview').then(v=>{if(n===seq.current){setOverview(v);setScope(v.owner);}}).catch(e=>{if(n===seq.current)setError(e.message);});
      api('/settings').then(v=>{if(n===seq.current)setSettings(v);}).catch(()=>{});
      return()=>{seq.current++;};
    },[profile]);
    const tabs=[['overview','总览'],['memories','记忆'],['knowledge','知识库'],['chats','聊天档案'],['network','记忆网'],['graph','关系图'],['preferences','画像与偏好'],['identities','账号与身份'],['settings','行为与模型'],['operations','导入与维护'],['panel','面板设置']];
    const saveSettings=(values,parseError)=>run(async()=>{if(parseError)throw Error(parseError);await api('/settings',{}, {values,revision:settings.revision},'PUT');setSettings(await api('/settings'));setMessage('GraMem 配置已保存并备份。需重新启动宿主实例以应用配置。');});
    const content={
      overview:()=>h('div',null,h('section',{className:'hc-hero'},h('div',null,h('span',{className:'hc-chip'},'GraMem 2 · 实例管理'),h('h2',null,'让记忆，连接起来。'),note('管理事实与偏好，探索关系，调整记忆如何生长。'),h('div',{className:'hc-toolbar'},b('探索关系图',()=>navigate('graph')),b('搜索记忆',()=>navigate('memories'),{className:'hc-secondary'}))),h('div',{className:'hc-hero-art','aria-hidden':true},h('span',null),h('span',null),h('span',null),h('span',null))),h('div',{className:'hc-stats'},['active','candidate','archived'].map(status=>h('div',{className:'hc-card',key:status},note({active:'有效记忆',candidate:'自动审核中',archived:'归档记忆'}[status]),h('strong',null,overview?.status.memories.find(v=>v.status===status)?.count??(overview?0:'—')))),h('div',{className:'hc-card'},note('图待同步'),h('strong',null,overview?.status.graph_pending??'—'))),box('记忆工作台',note('GraMem 的事实、偏好、画像与关系在这里管理。统计覆盖所选 profile，搜索和关系图按所选身份隔离。'),h('div',{className:'hc-toolbar'},b('搜索记忆',()=>navigate('memories')),b('打开关系网',()=>navigate('graph')),b('管理账号身份',()=>navigate('identities')),b('调整记忆行为',()=>navigate('settings')))),box('后台任务',h('div',{className:'hc-job-summary'},(overview?.status.jobs||[]).map(job=>h('div',{className:'hc-job-row',key:job.status},h('span',null,({pending:'待处理',processing:'处理中',completed:'已完成',done:'已完成',failed:'处理失败',redacted:'已脱敏'})[job.status]||job.status),h('strong',null,job.count)))),!(overview?.status.jobs||[]).length?note('暂无待处理任务，新的记忆会在后台自动整理。'):null)),
      memories:()=>overview?h(Memories,{key:profile,api,scope,run,notify:setMessage}):note('此 profile 尚未启用 GraMem。'),
      knowledge:()=>overview?h(Knowledge,{key:profile+scope,api,scope,run,notify:setMessage,download:id=>(window.__HERMES_BASE_PATH__||'')+`/api/plugins/hermes-control/knowledge/${id}/original?${new URLSearchParams({profile,scope})}`}):note('此 profile 尚未启用 GraMem。'),
      chats:()=>overview?h(ChatsView,{key:profile+scope,api,scope,run,download:(id,resource='original')=>(window.__HERMES_BASE_PATH__||'')+`/api/plugins/hermes-control/chats/${id}/${resource}?${new URLSearchParams({profile,scope})}`}):note('此 profile 尚未启用 GraMem。'),
      network:()=>overview?h(NetworkView,{key:profile+scope,api,scope,run}):note('此 profile 尚未启用 GraMem。'),
      graph:()=>overview?h(Graph,{key:profile,api,scope,run}):note('此 profile 尚未启用 GraMem。'),
      preferences:()=>overview?h(Profiles,{key:profile,api,scope,run,notify:setMessage}):note('此 profile 尚未启用 GraMem。'),
      identities:()=>settings?h(Identities,{key:profile,data:settings,save:saveSettings,onDirty:setDirty}):note('此工作空间尚未配置 GraMem。'),
      settings:()=>settings?h(Settings,{key:profile,data:settings,save:saveSettings,api,run,notify:setMessage,onDirty:setDirty,reload:async()=>setSettings(await api('/settings'))}):note('此 profile 尚未配置 GraMem。'),
      operations:()=>overview?h(Operations,{key:profile+scope,api,scope,run,notify:setMessage}):note('此 profile 尚未启用 GraMem。'),
      panel:()=>h(PanelSettings,{appearance,setAppearance,dark}),
    };
    return h('div',{className:'hc-root','data-mode':dark?'dark':'light',style:theme,'aria-busy':pending>0},
      h('header',{className:'hc-header'},h('div',{className:'hc-brand'},h('div',{className:'hc-brandmark','aria-hidden':true},h('svg',{viewBox:'0 0 48 48'},h('path',{d:'M12 13 L35 15 L24 35 Z M12 13 L24 24 L35 15 M24 24 L24 35',fill:'none',stroke:'currentColor',strokeWidth:2}),[ [12,13],[35,15],[24,35],[24,24] ].map(([x,y],i)=>h('circle',{key:i,cx:x,cy:y,r:i===3?4:6,fill:'currentColor'})))),h('div',null,h('div',{className:'hc-eyebrow'},'MEMORY, CONNECTED'),h('h1',null,'GraMem'),note('记忆、关系与偏好的管理组件'))),h('div',{className:'hc-profile'},h('label',null,'工作空间',select(profile,changeProfile,profiles.length?profiles.map(p=>[p.name,p.name]):[['default','default']],{disabled:pending>0})),overview?h('label',null,'记忆身份',select(scope,setScope,overview.scopes.map(s=>[s.principal,prettyScope(s.principal)]),{disabled:pending>0})):null,b('退出登录',()=>run(async()=>{await sdk.authedFetch('/auth/logout',{method:'POST'});location.href=(window.__HERMES_BASE_PATH__||'')+'/login';}),{className:'hc-quiet hc-signout'}))),
      h('nav',{className:'hc-tabs',role:'tablist','aria-label':'控制台功能'},tabs.map(([key,label],i)=>b(h(R.Fragment,null,icon(key),h('span',null,label)),()=>navigate(key),{
        key,id:'hc-tab-'+key,role:'tab','aria-selected':tab===key,'aria-controls':'hc-panel-'+key,tabIndex:tab===key?0:-1,className:tab===key?'hc-active':'',
        onKeyDown:e=>{const steps={ArrowRight:1,ArrowLeft:-1,Home:-i,End:tabs.length-1-i};if(!(e.key in steps))return;e.preventDefault();const next=tabs[(i+steps[e.key]+tabs.length)%tabs.length][0];navigate(next);requestAnimationFrame(()=>document.getElementById('hc-tab-'+next)?.focus());}
      }))),
      tab!=='overview'?h('div',{className:'hc-page-heading'},h('div',null,h('h2',null,tabs.find(([key])=>key===tab)[1]),note({chats:'跨平台与会话查找原话，查看自动整理的主题与时间线。',network:'连接原话、文件与发生过的事件，查看与记忆本体同步的权重。',memories:'查找事实，查看自动审核进度，管理记忆的每个版本。',knowledge:'长期保存原件，检索文档与图片文字，并定位每条知识的来源。',graph:'沿着实体与关系，探索有来源的记忆网络。',preferences:'查看有来源的画像，直接维护身份特征、兴趣和长期偏好。',identities:'关联已核实的账号，让同一个人跨平台使用同一份记忆。',settings:'调整记忆如何召回、生长，以及模型和图服务的连接。',operations:'导入知识，维护生命周期，查看持久队列与备份。',panel:'按照你的喜好，调整工作台的颜色与外观。'}[tab]))):null,
      pending?h('div',{className:'hc-pending',role:'status'},'正在处理…'):null,
      error?h('div',{className:'hc-error',role:'alert'},error,b('关闭',()=>setError(''))):null,
      message?h('div',{className:'hc-success',role:'status'},message,b('关闭',()=>setMessage(''))):null,
      h('div',{id:'hc-panel-'+tab,role:'tabpanel','aria-labelledby':'hc-tab-'+tab,className:'hc-page-content'},content[tab]())
    );
  }
  window.__HERMES_PLUGINS__.register('hermes-control',App);
})();
