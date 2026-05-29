// Simple Daily BI Dashboard Module
(function() {

  const MAX_DAYS = 180;          // Guard: block requests > 180 days to prevent DB hang
  const FETCH_TIMEOUT_MS = 90000; // 90 s — kill fetch if backend doesn't respond

  function init() {
    const els = {
      start: document.getElementById('startDate'),
      end: document.getElementById('endDate'),
      rated: document.getElementById('ratedCapacity'),
      production: document.getElementById('productionTag'),
      coal: document.getElementById('coalTag'),
      steam: document.getElementById('steamTag'),
      loadBtn: document.getElementById('loadBtn'),
      status: document.getElementById('status'),
      statsPanel: document.getElementById('statsPanel'),
      chartContainer: document.getElementById('chartContainer'),
      tableContainer: document.getElementById('tableContainer')
    };

  function fmt(v, d=3) {
    if (v === null || v === undefined) return '-';
    const num = Number(v);
    if (!Number.isFinite(num)) return '-';
    return num.toFixed(d);
  }

  function buildUrl() {
    const params = new URLSearchParams();
    params.set('start_date', els.start.value.trim());
    params.set('end_date', els.end.value.trim());
    if (els.rated.value.trim()) params.set('rated_capacity', els.rated.value.trim());
    params.set('production_tag', els.production.value.trim());
    params.set('coal_tag', els.coal.value.trim());
    params.set('steam_tag', els.steam.value.trim());
    return `/api/bi/simple_daily_metrics?${params.toString()}`;
  }

  function validate() {
    const s = els.start.value.trim();
    const e = els.end.value.trim();
    const prod = els.production.value.trim();

    if (!s || !e) return 'Start date and end date are required.';
    if (!/^\d{4}-\d{2}-\d{2}$/.test(s) || !/^\d{4}-\d{2}-\d{2}$/.test(e))
      return 'Dates must be in YYYY-MM-DD format.';

    const start = new Date(s);
    const end   = new Date(e);
    if (isNaN(start) || isNaN(end)) return 'Invalid date value.';
    if (end < start) return 'End date must be on or after start date.';

    const days = Math.round((end - start) / 86400000) + 1;
    if (days > MAX_DAYS)
      return `Date range is ${days} days. Maximum allowed is ${MAX_DAYS} days to prevent system overload. Please split into smaller ranges.`;

    if (!prod) return 'Production Tag is required.';
    return null; // OK
  }

  async function loadMetrics() {
    if (els.loadBtn.disabled) return; // Prevent double-click

    const validationError = validate();
    if (validationError) {
      els.status.innerHTML = `<div class="error">⚠️ ${validationError}</div>`;
      return;
    }
    
    els.status.innerHTML = '<div style="color:#00d4ff;">⏳ Loading daily metrics...</div>';
    els.loadBtn.disabled = true;
    els.loadBtn.style.opacity = '0.5';
    els.loadBtn.style.cursor = 'not-allowed';
    if (els.statsPanel) els.statsPanel.style.display = 'none';
    if (els.chartContainer) els.chartContainer.style.display = 'none';
    
    let abortCtrl = null;
    let timeoutId  = null;
    try {
      const url = buildUrl();
      abortCtrl = new AbortController();
      timeoutId = setTimeout(() => abortCtrl.abort(), FETCH_TIMEOUT_MS);

      const resp = await fetch(url, { signal: abortCtrl.signal });
      clearTimeout(timeoutId); timeoutId = null;
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      
      if (!data.success) throw new Error(data.error || data.message || 'Unknown error');
      
      if (!data.groups || data.groups.length === 0) {
        els.status.innerHTML = `<div class="error">⚠️ No data found in requested range. Message: ${data.message || 'No groups returned'}</div>`;
        return;
      }

      // Warn if actual data does not cover the full requested range
      if (data.actual_data_start && data.actual_data_end) {
        const reqStart = els.start.value.trim();
        const reqEnd   = els.end.value.trim();
        if (data.actual_data_start > reqStart || data.actual_data_end < reqEnd) {
          els.status.innerHTML = `<div style="color:#ff9800; background:rgba(255,152,0,0.15); border:1px solid #ff9800; padding:8px; border-radius:6px; margin-bottom:8px;">`
            + `⚠️ Requested range <b>${reqStart}</b> → <b>${reqEnd}</b> | Actual data available: <b>${data.actual_data_start}</b> → <b>${data.actual_data_end}</b></div>`;
        }
      }
      
      // Add period_mean to each group for table display
      const periodMean = data.overall_mean_load_mw;
      data.groups.forEach(g => {
        g.period_mean = periodMean;
      });
      
      renderStats(data);
      renderTable(data.groups);
      renderCharts(data);
      
      if (els.statsPanel) els.statsPanel.style.display = 'grid';
      if (els.chartContainer) els.chartContainer.style.display = 'block';
      els.status.innerHTML = `<div class="success">✓ Loaded ${data.groups.length} days successfully</div>`;
      
    } catch (err) {
      console.error(err);
      if (err.name === 'AbortError') {
        els.status.innerHTML = `<div class="error">⏱️ Request timed out after ${FETCH_TIMEOUT_MS/1000}s. The date range may be too wide or the server is busy. Try a shorter range.</div>`;
      } else {
        els.status.innerHTML = `<div class="error">❌ Error: ${err.message}</div>`;
      }
    } finally {
      if (timeoutId) clearTimeout(timeoutId);
      els.loadBtn.disabled = false;
      els.loadBtn.style.opacity = '1';
      els.loadBtn.style.cursor = 'pointer';
    }
  }

  function renderStats(data) {
    const statRated = document.getElementById('statRated');
    const statMean = document.getElementById('statMean');
    const statDays = document.getElementById('statDays');
    const statSampling = document.getElementById('statSampling');
    
    if (statRated) statRated.textContent = `${fmt(data.rated_capacity_mw)} MW`;
    if (statMean) statMean.textContent = data.overall_mean_load_mw ? `${fmt(data.overall_mean_load_mw)} MW` : '-';
    if (statDays) statDays.textContent = data.groups ? data.groups.length : '0';
    if (statSampling) statSampling.textContent = data.sampling_minutes ? `${fmt(data.sampling_minutes)} min` : '-';
  }

  function renderTable(groups) {
    if (!groups || !groups.length) { 
      els.tableContainer.innerHTML = '<div style="padding:20px; text-align:center; color:#ff9800;">No data to display</div>'; 
      return; 
    }
    
    const cols = [
      {key:'label', label:'Date', isText: true},
      {key:'avg_load_mw', label:'Avg Load (MW)', decimals:3},
      {key:'period_mean', label:'Period Mean (MW)', decimals:3},
      {key:'generation_mwh', label:'Generation (MWh)', decimals:3},
      {key:'utilization_pct', label:'Utilization (%)', decimals:2},
      {key:'availability_pct', label:'Availability (%)', decimals:2},
      {key:'performance_pct', label:'Performance (%)', decimals:2},
      {key:'oee_pct', label:'OEE (%)', decimals:2},
      {key:'coal_rate_tph', label:'Coal (TPH)', decimals:3},
      {key:'steam_flow_tph', label:'Steam (TPH)', decimals:3},
      {key:'scc_kg_per_kwh', label:'SCC (kg/kWh)', decimals:5},
      {key:'delta_from_mean_mw', label:'Δ Mean (MW)', decimals:3},
      {key:'delta_from_rated_mw', label:'Δ Rated (MW)', decimals:3},
      {key:'sample_count', label:'Samples', decimals:0},
      {key:'hours_covered', label:'Hours', decimals:2}
    ];
    
    let html = '<table><thead><tr>';
    cols.forEach(c => html += `<th>${c.label}</th>`);
    html += '</tr></thead><tbody>';
    
    groups.forEach(g => {
      html += '<tr>';
      cols.forEach(c => {
        const val = g[c.key];
        if (c.isText) {
          html += `<td>${val || '-'}</td>`;
        } else {
          const decimals = c.decimals !== undefined ? c.decimals : 2;
          html += `<td>${fmt(val, decimals)}</td>`;
        }
      });
      html += '</tr>';
    });
    
    html += '</tbody></table>';
    els.tableContainer.innerHTML = html;
  }

  function weightedMean(values, weights) {
    let num = 0, den = 0;
    values.forEach((v, i) => {
      const w = Number(weights[i] || 0);
      const n = Number(v);
      if (Number.isFinite(n) && Number.isFinite(w)) { num += n * w; den += w; }
    });
    return den > 0 ? num / den : null;
  }

  function renderCharts(data) {
    const groups = data.groups || [];
    const x = groups.map(g => g.label);
    const load = groups.map(g => g.avg_load_mw);
    const generation = groups.map(g => g.generation_mwh);
    const util = groups.map(g => g.utilization_pct);
    const avail = groups.map(g => g.availability_pct);
    const perf = groups.map(g => g.performance_pct);
    const oee = groups.map(g => g.oee_pct);
    const scc = groups.map(g => g.scc_kg_per_kwh);
    const deltaRated = groups.map(g => g.delta_from_rated_mw);
    const hours = groups.map(g => g.hours_covered);
    const ratedLine = Array(x.length).fill(data.rated_capacity_mw);
    const hoursWeights = hours.map(h => Number.isFinite(h) ? h : 0);

    const steamCoalRatio = [];
    const steamClean = [];
    const coalClean = [];
    const loadClean = [];
    const xClean = [];
    groups.forEach((g, i) => {
      const c = Number(g.coal_rate_tph);
      const s = Number(g.steam_flow_tph);
      const l = Number(load[i]);
      const label = x[i];
      const validCoal = Number.isFinite(c) && c !== 0;
      const validSteam = Number.isFinite(s);
      if (validCoal && validSteam) {
        steamCoalRatio.push(s / c);
        steamClean.push(s);
        coalClean.push(c);
        loadClean.push(Number.isFinite(l) ? l : null);
        xClean.push(label);
      }
    });

    const qualityDefault = Number(data.quality_default_pct ?? 92);
    const quality = groups.map(g => {
      const val = g.quality_pct;
      const num = Number(val);
      return Number.isFinite(num) ? num : qualityDefault; // default to configured quality when missing
    });

    const overallAvail = weightedMean(avail, hoursWeights) ?? null;
    const overallPerf = weightedMean(perf, hoursWeights) ?? null;
    const overallQual = weightedMean(quality, hoursWeights) ?? qualityDefault;
    const overallOEE = (overallAvail !== null && overallPerf !== null && overallQual !== null)
      ? (overallAvail * overallPerf * overallQual) / 10000.0
      : null;

    const layout = {
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: 'rgba(15, 52, 96, 0.3)',
      font: { color: '#e0e0e0', family: 'Segoe UI', size: 11 },
      xaxis: {
        gridcolor: 'rgba(0, 212, 255, 0.1)',
        color: '#00d4ff',
        autorange: true,
        type: 'date',
        fixedrange: false,
        tickfont: { size: 10 }
      },
      yaxis: {
        gridcolor: 'rgba(0, 212, 255, 0.1)',
        color: '#00d4ff',
        autorange: true,
        tickfont: { size: 10 }
      },
      height: 380,
      hovermode: 'closest',
      showlegend: true,
      legend: {
        bgcolor: 'rgba(0, 0, 0, 0.5)',
        bordercolor: '#00d4ff',
        borderwidth: 1,
        font: { size: 10 },
        orientation: 'h',
        x: 0.5,
        xanchor: 'center',
        y: -0.15
      },
      autosize: true,
      dragmode: 'zoom',
      margin: { l: 55, r: 15, t: 15, b: 50 }
    };

    const config = {
      responsive: true,
      displayModeBar: true, // keep fullscreen button available
      modeBarButtonsToRemove: ['lasso2d', 'select2d'],
      scrollZoom: true,
      doubleClick: 'reset',
      displaylogo: false
    };

    const loadGenLayout = {
      ...layout,
      height: null,
      yaxis: { ...layout.yaxis, title:{text:'MW', font:{size:11}} },
      yaxis2: {
        title:{text:'MWh', font:{size:11}},
        overlaying:'y',
        side:'right',
        showgrid:false,
        tickfont:{ size:10 }
      }
    };

    Plotly.react('chartLoadGen', [
      { x, y: load, type:'scatter', mode:'lines+markers', name:'Avg Load (MW)', line:{color:'#00d4ff', width:3}, marker:{color:'#00d4ff', size:6} },
      { x, y: ratedLine, type:'scatter', mode:'lines', name:'Rated Capacity', line:{color:'#ff9800', dash:'dash', width:2} },
      { x, y: generation, type:'bar', name:'Generation (MWh)', marker:{color:'rgba(255,255,255,0.35)', line:{color:'#ffa94d', width:1}}, yaxis:'y2', opacity:0.9 }
    ], loadGenLayout, config);

    const oeeGaugeValue = overallOEE !== null ? Number(overallOEE) : null;
    const gaugeLabel = oeeGaugeValue !== null ? `${fmt(oeeGaugeValue,1)}%` : 'N/A';
    Plotly.react('chartOEEGauge', [
      { values:[1,1,1], labels:['Availability','Performance','Quality'], type:'pie', hole:0.65,
        marker:{ colors:['#ffd700','#34c759','#00bcd4'] },
        text:[`A: ${fmt(overallAvail,1)}%`,`P: ${fmt(overallPerf,1)}%`,`Q: ${fmt(overallQual,1)}%`],
        textinfo:'text',
        hovertemplate:'%{label}: %{text}<extra></extra>',
        sort:false }
    ], {
      ...layout,
      height: null,
      showlegend: false,
      annotations: [
        { x:0.5, y:0.52, text:gaugeLabel, showarrow:false, font:{size:24, color:'#e0e0e0', family:'Segoe UI'} },
        { x:0.5, y:0.38, text:'OEE = A × P × Q / 10000', showarrow:false, font:{size:11, color:'#9cc9ff'} }
      ],
      margin:{l:20, r:20, t:10, b:10}
    }, config);

    const oeeLayout = {
      ...layout,
      barmode:'stack',
      yaxis:{...layout.yaxis, title:{text:'%', font:{size:11}}, range:[0,120]},
      height: null
    };


    Plotly.react('chartOEEStack', [
      { x, y: avail, type:'bar', name:'Availability', marker:{color:'#ffd700'} },
      { x, y: perf, type:'bar', name:'Performance', marker:{color:'#34c759'} },
      { x, y: oee, type:'scatter', mode:'lines+markers', name:'OEE', line:{color:'#ff4081', width:3}, marker:{size:6, color:'#ff4081'} }
    ], oeeLayout, config);

    Plotly.react('chartSCC', [
      { x, y: scc, type:'scatter', mode:'lines+markers', name:'SCC', line:{color:'#9c27b0', width:3}, marker:{color:'#e1bee7', size:6} }
    ], { ...layout, yaxis:{...layout.yaxis, title:{text:'kg/kWh', font:{size:11}}} }, config);

    Plotly.react('chartCoalSteamRatio', [
      { x: xClean, y: steamCoalRatio, type:'scatter', mode:'lines+markers', name:'Steam/Coal', line:{color:'#ffa94d', width:3}, marker:{size:6, color:'#ffa94d'},
        hovertemplate:'%{x}<br>Steam/Coal: %{y:.3f}<br>Steam: %{customdata[0]:.3f} TPH<br>Coal: %{customdata[1]:.3f} TPH<extra></extra>', customdata: steamClean.map((s,i)=>[steamClean[i], coalClean[i]]) },
      { x: xClean, y: loadClean, type:'scatter', mode:'lines', name:'Load (MW)', yaxis:'y2', line:{color:'#00d4ff', dash:'dot', width:2}, hovertemplate:'%{x}<br>Load: %{y:.3f} MW<extra></extra>' }
    ], {
      ...layout,
      yaxis:{...layout.yaxis, title:{text:'Steam/Coal Ratio'}, rangemode:'tozero'},
      yaxis2:{ ...layout.yaxis, title:{text:'Load (MW)'}, overlaying:'y', side:'right', showgrid:false, zeroline:false },
      legend:{...layout.legend, y:-0.2}
    }, config);

    Plotly.react('chartDeltaRated', [
      { x, y: deltaRated, type:'bar', name:'Δ Rated', marker:{color: deltaRated.map(v=> (v||0) >= 0 ? '#34c759' : '#ff3b30')},
        hovertemplate:'%{x}<br>Δ Rated: %{y:.3f} MW<extra></extra>' }
    ], { ...layout, yaxis:{...layout.yaxis, title:{text:'MW'}, zeroline:true, zerolinecolor:'#e0e0e0'} }, config);
  }

  // Default date range: last 7 days
  const today = new Date();
  const endISO = today.toISOString().slice(0,10);
  const startISO = new Date(today.getTime() - 6*86400000).toISOString().slice(0,10);
  els.start.value = startISO;
  els.end.value = endISO;

  els.loadBtn.addEventListener('click', loadMetrics);
  }

  // Initialize when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
