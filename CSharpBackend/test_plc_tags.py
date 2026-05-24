#!/usr/bin/env python3
"""
Quick test script to check if PLC tags are accessible from dashboard APIs
"""
import requests
import json
import time

def test_endpoints():
    """Test various endpoints to see if PLC tags are accessible"""
    
    endpoints = [
        "http://localhost:5003/api/tags/latest",
        "http://localhost:5002/api/mqtt/data", 
        "http://localhost:5002/api/api/data",
        "http://localhost:5001/api/plc/health",
        "http://localhost:5000/api/tags/latest"
    ]
    
    print("Testing PLC Tag Endpoints...")
    print("=" * 50)
    
    for url in endpoints:
        try:
            print(f"\nTesting: {url}")
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                print(f"✅ SUCCESS - Status: {response.status_code}")
                
                # Look for PLC tags specifically
                if isinstance(data, dict):
                    for key, value in data.items():
                        if "Blastfurnace" in str(key) or "plc" in str(key).lower():
                            print(f"   🔥 PLC TAG FOUND: {key} = {value}")
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            for k, v in item.items():
                                if "Blastfurnace" in str(k) or "plc" in str(k).lower():
                                    print(f"   🔥 PLC TAG FOUND: {k} = {v}")
                
                # Show first few items
                if isinstance(data, dict) and len(data) > 0:
                    print(f"   Sample data: {dict(list(data.items())[:3])}")
                elif isinstance(data, list) and len(data) > 0:
                    print(f"   Sample data: {data[:2]}")
                    
            else:
                print(f"❌ FAILED - Status: {response.status_code}")
                print(f"   Error: {response.text[:100]}")
                
        except requests.exceptions.ConnectionError:
            print(f"❌ CONNECTION REFUSED - Service not running on this port")
        except requests.exceptions.Timeout:
            print(f"❌ TIMEOUT - Service too slow to respond")
        except Exception as e:
            print(f"❌ ERROR: {str(e)}")

def test_specific_plc_tags():
    """Test specific PLC tag endpoints"""
    print("\n" + "=" * 50)
    print("Testing Specific PLC Tags...")
    
    plc_tags = [
        "Blastfurnace_Tuyer1_Pressure",
        "plc/Blastfurnace_Tuyer1_Pressure",
        "Random.Real4"
    ]
    
    base_urls = [
        "http://localhost:5002/api/mqtt/history/",
        "http://localhost:5002/api/api/history/",
        "http://localhost:5003/api/tags/"
    ]
    
    for base_url in base_urls:
        for tag in plc_tags:
            try:
                url = f"{base_url}{tag}"
                print(f"\nTesting: {url}")
                response = requests.get(url, timeout=5)
                
                if response.status_code == 200:
                    data = response.json()
                    print(f"✅ SUCCESS - Got data for {tag}")
                    if isinstance(data, list) and len(data) > 0:
                        print(f"   Latest value: {data[-1] if data else 'No data'}")
                else:
                    print(f"❌ FAILED - Status: {response.status_code}")
                    
            except requests.exceptions.ConnectionError:
                print(f"❌ CONNECTION REFUSED")
            except Exception as e:
                print(f"❌ ERROR: {str(e)}")

if __name__ == "__main__":
    print("PLC TAG ACCESSIBILITY TEST")
    print("=" * 50)
    
    test_endpoints()
    test_specific_plc_tags()
    
    print("\n" + "=" * 50)
    print("Test completed!")