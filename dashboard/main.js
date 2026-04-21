const tabs = document.querySelectorAll('.tab-btn');
const refreshBtn = document.getElementById('refresh-btn');

let currentTab = 'graduated';
let allTokens = [];
let searchFilter = '';

// Mobile Menu Toggle logic
const menuBtn = document.getElementById('mobile-menu-btn');
const sidebar = document.querySelector('.sidebar');

if (menuBtn && sidebar) {
    menuBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        sidebar.classList.toggle('open');
        menuBtn.textContent = sidebar.classList.contains('open') ? '✕' : '☰';
    });
    
    // Close sidebar when clicking outside or on a tab
    document.addEventListener('click', (e) => {
        if (sidebar.classList.contains('open') && !sidebar.contains(e.target) && e.target !== menuBtn) {
            sidebar.classList.remove('open');
            menuBtn.textContent = '☰';
        }
    });

    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            if (window.innerWidth <= 900) {
                sidebar.classList.remove('open');
                menuBtn.textContent = '☰';
            }
        });
    });
}

// Tab switching
tabs.forEach(tab => {
    tab.addEventListener('click', () => {
        tabs.forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        currentTab = tab.dataset.tab;
        
        const titleEl = document.getElementById('current-view-title');
        if (titleEl) titleEl.textContent = tab.textContent.trim();

        const searchContainer = document.getElementById('search-container');
        if (searchContainer) {
            searchContainer.style.display = 'flex'; // Always show search
        }

        document.querySelectorAll('.token-list').forEach(list => list.style.display = 'none');
        const activeList = document.getElementById(`list-${currentTab}`);
        if (activeList) activeList.style.display = 'flex';
        
        renderTokens();
    });
});

if (refreshBtn) {
    refreshBtn.addEventListener('click', () => {
        refreshBtn.textContent = '🔄 SYNCING...';
        loadTokens().finally(() => { refreshBtn.textContent = '🔄 SYNC DATA'; });
    });
}

function formatNum(num) {
    if (num === null || num === undefined) return '?';
    const val = parseFloat(num);
    if (isNaN(val)) return '0';
    if (val >= 1e9) return (val / 1e9).toFixed(1) + 'B';
    if (val >= 1e6) return (val / 1e6).toFixed(1) + 'M';
    if (val >= 1e3) return (val / 1e3).toFixed(1) + 'k';
    return Math.round(val).toString();
}

async function loadTokens() {
    try {
        const res = await fetch('http://localhost:8000/api/tokens');
        allTokens = await res.json();
        updateHealthStatus();
        renderTokens();
    } catch (err) { console.error("Error fetching tokens:", err); }
}

function updateHealthStatus() {
    const healthEl = document.getElementById('system-health');
    if (healthEl) {
        healthEl.innerHTML = `<span style="color: var(--success);">●</span> SSE ACTIVE | <span style="font-weight: 700;">${allTokens.length} MONITORED</span>`;
    }
}

function setupSSE() {
    const eventSource = new EventSource('http://localhost:8000/api/stream');
    eventSource.onopen = () => { console.log('✅ SSE Connected'); };
    eventSource.onerror = () => { eventSource.close(); setTimeout(setupSSE, 3000); };
    eventSource.addEventListener('update', (event) => {
        try {
            const data = JSON.parse(event.data);
            if (data.type === 'token_update') {
                upsertToken(data.payload);
            }
        } catch(e) {}
    });
}

function upsertToken(newToken) {
    const index = allTokens.findIndex(t => t.ca === newToken.ca);
    if (index !== -1) {
        allTokens[index] = { ...allTokens[index], ...newToken };
    } else {
        allTokens.unshift(newToken);
    }
    renderTokens();
}

setInterval(renderTokens, 30000);

