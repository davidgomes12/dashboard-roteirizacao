let DATA = null;
let chartRealKgDia = null;
let chartReentJustDia = null;
let chartReentJustMes = null;
let chartReentDia = null;
let chartFrotaDia = null;
let chartVespRealKgDia = null;

// ============ LOAD ============
async function loadData() {
    try {
        const r = await fetch('dashboard_data.json');
        DATA = await r.json();
        document.getElementById('headerDate').textContent = 'Atualizado em: ' + DATA.gerado_em;
        populateFilters();
        applyFilters();
        populateFiltersReent();
        applyFiltersReent();
        populateFiltersFrota();
        applyFiltersFrota();
        populateFiltersVesp();
        applyFiltersVesp();
        populateFiltersFresc();
        applyFiltersFresc();
    } catch (e) {
        console.error(e);
        alert('Erro ao carregar dados. Execute pipeline.py e acesse via http://localhost:8080/dashboard.html');
    } finally {
        document.getElementById('loading').classList.add('hide');
    }
}

// ============ FORMATTERS ============
const fmt = {
    num: v => v == null ? '--' : Number(v).toLocaleString('pt-BR'),
    dec: (v,d=2) => v == null ? '--' : Number(v).toLocaleString('pt-BR',{minimumFractionDigits:d,maximumFractionDigits:d}),
    pct: v => v == null ? '--' : fmt.dec(v,2)+'%',
    brl: v => v == null ? '--' : 'R$ '+Number(v).toLocaleString('pt-BR',{minimumFractionDigits:2,maximumFractionDigits:2}),
    tons: v => v == null ? '--' : fmt.dec(v/1000,1)+' Tons',
    mesLabel: m => { const [y,mo]=m.split('-'); const ms=['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez']; return ms[parseInt(mo)-1]+'/'+y; },
    diaLabel: d => { const [y,m,day]=d.split('-'); return day+'/'+m; },
};

// ============ HELPERS DE FILTRO (comuns a todas as abas) ============

// Popula os <select> de mês e dia com as opções disponíveis
function populateMesDia(mesId, diaId, meses, dias) {
    const sM = document.getElementById(mesId);
    const sD = document.getElementById(diaId);
    meses.forEach(m => { const o=document.createElement('option'); o.value=m; o.textContent=fmt.mesLabel(m); sM.appendChild(o); });
    dias.forEach(d => { const o=document.createElement('option'); o.value=d; o.textContent=fmt.diaLabel(d); sD.appendChild(o); });
}

// Recarrega as opções de dia filtrando pelo mês selecionado, mantendo seleção anterior se possível
function updateDiaSelect(diaSelectId, allDias, selectedMes) {
    const s = document.getElementById(diaSelectId);
    const cv = s.value;
    s.innerHTML = '<option value="all">Todos os Dias</option>';
    const dias = selectedMes !== 'all' ? allDias.filter(d => d.startsWith(selectedMes)) : allDias;
    dias.forEach(d => { const o=document.createElement('option'); o.value=d; o.textContent=fmt.diaLabel(d); s.appendChild(o); });
    if (dias.includes(cv)) s.value = cv;
}

// Calcula KPIs a partir dos dados granulares por dia/mês (escala e vespertina)
function kpisFromGrain(mes, dia, porDia, porMes, baseKpis) {
    if (dia !== 'all') {
        const d = porDia.find(r => r.DIA === dia);
        if (d) return { peso_total:d.peso, frete_total:d.frete, qtd_veiculos:d.veiculos, qtd_entregas:d.entregas, ocupacao_total:d.ocupacao, real_kg_total:d.real_kg, capac_total:d.capac };
    } else if (mes !== 'all') {
        const m = porMes.find(r => r.MES_KEY === mes);
        if (m) return { peso_total:m.peso, frete_total:m.frete, qtd_veiculos:m.veiculos, qtd_entregas:m.entregas, ocupacao_total:m.ocupacao, real_kg_total:m.real_kg, capac_total:m.capac };
    }
    return baseKpis;
}

// ============ FILTERS ROTEIRO ============
function populateFilters() { populateMesDia('filterMes', 'filterDia', DATA.filtros.meses, DATA.filtros.dias); }

function updateDiaOptions(mes) { updateDiaSelect('filterDia', DATA.filtros.dias, mes); }

function resetFilters() { document.getElementById('filterMes').value='all'; document.getElementById('filterDia').value='all'; document.getElementById('filterOperador').value='ambos'; applyFilters(); }

// ============ FILTERS REENTREGAS ============
function populateFiltersReent() { populateMesDia('filterMesReent', 'filterDiaReent', DATA.filtros.meses_reent||[], DATA.filtros.dias_reent||[]); }

function updateDiaOptionsReent(mes) { updateDiaSelect('filterDiaReent', DATA.filtros.dias_reent||[], mes); }

function resetFiltersReent() { document.getElementById('filterMesReent').value='all'; document.getElementById('filterDiaReent').value='all'; document.getElementById('filterOperadorReent').value='ambos'; applyFiltersReent(); }

// ============ APPLY ROTEIRO ============
function applyFilters() {
    const mes = document.getElementById('filterMes').value;
    const dia = document.getElementById('filterDia').value;
    const op  = document.getElementById('filterOperador').value;
    updateDiaOptions(mes);

    // Fonte de dados conforme operador (ambos = topo do JSON; senão o bundle do seg.)
    const R = op === 'ambos' ? DATA : DATA.seg[op];

    let porDia = R.por_dia;
    let porVeiculoDia = R.por_veiculo_dia;
    let porVeiculoMes = R.por_veiculo_mes;

    if (mes !== 'all') {
        porDia = porDia.filter(r => r.DIA.startsWith(mes));
        porVeiculoMes = porVeiculoMes.filter(r => r.MES_KEY === mes);
    }
    if (dia !== 'all') porVeiculoDia = porVeiculoDia.filter(r => r.DIA === dia);

    const kpis = kpisFromGrain(mes, dia, porDia, R.por_mes, R.kpis);

    document.getElementById('kpiVeiculos').textContent = fmt.num(kpis.qtd_veiculos);
    document.getElementById('kpiEntregas').textContent = fmt.num(kpis.qtd_entregas);
    document.getElementById('kpiPeso').textContent = fmt.tons(kpis.peso_total);
    document.getElementById('kpiRealKg').textContent = fmt.brl(kpis.real_kg_total);

    // Ocupação KPI card - valor branco + delta vs meta
    const occRounded = Math.round(kpis.ocupacao_total);
    document.getElementById('kpiOcupacao').textContent = occRounded + '%';
    document.getElementById('kpiOcupacao').className = 'kpi-value';
    const occDiff = occRounded - 84;
    const occDeltaEl = document.getElementById('kpiOcupacaoDelta');
    occDeltaEl.textContent = occDiff >= 0 ? `🔺 +${occDiff}% acima da meta` : `🔻 ${occDiff}% abaixo da meta`;
    occDeltaEl.className = 'kpi-delta ' + (occDiff >= 0 ? 'good' : 'bad');

    // Real Kg KPI card - valor branco + delta vs meta
    const rkRounded = Math.round(kpis.real_kg_total * 100) / 100;
    document.getElementById('kpiRealKg').className = 'kpi-value';
    const rkDiff = rkRounded - 0.67;
    const rkDiffAbs = Math.abs(rkDiff).toFixed(2);
    const rkDeltaEl = document.getElementById('kpiRealKgDelta');
    rkDeltaEl.textContent = rkDiff > 0 ? `🔺 +R$ ${rkDiffAbs} acima da meta` : `🔻 -R$ ${rkDiffAbs} abaixo da meta`;
    rkDeltaEl.className = 'kpi-delta ' + (rkDiff > 0 ? 'bad' : 'good');

    // Performance Rings
    drawRing('ringOcupacao', kpis.ocupacao_total, 100, false);
    document.getElementById('ringOcupacaoVal').textContent = occRounded + '%';
    const occGood = occRounded >= 84;
    const occSt = document.getElementById('ringOcupacaoStatus');
    occSt.textContent = occGood ? 'Na meta' : 'Abaixo da meta';
    occSt.className = 'perf-status ' + (occGood ? 'good' : 'bad');

    drawRing('ringRealKg', kpis.real_kg_total, 1.5, true);
    document.getElementById('ringRealKgVal').textContent = fmt.brl(kpis.real_kg_total);
    const rkGood = rkRounded <= 0.67;
    const rkSt = document.getElementById('ringRealKgStatus');
    rkSt.textContent = rkGood ? 'Na meta' : 'Acima da meta';
    rkSt.className = 'perf-status ' + (rkGood ? 'good' : 'bad');

    renderChartRealKgDia(porDia);
    renderTableVeiculo('tableDia', porVeiculoDia);
    renderTableVeiculo('tableMes', mes !== 'all' ? porVeiculoMes : R.por_veiculo);

    // Distribuição por faixa de KM
    let d0100Dia = R.dist_0_100_dia;
    let d0100Mes = R.dist_0_100_mes;
    let d100pDia = R.dist_100p_dia;
    let d100pMes = R.dist_100p_mes;
    if (mes !== 'all') {
        d0100Mes = d0100Mes.filter(r => r.MES_KEY === mes);
        d100pMes = d100pMes.filter(r => r.MES_KEY === mes);
    }
    if (dia !== 'all') {
        d0100Dia = d0100Dia.filter(r => r.DIA === dia);
        d100pDia = d100pDia.filter(r => r.DIA === dia);
    }
    renderTableVeiculo('tableDist0100Dia', d0100Dia);
    renderTableVeiculo('tableDist0100Mes', mes !== 'all' ? d0100Mes : R.dist_0_100_veic);
    renderTableVeiculo('tableDist100pDia', d100pDia);
    renderTableVeiculo('tableDist100pMes', mes !== 'all' ? d100pMes : R.dist_100p_veic);
}

