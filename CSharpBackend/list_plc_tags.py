#!/usr/bin/env python3
"""Quick script to list all tags from PLC"""
from pycomm3 import LogixDriver

try:
    print("Connecting to PLC 192.168.0.20...")
    plc = LogixDriver('192.168.0.20/1,0')
    plc.open()
    
    print("\n=== AVAILABLE PLC TAGS ===\n")
    tags = plc.get_tag_list()
    
    print(f"Type of tags: {type(tags)}")
    print(f"First item: {tags[0] if tags else 'empty'}")
    
    if isinstance(tags, list):
        for i, tag in enumerate(tags, 1):
            if hasattr(tag, 'tag_name'):
                print(f"{i:3d}. {tag.tag_name:40s} ({tag.data_type})")
            elif isinstance(tag, dict):
                print(f"{i:3d}. {tag}")
            else:
                print(f"{i:3d}. {str(tag)}")
    elif isinstance(tags, dict):
        for i, (tag_name, tag_info) in enumerate(tags.items(), 1):
            print(f"{i:3d}. {tag_name}")
    
    print(f"\n=== TOTAL: {len(tags)} tags ===")
    
    plc.close()
    
except Exception as e:
    print(f"ERROR: {e}")