function renderTokens() {
    const categories = ['graduated', 'analyzing', 'gems', 'established', 'legacy', 'trending', 'hall_of_fame', 'scam_trending', 'scams', 'scammed', 'died'];
    allTokens.sort((a, b) => (b.telegram_submission_time || 0) - (a.telegram_submission_time || 0));

    categories.forEach(cat => {
        const listEl = document.getElementById(`list-${cat}`);
        if (!listEl) return;

        let filtered = [];

        if (searchFilter) {
            // Global search: search ALL tokens regardless of category
            filtered = allTokens.filter(t => 
                (t.ca || '').toLowerCase().includes(searchFilter.toLowerCase()) || 
                (t.name || '').toLowerCase().includes(searchFilter.toLowerCase()) ||
                (t.symbol || '').toLowerCase().includes(searchFilter.toLowerCase())
            );
            // Only render search results in the currently active tab
            if (cat !== currentTab) return;
        } else {
            filtered = allTokens.filter(t => matchesCategory(t, cat));
        }

        if (cat === 'analyzing') filtered = filtered.slice(0, 15);

        if (filtered.length === 0) {
            const emptyMsg = searchFilter 
                ? `<div style="text-align:center; opacity:0.3; padding:3rem;">No tokens found for "${searchFilter}"</div>` 
                : `<div style="text-align:center; opacity:0.1; padding:3rem;">No tokens currently in ${cat}.</div>`;
            listEl.innerHTML = emptyMsg;
            return;
        }

        // Peak X visibility pinned to Graduation Release (Always show for context)
        const showPerf = true; 
        const showDest = false; // REMOVED: Destination column removed per user request
        const showSafe = ['gems', 'established', 'legacy', 'hall_of_fame', 'trending'].includes(cat);

        listEl.classList.remove('has-dest', 'has-perf');
        if (showPerf) listEl.classList.add('has-perf');

        const existingTokens = Array.from(listEl.querySelectorAll('.token-row:not(.header-row)'));
        
        // Remove tokens no longer in this list
        existingTokens.forEach(el => {
            const tokenCA = el.id.replace('token-', '');
            if (!filtered.find(t => t.ca === tokenCA)) {
                el.remove();
            }
        });

        // Add header if missing
        if (!listEl.querySelector('.header-row')) {
            listEl.insertAdjacentHTML('afterbegin', createHeaderRow(showPerf));
        }

        // Add or Update tokens
        filtered.forEach((token, index) => {
            const rowId = `token-${token.ca}`;
            let existingRow = document.getElementById(rowId);
            const rowHtml = createTokenRow(token, showPerf, showDest, showSafe);

            if (existingRow) {
                const tempDiv = document.createElement('div');
                tempDiv.innerHTML = rowHtml;
                const newRow = tempDiv.firstElementChild;
                
                if (existingRow.innerHTML !== newRow.innerHTML) {
                    existingRow.innerHTML = newRow.innerHTML;
                }
            } else {
                listEl.insertAdjacentHTML('beforeend', rowHtml);
            }
        });

        // Re-ordering (very basic move to matching index)
        filtered.forEach((token, i) => {
            const el = document.getElementById(`token-${token.ca}`);
            const expectedIndex = i + 1; // +1 because of header
            if (listEl.children[expectedIndex] !== el) {
                listEl.insertBefore(el, listEl.children[expectedIndex]);
            }
        });
    });

    const resLabel = document.getElementById('search-results-label');
    if (resLabel) resLabel.textContent = searchFilter ? `${allTokens.filter(t => (t.ca||'').toLowerCase().includes(searchFilter.toLowerCase()) || (t.name||'').toLowerCase().includes(searchFilter.toLowerCase()) || (t.symbol||'').toLowerCase().includes(searchFilter.toLowerCase())).length} results` : '';
}

function createHeaderRow(showPerf) {
    return `
        <div class="token-row header-row">
            <div>TOKEN</div>
            <div>MC</div>
            ${showPerf ? '<div style="text-align:center;">PEAK</div>' : ''}
            <div>HOLDERS</div>
            <div>LIQ</div>
            <div>LINKS</div>
            <div>SCORE</div>
            <div>AGE</div>
            <div style="text-align:center;">INFO</div>
        </div>
    `;
}