// ============ APPLY REENTREGAS ============
function applyFiltersReent() {
    const mes = document.getElementById('filterMesReent').value;
    const dia = document.getElementById('filterDiaReent').value;
    const op  = document.getElementById('filterOperadorReent').value;
    updateDiaOptionsReent(mes);

    // Reentregas seguem o operador filtrado (RE); a Qtd. de Entregas é SEMPRE o
    // total de ambos (DATA = topo do JSON), então o % = reentregas(op) / entregas(ambos).
    const RE = op === 'ambos' ? DATA : DATA.seg[op];
    const reentKpis = op === 'ambos' ? DATA.kpis : RE.reent_kpis;

    let totalReent, totalEntregas;

    if (dia !== 'all') {
        const rd = RE.reentregas_dia.find(r => r.DIA === dia);
        const nd = DATA.nf_entregas_dia.find(r => r.DIA === dia);
        totalReent = rd ? rd.reentregas : 0;
        totalEntregas = nd ? nd.qtd_entregas : 0;
    } else if (mes !== 'all') {
        const rm = RE.reentregas_mes.find(r => r.MES_KEY === mes);
        const nm = DATA.nf_entregas_mes.find(r => r.MES_KEY === mes);
        totalReent = rm ? rm.reentregas : 0;
        totalEntregas = nm ? nm.qtd_entregas : 0;
    } else {
        totalReent = reentKpis.reentregas;
        totalEntregas = DATA.kpis.qtd_entregas_nf;
    }

    const pct = totalEntregas > 0 ? (totalReent / totalEntregas * 100) : 0;

    document.getElementById('kpiReentregas').textContent = fmt.num(totalReent);
    document.getElementById('kpiEntregasNF').textContent = fmt.num(totalEntregas);
    document.getElementById('kpiPctReent').textContent = fmt.pct(pct);

    // === KPIs MÊS ===
    const mesKpiKey = dia !== 'all' ? dia.substring(0, 7) : (mes !== 'all' ? mes : null);
    if (mesKpiKey) {
        const rm = RE.reentregas_mes.find(r => r.MES_KEY === mesKpiKey);
        const nm = DATA.nf_entregas_mes.find(r => r.MES_KEY === mesKpiKey);
        const reentMes = rm ? rm.reentregas : 0;
        const entregasMes = nm ? nm.qtd_entregas : 0;
        const pctMes = entregasMes > 0 ? (reentMes / entregasMes * 100) : 0;
        document.getElementById('kpiReentMes').textContent = fmt.num(reentMes);
        document.getElementById('kpiPctReentMes').textContent = fmt.pct(pctMes);
        const mesLbl = fmt.mesLabel(mesKpiKey);
        document.getElementById('kpiReentMesSub').textContent = mesLbl;
        document.getElementById('kpiPctReentMesSub').textContent = mesLbl;
    } else {
        document.getElementById('kpiReentMes').textContent = fmt.num(totalReent);
        document.getElementById('kpiPctReentMes').textContent = fmt.pct(pct);
        document.getElementById('kpiReentMesSub').textContent = 'todos os meses';
        document.getElementById('kpiPctReentMesSub').textContent = 'todos os meses';
    }

    // === Gráfico de Linha Reentregas por Dia ===
    let reentDiaChart = RE.reentregas_dia;
    if (mes !== 'all') reentDiaChart = reentDiaChart.filter(r => r.DIA.startsWith(mes));
    else if (dia !== 'all') reentDiaChart = reentDiaChart.filter(r => r.DIA.startsWith(dia.substring(0, 7)));
    renderChartReentDia(reentDiaChart);

    // === Dados DIA ===
    let transpDia, justDia, detailDia, labelDia;
    if (dia !== 'all') {
        transpDia = aggregateReentTransp(
            RE.reentregas_transp_dia.filter(r => r.DIA === dia),
            RE.nf_transp_dia.filter(r => r.DIA === dia)
        );
        justDia = aggregateReent(RE.reentregas_just_dia.filter(r => r.DIA === dia), 'DESC JUST OC');
        detailDia = RE.reentregas_transp_just_dia.filter(r => r.DIA === dia).sort((a,b) => b.reentregas - a.reentregas);
        labelDia = fmt.diaLabel(dia);
    } else if (mes !== 'all') {
        transpDia = aggregateReentTransp(
            RE.reentregas_transp_dia.filter(r => r.DIA.startsWith(mes)),
            RE.nf_transp_dia.filter(r => r.DIA.startsWith(mes))
        );
        justDia = aggregateReent(RE.reentregas_just_dia.filter(r => r.DIA.startsWith(mes)), 'DESC JUST OC');
        detailDia = aggregateReentDetail(RE.reentregas_transp_just_dia.filter(r => r.DIA.startsWith(mes)));
        labelDia = 'Todos os Dias';
    } else {
        transpDia = RE.reentregas_transportadora;
        justDia = RE.reentregas_justificativa;
        detailDia = RE.reentregas_transp_just;
        labelDia = 'Todos os Dias';
    }

    // === Dados MÊS ===
    let transpMes, justMes, detailMes, labelMes;
    const mesKey = dia !== 'all' ? dia.substring(0, 7) : mes;
    if (mesKey !== 'all') {
        transpMes = aggregateReentTransp(
            RE.reentregas_transp_dia.filter(r => r.DIA.startsWith(mesKey)),
            RE.nf_transp_dia.filter(r => r.DIA.startsWith(mesKey))
        );
        justMes = aggregateReent(RE.reentregas_just_dia.filter(r => r.DIA.startsWith(mesKey)), 'DESC JUST OC');
        detailMes = aggregateReentDetail(RE.reentregas_transp_just_dia.filter(r => r.DIA.startsWith(mesKey)));
        labelMes = fmt.mesLabel(mesKey);
    } else {
        transpMes = RE.reentregas_transportadora;
        justMes = RE.reentregas_justificativa;
        detailMes = RE.reentregas_transp_just;
        labelMes = 'Todos os Meses';
    }

    // Labels
    document.getElementById('labelTranspDia').textContent = labelDia;
    document.getElementById('labelTranspMes').textContent = labelMes;
    document.getElementById('labelJustDia').textContent = labelDia;
    document.getElementById('labelJustMes').textContent = labelMes;
    document.getElementById('labelDetailDia').textContent = labelDia;
    document.getElementById('labelDetailMes').textContent = labelMes;

    // Render Dia
    renderTableReentTransp('tableReentTranspDia', transpDia);
    renderChartReentJust('chartReentJustDia', justDia, 'dia');
    renderTableReentDetail('tableReentDetailDia', detailDia);

    // Render Mês
    renderTableReentTransp('tableReentTranspMes', transpMes);
    renderChartReentJust('chartReentJustMes', justMes, 'mes');
    renderTableReentDetail('tableReentDetailMes', detailMes);
}

