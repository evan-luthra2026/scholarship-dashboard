#!/usr/bin/env python3
"""Enrich scholarship entries by reading emails via himalaya."""
import json, re, subprocess, sys, time

# Read HTML
with open('/tmp/scholarship-repo/index.html', 'r') as f:
    content = f.read()

match = re.search(r'const RAW_DATA = (\[.*?\]);', content, re.DOTALL)
data = json.loads(match.group(1))

# Build lookup by id
lookup = {e['id']: e for e in data}

# Find incomplete
incomplete_ids = [e['id'] for e in data if len(e.get('useCase', '').strip()) < 5]
print(f"Total entries: {len(data)}, Incomplete: {len(incomplete_ids)}")

def parse_email(email_id):
    """Read an email and extract fields."""
    try:
        result = subprocess.run(
            ['himalaya', 'message', 'read', '-a', 'evan', '-f', '[Gmail]/All Mail', str(email_id)],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            return None
        
        body = result.stdout
        if not body or len(body) < 20:
            return None
        
        # Format: "field: \n value  nextfield:"
        # Extract between field labels
        fields = {}
        
        # email
        m = re.search(r'email:\s*\n\s*(.+?)(?:\s{2,}|\n)', body, re.IGNORECASE)
        if m: fields['email'] = m.group(1).strip()
        
        # country
        m = re.search(r'country:\s*\n\s*(.+?)(?:\s{2,}|\n)', body, re.IGNORECASE)
        if m: fields['country'] = m.group(1).strip()
        
        # role
        m = re.search(r'role:\s*\n\s*(.+?)(?:\s{2,}|\n)', body, re.IGNORECASE)
        if m: fields['role'] = m.group(1).strip()
        
        # useCase - can be long, grab until whySelected or social
        m = re.search(r'useCase:\s*\n\s*(.+?)(?:\s{2,}whySelected:|\s{2,}social:)', body, re.IGNORECASE | re.DOTALL)
        if m: 
            uc = m.group(1).strip()
            uc = re.sub(r'\s+', ' ', uc)
            fields['useCase'] = uc[:500]
        
        # whySelected
        m = re.search(r'whySelected:\s*\n\s*(.+?)(?:\s{2,}social:)', body, re.IGNORECASE | re.DOTALL)
        if m:
            ws = m.group(1).strip()
            ws = re.sub(r'\s+', ' ', ws)
            fields['whySelected'] = ws[:500]
        
        # social
        m = re.search(r'social:\s*\n\s*(.+?)(?:\s{2,}|\n\n|Submitted at)', body, re.IGNORECASE | re.DOTALL)
        if m:
            s = m.group(1).strip()
            s = re.sub(r'\s+', ' ', s)
            if len(s) > 2 and s != '@':
                fields['social'] = s
        
        return fields
        
    except subprocess.TimeoutExpired:
        return None
    except Exception as e:
        print(f"  EXCEPTION for {email_id}: {e}")
        return None

# Process in batches of 5
enriched_count = 0
failed_count = 0
batch_size = 5

for i in range(0, len(incomplete_ids), batch_size):
    batch = incomplete_ids[i:i+batch_size]
    batch_num = i // batch_size + 1
    total_batches = (len(incomplete_ids) + batch_size - 1) // batch_size
    print(f"\n--- Batch {batch_num}/{total_batches} ---")
    
    for eid in batch:
        sys.stdout.write(f"  {eid}...")
        sys.stdout.flush()
        result = parse_email(eid)
        
        if result and any(result.get(f) for f in ['email', 'country', 'role', 'useCase']):
            entry = lookup[eid]
            
            for field in ['email', 'country', 'role', 'useCase', 'whySelected', 'social']:
                val = result.get(field, '')
                if val and len(val) > 1:
                    if field == 'social' and val:
                        # Also set socialLink if it looks like a URL
                        if 'http' in val or 'x.com' in val or 'linkedin' in val or 'twitter' in val:
                            entry['socialLink'] = val if val.startswith('http') else 'https://' + val
                    entry[field] = val
            
            enriched_count += 1
            uc_preview = result.get('useCase', '')[:40]
            print(f" ✅ {result.get('country','')} | {result.get('role','')[:20]} | {uc_preview}...")
        else:
            failed_count += 1
            print(f" ❌")
    
    # Small delay between batches
    if i + batch_size < len(incomplete_ids):
        time.sleep(0.5)

print(f"\n=== SUMMARY ===")
print(f"Total incomplete: {len(incomplete_ids)}")
print(f"Enriched: {enriched_count}")
print(f"Failed/skipped: {failed_count}")

# Write updated data back
data_ordered = [lookup[e['id']] for e in data if e['id'] in lookup]

# 1. Save JSON
with open('/Users/evanai/.openclaw/workspace/scholarship_data.json', 'w') as f:
    json.dump(data_ordered, f, indent=2, ensure_ascii=False)
print("Saved scholarship_data.json")

# 2. Update HTML
json_str = json.dumps(data_ordered, ensure_ascii=False)
new_line = f'const RAW_DATA = {json_str};'
new_content = re.sub(r'const RAW_DATA = \[.*?\];', new_line, content, flags=re.DOTALL)
with open('/tmp/scholarship-repo/index.html', 'w') as f:
    f.write(new_content)
print("Updated index.html")