function matchesCategory(token, cat) {
    const tCat = (token.current_category || 'analyzing').toLowerCase();
    const targetCat = cat.toLowerCase();

    if (targetCat === 'hall_of_fame') {
        // Backend induction ONLY (Must hit 10x or $500k in Established/Legacy phases)
        return (tCat === 'hall_of_fame');
    }
    
    // Unified Intake: Graduated tab shows both Scraper graduates and Telegram analysis
    if (targetCat === 'graduated') {
        return (tCat === 'graduated' || tCat === 'analyzing');
    }
    
    // Phase 68: 24H Gems — Trending tab only shows tokens < 24 hours old
    if (targetCat === 'trending' && tCat === 'trending') {
        const pairTs = token.pair_created_at;
        if (pairTs) {
            const ageH = (Date.now()/1000 - (pairTs > 1e12 ? pairTs/1000 : pairTs)) / 3600;
            if (ageH > 24) return false;
        }
    }

    // Gated Categories: Only show if liquidity is locked (OR is a Pump.fun token)
    const gatedCats = ['gems', 'established', 'legacy', 'trending'];
    if (gatedCats.includes(targetCat)) {
        const isLocked = !!token.liquidity_locked || (token.ca || '').toLowerCase().endsWith('pump');
        if (!isLocked) return false;
    }

    if (tCat === targetCat) return true;
    if (targetCat === 'analyzing' && (token.score === -1 || !token.current_category)) return true;
    return false;
}

