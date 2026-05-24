#!/usr/bin/env python3
"""
LOCAL TCP Client - Receives PLC data from local network server

NO CLOUD! NO INTERNET! ALL DATA STAYS ON YOUR NETWORK!

Usage:
    python local_tcp_client.py [server_ip] [port]
    
Examples:
    python local_tcp_client.py                    # Connect to localhost:5050
    python local_tcp_client.py 192.168.1.100      # Connect to specific IP
    python local_tcp_client.py 192.168.1.100 5050 # Specify IP and port
"""

import socket
import json
import sys
from datetime import datetime

# Default configuration
DEFAULT_HOST = "localhost"  # Change to your server IP
DEFAULT_PORT = 5050

def format_value(value):
    """Format value for display"""
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)

def main():
    # Parse command line args
    host = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_HOST
    port = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_PORT
    
    print("\n" + "=" * 70)
    print("    LOCAL PLC DATA CLIENT")
    print("    🔒 Data stays on your local network - NO CLOUD!")
    print("=" * 70)
    print(f"\nConnecting to {host}:{port}...")
    
    # Create socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)
    
    try:
        sock.connect((host, port))
        print(f"✅ Connected to {host}:{port}")
        print("\n" + "-" * 70)
        print("Receiving PLC data... (Ctrl+C to stop)")
        print("-" * 70 + "\n")
        
        buffer = ""
        message_count = 0
        
        while True:
            try:
                # Receive data
                data = sock.recv(65536).decode('utf-8')
                if not data:
                    print("\n❌ Server closed connection")
                    break
                
                buffer += data
                
                # Process complete JSON messages (newline-delimited)
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    if not line.strip():
                        continue
                    
                    try:
                        msg = json.loads(line)
                        message_count += 1
                        
                        msg_type = msg.get('type', 'unknown')
                        timestamp = msg.get('timestamp', '')
                        
                        if msg_type == 'welcome':
                            print(f"📡 {msg.get('message', 'Connected')}")
                            print(f"   Server: {msg.get('server', 'unknown')}")
                            print(f"   Update interval: {msg.get('intervalMs', 1000)}ms")
                            print()
                            
                        elif msg_type == 'plc_data':
                            values = msg.get('values', [])
                            count = msg.get('count', 0)
                            
                            # Clear screen and show header
                            print(f"\r[{datetime.now().strftime('%H:%M:%S')}] Message #{message_count} - {count} tags")
                            print("-" * 70)
                            
                            # Group by PLC
                            plcs = {}
                            for v in values:
                                plc_id = v.get('plcId', 'Unknown')
                                if plc_id not in plcs:
                                    plcs[plc_id] = []
                                plcs[plc_id].append(v)
                            
                            # Display values
                            for plc_id, tags in plcs.items():
                                print(f"\n📟 PLC: {plc_id}")
                                for tag in tags[:15]:  # Limit display
                                    name = tag.get('tag', tag.get('tagName', 'N/A'))
                                    value = format_value(tag.get('value', 'N/A'))
                                    quality = tag.get('quality', 'Good')
                                    data_type = tag.get('dataType', '')
                                    
                                    quality_icon = "✓" if quality == "Good" else "⚠"
                                    print(f"   {quality_icon} {name:30} = {value:>12} ({data_type})")
                                
                                if len(tags) > 15:
                                    print(f"   ... and {len(tags) - 15} more tags")
                            
                            print()
                            
                    except json.JSONDecodeError as e:
                        print(f"⚠️ Invalid JSON: {e}")
                        
            except socket.timeout:
                print(".", end="", flush=True)
                continue
                
    except ConnectionRefusedError:
        print(f"\n❌ Connection refused - is the server running at {host}:{port}?")
        print("\nMake sure the C# application is running with LocalBroadcast enabled.")
        
    except KeyboardInterrupt:
        print("\n\n👋 Stopped by user")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        
    finally:
        sock.close()
        print(f"\nTotal messages received: {message_count}")

if __name__ == "__main__":
    main()
