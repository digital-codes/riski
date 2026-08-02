# Vote Extraction from City Council Image

## Overview
Extract voting results from German city council meeting images. Detect donut charts (totals), OB vote box, party name blocks, and member vote blocks with their colors and shapes.

## Image Layout (Expected)
```
┌─────────────────────────────────────────────────────────────┐
│  [OB Vote Box]          [JA Donut] [NEIN Donut] [ENTH Donut]│
│                                                             │
│  [Party1] [Party2] [Party3] [Party4] ...                   │
│  [Member] [Member] [Member] [Member]                       │
│  [Member] [Member] [Member] [Member]                       │
│  [Member] [Member] [Member] [Member]                       │
│                                                             │
│  ...                                                        │
│                                          [PartyN]           │
│                                          [Member]           │
│                                          [Member]           │
└─────────────────────────────────────────────────────────────┘
```

## Detection Strategy

### 1. Color Space Analysis
- Convert to HSV for robust color detection
- Define color ranges for vote states:
  - **JA (Yes)**: Yellow/Green range (H: 30-90, S: 100-255, V: 100-255)
  - **NEIN (No)**: Red range (H: 0-10, 170-180, S: 100-255, V: 100-255)
  - **ENTHALTUNG (Abstain)**: Blue/Purple range (H: 100-140, S: 100-255, V: 100-255)
  - **Gray (neutral)**: Low saturation (S: 0-50, V: 100-200)

### 2. Shape Detection (Flexible)
Support multiple shapes via configuration:
- **Rectangle**: Contour approximation with 4 vertices
- **Circle**: Contour approximation with circularity > 0.8
- **Donut**: Nested contours (outer circle - inner circle)

**Shape Detection Algorithm:**
```python
def detect_shape(contour):
    area = cv2.contourArea(contour)
    perimeter = cv2.contourArcLength(contour, True)
    circularity = 4 * pi * area / (perimeter * perimeter)
    
    if circularity > 0.8:
        return "circle"
    
    approx = cv2.approxPolyDP(contour, 0.04 * perimeter, True)
    if len(approx) == 4:
        return "rectangle"
    
    return "unknown"
```

### 3. Contour Detection Pipeline
```
1. Load image
2. Convert to HSV
3. Create color masks for each vote type
4. For each mask:
   - Apply morphological operations (close gaps)
   - Find contours
   - Filter by area (min_size, max_size)
   - Classify shape
   - Extract bounding box
   - Calculate dominant color
5. Merge overlapping detections
```

### 4. Region Classification

**Donut Charts (Top Right):**
- Largest circular contours in upper-right quadrant
- Detect nested circles (donut = outer - inner)
- Extract center, radius, color distribution
- Count segments by color

**OB Vote Box (Top Center):**
- Single rectangular/colored contour in top-center
- Contains text (name) - use OCR
- Color determines vote

**Party Name Blocks:**
- Smaller contours in first row below OB
- All gray initially
- Contains party name text
- Group by vertical position (same Y coordinate)

**Member Vote Blocks:**
- Larger contours below party names
- Colored (JA/NEIN/ENTHALTUNG) or gray
- Contains member name text
- Group by column (same X coordinate as party)

### 5. Spatial Analysis

**Column Detection:**
1. Find all party name blocks (first row, gray, smaller)
2. Calculate average X position for each party
3. Assign member blocks to nearest party column
4. Sort members by Y position within column

**Size-Based Separation:**
- Party blocks: smaller area (configurable threshold)
- Member blocks: larger area
- Use area ratio or absolute size threshold

### 6. OCR Integration (Tesseract)

**Text Extraction:**
```python
def extract_text(image, bbox):
    # Crop to bounding box
    roi = image[bbox[1]:bbox[1]+bbox[3], bbox[0]:bbox[0]+bbox[2]]
    
    # Preprocess for OCR
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    # OCR with German language
    text = pytesseract.image_to_string(thresh, lang='deu')
    return text.strip()
```

**Text Validation:**
- Compare extracted names against known lists
- Use fuzzy matching (Levenshtein distance) for typos
- Flag low-confidence matches for manual review

### 7. Data Structure

```python
class VoteResult:
    def __init__(self):
        self.ob_vote = {
            'name': str,
            'vote': str,  # JA, NEIN, ENTHALTUNG
            'bbox': (x, y, w, h),
            'color': (h, s, v)
        }
        
        self.totals = {
            'ja': int,
            'nein': int,
            'enthaltung': int
        }
        
        self.parties = [
            {
                'name': str,
                'bbox': (x, y, w, h),
                'members': [
                    {
                        'name': str,
                        'vote': str,
                        'bbox': (x, y, w, h),
                        'color': (h, s, v),
                        'shape': str  # rectangle, circle, donut
                    }
                ]
            }
        ]
```

### 8. Validation & Iteration

**External Data Sources:**
```python
# Load known names/parties
known_parties = load_from_file('parties.txt')
known_members = load_from_file('members.txt')

# Validate extracted data
def validate_results(results, known_parties, known_members):
    for party in results.parties:
        if party.name not in known_parties:
            # Try fuzzy match
            match = fuzzy_match(party.name, known_parties)
            if match:
                party.name = match
            else:
                flag_for_review(party)
        
        for member in party.members:
            if member.name not in known_members:
                match = fuzzy_match(member.name, known_members)
                if match:
                    member.name = match
                else:
                    flag_for_review(member)
```