function createTokenRow(token, showPerf, showDest, showSafe) {
    const isAnalyzing = token.score === -1 || token.score === undefined;
    const symbol = token.symbol || token.ca.substring(0, 4);
    const riskClass = getRiskClass(token.score);
    const scoreHtml = isAnalyzing ? '<span class="score-badge analyzing">...</span>' : `<span class="score-badge ${riskClass}">${token.score}</span>`;

    // PEAK X Calculation (Refined: Dashboard Release Baseline)
    let multiplierStr = '-';
    const gradMc = token.graduation_mc;
    if (gradMc > 0) {
        const peakX = token.peak_x || (token.highest_mc_post_grad / gradMc) || 1.0;
        const currentX = token.current_x || (token.mc / gradMc) || 1.0;
        
        if (currentX < 0.95) {
            // Negative Growth (Drawdown from release)
            const lossPct = Math.round((1 - currentX) * 100);
            multiplierStr = `<div style="display:flex; flex-direction:column; align-items:center;">
                                <span style="color:#ff4d4d; font-weight:800; font-size:0.85rem;">-${lossPct}%</span>
                                <small style="font-size:0.6rem; opacity:0.4;">DRAWDOWN</small>
                             </div>`;
        } else {
            // Positive Growth (Net Gain from release - User requested "1x extra" fix)
            const netX = Math.max(0, peakX - 1.0);
            const isHigh = netX >= 1.0; // 1x gain = 2x total
            multiplierStr = `<div style="display:flex; flex-direction:column; align-items:center;">
                                <span style="color:${isHigh ? 'var(--primary)' : 'var(--success)'}; font-weight:800; font-size:0.85rem; ${isHigh ? 'text-shadow: 0 0 10px var(--primary);' : ''}">${netX.toFixed(1)}x</span>
                                <small style="font-size:0.6rem; opacity:0.4;">NET GAIN</small>
                             </div>`;
        }
    }

    // 1H Growth Badge (compact, color-coded, in brackets)
    const g1h = token.mc_growth_1h || 0;
    const gColor = g1h > 0 ? 'var(--success)' : (g1h < 0 ? 'var(--danger)' : 'rgba(255,255,255,0.3)');
    const growthHtml = `<span style="font-family:monospace; font-size:0.65rem; font-weight:700; color:${gColor}; padding:2px 5px; border-radius:4px; background:rgba(0,0,0,0.25); white-space:nowrap;">[${g1h > 0 ? '+' : ''}${g1h.toFixed(1)}%] <span style="font-size:0.5rem; opacity:0.4; font-weight:800;">1H</span></span>`;

    // Premium Copy Icon (SVG)
    const copyIcon = `<svg class="copy-btn" onclick="copyToClipboard('${token.ca}', 'CA')" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>`;

    const imgUrl = token.image_url ? token.image_url : 'https://api.dicebear.com/7.x/identicon/svg?seed=' + token.ca;

    return `
        <div class="token-row" id="token-${token.ca}">
            <div class="token-id-cell" style="display: flex; align-items: center; gap: 10px; overflow:visible;">
                <div class="live-indicator"></div>
                <img src="${imgUrl}" style="width: 32px; height: 32px; border-radius: 50%; object-fit: cover; background: #1a1a1e; border: 1px solid rgba(255,255,255,0.1);" onerror="this.src='https://api.dicebear.com/7.x/identicon/svg?seed=${token.ca}'" />
                <div style="overflow:hidden;">
                    <div style="display:flex; align-items:center;">
                        <span style="font-weight: 700; color: #fff; cursor: pointer;" onclick="copyToClipboard('${token.ca}', 'CA')">${symbol}</span>
                        ${growthHtml}
                        ${(() => {
                            let badge = '';
                            const rep = token.reputation || 'neutral';
                            const success = token.creator_success_count || 0;
                            const total = token.creator_total_tokens || 0;
                            
                            if (rep === 'trusted') {
                                badge = `<span class="badge" title="Verified Success: This developer has ${success} successful (10x+) launches out of ${total} total tokens." style="background:linear-gradient(45deg, #00ffff, #0088ff); color:#000; font-size:0.6rem; font-weight:900; padding:1px 4px; border-radius:3px; margin-left:4px; cursor:help; box-shadow:0 0 10px rgba(0,255,255,0.4);">TRUSTED DEV</span>`;
                            } else if (rep === 'scammer') {
                                badge = `<span class="badge" title="High Risk: This developer has a history of rugged or failed tokens (${total-success} failures)." style="background:#ff4d4d; color:#fff; font-size:0.6rem; font-weight:900; padding:1px 4px; border-radius:3px; margin-left:4px; cursor:help;">SCAMMER</span>`;
                            } else {
                                // Neutral / New Developer
                                badge = `<span class="badge" title="Audit Pending: No historical data found for this wallet on Solana. Scraper Sync in progress." style="background:rgba(255,255,255,0.08); color:rgba(255,255,255,0.6); font-size:0.6rem; font-weight:800; padding:1px 4px; border:1px solid rgba(255,255,255,0.1); border-radius:3px; margin-left:4px; cursor:help;">NEW DEV</span>`;
                            }
                            
                            if (token.is_followed_by_user) {
                                badge += `<span title="Trusted Source: Part of your X following network" style="font-size:0.7rem; margin-left:4px; filter:drop-shadow(0 0 3px #1da1f2); cursor:help;">👤✅</span>`;
                            }
                            return badge;
                        })()}
                        ${(token.is_safe && showSafe) ? `<span title="Verified Safe: Passed all deep audit checks" style="cursor:help; font-size:0.85rem; filter:drop-shadow(0 0 4px rgba(0,255,136,0.5)); margin-left:4px;">🛡️</span>` : ''}
                        ${(() => {
                            if (!token.risk_flags) return '';
                            const reasons = [];
                            if (token.risk_flags.low_lp_providers) reasons.push("Low LP Density");
                            if (token.risk_flags.serial_rugger) reasons.push("Serial Rugger");
                            if (token.risk_flags.whale_concentration) reasons.push("Whale Heavy");
                            
                            if (reasons.length > 0 && !token.is_safe) {
                                return `<span title="Risk Detected: ${reasons.join(', ')}" class="risk-alert-icon" style="cursor:pointer; margin-left:4px;" onclick="event.stopPropagation(); showReport('${token.ca}')">⚠️</span>`;
                            }
                            return '';
                        })()}
                    </div>
                    <div class="ca-sub">${token.ca.substring(0,4)}...${token.ca.slice(-4)} ${copyIcon}</div>
                </div>
            </div>
            <div class="token-mc-cell" data-label="Market Cap" style="font-weight: 700; display:flex; flex-direction:column;">
                <span>$${formatNum(token.mc)}</span>
                <div style="display:flex; flex-direction:column; gap:1px; margin-top:2px;">
                    ${(() => {
                        const startVal = token.graduation_mc || token.initial_mc || 0;
                        const peakVal = token.highest_mc_post_grad || token.highest_mc_ever || 0;
                        const isSuccess = peakVal >= startVal;
                        const perfColor = isSuccess ? '#00a300' : '#cc0000';
                        const startColor = (token.mc >= startVal) ? '#00a300' : '#cc0000';
                        
                        return `
                            <small style="font-size:0.6rem; opacity:0.8; font-weight:800; color:var(--primary); line-height:1.1; white-space:nowrap;">START: $${formatNum(startVal)}</small>
                            <small style="font-size:0.6rem; opacity:0.8; font-weight:800; color:${perfColor}; line-height:1.1; white-space:nowrap;">PEAK: $${formatNum(peakVal)}</small>
                        `;
                    })()}
                </div>
            </div>
            ${showPerf ? `<div class="token-perf-cell" data-label="Performance" style="color:var(--primary); font-weight:700;">${multiplierStr}</div>` : ''}
            <div class="token-holders-cell" data-label="Holders" style="font-weight:700; color:${token.holders_count > 100 ? 'var(--success)' : '#fff'};">
                ${formatNum(token.holders_count)}
                ${token.holders_count === 0 ? '<span style="color:var(--danger); font-size:0.6rem; display:block;">SYNCING...</span>' : ''}
            </div>
            <div class="token-liq-cell" data-label="Liquidity" style="opacity: 0.6;">$${formatNum(token.liquidity)}</div>
            <div class="token-links-cell" data-label="Links" style="display: flex; gap: 8px; align-items:center;">
                ${token.x_link ? `<a href="${token.x_link}" target="_blank" style="color:#fff; opacity:0.8; line-height:0;"><svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg></a>` : ''}
                ${token.tg_link ? `<a href="${token.tg_link}" target="_blank" style="text-decoration:none;">✈️</a>` : ''}
                <a href="https://dexscreener.com/solana/${token.ca}" target="_blank" style="text-decoration:none;">📊</a>
            </div>
            <div class="token-score-cell" data-label="Risk Score">${scoreHtml}</div>
            <div class="token-age-cell" data-label="Age" style="opacity: 0.5; font-size: 0.7rem;">${formatAge(token.pair_created_at)}</div>
            <div class="token-report-cell" style="text-align: center;">
                <button onclick="showReport('${token.ca}')" style="background:none; border:none; color:var(--primary); cursor:pointer; padding:6px; opacity:0.6; transition:opacity 0.2s;">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
                </button>
            </div>
        </div>
    `;
}