function aggregateReentTransp(reentData, nfData) {
    const reentGrouped = {};
    reentData.forEach(r => {
        const k = r['NOME TRANSPORTADORA'] || 'N/A';
        if (!reentGrouped[k]) reentGrouped[k] = 0;
        reentGrouped[k] += r.reentregas;
    });
    const nfGrouped = {};
    nfData.forEach(r => {
        const k = r['NOME TRANSPORTADORA'] || 'N/A';
        if (!nfGrouped[k]) nfGrouped[k] = 0;
        nfGrouped[k] += r.entregas;
    });
    const arr = Object.entries(reentGrouped).map(([name, reent]) => ({
        'NOME TRANSPORTADORA': name,
        reentregas: reent,
        entregas: nfGrouped[name] || 0,
        pct: nfGrouped[name] > 0 ? Math.round(reent / nfGrouped[name] * 10000) / 100 : 0
    }));
    arr.sort((a,b) => b.reentregas - a.reentregas);
    return arr;
}

function aggregateReent(data, key) {
    const grouped = {};
    data.forEach(r => {
        const k = r[key] || 'N/A';
        if (!grouped[k]) grouped[k] = 0;
        grouped[k] += r.reentregas;
    });
    const arr = Object.entries(grouped).map(([name, reent]) => ({[key]: name, reentregas: reent}));
    arr.sort((a,b) => b.reentregas - a.reentregas);
    const total = arr.reduce((s,r) => s + r.reentregas, 0);
    arr.forEach(r => r.pct = total > 0 ? Math.round(r.reentregas / total * 10000) / 100 : 0);
    return arr;
}

function aggregateReentDetail(data) {
    const grouped = {};
    data.forEach(r => {
        const k = (r['NOME TRANSPORTADORA']||'N/A') + '|||' + (r['DESC JUST OC']||'N/A');
        if (!grouped[k]) grouped[k] = {'NOME TRANSPORTADORA': r['NOME TRANSPORTADORA'], 'DESC JUST OC': r['DESC JUST OC'], reentregas: 0};
        grouped[k].reentregas += r.reentregas;
    });
    return Object.values(grouped).sort((a,b) => b.reentregas - a.reentregas);
}

// ============ PERFORMANCE RINGS ============
function drawRing(id, value, max, invert) {
    const el = document.getElementById(id);
    const circ = 2 * Math.PI * 68; // 427.26
    const pct = Math.min(value / max, 1);
    const offset = circ * (1 - pct);
    el.style.strokeDashoffset = offset;

    const rounded = invert ? Math.round(value * 100) / 100 : Math.round(value);
    const isGood = invert ? rounded <= 0.67 : rounded >= 84;
    el.style.stroke = isGood ? 'var(--success)' : 'var(--primary)';
    // Glow
    el.parentElement.style.filter = isGood
        ? 'drop-shadow(0 0 10px rgba(45,179,126,0.25))'
        : 'drop-shadow(0 0 10px rgba(245,26,32,0.2))';
}

// ============ CHART REAL KG ============
function renderChartRealKgDia(data) {
    const ctx = document.getElementById('chartRealKgDia').getContext('2d');
    if (chartRealKgDia) chartRealKgDia.destroy();
    const labels = data.map(r => fmt.diaLabel(r.DIA));
    const values = data.map(r => r.real_kg);
    const grad = ctx.createLinearGradient(0, 0, 0, 300);
    grad.addColorStop(0, 'rgba(238,203,2,0.18)');
    grad.addColorStop(1, 'rgba(238,203,2,0.02)');

    chartRealKgDia = new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets: [{
                label: 'R$/Kg', data: values,
                borderColor: '#EECB02', backgroundColor: grad,
                borderWidth: 2, fill: true, tension: 0.4,
                pointRadius: 0, pointHoverRadius: 5,
                pointHoverBackgroundColor: '#EECB02',
                pointHoverBorderColor: '#fff', pointHoverBorderWidth: 2,
            }, {
                label: 'Meta R$ 0,67',
                data: Array(labels.length).fill(0.67),
                borderColor: 'rgba(217,160,102,0.6)', borderWidth: 1.5, borderDash: [6,4],
                pointRadius: 0, fill: false,
            }]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: { legend: { display: false },
                tooltip: { backgroundColor: 'rgba(255,250,240,0.98)', borderColor: 'rgba(139,38,53,0.20)', borderWidth: 1, padding: 12, cornerRadius: 10,
                    titleColor: '#2a2620', bodyColor: '#5a4f44', titleFont: { weight: '600' },
                    callbacks: { label: c => c.datasetIndex===0 ? 'R$/Kg: '+fmt.dec(c.raw,2) : 'Meta: R$ 0,67' }
                }
            },
            scales: {
                x: { grid: { color: 'rgba(139,38,53,0.09)' }, ticks: { color: '#8a7f83', font: { size: 10 }, maxTicksLimit: 15 }, border: { display: false } },
                y: { grid: { color: 'rgba(139,38,53,0.09)' }, ticks: { color: '#8a7f83', font: { size: 10 }, callback: v => 'R$ '+v.toFixed(2) }, border: { display: false } }
            }
        }
    });
}

// ============ TABLE VEÍCULO ============
function renderTableVeiculo(tableId, data) {
    const tbody = document.querySelector('#'+tableId+' tbody');
    if (!data || !data.length) { tbody.innerHTML='<tr><td colspan="6" style="text-align:center;color:var(--text-muted);padding:2rem;">Sem dados</td></tr>'; return; }

    const grouped = {};
    data.forEach(r => {
        const v = r.VEICULO;
        if (!grouped[v]) grouped[v] = { peso:0, capac:0, frete:0, veiculos:0, entregas:0 };
        grouped[v].peso += r.peso; grouped[v].capac += r.capac;
        grouped[v].frete += r.frete; grouped[v].veiculos += r.veiculos;
        grouped[v].entregas += r.entregas;
    });

    let html = '';
    for (const [v, g] of Object.entries(grouped)) {
        const ocup = g.capac > 0 ? (g.peso/g.capac*100) : 0;
        const rk = g.peso > 0 ? (g.frete/g.peso) : 0;
        const me = g.veiculos > 0 ? (g.entregas/g.veiculos) : 0;
        const mp = g.veiculos > 0 ? (g.peso/g.veiculos) : 0;
        const badge = ocup >= 84 ? 'badge-green' : ocup >= 60 ? 'badge-yellow' : 'badge-red';
        html += `<tr>
            <td><strong>${v}</strong></td>
            <td class="num">${fmt.num(g.veiculos)}</td>
            <td class="num">${fmt.dec(me,0)}</td>
            <td class="num">${fmt.dec(mp,0)} kg</td>
            <td class="num"><span class="badge ${badge}">${fmt.dec(ocup,0)}%</span></td>
            <td class="num">${fmt.brl(rk)}</td>
        </tr>`;
    }

    // Total
    const tP = Object.values(grouped).reduce((s,g)=>s+g.peso,0);
    const tC = Object.values(grouped).reduce((s,g)=>s+g.capac,0);
    const tF = Object.values(grouped).reduce((s,g)=>s+g.frete,0);
    const tV = Object.values(grouped).reduce((s,g)=>s+g.veiculos,0);
    const tE = Object.values(grouped).reduce((s,g)=>s+g.entregas,0);
    const tOc = tC > 0 ? (tP/tC*100) : 0;
    const tRk = tP > 0 ? (tF/tP) : 0;
    const tMe = tV > 0 ? (tE/tV) : 0;
    const tMp = tV > 0 ? (tP/tV) : 0;

    html += `<tr style="font-weight:700;border-top:2px solid var(--primary);">
        <td>TOTAL</td><td class="num">${fmt.num(tV)}</td><td class="num">${fmt.dec(tMe,0)}</td>
        <td class="num">${fmt.dec(tMp,0)} kg</td><td class="num">${fmt.dec(tOc,0)}%</td><td class="num">${fmt.brl(tRk)}</td>
    </tr>`;
    tbody.innerHTML = html;
}

