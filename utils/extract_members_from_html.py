#!/usr/bin/env python3
"""Extract member data from HTML file"""

import re
import json
from pathlib import Path

def parse_members_html(html_file):
    """Parse the HTML file and extract member data"""
    
    with open(html_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Pattern to match each table row
    # <tr>...<p><a href="people-XXX">Name</a></p>...</td><td>PARTY, Function<br>Role</td>...</tr>
    # Party can be multi-word like "Die Linke", "Die PARTEI", "FDP/FW"
    # Comma after party is optional (e.g., "FDP/FW Stadträtin")
    pattern = r'<tr>\s*<td>\s*<p><a href="people-\d+"[^>]*>([^<]+)</a></p>\s*</td>\s*<td>\s*(.+?)<br>([^<]+?)\s*</td>'
    
    members = []
    matches = re.finditer(pattern, content, re.MULTILINE | re.DOTALL)
    
    for match in matches:
        name = match.group(1).strip()
        party = match.group(2).strip()
        function = match.group(3).strip()
        role = match.group(4).strip()
        
        members.append({
            'name': name,
            'party': party,
            'function': function,
            'role': role
        })
    
    return members

if __name__ == '__main__':
    html_file = Path('abstimmung-members.html')
    members = parse_members_html(html_file)
    
    # Save to JSON
    output_file = Path('members_data.json')
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(members, f, indent=2, ensure_ascii=False)
    
    print(f"Extracted {len(members)} members")
    print(f"Saved to {output_file}")
    
    # Show sample
    print("\nSample entries:")
    for i, member in enumerate(members[:5]):
        print(f"{i+1}. {member['name']} - {member['party']} - {member['function']}")