function getDestinationBadge(token) {
    const cat = (token.current_category || '').toUpperCase();
    if (token.is_rugged) return '<span class="badge scam">RUG</span>';
    if (token.is_scam || token.score < 30) return '<span class="badge scam">SCAM</span>';
    if (cat === 'SCAM_TRENDING') return '<span class="badge" style="background:linear-gradient(45deg, #ff00ff, #00ffff); color:#000; font-weight:800; animation: pulse 2s infinite;">RECOVERY</span>';
    if (cat === 'GEMS') return '<span class="badge gem">GEM</span>';
    return `<span class="badge" style="background:rgba(255,255,255,0.05); color:#888;">${cat}</span>`;
}

function formatAge(ts) {
    if (!ts) return 'n/a';
    const now = Date.now() / 1000;
    const diff = now - (ts > 1e12 ? ts / 1000 : ts);
    if (diff < 3600) return `${Math.floor(diff / 60)}m`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
    return `${Math.floor(diff / 86400)}d`;
}

function getRiskClass(score) {
    if (!score || score === -1) return '';
    if (score > 80) return 'risk-success';
    if (score > 60) return 'risk-warning';
    return 'risk-danger';
}

window.copyToClipboard = function(text, label) {
    const performCopy = (txt) => {
        const toast = document.getElementById('toast');
        if (toast) {
            toast.textContent = `Copied ${label}!`;
            toast.style.transform = "translateY(0)";
            setTimeout(() => toast.style.transform = "translateY(100px)", 1500);
        }
    };

    if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(text).then(() => performCopy(text)).catch(err => {
            console.error('Clipboard API failed', err);
            legacyCopy(text, label);
        });
    } else {
        legacyCopy(text, label);
    }

    function legacyCopy(txt, lbl) {
        try {
            const textArea = document.createElement("textarea");
            textArea.value = txt;
            textArea.style.position = "fixed";
            textArea.style.left = "-999999px";
            textArea.style.top = "-999999px";
            document.body.appendChild(textArea);
            textArea.focus();
            textArea.select();
            const successful = document.execCommand('copy');
            document.body.removeChild(textArea);
            if (successful) performCopy(txt);
        } catch (err) {
            console.error('Fallback copy failed', err);
        }
    }
};