**Iterative Refinement:**
1. First pass: detect all contours
2. Validate names against known lists
3. If validation fails:
   - Adjust color thresholds
   - Adjust size thresholds
   - Retry OCR with different preprocessing
4. Manual override for flagged items

## Configuration Parameters

```python
CONFIG = {
    # Shape detection
    'shape_type': 'auto',  # auto, rectangle, circle, donut
    'min_contour_area': 500,
    'max_contour_area': 50000,
    
    # Color thresholds (HSV)
    'ja_color': {'h_min': 30, 'h_max': 90, 's_min': 100, 'v_min': 100},
    'nein_color': {'h_min': 0, 'h_max': 10, 's_min': 100, 'v_min': 100},
    'nein_color_alt': {'h_min': 170, 'h_max': 180, 's_min': 100, 'v_min': 100},
    'enthaltung_color': {'h_min': 100, 'h_max': 140, 's_min': 100, 'v_min': 100},
    'gray_color': {'s_max': 50, 'v_min': 100, 'v_max': 200},
    
    # Size thresholds
    'party_block_max_area': 3000,
    'member_block_min_area': 3000,
    
    # Spatial
    'column_tolerance': 50,  # pixels
    'row_tolerance': 30,  # pixels
    
    # OCR
    'ocr_lang': 'deu',
    'fuzzy_match_threshold': 0.8,
}
```

## Implementation Steps

### Phase 1: Basic Detection
1. Load image and convert to HSV
2. Create color masks for each vote type
3. Find contours in each mask
4. Filter contours by area
5. Classify shapes
6. Extract bounding boxes and colors

### Phase 2: Spatial Organization
1. Identify donut charts (largest circles, top-right)
2. Identify OB box (top-center, colored rectangle)
3. Identify party row (first row of small gray blocks)
4. Group member blocks into columns
5. Sort by position

### Phase 3: OCR & Validation
1. Extract text from each block
2. Validate against known lists
3. Apply fuzzy matching
4. Flag uncertain matches

### Phase 4: Output
1. Generate structured JSON output
2. Create visualization overlay (optional)
3. Log confidence scores
4. Export flagged items for review

## Dependencies

```
opencv-python>=4.8.0
numpy>=1.24.0
pytesseract>=0.3.10
scikit-image>=0.21.0  # optional, for advanced morphology
python-Levenshtein>=0.21.0  # fuzzy matching
```

## Current Status (After Initial Implementation)

**Working:**
- OB detection: Dr. Mentrup with JA vote (HSV: 37, 210, 234)
- Member vote blocks: 50 blocks detected with names
- Color classification: JA votes correctly identified (HSV ~29, 243, 244)
- Shape detection: Rectangles detected correctly
- Donut chart detection: 3 donuts detected in top-right (JA, NEIN, ENTHALTUNG)
- Vote counting: 20 JA votes counted from member blocks

**Issues Identified:**
1. **Party names not extracted reliably**: OCR fails on small gray party name blocks (39x49 to 85x108 pixels)
   - Party blocks detected at 4 locations
   - OCR results are mostly garbage: "|", "N", "", "4", "V4"
   - Root cause: Text is too small and unclear for reliable OCR
   - **Solution**: Use external party name list with fuzzy matching (already implemented)

2. **Member-to-party assignment incomplete**: Only 5 parties created from 4 party blocks
   - Spatial grouping by X position needs refinement
   - Some member blocks not assigned to any party
   - Column tolerance (50px) may need adjustment

3. **Donut chart text not extracted**: Donuts detected but vote counts not read from labels
   - Currently counting votes from member blocks instead
   - Could add OCR on donut labels for cross-validation

**What Works Well:**
- Member name extraction: Good quality (Hofmann, Bunk-Merkel, Dr. Dogan, etc.)
- Vote color classification: Accurate for JA (yellow/orange)
- Spatial organization: Members grouped into columns correctly
- Shape detection: Rectangles identified properly

**Recommended Workflow:**
1. Run extraction script to get member names and votes
2. Provide external party name list (parties.txt)
3. Provide external member name list (members.txt) for validation
4. Script will fuzzy-match extracted names against known lists
5. Review flagged low-confidence matches manually

**Example Usage:**
```bash
# Create name lists
echo -e "CDU\nSPD\nGRÜNE\nFDP\nAfD" > parties.txt
echo -e "Hofmann\nBunk-Merkel\nDr. Dogan\nKehrle\nMüller" > members.txt

# Run extraction with validation
python3 extract_votes.py abstimmung.png \
  --parties-file parties.txt \
  --members-file members.txt \
  --output votes.json \
  --visualize
```

## Testing Strategy

1. **Unit Tests:**
   - Color mask generation
   - Shape classification
   - Contour filtering
   - OCR preprocessing

2. **Integration Tests:**
   - Full pipeline on sample images
   - Validation against known results
   - Edge cases (overlapping contours, poor lighting)

3. **Manual Verification:**
   - Visual overlay of detected regions
   - Side-by-side comparison with original
   - Confidence score review

## Future Extensions

- Support for rotated/skewed images (perspective correction)
- Machine learning for shape classification
- Batch processing for multiple images
- Web interface for manual corrections
- Export to various formats (CSV, Excel, JSON)
