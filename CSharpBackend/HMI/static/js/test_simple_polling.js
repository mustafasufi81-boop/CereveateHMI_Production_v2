// 🧪 MINIMAL TEST SCRIPT - NO DEPENDENCIES
// This script ONLY tests OPC API polling - nothing else

console.log('🧪 TEST SCRIPT LOADED');

let testPollCount = 0;

async function testPollOPC() {
    testPollCount++;
    const timestamp = new Date().toLocaleTimeString();
    
    console.log(`\n[${ timestamp}] 🔄 TEST POLL #${testPollCount}`);
    
    try {
        const response = await fetch('http://localhost:5001/api/opc/values');
        
        if (!response.ok) {
            console.error(`❌ HTTP ${response.status}: ${response.statusText}`);
            return;
        }
        
        const data = await response.json();
        console.log(`✅ SUCCESS: Received ${data.tags.length} tags`);
        
        // Show first 3 tags
        data.tags.slice(0, 3).forEach(tag => {
            console.log(`   📊 ${tag.tagId}: ${tag.value} (${tag.quality})`);
        });
        
    } catch (error) {
        console.error(`❌ FETCH ERROR:`, error);
    }
}

// Start immediately when script loads
console.log('🚀 Starting test polling in 1 second...');
setTimeout(() => {
    testPollOPC();
    setInterval(testPollOPC, 2000); // Poll every 2 seconds
}, 1000);