document.getElementById('global-search').addEventListener('input', (e) => {
    searchFilter = e.target.value.trim();
    renderTokens();
});

window.showReport = function(ca) {
    const token = allTokens.find(t => t.ca === ca);
    if (!token) return;

    const riskFlags = token.risk_flags || {};
    const sec = token.security_details || {};
    const riskReasons = [];
    if (riskFlags.low_lp_providers) riskReasons.push("Low Liquidity Provider Density");
    if (riskFlags.serial_rugger) riskReasons.push("Creator Rug History Found");
    if (riskFlags.whale_concentration) riskReasons.push("High Whale Concentration");
    if (riskFlags.low_liquidity) riskReasons.push("Low Market Liquidity");

    let breakdown = token.breakdown || [];
    if (typeof breakdown === 'string') { try { breakdown = JSON.parse(breakdown); } catch(e) { breakdown = []; } }

    const breakdownHtml = breakdown.map(r => `
        <div style="display:flex;justify-content:space-between;font-size:0.75rem;margin-bottom:4px;padding:4px 0;border-bottom:1px solid rgba(255,255,255,0.03);">
            <span>${r.split(':').slice(1).join(':') || r}</span>
            <span style="font-weight:bold;color:${r.startsWith('-') ? 'var(--danger)' : 'var(--success)'}">${r.split(':')[0]}</span>
        </div>
    `).join('') || '<div style="opacity:0.5;font-size:0.75rem;">No performance logs found for this cycle.</div>';

    const renderCheck = (val, label) => `
        <div style="display:flex; justify-content:space-between; padding:6px 0; border-bottom:1px solid rgba(255,255,255,0.05);">
            <span style="opacity:0.6; font-size:0.75rem;">${label}</span>
            <span style="font-weight:700; color:${val ? 'var(--danger)' : 'var(--success)'}; font-size:0.75rem;">
                ${val ? 'YES 🚩' : 'PASS ✅'}
            </span>
        </div>
    `;

    const renderValue = (val, label, color = '#fff') => `
        <div style="display:flex; justify-content:space-between; padding:6px 0; border-bottom:1px solid rgba(255,255,255,0.05);">
            <span style="opacity:0.6; font-size:0.75rem;">${label}</span>
            <span style="font-weight:700; color:${color}; font-size:0.75rem;">${val}</span>
        </div>
    `;

    const modalHtml = `
        <div id="report-modal" style="position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.9);display:flex;justify-content:center;align-items:center;z-index:99999999;backdrop-filter:blur(10px);">
            <div style="background:#0a0a0f; border:1px solid #333; padding:0; border-radius:16px; max-width:650px; width:95%; position:relative; overflow-y:auto; max-height:90vh; box-shadow: 0 20px 60px rgba(0,0,0,0.8); border-top: 4px solid ${token.is_safe ? 'var(--success)' : (riskReasons.length > 0 ? 'var(--danger)' : 'var(--primary)')}">
                <button onclick="document.getElementById('report-modal').remove()" style="position:absolute; right:1.5rem; top:1.5rem; background:none; border:none; color:#fff; cursor:pointer; font-size:1.5rem; opacity:0.5; z-index:10;">&times;</button>
                
                <div style="padding: 1.5rem;">
                    <div style="display:flex; align-items:center; gap:12px; margin-bottom:1rem; border-bottom:1px solid rgba(255,255,255,0.1); padding-bottom:1rem;">
                        <img src="${token.image_url || 'https://api.dicebear.com/7.x/identicon/svg?seed=' + token.ca}" style="width:54px; height:54px; border-radius:14px; border:1px solid var(--glass-border); background:#1a1a1e;" />
                        <div>
                            <h2 style="margin:0; font-family:var(--font-accent); font-size:1.5rem; color:#fff;">${token.symbol} Analysis</h2>
                            <div style="font-size:0.75rem; opacity:0.4; font-family:monospace; margin-top:4px;">${token.ca}</div>
                        </div>
                        ${token.is_safe ? `<div class="safe-badge" style="margin-left:auto; font-size:0.8rem; padding:6px 14px;">🛡️ SAFE</div>` : ''}
                    </div>

                    <!-- Top KPI Row -->
                    <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-bottom:1.5rem;">
                        <div style="background:rgba(255,255,255,0.03); padding:15px; border-radius:12px; text-align:center; border:1px solid rgba(255,255,255,0.05);">
                            <small style="opacity:0.4; text-transform:uppercase; font-size:0.6rem; letter-spacing:1px; display:block; margin-bottom:5px;">Price 1H</small>
                            <div style="font-size:1.6rem; font-weight:700; color:var(--primary);">${(token.mc_growth_1h||0).toFixed(2)}%</div>
                        </div>
                        <div style="background:rgba(255,255,255,0.03); padding:15px; border-radius:12px; text-align:center; border:1px solid rgba(255,255,255,0.05);">
                            <small style="opacity:0.4; text-transform:uppercase; font-size:0.6rem; letter-spacing:1px; display:block; margin-bottom:5px;">Holder Momentum</small>
                            <div style="font-size:1.6rem; font-weight:700; color:var(--success);">${(token.holder_growth_1h||0).toFixed(2)}%</div>
                        </div>
                    </div>

                    <div style="display:grid; grid-template-columns:1fr 1fr; gap:1.5rem; margin-bottom:1.5rem;">
                        <!-- Column 1: Core Performance Logs -->
                        <div>
                            <h3 style="font-size:0.75rem; text-transform:uppercase; letter-spacing:1px; margin-bottom:0.8rem; color:#888;">Core Audit Logs</h3>
                            <div style="background:rgba(0,0,0,0.2); padding:0.8rem; border-radius:8px; border:1px solid rgba(255,255,255,0.05);">
                                ${breakdownHtml}
                            </div>
                        </div>

                        <!-- Column 2: Peak Performance Details -->
                        <div>
                            <h3 style="font-size:0.75rem; text-transform:uppercase; letter-spacing:1px; margin-bottom:0.8rem; color:#888;">Live Performance</h3>
                            <div style="background:rgba(255,255,255,0.03); padding:1rem; border-radius:12px; border:1px solid rgba(0, 242, 255, 0.1); position:relative; overflow:hidden;">
                                <div style="position:absolute; top:0; right:0; padding:4px 8px; background:rgba(0, 242, 255, 0.1); color:var(--primary); font-size:0.6rem; font-weight:800; border-bottom-left-radius:8px;">REAL-TIME</div>
                                ${renderValue('$' + formatNum(token.graduation_mc || token.initial_mc || token.mc), "Release MC", "var(--primary)")}
                                ${renderValue('$' + formatNum(token.highest_mc_post_grad || token.highest_mc_ever || token.mc), "Highest Reach", "var(--success)")}
                                <div style="display:flex; justify-content:space-between; padding:12px 0 6px 0; align-items:center;">
                                    <span style="opacity:0.6; font-size:0.75rem;">Net Performance</span>
                                    <span style="font-weight:800; color:var(--success); font-size:1.4rem; text-shadow: 0 0 10px rgba(0,255,136,0.3);">
                                        ${Math.max(0, (token.peak_x || 1.0) - 1.0).toFixed(2)}x
                                    </span>
                                </div>
                                ${renderValue('$' + formatNum(token.mc), "Current MC", "#fff")}
                            </div>
                        </div>
                    </div>

                    <div style="display:grid; grid-template-columns:1fr 1fr; gap:1.5rem; margin-bottom:1.5rem;">
                        <!-- Column 3: Deep Security Signals -->
                        <div>
                            <h3 style="font-size:0.75rem; text-transform:uppercase; letter-spacing:1px; margin-bottom:0.8rem; color:#888;">Contract Security</h3>
                            ${renderCheck(sec.is_honeypot, "Honeypot")}
                            ${renderCheck(sec.is_mintable, "Minting")}
                            ${renderCheck(sec.is_proxy, "Proxy")}
                            ${renderValue((sec.buy_tax || '0') + '%', "Buy Tax")}
                            ${renderValue((sec.sell_tax || '0') + '%', "Sell Tax")}
                        </div>
                        
                        <!-- Column 4: Social & Creator Reputation -->
                        <div>
                             <h3 style="font-size:0.75rem; text-transform:uppercase; letter-spacing:1px; margin-bottom:0.8rem; color:#888;">Social & Creator Reputation</h3>
                             ${renderValue(token.social_meta?.followers || '0', "X Followers")}
                             ${renderValue(token.social_meta?.is_verified ? 'YES' : 'No', "X Verified", token.social_meta?.is_verified ? 'var(--primary)' : '#fff')}
                             
                             <div style="margin-top:10px; padding-top:10px; border-top:1px solid rgba(255,255,255,0.05);">
                                 ${renderValue(token.reputation.toUpperCase(), "Reputation", token.reputation === 'trusted' ? 'var(--primary)' : (token.reputation === 'scammer' ? 'var(--danger)' : '#fff'))}
                                 ${renderValue(token.creator_success_count + ' / ' + token.creator_total_tokens, "Past 10x Successes")}
                             </div>
                        </div>
                    </div>

                    <!-- Risk Heuristics Summary -->
                    <div style="background:rgba(255,255,255,0.02); border-radius:12px; padding:1.2rem; border:1px solid ${riskReasons.length > 0 ? 'rgba(255, 77, 77, 0.2)' : 'rgba(0, 242, 255, 0.1)'}">
                        <div style="font-weight:800; font-size:0.7rem; margin-bottom:10px; text-transform:uppercase; letter-spacing:1px; opacity:0.5;">Proprietary Risk Signals</div>
                        <div style="display:flex; flex-direction:column; gap:8px;">
                            ${riskReasons.length > 0 ? 
                                riskReasons.map(r => `<div style="font-size:0.8rem; color:var(--danger); display:flex; align-items:center; gap:8px;">🚩 ${r}</div>`).join('') : 
                                `<div style="font-size:0.8rem; color:var(--success); display:flex; align-items:center; gap:8px;">🛡️ All risk heuristics passed.</div>`
                            }
                        </div>
                    </div>

                    <div style="margin-top:1.5rem; text-align:center; font-size:0.65rem; opacity:0.3;">
                        System Update: ${new Date().toLocaleTimeString()} | MeMeIt Intelligence Terminal
                    </div>
                </div>
                
                <button onclick="copyToClipboard('${token.ca}', 'CA')" style="width:100%; padding:1.2rem; background:var(--primary); color:#000; border:none; font-weight:800; cursor:pointer; letter-spacing:1px; font-size:0.9rem; text-transform:uppercase;">
                    Copy Contract Address
                </button>
            </div>
        </div>
    `;
    const existing = document.getElementById('report-modal');
    if (existing) existing.remove();
    document.body.insertAdjacentHTML('beforeend', modalHtml);
};

function getRiskColor(score) {
    if (!score || score === -1) return '#666';
    if (score > 80) return '#00ff88';
    if (score > 60) return '#ffcc00';
    return '#ff4d4d';
}

loadTokens();
setupSSE();