// ============ TABLE REENTREGAS TRANSP ============
function renderTableReentTransp(tableId, data) {
    const tbody = document.querySelector('#'+tableId+' tbody');
    const mx = data.length > 0 ? Math.max(...data.map(r=>r.reentregas)) : 1;
    let html = '';
    data.forEach(r => {
        const nm = r['NOME TRANSPORTADORA'] || 'N/A';
        const bw = (r.reentregas/mx*100);
        const entregas = r.entregas || 0;
        html += `<tr><td>${nm}</td><td class="num"><strong>${fmt.num(r.reentregas)}</strong></td><td class="num">${fmt.num(entregas)}</td><td class="num">${fmt.pct(r.pct)}</td>
            <td><div class="mini-bar" style="width:120px;"><div class="mini-bar-fill" style="width:${bw}%"></div></div></td></tr>`;
    });
    tbody.innerHTML = html;
}

// ============ CHART REENTREGAS JUST ============
function renderChartReentJust(canvasId, data, scope) {
    const ctx = document.getElementById(canvasId).getContext('2d');
    if (scope === 'dia' && chartReentJustDia) chartReentJustDia.destroy();
    if (scope === 'mes' && chartReentJustMes) chartReentJustMes.destroy();
    const top = data.slice(0,8);
    const colors = ['#EECB02','#FCD34D','#FDE68A','#FEF08A','#EAB308','#CA8A04','#A16207','#854D0E'];

    // Plugin inline: desenha o % (participação no total) no fim de cada barra.
    const pctLabelPlugin = {
        id: 'reentJustPct',
        afterDatasetsDraw(chart) {
            const meta = chart.getDatasetMeta(0);
            if (!meta || !meta.data) return;
            const c = chart.ctx; c.save();
            c.font = '700 10px Inter, system-ui, sans-serif'; c.textBaseline = 'middle';
            meta.data.forEach((bar, i) => {
                const pct = top[i] ? (top[i].pct || 0) : 0;
                const txt = fmt.dec(pct, 1) + '%';
                const w = c.measureText(txt).width;
                if ((bar.x + 6 + w) <= chart.chartArea.right) { c.fillStyle = '#7A5A00'; c.textAlign = 'left';  c.fillText(txt, bar.x + 6, bar.y); }
                else                                          { c.fillStyle = '#3A2A00'; c.textAlign = 'right'; c.fillText(txt, bar.x - 6, bar.y); }
            });
            c.restore();
        }
    };

    const chart = new Chart(ctx, {
        type: 'bar',
        data: { labels: top.map(r=>r['DESC JUST OC']||'N/A'), datasets: [{ data: top.map(r=>r.reentregas), backgroundColor: colors.slice(0,top.length), borderRadius: 6, borderSkipped: false, barThickness: 28 }] },
        plugins: [pctLabelPlugin],
        options: {
            indexAxis: 'y', responsive: true, maintainAspectRatio: false,
            layout: { padding: { right: 8 } },
            plugins: { legend: { display: false }, tooltip: { backgroundColor: 'rgba(255,250,240,0.98)', borderColor: 'rgba(139,38,53,0.20)', borderWidth: 1, padding: 12, cornerRadius: 10, titleColor: '#2a2620', bodyColor: '#5a4f44', callbacks: { label: c => 'Reentregas: ' + fmt.num(c.raw) + '  (' + fmt.dec(top[c.dataIndex] ? top[c.dataIndex].pct : 0, 1) + '%)' } } },
            scales: {
                x: { grace: '12%', grid: { color: 'rgba(139,38,53,0.09)' }, ticks: { color: '#8a7f83', font: { size: 10 } }, border: { display: false } },
                y: { grid: { display: false }, ticks: { color: '#5a4f44', font: { size: 10 }, callback: function(v){ const l=this.getLabelForValue(v); return l.length>30?l.substr(0,30)+'...':l; } }, border: { display: false } }
            }
        }
    });
    if (scope === 'dia') chartReentJustDia = chart;
    if (scope === 'mes') chartReentJustMes = chart;
}

// ============ CHART REENTREGAS POR DIA (LINHA) ============
function renderChartReentDia(data) {
    const ctx = document.getElementById('chartReentDia').getContext('2d');
    if (chartReentDia) chartReentDia.destroy();
    const labels = data.map(r => fmt.diaLabel(r.DIA));
    const values = data.map(r => r.reentregas);
    const grad = ctx.createLinearGradient(0, 0, 0, 280);
    grad.addColorStop(0, 'rgba(238,203,2,0.18)');
    grad.addColorStop(1, 'rgba(238,203,2,0.02)');

    chartReentDia = new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets: [{
                label: 'Reentregas', data: values,
                borderColor: '#EECB02', backgroundColor: grad,
                borderWidth: 2, fill: true, tension: 0.4,
                pointRadius: 0, pointHoverRadius: 5,
                pointHoverBackgroundColor: '#EECB02',
                pointHoverBorderColor: '#fff', pointHoverBorderWidth: 2,
            }]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: { legend: { display: false },
                tooltip: { backgroundColor: 'rgba(255,250,240,0.98)', borderColor: 'rgba(139,38,53,0.20)', borderWidth: 1, padding: 12, cornerRadius: 10,
                    titleColor: '#2a2620', bodyColor: '#5a4f44', titleFont: { weight: '600' },
                    callbacks: { label: c => 'Reentregas: ' + fmt.num(c.raw) }
                }
            },
            scales: {
                x: { grid: { color: 'rgba(139,38,53,0.09)' }, ticks: { color: '#8a7f83', font: { size: 10 }, maxTicksLimit: 15 }, border: { display: false } },
                y: { grid: { color: 'rgba(139,38,53,0.09)' }, ticks: { color: '#8a7f83', font: { size: 10 } }, border: { display: false }, beginAtZero: true }
            }
        }
    });
}

// ============ TABLE DETAIL ============
function renderTableReentDetail(tableId, data) {
    const tbody = document.querySelector('#'+tableId+' tbody');
    let html = '';
    data.slice(0,50).forEach(r => {
        html += `<tr><td>${r['NOME TRANSPORTADORA']||'N/A'}</td><td>${r['DESC JUST OC']||'N/A'}</td><td class="num"><strong>${fmt.num(r.reentregas)}</strong></td></tr>`;
    });
    tbody.innerHTML = html;
}

// ============ FILTERS FROTA ============
function populateFiltersFrota() { populateMesDia('filterMesFrota', 'filterDiaFrota', DATA.filtros.meses_frota||[], DATA.filtros.dias_frota||[]); }

