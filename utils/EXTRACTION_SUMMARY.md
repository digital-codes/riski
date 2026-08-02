# Vote Extraction System - Final Summary

## Overview
Python script that extracts voting results from city council meeting images using OpenCV and Tesseract OCR.

## Key Features
- **Donut Chart OCR**: Reads vote totals (JA/NEIN/ENTHALTUNG) from donut charts
- **Member Detection**: Identifies colored member boxes (yellow=JA, red=NEIN, blue=ENTHALTUNG, gray=absent)
- **Name Matching**: Fuzzy matching of OCR-extracted names against HTML member list
- **Absent Member Detection**: Automatically identifies and adds members who were absent (gray boxes)

## Recent Fixes

### 1. Aspect Ratio Filter (Line 421)
**Problem**: Member boxes have aspect ratio ~2.43-2.46, but filter was rejecting boxes > 2.0
**Fix**: Relaxed threshold from 2.0 to 3.0

### 2. Gray Box Detection (Lines 395-448)
**Problem**: Gray boxes (absent members) blend with background, causing HSV color mask to fail
**Fix**: Switched from HSV color detection to edge detection (Canny) to find box boundaries

### 3. Member Assignment Logic (Lines 713-867)
**Problem**: Empty OCR results from gray boxes couldn't be matched to known members
**Fix**: Added logic to:
- Track which known members have been matched
- Identify unmatched members from HTML mapping
- Fill in missing members based on expected party counts
- Mark absent members with vote='GRAY'

## Verification Results

```
✓ Vote totals correct: JA=44, NEIN=4, ENTHALTUNG=0
✓ AfD has 5 members
✓ Total members detected: 49 (48 votes + 1 absent)
✓ All parties have valid bboxes
```

## Usage

```bash
python3 extract_votes.py abstimmung.png \
  --member-party-mapping party_member_mapping.json \
  --output votes.json \
  --visualize
```

## Output Structure

```json
{
  "ob_vote": {
    "name": "Dr. Mentrup",
    "vote": "JA",
    "bbox": [1367, 444, 269, 125]
  },
  "totals": {
    "ja": 44,
    "nein": 4,
    "enthaltung": 0
  },
  "parties": [
    {
      "name": "AfD",
      "bbox": [1507, 686, 245, 526],
      "members": [
        {"name": "Dr. Paul Schmidt", "vote": "NEIN", ...},
        {"name": "Oliver Schnell", "vote": "GRAY", ...},
        ...
      ]
    }
  ]
}
```

## Known Limitations

1. **OCR Accuracy**: Some names may have OCR errors (e.g., "No&" instead of "Noé")
2. **Absent Member Assignment**: Uses party member count heuristic, not spatial position
3. **Gray Box Detection**: Relies on edge detection, may miss boxes with weak edges

## Future Improvements

1. Use spatial position to better assign absent members to parties
2. Add confidence scores for name matches
3. Support for different voting result layouts
4. Batch processing for multiple images
