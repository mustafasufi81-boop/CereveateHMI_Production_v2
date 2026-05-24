# Cereveate Historian Query Tool - Quick Reference

## ✅ ALL FIXES APPLIED

### Fixed Issues:
1. ✅ **Records/Second** displaying correctly (was "--")
2. ✅ **Tag dropdown** loads all 84 tags
3. ✅ **Execute Query** button working
4. ✅ **Connection pooling** prevents failures
5. ✅ **Value formatting** shows 3 decimal places
6. ✅ **Error handling** with user feedback

## 🚀 Quick Start

```bash
python historian_query_tool_v2.py
```

Open: **http://localhost:7005**

## 📊 Current Database Stats

- Records: **6,931,172**
- Tags: **84 active**
- Size: **1242 MB**
- Rate: **27.30 records/second**

## 🎯 How to Use Query Tab

1. Select tags (Ctrl+Click for multiple)
2. Set time range (optional)
3. Set limit (1-100,000)
4. Click "Execute Query"
5. Export as CSV if needed

## 🔍 Testing

```powershell
# Test health
curl http://localhost:7005/api/health

# Test tags
curl http://localhost:7005/api/tags/list

# Test query
curl "http://localhost:7005/api/data/query?tag_id[]=Power&limit=10"
```

## ⚙️ Technical Details

- **Connection Pool**: 1-10 connections
- **Query Timeout**: 30 seconds
- **Auto-refresh**: Every 2 seconds
- **Max Query Limit**: 100,000 records

## 🟢 Status: PRODUCTION READY