function updateDiaOptionsFrota(mes) { updateDiaSelect('filterDiaFrota', DATA.filtros.dias_frota||[], mes); }

function resetFiltersFrota() { document.getElementById('filterMesFrota').value='all'; document.getElementById('filterDiaFrota').value='all'; applyFiltersFrota(); }

// ============ APPLY FROTA ============
function applyFiltersFrota() {
    const mes = document.getElementById('filterMesFrota').value;
    const dia = document.getElementById('filterDiaFrota').value;
    updateDiaOptionsFrota(mes);

    let totalDisp, totalUtil;

    if (dia !== 'all') {
        const d = DATA.frota_dia.find(r => r.DIA === dia);
        totalDisp = d ? d.disponibilizado : 0;
        totalUtil = d ? d.utilizado : 0;
    } else if (mes !== 'all') {
        const m = DATA.frota_mes.find(r => r.MES_KEY === mes);
        totalDisp = m ? m.disponibilizado : 0;
        totalUtil = m ? m.utilizado : 0;
    } else {
        totalDisp = DATA.frota_kpis.total_disp;
        totalUtil = DATA.frota_kpis.total_util;
    }

    const pct = totalDisp > 0 ? (totalUtil / totalDisp * 100) : 0;
    const naoUtil = totalDisp - totalUtil;

    document.getElementById('kpiFrotaDisp').textContent = fmt.num(totalDisp);
    document.getElementById('kpiFrotaUtil').textContent = fmt.num(totalUtil);
    document.getElementById('kpiFrotaPct').textContent = fmt.dec(pct, 0) + '%';
    document.getElementById('kpiFrotaNaoUtil').textContent = fmt.num(naoUtil);

    // Ring
    drawRingFrota(pct);

    // Chart
    let frotaDiaData = DATA.frota_dia;
    if (mes !== 'all') frotaDiaData = frotaDiaData.filter(r => r.DIA.startsWith(mes));
    renderChartFrotaDia(frotaDiaData);

    // Tables - filtrar por dia ou mês
    let transpData = DATA.frota_transportadora;
    let veicData = DATA.frota_veiculo;

    if (dia !== 'all') {
        const td = DATA.frota_transp_dia.filter(r => r.DIA === dia);
        transpData = aggregateFrotaTransp(td, 'Transportadora');
        const vd = DATA.frota_veic_dia.filter(r => r.DIA === dia);
        veicData = aggregateFrotaTransp(vd, 'Veiculo');
    } else if (mes !== 'all') {
        const td = DATA.frota_transp_dia.filter(r => r.DIA.startsWith(mes));
        transpData = aggregateFrotaTransp(td, 'Transportadora');
        const vd = DATA.frota_veic_dia.filter(r => r.DIA.startsWith(mes));
        veicData = aggregateFrotaTransp(vd, 'Veiculo');
    }

    renderTableFrota('tableFrotaTransp', transpData, 'Transportadora');
    renderTableFrota('tableFrotaVeic', veicData, 'Veiculo');
}

function aggregateFrotaTransp(data, key) {
    const grouped = {};
    data.forEach(r => {
        const k = r[key];
        if (!grouped[k]) grouped[k] = {disponibilizado: 0, utilizado: 0};
        grouped[k].disponibilizado += r.disponibilizado;
        grouped[k].utilizado += r.utilizado;
    });
    return Object.entries(grouped).map(([name, v]) => ({
        [key]: name,
        disponibilizado: v.disponibilizado,
        utilizado: v.utilizado,
        pct: v.disponibilizado > 0 ? Math.round(v.utilizado / v.disponibilizado * 100 * 100) / 100 : 0
    })).sort((a,b) => b.disponibilizado - a.disponibilizado);
}

function drawRingFrota(pct) {
    const el = document.getElementById('ringFrota');
    const circ = 2 * Math.PI * 76; // 477.52
    const offset = circ * (1 - Math.min(pct / 100, 1));
    el.style.strokeDashoffset = offset;
    const good = pct >= 80;
    el.style.stroke = good ? 'var(--success)' : 'var(--warning)';
    el.parentElement.style.filter = good
        ? 'drop-shadow(0 0 10px rgba(45,179,126,0.25))'
        : 'drop-shadow(0 0 14px rgba(217,160,102,0.35))';
    document.getElementById('ringFrotaVal').textContent = fmt.dec(pct, 0) + '%';
}

function renderChartFrotaDia(data) {
    const ctx = document.getElementById('chartFrotaDia').getContext('2d');
    if (chartFrotaDia) chartFrotaDia.destroy();
    const labels = data.map(r => fmt.diaLabel(r.DIA));
    const dispVals = data.map(r => r.disponibilizado);
    const utilVals = data.map(r => r.utilizado);

    chartFrotaDia = new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [
                { label: 'Disponibilizado', data: dispVals, backgroundColor: 'rgba(138,127,131,0.3)', borderColor: 'rgba(138,127,131,0.6)', borderWidth: 1, borderRadius: 4 },
                { label: 'Utilizado', data: utilVals, backgroundColor: 'rgba(238,203,2,0.70)', borderColor: '#EECB02', borderWidth: 1, borderRadius: 4 },
            ]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { labels: { color: '#5a4f44', font: { size: 10 } } },
                tooltip: { backgroundColor: 'rgba(255,250,240,0.98)', borderColor: 'rgba(139,38,53,0.20)', borderWidth: 1, padding: 12, cornerRadius: 10, titleColor: '#2a2620', bodyColor: '#5a4f44' }
            },
            scales: {
                x: { grid: { color: 'rgba(139,38,53,0.09)' }, ticks: { color: '#8a7f83', font: { size: 10 }, maxTicksLimit: 15 }, border: { display: false } },
                y: { grid: { color: 'rgba(139,38,53,0.09)' }, ticks: { color: '#8a7f83', font: { size: 10 } }, border: { display: false } }
            }
        }
    });
}

function renderTableFrota(tableId, data, nameKey) {
    const tbody = document.querySelector('#'+tableId+' tbody');
    if (!data || !data.length) { tbody.innerHTML='<tr><td colspan="5" style="text-align:center;color:var(--text-muted);padding:2rem;">Sem dados</td></tr>'; return; }
    const mx = Math.max(...data.map(r => r.disponibilizado));
    let html = '';
    let tDisp=0, tUtil=0;
    data.forEach(r => {
        const name = r[nameKey] || 'N/A';
        const pct = r.pct || 0;
        const bw = r.disponibilizado > 0 ? (r.utilizado / r.disponibilizado * 100) : 0;
        const badge = pct >= 90 ? 'badge-green' : pct >= 70 ? 'badge-yellow' : 'badge-red';
        tDisp += r.disponibilizado; tUtil += r.utilizado;
        html += `<tr>
            <td><strong>${name}</strong></td>
            <td class="num">${fmt.num(r.disponibilizado)}</td>
            <td class="num">${fmt.num(r.utilizado)}</td>
            <td class="num"><span class="badge ${badge}">${fmt.dec(pct,0)}%</span></td>
            <td><div class="mini-bar" style="width:100px;"><div class="mini-bar-fill" style="width:${bw}%"></div></div></td>
        </tr>`;
    });
    const tPct = tDisp > 0 ? (tUtil/tDisp*100) : 0;
    html += `<tr style="font-weight:700;border-top:2px solid var(--primary);">
        <td>TOTAL</td><td class="num">${fmt.num(tDisp)}</td><td class="num">${fmt.num(tUtil)}</td>
        <td class="num">${fmt.dec(tPct,0)}%</td><td></td>
    </tr>`;
    tbody.innerHTML = html;
}

