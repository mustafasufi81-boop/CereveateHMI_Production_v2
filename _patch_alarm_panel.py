path = r'd:\CereveateHMI_Production\HMI\apex-hmi\src\components\hmi\AlarmPanel.tsx'
with open(path, 'r', encoding='utf-8') as f:
    c = f.read()

# ── diagnostics first ─────────────────────────────────────────────────────
print('tagQuality state:', 'tagQuality' in c)
print('tagStale state:', 'tagStale' in c)
print('qualityMap in fetch:', 'qualityMap' in c)
print('setTagQuality called:', 'setTagQuality(' in c)
print('setTagStale called:', 'setTagStale(' in c)
print('setTagTimestamps called:', 'setTagTimestamps(' in c)
print('staleMap in code:', 'staleMap' in c)
print('tsMap in code:', 'tsMap' in c)
