// DIAGNOSTIC SCRIPT - Checks what scripts are loading
console.log('✅ check_load.js loaded successfully');
console.log('Chart.js available:', typeof Chart !== 'undefined');
console.log('io (Socket.IO) available:', typeof io !== 'undefined');
console.log('TrendEngine available:', typeof TrendEngine !== 'undefined');

// Check if dashboard.js functions exist
setTimeout(() => {
    console.log('=== DIAGNOSTIC CHECK ===');
    console.log('state object exists:', typeof state !== 'undefined');
    console.log('startTagPolling exists:', typeof startTagPolling !== 'undefined');
    console.log('DOM elements:');
    console.log('  - main-chart:', document.getElementById('main-chart') !== null);
    console.log('  - live-values-body:', document.getElementById('live-values-body') !== null);
    console.log('  - btn-live:', document.getElementById('btn-live') !== null);
}, 100);