// ============ FILTERS VESPERTINA ============
function populateFiltersVesp() { populateMesDia('filterMesVesp', 'filterDiaVesp', DATA.filtros.meses_vesp||[], DATA.filtros.dias_vesp||[]); }

function updateDiaOptionsVesp(mes) { updateDiaSelect('filterDiaVesp', DATA.filtros.dias_vesp||[], mes); }

function resetFiltersVesp() { document.getElementById('filterMesVesp').value='all'; document.getElementById('filterDiaVesp').value='all'; applyFiltersVesp(); }

function applyFiltersVesp() {
    const mes = document.getElementById('filterMesVesp').value;
    const dia = document.getElementById('filterDiaVesp').value;
    updateDiaOptionsVesp(mes);

    let porDia = DATA.vesp_por_dia;
    let porVeiculoDia = DATA.vesp_por_veiculo_dia;
    let porVeiculoMes = DATA.vesp_por_veiculo_mes;
    let porDiaTL = DATA.vesp_tl_por_dia;
    let porVeiculoDiaTL = DATA.vesp_tl_por_veiculo_dia;
    let porVeiculoMesTL = DATA.vesp_tl_por_veiculo_mes;

    if (mes !== 'all') {
        porDia = porDia.filter(r => r.DIA.startsWith(mes));
        porVeiculoMes = porVeiculoMes.filter(r => r.MES_KEY === mes);
        porDiaTL = porDiaTL.filter(r => r.DIA.startsWith(mes));
        porVeiculoMesTL = porVeiculoMesTL.filter(r => r.MES_KEY === mes);
    }
    if (dia !== 'all') {
        porVeiculoDia = porVeiculoDia.filter(r => r.DIA === dia);
        porVeiculoDiaTL = porVeiculoDiaTL.filter(r => r.DIA === dia);
    }

    const kpis = kpisFromGrain(mes, dia, porDia, DATA.vesp_por_mes, DATA.vesp_kpis);

    document.getElementById('kpiVespVeiculos').textContent = fmt.num(kpis.qtd_veiculos);
    document.getElementById('kpiVespEntregas').textContent = fmt.num(kpis.qtd_entregas);
    document.getElementById('kpiVespPeso').textContent = fmt.tons(kpis.peso_total);

    const ocup = kpis.ocupacao_total;
    const rk = kpis.real_kg_total;
    const elOcup = document.getElementById('kpiVespOcupacao');
    const elRk = document.getElementById('kpiVespRealKg');
    elOcup.textContent = fmt.dec(ocup, 0) + '%';
    elRk.textContent = fmt.brl(rk);
    elOcup.className = 'kpi-value';
    elRk.className = 'kpi-value';

    const occDiffVesp = Math.round(ocup) - 84;
    const occDeltaVesp = document.getElementById('kpiVespOcupacaoDelta');
    occDeltaVesp.textContent = occDiffVesp >= 0 ? `🔺 +${occDiffVesp}% acima da meta` : `🔻 ${occDiffVesp}% abaixo da meta`;
    occDeltaVesp.className = 'kpi-delta ' + (occDiffVesp >= 0 ? 'good' : 'bad');

    const rkRoundedVesp = Math.round(rk * 100) / 100;
    const rkDiffVesp = rkRoundedVesp - 0.67;
    const rkDiffAbsVesp = Math.abs(rkDiffVesp).toFixed(2);
    const rkDeltaVesp = document.getElementById('kpiVespRealKgDelta');
    rkDeltaVesp.textContent = rkDiffVesp > 0 ? `🔺 +R$ ${rkDiffAbsVesp} acima da meta` : `🔻 -R$ ${rkDiffAbsVesp} abaixo da meta`;
    rkDeltaVesp.className = 'kpi-delta ' + (rkDiffVesp > 0 ? 'bad' : 'good');

    // Rings
    drawRing('ringVespOcupacao', ocup, 100, false);
    document.getElementById('ringVespOcupacaoVal').textContent = fmt.dec(ocup, 0) + '%';
    const sO = document.getElementById('ringVespOcupacaoStatus');
    sO.textContent = Math.round(ocup) >= 84 ? 'Dentro da meta' : 'Abaixo da meta';
    sO.className = 'perf-status ' + (Math.round(ocup) >= 84 ? 'good' : 'bad');

    drawRing('ringVespRealKg', rk, 1.5, true);
    document.getElementById('ringVespRealKgVal').textContent = fmt.brl(rk);
    const sR = document.getElementById('ringVespRealKgStatus');
    sR.textContent = Math.round(rk * 100) / 100 <= 0.67 ? 'Dentro da meta' : 'Acima da meta';
    sR.className = 'perf-status ' + (Math.round(rk * 100) / 100 <= 0.67 ? 'good' : 'bad');

    // Chart
    renderChartVespRealKgDia(porDia);

    // Tables
    renderTableVeiculo('tableVespDia', porVeiculoDia);
    renderTableVeiculo('tableVespMes', mes !== 'all' ? porVeiculoMes : DATA.vesp_por_veiculo);
    renderTableVeiculo('tableVespTLDia', porVeiculoDiaTL);
    renderTableVeiculo('tableVespTLMes', mes !== 'all' ? porVeiculoMesTL : DATA.vesp_tl_por_veiculo);
}

function renderChartVespRealKgDia(porDia) {
    const ctx = document.getElementById('chartVespRealKgDia').getContext('2d');
    if (chartVespRealKgDia) chartVespRealKgDia.destroy();
    const labels = porDia.map(r => fmt.diaLabel(r.DIA));
    const values = porDia.map(r => r.real_kg);
    chartVespRealKgDia = new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets: [
                { label: 'R$/Kg', data: values, borderColor: '#EECB02', backgroundColor: 'rgba(238,203,2,0.10)', tension: 0.4, fill: true, pointRadius: 3, pointHoverRadius: 6, borderWidth: 2 },
                { label: 'Meta', data: Array(labels.length).fill(0.67), borderColor: 'rgba(217,160,102,0.6)', borderDash: [6,4], borderWidth: 1.5, pointRadius: 0, fill: false },
            ]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: { backgroundColor: 'rgba(255,250,240,0.98)', borderColor: 'rgba(139,38,53,0.20)', borderWidth: 1, padding: 12, cornerRadius: 10,
                    titleColor: '#2a2620', bodyColor: '#5a4f44',
                    callbacks: { label: c => c.datasetIndex===0 ? 'R$/Kg: '+fmt.dec(c.raw,2) : 'Meta: R$ 0,67' } }
            },
            scales: {
                x: { grid: { color: 'rgba(139,38,53,0.09)' }, ticks: { color: '#8a7f83', font: { size: 9 }, maxRotation: 45 }, border: { display: false } },
                y: { grid: { color: 'rgba(139,38,53,0.09)' }, ticks: { color: '#8a7f83', font: { size: 10 }, callback: v => 'R$ '+v.toFixed(2) }, border: { display: false } }
            }
        }
    });
}

// ============ FILTERS FRESCAL ============
function populateFiltersFresc() { populateMesDia('filterMesFresc', 'filterDiaFresc', DATA.filtros.meses_fresc||[], DATA.filtros.dias_fresc||[]); }

function updateDiaOptionsFresc(mes) { updateDiaSelect('filterDiaFresc', DATA.filtros.dias_fresc||[], mes); }

function resetFiltersFresc() { document.getElementById('filterMesFresc').value='all'; document.getElementById('filterDiaFresc').value='all'; applyFiltersFresc(); }

