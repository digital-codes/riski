#!/usr/bin/env python3
import json

with open('votes_test.json') as f:
    data = json.load(f)

print('Parties and member counts:')
for party in data['parties']:
    print(f"  {party['name']}: {len(party['members'])} members")
    for m in party['members']:
        print(f"    - {m['name']}: {m['vote']}")