function applyFiltersFresc() {
    const mes = document.getElementById('filterMesFresc').value;
    const dia = document.getElementById('filterDiaFresc').value;
    updateDiaOptionsFresc(mes);

    let porDia = DATA.fresc_por_dia || [];
    let porVeiculoDia = DATA.fresc_por_veiculo_dia || [];
    let porVeiculoMes = DATA.fresc_por_veiculo_mes || [];

    if (mes !== 'all') {
        porDia = porDia.filter(r => r.DIA.startsWith(mes));
        porVeiculoMes = porVeiculoMes.filter(r => r.MES_KEY === mes);
    }
    if (dia !== 'all') porVeiculoDia = porVeiculoDia.filter(r => r.DIA === dia);

    const kpis = kpisFromGrain(mes, dia, porDia, DATA.fresc_por_mes || [], DATA.fresc_kpis || {});

    document.getElementById('kpiFrescVeiculos').textContent = fmt.num(kpis.qtd_veiculos);
    document.getElementById('kpiFrescEntregas').textContent = fmt.num(kpis.qtd_entregas);
    document.getElementById('kpiFrescPeso').textContent = fmt.tons(kpis.peso_total);

    const ocup = kpis.ocupacao_total || 0;
    const rk   = kpis.real_kg_total  || 0;

    const elOcup = document.getElementById('kpiFrescOcupacao');
    const elRk   = document.getElementById('kpiFrescRealKg');
    elOcup.textContent = fmt.dec(ocup, 0) + '%';
    elRk.textContent   = fmt.brl(rk);
    elOcup.className   = 'kpi-value';
    elRk.className     = 'kpi-value';

    renderTableVeiculo('tableFrescDia', porVeiculoDia);
    renderTableVeiculo('tableFrescMes', mes !== 'all' ? porVeiculoMes : (DATA.fresc_por_veiculo || []));

    // Entregas Realizadas Mês — sempre usa total mensal (ignora filtro de dia)
    const mesRow = mes !== 'all' ? (DATA.fresc_por_mes || []).find(r => r.MES_KEY === mes) : null;
    const entMes = mesRow ? mesRow.entregas : (DATA.fresc_kpis?.qtd_entregas || 0);
    document.getElementById('kpiFrescSumEntregas').textContent = fmt.num(entMes);
}

// ============ PAGE SWITCH ============
const PAGE_LABELS = { roteiro:'Roteiro', reentregas:'Reentregas', frota:'Frota', vespertina:'Vespertina', frescal:'Frescal' };
let _switching = false;

const PAGE_ORDER = ['roteiro', 'reentregas', 'frota', 'vespertina', 'frescal'];
function switchPage(page, btn) {
    if (_switching) return;
    const current = document.querySelector('.page-section.active');
    const next    = document.getElementById('page-' + page);
    if (!next || current === next) return;

    _switching = true;

    // Atualiza visual e acessibilidade da aba imediatamente (sem esperar transição)
    document.querySelectorAll('.tab').forEach(t => { t.classList.remove('active'); t.setAttribute('aria-selected', 'false'); });
    if (btn) {
        btn.classList.add('active');
        btn.setAttribute('aria-selected', 'true');
    } else {
        document.querySelectorAll('.tab').forEach(t => {
            if (t.textContent.trim() === PAGE_LABELS[page]) { t.classList.add('active'); t.setAttribute('aria-selected', 'true'); }
        });
    }
    if (typeof updateTabIndicator === 'function') updateTabIndicator();

    // Inicia o fade-out da página atual; a próxima já entra com delay (definido no CSS)
    current.classList.add('leaving');
    next.classList.add('active');

    if (page === 'reentregas') setTimeout(applyFiltersReent, 200);
    if (page === 'frota')      setTimeout(applyFiltersFrota, 200);
    if (page === 'vespertina') setTimeout(applyFiltersVesp, 200);
    if (page === 'frescal')    setTimeout(applyFiltersFresc, 200);

    // Limpa o estado da página anterior após o fade-out terminar (420ms)
    setTimeout(() => {
        current.classList.remove('active', 'leaving');
    }, 440);

    // Libera o lock após a entrada da próxima completar (delay 180 + 550ms)
    setTimeout(() => {
        _switching = false;
    }, 740);
}

// ============ MODO APRESENTAÇÃO ============
(function () {
    const PAGES    = ['roteiro', 'reentregas', 'frota', 'vespertina', 'frescal'];
    const DURATION = 30; // segundos por aba

    const params = new URLSearchParams(window.location.search);
    if (!params.has('apresentacao')) return;

    let idx         = 0;
    let remaining   = DURATION;
    let rafId       = null;
    let scrollRafId = null;
    let lastTs      = null;

    const bar       = document.getElementById('presBar');
    const badge     = document.getElementById('presBadge');
    const countdown = document.getElementById('presCountdown');

    bar.classList.add('active');
    badge.classList.add('active');

    // Filtros de cada aba
    const FILTERS = {
        roteiro:    { mes: 'filterMes',      dia: 'filterDia',      apply: () => applyFilters() },
        reentregas: { mes: 'filterMesReent', dia: 'filterDiaReent', apply: () => applyFiltersReent() },
        frota:      { mes: 'filterMesFrota', dia: 'filterDiaFrota', apply: () => applyFiltersFrota() },
        vespertina: { mes: 'filterMesVesp',  dia: 'filterDiaVesp',  apply: () => applyFiltersVesp() },
        frescal:    { mes: 'filterMesFresc', dia: 'filterDiaFresc', apply: () => applyFiltersFresc() },
    };

    // Seleciona a última opção do select e dispara o evento de mudança
    function selectLast(id) {
        const el = document.getElementById(id);
        if (!el || el.options.length <= 1) return;
        el.value = el.options[el.options.length - 1].value;
        el.dispatchEvent(new Event('change'));
    }

    // Aplica o filtro de data mais recente (mês e dia) para a aba indicada
    function applyPresFilters(page) {
        const cfg = FILTERS[page];
        if (!cfg) return;
        selectLast(cfg.mes);           // → dispara onchange → atualiza lista de dias
        setTimeout(() => {
            selectLast(cfg.dia);       // → seleciona último dia do mês escolhido
            cfg.apply();               // → re-renderiza com dia selecionado
        }, 250);
    }

    // Scroll suave de cima a baixo ao longo dos segundos disponíveis
    function stopScroll() {
        if (scrollRafId) { cancelAnimationFrame(scrollRafId); scrollRafId = null; }
    }

    function startScroll() {
        stopScroll();
        window.scrollTo(0, 0);
        let scrollStart = null;
        const scrollMs = (DURATION - 2.5) * 1000; // reserva 2.5 s para filtros/charts

        function step(ts) {
            if (!scrollStart) scrollStart = ts;
            const t = Math.min((ts - scrollStart) / scrollMs, 1);
            // Ignora os extremos para não travar no topo nem embalar no fundo
            const eased = t < 0.04 ? 0 : t > 0.96 ? 1 : (t - 0.04) / 0.92;
            const maxY  = document.documentElement.scrollHeight - window.innerHeight;
            if (maxY > 0) window.scrollTo(0, maxY * eased);
            if (t < 1) scrollRafId = requestAnimationFrame(step);
        }
        scrollRafId = requestAnimationFrame(step);
    }

    // Chamado após cada troca de aba: aplica filtros e inicia scroll
    function onPageActivated(page) {
        applyPresFilters(page);
        setTimeout(startScroll, 2500); // aguarda filtros + charts renderizarem
    }

    function tick(ts) {
        if (!lastTs) lastTs = ts;
        const elapsed = (ts - lastTs) / 1000;
        lastTs = ts;

        remaining -= elapsed;
        if (remaining < 0) remaining = 0;

        const pct = ((DURATION - remaining) / DURATION) * 100;
        bar.style.width = pct + '%';
        countdown.textContent = Math.ceil(remaining) + 's';

        if (remaining <= 0) {
            stopScroll();
            idx = (idx + 1) % PAGES.length;
            switchPage(PAGES[idx], null);
            setTimeout(() => onPageActivated(PAGES[idx]), 420); // após transição
            remaining = DURATION;
            lastTs    = null;
            bar.style.transition = 'none';
            bar.style.width = '0%';
            setTimeout(() => { bar.style.transition = ''; }, 50);
        }

        rafId = requestAnimationFrame(tick);
    }

    window.addEventListener('DOMContentLoaded', () => {
        setTimeout(() => {
            onPageActivated(PAGES[idx]); // primeira aba já entra com filtro mais recente
            rafId = requestAnimationFrame(tick);
        }, 1800);
    });
})();

// =========================================================
// ✨ EFEITOS MODERNOS — wrappers, count-up, tab indicator
// =========================================================
let _animationsReady = false;
const PAGE_OF_FN = {
    applyFilters:      'roteiro',
    applyFiltersReent: 'reentregas',
    applyFiltersFrota: 'frota',
    applyFiltersVesp:  'vespertina',
    applyFiltersFresc: 'frescal',
};

// Injeta elementos auxiliares (shimmer e scan-line) em cada card
function injectCardEffects() {
    document.querySelectorAll('.kpi-card').forEach(c => {
        if (!c.querySelector('.shimmer')) {
            const s = document.createElement('span');
            s.className = 'shimmer';
            c.appendChild(s);
        }
    });
    document.querySelectorAll('.chart-card').forEach(c => {
        if (!c.querySelector('.scan-line')) {
            const s = document.createElement('span');
            s.className = 'scan-line';
            c.appendChild(s);
        }
    });
}

// ---------- Count-up suave estilo cronômetro ----------
// Faz o parsing do texto formatado (prefixo, sufixo, número, casas decimais)
function _parseFormattedNumber(text) {
    if (text == null) return null;
    const str = String(text).trim();
    if (!str || str === '--') return null;
    // Captura: prefixo (não-numérico/sinal), número (com . , - ), sufixo
    const m = str.match(/^([^0-9\-]*)(-?[0-9.,]+)(.*)$/);
    if (!m) return null;
    const prefix = m[1];
    let numStr   = m[2];
    const suffix = m[3];
    // pt-BR: vírgula é decimal, ponto é milhar -> normaliza para JS
    const hasComma = numStr.includes(',');
    if (hasComma) {
        numStr = numStr.replace(/\./g, '').replace(',', '.');
    } else {
        // sem vírgula: pontos podem ser milhares (ex.: "1.234") ou decimais raros
        // se houver mais de um ponto ou o último grupo tem 3 dígitos, são milhares
        const parts = numStr.split('.');
        if (parts.length > 2 || (parts.length === 2 && parts[1].length === 3)) {
            numStr = parts.join('');
        }
    }
    const value = parseFloat(numStr);
    if (!Number.isFinite(value)) return null;
    // Detecta nº de casas decimais a partir do texto original
    const decMatch = m[2].match(/,(\d+)$/);
    const decimals = decMatch ? decMatch[1].length : 0;
    return { value, prefix, suffix, decimals };
}

function _formatLikeBR(value, prefix, suffix, decimals) {
    const n = Number(value).toLocaleString('pt-BR', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
    });
    return prefix + n + suffix;
}

// Anima o conteúdo numérico de `el` saindo de `fromText` para `toText`
function animateNumber(el, fromText, toText, duration) {
    const from = _parseFormattedNumber(fromText);
    const to   = _parseFormattedNumber(toText);
    // Se não der pra interpretar como número, aplica direto sem animar
    if (!from || !to || from.value === to.value) {
        el.textContent = toText;
        return;
    }
    const start = performance.now();
    const dur   = duration || 700;
    const delta = to.value - from.value;
    // easeOutExpo — rápido no início, acomoda macio no fim (sensação de cronômetro)
    const ease = t => (t === 1 ? 1 : 1 - Math.pow(2, -10 * t));

    if (el._countRaf) cancelAnimationFrame(el._countRaf);

    const step = now => {
        const t = Math.min(1, (now - start) / dur);
        const v = from.value + delta * ease(t);
        el.textContent = _formatLikeBR(v, to.prefix, to.suffix, to.decimals);
        if (t < 1) {
            el._countRaf = requestAnimationFrame(step);
        } else {
            el.textContent = toText; // garante valor final exato
            el._countRaf = null;
        }
    };
    el._countRaf = requestAnimationFrame(step);
}

// Envolve uma função applyFilters* — captura valores antigos, aplica os novos
// e roda o count-up entre eles. Sem morph, sem flash, sem blur.
function wrapApplyFn(fnName) {
    const orig = window[fnName];
    if (typeof orig !== 'function') return;
    const pageId = PAGE_OF_FN[fnName];

    window[fnName] = function () {
        // Sem animação no carregamento inicial: chama direto
        if (!_animationsReady) return orig.apply(this, arguments);

        const section = document.getElementById('page-' + pageId);
        if (!section) return orig.apply(this, arguments);

        // 1) Captura valores antigos de todos elementos numéricos da página
        const numEls = section.querySelectorAll('.kpi-value, .perf-ring-value');
        const oldVals = Array.from(numEls).map(el => el.textContent);

        // 2) Aplica os novos valores imediatamente (gráficos, tabelas, etc.)
        orig.apply(this, arguments);

        // 3) Anima cada KPI do valor antigo para o novo
        numEls.forEach((el, i) => {
            const newVal = el.textContent;
            animateNumber(el, oldVals[i], newVal, 750);
        });

        // 4) Stagger sutil nas linhas da tabela (revelação leve, sem blur)
        section.querySelectorAll('.data-table tbody tr').forEach((tr, i) => {
            tr.classList.remove('row-reveal');
            void tr.offsetWidth;
            tr.classList.add('row-reveal');
            tr.style.animationDelay = (i * 18) + 'ms';
        });
    };
}

// Indicador deslizante das abas
function updateTabIndicator() {
    const tabs = document.querySelector('.tabs');
    if (!tabs) return;
    const active = tabs.querySelector('.tab.active');
    if (!active) return;
    const tRect = tabs.getBoundingClientRect();
    const aRect = active.getBoundingClientRect();
    tabs.style.setProperty('--tab-w', aRect.width + 'px');
    tabs.style.setProperty('--tab-x', (aRect.left - tRect.left) + 'px');
    tabs.classList.add('indicator-ready');
}

// Brilho ao mudar selects de filtro
function bindSelectGlow() {
    document.querySelectorAll('.filter-select').forEach(sel => {
        sel.addEventListener('change', () => {
            sel.classList.remove('flash-glow');
            void sel.offsetWidth;
            sel.classList.add('flash-glow');
            setTimeout(() => sel.classList.remove('flash-glow'), 1000);
        });
    });
}

// Pisca o badge "Atualizado em" quando os dados são (re)carregados
function flashHeaderDate() {
    const el = document.getElementById('headerDate');
    if (!el) return;
    el.classList.remove('flash-glow');
    void el.offsetWidth;
    el.classList.add('flash-glow');
    setTimeout(() => el.classList.remove('flash-glow'), 1100);
}

// Boot dos efeitos: roda 1 vez após o DOM e depois de DATA carregar
function bootAnimations() {
    injectCardEffects();
    bindSelectGlow();
    updateTabIndicator();
    document.querySelectorAll('.data-table thead th').forEach(th => { if (!th.hasAttribute('scope')) th.setAttribute('scope', 'col'); });
    Object.keys(PAGE_OF_FN).forEach(wrapApplyFn);
    window.addEventListener('resize', updateTabIndicator);
    window.addEventListener('load', updateTabIndicator);
    if (document.fonts && document.fonts.ready) {
        document.fonts.ready.then(updateTabIndicator);
    }
    // Habilita as animações depois do load inicial (evita ruído)
    setTimeout(() => { _animationsReady = true; flashHeaderDate(); }, 1200);
}

// =========================================================
// ============ INIT ============
window.addEventListener('DOMContentLoaded', () => {
    loadData();
    bootAnimations();
});
