#!/usr/bin/env python3
"""
Vote Extraction from City Council Images
Extracts voting results from German city council meeting images.
"""

import cv2
import numpy as np
import pytesseract
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
import json
import argparse
from pathlib import Path

try:
    from Levenshtein import ratio as fuzzy_ratio
except ImportError:
    # Fallback if python-Levenshtein not available
    def fuzzy_ratio(s1, s2):
        """Simple fuzzy matching fallback"""
        if len(s1) == 0 or len(s2) == 0:
            return 0.0
        max_len = max(len(s1), len(s2))
        distance = sum(1 for a, b in zip(s1, s2) if a != b) + abs(len(s1) - len(s2))
        return 1.0 - (distance / max_len)


@dataclass
class MemberVote:
    name: str
    vote: str  # JA, NEIN, ENTHALTUNG, GRAY
    bbox: Tuple[int, int, int, int]  # x, y, w, h
    color_hsv: Tuple[int, int, int]
    shape: str  # rectangle, circle, donut
    confidence: float = 1.0


@dataclass
class Party:
    name: str
    bbox: Tuple[int, int, int, int]
    members: List[MemberVote] = field(default_factory=list)


@dataclass
class VoteResult:
    ob_vote: Optional[Dict] = None
    totals: Dict[str, int] = field(default_factory=lambda: {'ja': 0, 'nein': 0, 'enthaltung': 0})
    parties: List[Party] = field(default_factory=list)
    all_boxes: List[Dict] = field(default_factory=list)
    image_info: Dict = field(default_factory=dict)
    
    def to_dict(self):
        return {
            'image_info': self.image_info,
            'ob_vote': self.ob_vote,
            'totals': self.totals,
            'parties': [
                {
                    'name': p.name,
                    'bbox': p.bbox,
                    'members': [
                        {
                            'name': m.name,
                            'vote': m.vote,
                            'bbox': m.bbox,
                            'color_hsv': m.color_hsv,
                            'shape': m.shape,
                            'confidence': m.confidence
                        }
                        for m in p.members
                    ]
                }
                for p in self.parties
            ],
            'all_boxes': self.all_boxes
        }


class VoteExtractor:
    def __init__(self, config: Dict = None):
        self.config = self._default_config()
        if config:
            self.config.update(config)
        self.image = None
        self.hsv = None
        self.results = VoteResult()
        
    def _default_config(self) -> Dict:
        return {
            # Shape detection
            'shape_type': 'auto',  # auto, rectangle, circle, donut
            'min_contour_area': 500,
            'max_contour_area': 50000,
            
            # Color thresholds (HSV)
            'ja_color': {'h_min': 20, 'h_max': 90, 's_min': 100, 'v_min': 100},
            'nein_color': {'h_min': 0, 'h_max': 22, 's_min': 100, 'v_min': 100},
            'nein_color_alt': {'h_min': 165, 'h_max': 180, 's_min': 100, 'v_min': 100},
            'enthaltung_color': {'h_min': 90, 'h_max': 140, 's_min': 100, 'v_min': 100},
            'gray_color': {'s_max': 60, 'v_min': 100, 'v_max': 200},
            
            # Size thresholds
            'party_block_max_area': 2500,  # Smaller to avoid overlap
            'member_block_min_area': 3500,  # Larger to avoid overlap
            
            # Spatial
            'column_tolerance': 50,
            'row_tolerance': 30,
            
            # OCR
            'ocr_lang': 'deu',
            'fuzzy_match_threshold': 0.75,
        }
    
    def load_image(self, image_path: str):
        """Load image and convert to HSV"""
        self.image = cv2.imread(image_path)
        if self.image is None:
            raise ValueError(f"Could not load image: {image_path}")
        self.hsv = cv2.cvtColor(self.image, cv2.COLOR_BGR2HSV)
        print(f"Loaded image: {self.image.shape}")
        
        # Store image info
        self.results.image_info = {
            'width': self.image.shape[1],
            'height': self.image.shape[0],
            'bbox': [0, 0, self.image.shape[1], self.image.shape[0]],
            'origin': 'top-left',
            'format': self._detect_format()
        }
        print(f"Image size: {self.image.shape[1]}x{self.image.shape[0]}, origin: top-left")
        
        # Detect format
        self.format = self._detect_format()
        print(f"Detected format: {self.format}")
    
    def _detect_format(self) -> str:
        """Detect whether image uses new format (donuts) or old format (summary boxes)"""
        # Check for blue background (old format)
        blue_pixels = cv2.countNonZero(cv2.inRange(self.hsv, np.array([100, 50, 50]), np.array([130, 255, 255])))
        total_pixels = self.image.shape[0] * self.image.shape[1]
        blue_ratio = blue_pixels / total_pixels
        
        if blue_ratio > 0.01:  # More than 1% blue = old format
            return "old_format"
        
        # Check for donut charts (new format)
        gray = cv2.cvtColor(self.image, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (9, 9), 2)
        circles = cv2.HoughCircles(blurred, cv2.HOUGH_GRADIENT, 1, 100,
                                   param1=100, param2=50, minRadius=80, maxRadius=150)
        
        if circles is not None and len(circles[0]) >= 3:
            return "new_format"
        
        return "unknown"
    
    def _detect_summary_boxes(self) -> List[Dict]:
        """Detect summary boxes in old format (rectangular boxes with vote counts)"""
        # Look for boxes in top area with text
        height, width = self.image.shape[:2]
        top_region = self.image[0:int(height*0.3), :]
        top_hsv = self.hsv[0:int(height*0.3), :]
        
        # Create masks for different vote colors
        # Yellow (JA)
        yellow_mask = cv2.inRange(top_hsv, np.array([20, 100, 100]), np.array([35, 255, 255]))
        
        # Red (NEIN)
        red_mask = cv2.inRange(top_hsv, np.array([0, 100, 100]), np.array([10, 255, 255]))
        red_mask2 = cv2.inRange(top_hsv, np.array([165, 100, 100]), np.array([180, 255, 255]))
        red_mask = cv2.bitwise_or(red_mask, red_mask2)
        
        # White/Light gray (ENTHALTUNG) - high value, low saturation
        white_mask = cv2.inRange(top_hsv, np.array([0, 0, 200]), np.array([180, 40, 255]))
        
        # Combine all masks
        combined_mask = cv2.bitwise_or(yellow_mask, cv2.bitwise_or(red_mask, white_mask))
        
        # Clean up
        kernel = np.ones((5, 5), np.uint8)
        combined_mask = cv2.morphologyEx(combined_mask, cv2.MORPH_CLOSE, kernel)
        combined_mask = cv2.morphologyEx(combined_mask, cv2.MORPH_OPEN, kernel)
        
        contours, _ = cv2.findContours(combined_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        summary_boxes = []
        for contour in contours:
            area = cv2.contourArea(contour)
            # Summary boxes should be larger than member boxes
            if 3000 <= area <= 150000:
                x, y, w, h = cv2.boundingRect(contour)
                
                # Extract text from box
                roi = top_region[y:y+h, x:x+w]
                text = self._extract_summary_text(roi)
                
                if text:
                    # Determine vote type by color
                    roi_hsv = top_hsv[y:y+h, x:x+w]
                    mean_hsv = cv2.mean(roi_hsv, mask=combined_mask[y:y+h, x:x+w])[:3]
                    
                    vote_type = "unknown"
                    if 20 <= mean_hsv[0] <= 35 and mean_hsv[1] >= 100:
                        vote_type = "ja"
                    elif (mean_hsv[0] <= 10 or mean_hsv[0] >= 165) and mean_hsv[1] >= 100:
                        vote_type = "nein"
                    elif mean_hsv[2] >= 200 and mean_hsv[1] <= 40:
                        vote_type = "enthaltung"
                    
                    summary_boxes.append({
                        'bbox': (x, y, w, h),
                        'text': text,
                        'area': area,
                        'vote_type': vote_type
                    })
        
        return summary_boxes
    
    def _extract_summary_text(self, roi: np.ndarray) -> Optional[int]:
        """Extract vote count from summary box"""
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # Add padding
        padded = cv2.copyMakeBorder(thresh, 10, 10, 10, 10, cv2.BORDER_CONSTANT, value=255)
        
        # OCR with number whitelist
        config = r'--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789'
        try:
            text = pytesseract.image_to_string(padded, config=config).strip()
            import re
            numbers = re.findall(r'\d+', text)
            if numbers:
                return int(numbers[0])
        except:
            pass
        
        return None
    
    def _detect_shape(self, contour) -> str:
        """Detect shape of contour"""
        if self.config['shape_type'] != 'auto':
            return self.config['shape_type']
        
        area = cv2.contourArea(contour)
        perimeter = cv2.arcLength(contour, True)
        
        if perimeter == 0:
            return "unknown"
        
        circularity = 4 * np.pi * area / (perimeter * perimeter)
        
        if circularity > 0.8:
            return "circle"
        
        approx = cv2.approxPolyDP(contour, 0.04 * perimeter, True)
        if len(approx) == 4:
            return "rectangle"
        
        return "unknown"
    
    def _create_color_mask(self, color_config: Dict) -> np.ndarray:
        """Create binary mask for color range"""
        lower = np.array([color_config.get('h_min', 0), 
                         color_config.get('s_min', 0), 
                         color_config.get('v_min', 0)])
        upper = np.array([color_config.get('h_max', 180), 
                         color_config.get('s_max', 255), 
                         color_config.get('v_max', 255)])
        
        mask = cv2.inRange(self.hsv, lower, upper)
        
        # Morphological operations to clean up
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        
        return mask
    
    def _get_dominant_color(self, contour) -> Tuple[int, int, int]:
        """Get dominant HSV color in contour region"""
        mask = np.zeros(self.hsv.shape[:2], dtype=np.uint8)
        cv2.drawContours(mask, [contour], -1, 255, -1)
        
        mean_hsv = cv2.mean(self.hsv, mask=mask)[:3]
        return tuple(int(x) for x in mean_hsv)
    
    def _classify_vote_by_color(self, hsv_color: Tuple[int, int, int]) -> str:
        """Classify vote based on HSV color"""
        h, s, v = hsv_color
        
        # Check gray first (low saturation)
        gray_cfg = self.config['gray_color']
        if s <= gray_cfg.get('s_max', 50):
            return "GRAY"
        
        # Check JA (yellow/green)
        ja_cfg = self.config['ja_color']
        if ja_cfg['h_min'] <= h <= ja_cfg['h_max'] and s >= ja_cfg['s_min'] and v >= ja_cfg['v_min']:
            return "JA"
        
        # Check NEIN (red - two ranges)
        nein_cfg = self.config['nein_color']
        nein_alt_cfg = self.config['nein_color_alt']
        if ((nein_cfg['h_min'] <= h <= nein_cfg['h_max'] or 
             nein_alt_cfg['h_min'] <= h <= nein_alt_cfg['h_max']) and 
            s >= nein_cfg['s_min'] and v >= nein_cfg['v_min']):
            return "NEIN"
        
        # Check ENTHALTUNG (blue)
        enth_cfg = self.config['enthaltung_color']
        if enth_cfg['h_min'] <= h <= enth_cfg['h_max'] and s >= enth_cfg['s_min'] and v >= enth_cfg['v_min']:
            return "ENTHALTUNG"
        
        return "UNKNOWN"
    
    def _find_contours(self, mask: np.ndarray) -> List:
        """Find and filter contours"""
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        filtered = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if self.config['min_contour_area'] <= area <= self.config['max_contour_area']:
                filtered.append(contour)
        
        return filtered
    
    def _extract_text(self, bbox: Tuple[int, int, int, int]) -> str:
        """Extract text from region using OCR"""
        x, y, w, h = bbox
        
        # Add padding
        pad = 5
        x1 = max(0, x - pad)
        y1 = max(0, y - pad)
        x2 = min(self.image.shape[1], x + w + pad)
        y2 = min(self.image.shape[0], y + h + pad)
        
        roi = self.image[y1:y2, x1:x2]
        
        # Convert to grayscale and threshold
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        
        # For small regions, upscale for better OCR
        if w < 100 or h < 100:
            scale = 3
            roi_upscaled = cv2.resize(roi, (w*scale, h*scale), interpolation=cv2.INTER_CUBIC)
            gray = cv2.cvtColor(roi_upscaled, cv2.COLOR_BGR2GRAY)
        
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # OCR with custom config for better small text recognition
        custom_config = r'--oem 3 --psm 7'  # Treat as single line
        text = pytesseract.image_to_string(thresh, lang=self.config['ocr_lang'], config=custom_config)
        return text.strip()
    
    def _detect_donut_charts(self, all_contours: List) -> List:
        """Detect donut charts in top-right area and extract vote counts via OCR"""
        # Filter for large circular contours in upper-right quadrant
        height, width = self.image.shape[:2]
        right_region_x = width * 0.6
        
        donuts = []
        
        # Use Hough Circle Transform for better circle detection
        gray = cv2.cvtColor(self.image, cv2.COLOR_BGR2GRAY)
        
        # Apply Gaussian blur to reduce noise
        blurred = cv2.GaussianBlur(gray, (9, 9), 2)
        
        circles = cv2.HoughCircles(blurred, cv2.HOUGH_GRADIENT, 1, 100,
                                   param1=100, param2=50, minRadius=80, maxRadius=150)
        
        if circles is not None:
            circles = np.uint16(np.around(circles))
            for circle in circles[0]:
                x, y, radius = circle
                # Check if in right region and top area
                if x > right_region_x and y < height * 0.4 and radius > 80:
                    # Create a donut-like structure
                    bbox = (x - radius, y - radius, radius * 2, radius * 2)
                    
                    # Get color from the ring area
                    mask = np.zeros(gray.shape, dtype=np.uint8)
                    cv2.circle(mask, (x, y), radius, 255, -1)
                    inner_mask = np.zeros(gray.shape, dtype=np.uint8)
                    cv2.circle(inner_mask, (x, y), int(radius * 0.6), 255, -1)
                    ring_mask = cv2.subtract(mask, inner_mask)
                    
                    mean_hsv = cv2.mean(self.hsv, mask=ring_mask)[:3]
                    color = tuple(int(c) for c in mean_hsv)
                    
                    # Extract and OCR the center region
                    vote_count = self._extract_donut_count(x, y, radius)
                    
                    donuts.append({
                        'bbox': bbox,
                        'color': color,
                        'center': (x, y),
                        'radius': radius,
                        'area': np.pi * radius * radius,
                        'count': vote_count
                    })
        
        # Sort by x position (left to right) and take top 3
        donuts.sort(key=lambda d: d['center'][0])
        return donuts[:3]  # Expect exactly 3 donuts (JA, NEIN, ENTHALTUNG)
    
    def _extract_donut_count(self, center_x: int, center_y: int, radius: int) -> Optional[int]:
        """Extract the vote count number from inside a donut chart"""
        # Extract the center region (inner 60% of radius)
        inner_radius = int(radius * 0.6)
        
        # Create a bounding box for the center
        x1 = max(0, center_x - inner_radius)
        y1 = max(0, center_y - inner_radius)
        x2 = min(self.image.shape[1], center_x + inner_radius)
        y2 = min(self.image.shape[0], center_y + inner_radius)
        
        # Extract the region
        roi = self.image[y1:y2, x1:x2]
        
        # Convert to grayscale
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        
        # Apply threshold to get clean text
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # Add padding on the right to handle truncation
        padding = 20
        padded = cv2.copyMakeBorder(thresh, padding, padding, padding, padding * 2, 
                                     cv2.BORDER_CONSTANT, value=255)
        
        # OCR with specific config for single numbers
        # PSM 6 = uniform block of text (works better for donut numbers)
        custom_config = r'--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789'
        
        try:
            text = pytesseract.image_to_string(padded, config=custom_config).strip()
            
            # Try to extract number from text
            import re
            numbers = re.findall(r'\d+', text)
            
            if numbers:
                # Take the first number found
                count = int(numbers[0])
                return count
        except Exception as e:
            print(f"OCR error for donut at ({center_x}, {center_y}): {e}")
        
        return None
    
    def _detect_ob_box(self, all_contours: List) -> Optional[Dict]:
        """Detect OB vote box in top-center"""
        height, width = self.image.shape[:2]
        center_region = (width * 0.3, width * 0.7)
        
        candidates = []
        for contour in all_contours:
            x, y, w, h = cv2.boundingRect(contour)
            area = cv2.contourArea(contour)
            
            # Check if in center region and colored (not gray)
            if center_region[0] < x < center_region[1] and y < height * 0.3:
                color = self._get_dominant_color(contour)
                vote = self._classify_vote_by_color(color)
                
                if vote != "GRAY" and vote != "UNKNOWN":
                    candidates.append({
                        'bbox': (x, y, w, h),
                        'color': color,
                        'vote': vote,
                        'area': area
                    })
        
        if candidates:
            # Return largest candidate
            return max(candidates, key=lambda c: c['area'])
        
        return None
    
    def _detect_party_and_member_blocks(self, all_contours: List) -> Tuple[List, List, List]:
        """Detect party name blocks and member vote blocks, return all boxes"""
        party_blocks = []
        member_blocks = []
        all_boxes = []  # Store all detected boxes
        
        height, width = self.image.shape[:2]
        
        # First, detect all colored boxes from contours
        colored_boxes = []
        for contour in all_contours:
            x, y, w, h = cv2.boundingRect(contour)
            area = cv2.contourArea(contour)
            bbox = (x, y, w, h)
            color = self._get_dominant_color(contour)
            vote = self._classify_vote_by_color(color)
            shape = self._detect_shape(contour)
            
            # Filter out full-width bars (likely headers)
            if w > width * 0.8:
                continue
            
            box_data = {
                'bbox': bbox,
                'color': color,
                'vote': vote,
                'shape': shape,
                'area': area,
                'contour': contour
            }
            colored_boxes.append(box_data)
            all_boxes.append(box_data)
        
        # Now detect gray boxes (absent members)
        # Gray boxes have low saturation in HSV, but they blend with background
        # Use edge detection to find box boundaries
        
        # Create mask for low saturation (gray) regions
        gray_mask = cv2.inRange(self.hsv, np.array([0, 0, 100]), np.array([180, 60, 255]))
        
        # Clean up the mask
        kernel = np.ones((3, 3), np.uint8)
        gray_mask = cv2.morphologyEx(gray_mask, cv2.MORPH_CLOSE, kernel)
        gray_mask = cv2.morphologyEx(gray_mask, cv2.MORPH_OPEN, kernel)
        
        # Use edge detection to find box boundaries within gray regions
        gray_img = cv2.cvtColor(self.image, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray_img, (5, 5), 0)
        edges = cv2.Canny(blurred, 50, 150)
        
        # Find contours in edges
        edge_contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # Filter for rectangular boxes
        for contour in edge_contours:
            area = cv2.contourArea(contour)
            if area < 500:  # Too small
                continue
            
            x, y, w, h = cv2.boundingRect(contour)
            
            # Filter out full-width bars
            if w > width * 0.8:
                continue
            
            # Check aspect ratio for rectangular shape
            aspect_ratio = w / h if h > 0 else 0
            if not (0.5 <= aspect_ratio <= 3.0):
                continue
            
            # Check if this overlaps with any colored box
            overlaps = False
            for box in colored_boxes:
                bx, by, bw, bh = box['bbox']
                # Calculate overlap
                overlap_x = max(0, min(x + w, bx + bw) - max(x, bx))
                overlap_y = max(0, min(y + h, by + bh) - max(y, by))
                overlap_area = overlap_x * overlap_y
                
                if overlap_area > 0.3 * min(area, box['area']):  # 30% overlap
                    overlaps = True
                    break
            
            if overlaps:
                continue
            
            # Check if it's actually gray
            color = self._get_dominant_color(contour)
            vote = self._classify_vote_by_color(color)
            shape = self._detect_shape(contour)
            
            if vote == 'GRAY' and area >= self.config['member_block_min_area']:
                colored_boxes.append({
                    'bbox': (x, y, w, h),
                    'color': color,
                    'vote': vote,
                    'shape': shape,
                    'area': area,
                    'contour': contour
                })
        
        # Now separate into party and member blocks by size
        for box in colored_boxes:
            area = box['area']
            if area <= self.config['party_block_max_area']:
                party_blocks.append({
                    'bbox': box['bbox'],
                    'color': box['color'],
                    'vote': box['vote'],
                    'shape': box['shape'],
                    'area': area
                })
            elif area >= self.config['member_block_min_area']:
                member_blocks.append({
                    'bbox': box['bbox'],
                    'color': box['color'],
                    'vote': box['vote'],
                    'shape': box['shape'],
                    'area': area
                })
        
        return party_blocks, member_blocks, all_boxes
    
    def _group_by_columns(self, blocks: List, tolerance: int) -> List[List]:
        """Group blocks into columns by X position"""
        if not blocks:
            return []
        
        # Sort by x position
        blocks_sorted = sorted(blocks, key=lambda b: b['bbox'][0])
        
        columns = []
        current_column = [blocks_sorted[0]]
        current_x = blocks_sorted[0]['bbox'][0]
        
        for block in blocks_sorted[1:]:
            block_x = block['bbox'][0]
            if abs(block_x - current_x) <= tolerance:
                current_column.append(block)
            else:
                columns.append(current_column)
                current_column = [block]
                current_x = block_x
        
        if current_column:
            columns.append(current_column)
        
        return columns
    
    def _assign_members_to_parties(self, party_blocks: List, member_blocks: List) -> List[Party]:
        """Assign member blocks to party columns"""
        parties = []
        
        # Group party blocks by row (first row)
        party_columns = self._group_by_columns(party_blocks, self.config['column_tolerance'])
        
        # Group member blocks by column
        member_columns = self._group_by_columns(member_blocks, self.config['column_tolerance'])
        
        # Match party columns with member columns by X position
        for party_col in party_columns:
            if not party_col:
                continue
            
            # Get party block (first in column)
            party_block = min(party_col, key=lambda b: b['bbox'][1])
            party_x = party_block['bbox'][0]
            
            # Find matching member column
            best_match = None
            min_distance = float('inf')
            
            for member_col in member_columns:
                if member_col:
                    member_x = member_col[0]['bbox'][0]
                    distance = abs(party_x - member_x)
                    if distance < min_distance:
                        min_distance = distance
                        best_match = member_col
            
            # Create party
            party_name = self._extract_text(party_block['bbox'])
            party = Party(
                name=party_name,
                bbox=party_block['bbox']
            )
            
            # Add members
            if best_match:
                # Sort members by Y position
                sorted_members = sorted(best_match, key=lambda b: b['bbox'][1])
                
                for member_block in sorted_members:
                    member_name = self._extract_text(member_block['bbox'])
                    member = MemberVote(
                        name=member_name,
                        vote=member_block['vote'],
                        bbox=member_block['bbox'],
                        color_hsv=member_block['color'],
                        shape=member_block['shape']
                    )
                    party.members.append(member)
            
            parties.append(party)
        
        return parties
    
    def _count_totals_from_donuts(self, donuts: List) -> Dict[str, int]:
        """Extract vote counts from donut charts using OCR"""
        totals = {'ja': 0, 'nein': 0, 'enthaltung': 0}
        
        # Donuts are sorted by x position: JA, NEIN, ENTHALTUNG
        if len(donuts) >= 1 and donuts[0].get('count') is not None:
            totals['ja'] = donuts[0]['count']
            print(f"Donut JA count: {totals['ja']}")
        
        if len(donuts) >= 2 and donuts[1].get('count') is not None:
            totals['nein'] = donuts[1]['count']
            print(f"Donut NEIN count: {totals['nein']}")
        
        if len(donuts) >= 3 and donuts[2].get('count') is not None:
            totals['enthaltung'] = donuts[2]['count']
            print(f"Donut ENTHALTUNG count: {totals['enthaltung']}")
        
        # Fallback: count from member votes if OCR failed
        if totals['ja'] == 0 and totals['nein'] == 0 and totals['enthaltung'] == 0:
            print("Donut OCR failed, falling back to member vote counting")
            for party in self.results.parties:
                for member in party.members:
                    if member.vote == "JA":
                        totals['ja'] += 1
                    elif member.vote == "NEIN":
                        totals['nein'] += 1
                    elif member.vote == "ENTHALTUNG":
                        totals['enthaltung'] += 1
        
        return totals
    
    def validate_names(self, known_parties: List[str] = None, known_members: List[str] = None):
        """Validate extracted names against known lists"""
        if known_parties:
            for party in self.results.parties:
                if party.name not in known_parties:
                    # Try fuzzy match
                    best_match = None
                    best_score = 0
                    
                    for known in known_parties:
                        score = fuzzy_ratio(party.name.lower(), known.lower())
                        if score > best_score:
                            best_score = score
                            best_match = known
                    
                    if best_score >= self.config['fuzzy_match_threshold']:
                        print(f"Corrected party name: '{party.name}' -> '{best_match}' (score: {best_score:.2f})")
                        party.name = best_match
                    else:
                        print(f"Warning: Unknown party name '{party.name}' (best match: {best_match}, score: {best_score:.2f})")
        
        if known_members:
            for party in self.results.parties:
                for member in party.members:
                    if member.name not in known_members:
                        best_match = None
                        best_score = 0
                        
                        for known in known_members:
                            score = fuzzy_ratio(member.name.lower(), known.lower())
                            if score > best_score:
                                best_score = score
                                best_match = known
                        
                        if best_score >= self.config['fuzzy_match_threshold']:
                            print(f"Corrected member name: '{member.name}' -> '{best_match}' (score: {best_score:.2f})")
                            member.name = best_match
                        else:
                            print(f"Warning: Unknown member name '{member.name}' (best match: {best_match}, score: {best_score:.2f})")
    
    def extract(self, image_path: str, known_parties: List[str] = None, known_members: List[str] = None, 
                party_mapping: Dict[str, str] = None, member_party_mapping: Dict[str, str] = None) -> VoteResult:
        """Main extraction pipeline - handles multiple formats"""
        print(f"Processing image: {image_path}")
        
        # Load image and detect format
        self.load_image(image_path)
        
        # Try extraction strategies based on detected format
        if self.format == "old_format":
            return self._extract_old_format(known_parties, known_members, party_mapping, member_party_mapping)
        elif self.format == "new_format":
            return self._extract_new_format(known_parties, known_members, party_mapping, member_party_mapping)
        else:
            # Unknown format - try both strategies
            print("Unknown format, trying new format first...")
            result = self._extract_new_format(known_parties, known_members, party_mapping, member_party_mapping)
            if result.totals['ja'] + result.totals['nein'] + result.totals['enthaltung'] == 0:
                print("New format failed, trying old format...")
                result = self._extract_old_format(known_parties, known_members, party_mapping, member_party_mapping)
            return result
    
    def _extract_new_format(self, known_parties, known_members, party_mapping, member_party_mapping) -> VoteResult:
        """Extract from new format (donut charts)"""
        # Create color masks
        ja_mask = self._create_color_mask(self.config['ja_color'])
        nein_mask = self._create_color_mask(self.config['nein_color'])
        nein_alt_mask = self._create_color_mask(self.config['nein_color_alt'])
        enth_mask = self._create_color_mask(self.config['enthaltung_color'])
        gray_mask = self._create_color_mask(self.config['gray_color'])
        
        # Combine masks
        combined_mask = cv2.bitwise_or(ja_mask, nein_mask)
        combined_mask = cv2.bitwise_or(combined_mask, nein_alt_mask)
        combined_mask = cv2.bitwise_or(combined_mask, enth_mask)
        combined_mask = cv2.bitwise_or(combined_mask, gray_mask)
        
        # Find all contours
        all_contours = self._find_contours(combined_mask)
        print(f"Found {len(all_contours)} contours")
        
        # Detect donut charts
        donuts = self._detect_donut_charts(all_contours)
        print(f"Detected {len(donuts)} donut charts")
        
        # Detect OB box
        ob_box = self._detect_ob_box(all_contours)
        if ob_box:
            ob_name = self._extract_text(ob_box['bbox'])
            self.results.ob_vote = {
                'name': ob_name,
                'vote': ob_box['vote'],
                'bbox': ob_box['bbox'],
                'color': ob_box['color']
            }
            print(f"Detected OB: {ob_name} ({ob_box['vote']})")
        
        party_blocks, member_blocks, all_boxes = self._detect_party_and_member_blocks(all_contours)
        print(f"Detected {len(party_blocks)} party blocks, {len(member_blocks)} member blocks")
        
        # Store all detected boxes in results
        self.results.all_boxes = [
            {
                'bbox': box['bbox'],
                'color': box['color'],
                'vote': box['vote'],
                'shape': box['shape'],
                'area': box['area']
            }
            for box in all_boxes
        ]
        
        # Assign members to parties
        if member_party_mapping:
            print("Using member-party mapping from HTML data")
            self.results.parties = self._assign_members_by_known_mapping(member_blocks, member_party_mapping)
        else:
            self.results.parties = self._assign_members_to_parties(party_blocks, member_blocks)
            if party_mapping:
                for party in self.results.parties:
                    if party.name in party_mapping:
                        old_name = party.name
                        party.name = party_mapping[old_name]
                        print(f"Mapped party name: '{old_name}' -> '{party.name}'")
        
        # Count totals from donuts
        self.results.totals = self._count_totals_from_donuts(donuts)
        
        # Validate names
        if known_parties or known_members:
            self.validate_names(known_parties, known_members)
        
        print(f"\nExtraction complete:")
        print(f"  OB: {self.results.ob_vote}")
        print(f"  Totals: {self.results.totals}")
        print(f"  Parties: {len(self.results.parties)}")
        
        return self.results
    
    def _detect_background_color(self) -> Tuple[int, int, int]:
        """Detect background color by sampling corners"""
        h, w = self.hsv.shape[:2]
        corners = [
            (0, 0), (w-1, 0), (0, h-1), (w-1, h-1)
        ]
        
        # Sample corner pixels
        samples = []
        for x, y in corners:
            samples.append(self.hsv[y, x])
        
        # Average the samples
        avg_hsv = np.mean(samples, axis=0)
        return tuple(int(x) for x in avg_hsv)
    
    def _classify_vote_adaptive(self, hsv_color: Tuple[int, int, int], bg_color: Tuple[int, int, int]) -> str:
        """Classify vote by comparing to background color"""
        h, s, v = hsv_color
        bg_h, bg_s, bg_v = bg_color
        
        # Calculate color distance from background
        h_diff = abs(h - bg_h)
        s_diff = abs(s - bg_s)
        v_diff = abs(v - bg_v)
        
        # If very similar to background, it's a gray/absent box
        if h_diff < 10 and s_diff < 20 and v_diff < 30:
            return "GRAY"
        
        # Check if yellowish (JA) - hue around 20-40, high saturation
        if 15 <= h <= 45 and s > 80:
            return "JA"
        
        # Check if reddish (NEIN) - hue around 0-10 or 170-180
        if (h <= 15 or h >= 165) and s > 80:
            return "NEIN"
        
        # Check if white/light gray (ENTHALTUNG) - low saturation, high value
        if s < 50 and v > 180:
            return "ENTHALTUNG"
        
        # Default to gray if unclear
        return "GRAY"
    
    def _extract_old_format(self, known_parties, known_members, party_mapping, member_party_mapping) -> VoteResult:
        """Extract from old format (summary boxes)"""
        # Detect summary boxes with vote counts
        summary_boxes = self._detect_summary_boxes()
        print(f"Detected {len(summary_boxes)} summary boxes")
        
        # For old format, detect colored boxes directly
        # Yellow (JA)
        yellow_mask = cv2.inRange(self.hsv, np.array([20, 100, 150]), np.array([35, 255, 255]))
        
        # Red (NEIN) - two ranges
        red_mask1 = cv2.inRange(self.hsv, np.array([0, 100, 100]), np.array([10, 255, 255]))
        red_mask2 = cv2.inRange(self.hsv, np.array([170, 100, 100]), np.array([180, 255, 255]))
        red_mask = cv2.bitwise_or(red_mask1, red_mask2)
        
        # Gray (absent) - low saturation
        gray_mask = cv2.inRange(self.hsv, np.array([0, 0, 150]), np.array([180, 50, 255]))
        
        # White (ENTHALTUNG) - high value, low saturation
        white_mask = cv2.inRange(self.hsv, np.array([0, 0, 200]), np.array([180, 30, 255]))
        
        # Combine all vote colors
        all_votes_mask = cv2.bitwise_or(yellow_mask, red_mask)
        all_votes_mask = cv2.bitwise_or(all_votes_mask, gray_mask)
        all_votes_mask = cv2.bitwise_or(all_votes_mask, white_mask)
        
        # Clean up
        kernel = np.ones((3, 3), np.uint8)
        all_votes_mask = cv2.morphologyEx(all_votes_mask, cv2.MORPH_CLOSE, kernel)
        all_votes_mask = cv2.morphologyEx(all_votes_mask, cv2.MORPH_OPEN, kernel)
        
        # Find contours
        contours, _ = cv2.findContours(all_votes_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # Filter for box-sized contours
        all_boxes = []
        for contour in contours:
            area = cv2.contourArea(contour)
            # Member boxes are typically 100x100 to 250x250 pixels
            if 10000 <= area <= 80000:
                x, y, w, h = cv2.boundingRect(contour)
                
                # Check aspect ratio to ensure it's box-like
                aspect_ratio = w / h if h > 0 else 0
                if 0.5 <= aspect_ratio <= 2.0:
                    # Sample color inside the box
                    mask = np.zeros(self.hsv.shape[:2], dtype=np.uint8)
                    cv2.drawContours(mask, [contour], -1, 255, -1)
                    mean_hsv = cv2.mean(self.hsv, mask=mask)[:3]
                    
                    # Classify vote by color
                    vote = self._classify_vote_adaptive(mean_hsv, (0, 0, 240))  # Light background
                    
                    all_boxes.append({
                        'bbox': (x, y, w, h),
                        'color': mean_hsv,
                        'vote': vote,
                        'shape': self._detect_shape(contour),
                        'area': area,
                        'contour': contour
                    })
        
        print(f"Found {len(all_boxes)} total boxes")
        
        # Store all detected boxes in results
        self.results.all_boxes = [
            {
                'bbox': box['bbox'],
                'color': box['color'],
                'vote': box['vote'],
                'shape': box['shape'],
                'area': box['area']
            }
            for box in all_boxes
        ]
        
        # Separate into party and member blocks
        # In old format, party blocks are smaller (text labels)
        party_blocks = [b for b in all_boxes if b['area'] <= 10000]
        member_blocks = [b for b in all_boxes if b['area'] > 10000]
        
        print(f"Detected {len(party_blocks)} party blocks, {len(member_blocks)} member blocks")
        
        # For old format, party names are below members
        # Try to detect party blocks in bottom area
        height = self.image.shape[0]
        bottom_region = self.hsv[int(height*0.7):, :]
        
        # Assign members to parties
        if member_party_mapping:
            print("Using member-party mapping from HTML data")
            self.results.parties = self._assign_members_by_known_mapping(member_blocks, member_party_mapping)
        else:
            self.results.parties = self._assign_members_to_parties(party_blocks, member_blocks)
            if party_mapping:
                for party in self.results.parties:
                    if party.name in party_mapping:
                        old_name = party.name
                        party.name = party_mapping[old_name]
                        print(f"Mapped party name: '{old_name}' -> '{party.name}'")
        
        # Extract totals from summary boxes
        self.results.totals = self._count_totals_from_summary_boxes(summary_boxes)
        
        # Validate totals match detected votes
        detected_votes = sum(len(p.members) for p in self.results.parties)
        summary_total = self.results.totals['ja'] + self.results.totals['nein'] + self.results.totals['enthaltung']
        
        if detected_votes != summary_total and summary_total > 0:
            print(f"Warning: Detected {detected_votes} votes but summary shows {summary_total}")
        
        # Validate names
        if known_parties or known_members:
            self.validate_names(known_parties, known_members)
        
        print(f"\nExtraction complete:")
        print(f"  Totals (from summary): {self.results.totals}")
        print(f"  Parties: {len(self.results.parties)}")
        
        return self.results
    
    def _count_totals_from_summary_boxes(self, summary_boxes: List[Dict]) -> Dict[str, int]:
        """Extract vote totals from summary boxes"""
        totals = {'ja': 0, 'nein': 0, 'enthaltung': 0}
        
        # Use vote_type if available, otherwise fall back to position
        for box in summary_boxes:
            vote_type = box.get('vote_type', 'unknown')
            count = box.get('text', 0)
            
            if vote_type == 'ja':
                totals['ja'] = count
            elif vote_type == 'nein':
                totals['nein'] = count
            elif vote_type == 'enthaltung':
                totals['enthaltung'] = count
        
        # If no vote_type information, fall back to position-based assignment
        if all(v == 0 for v in totals.values()):
            sorted_boxes = sorted(summary_boxes, key=lambda b: b['bbox'][0])
            if len(sorted_boxes) >= 3:
                totals['ja'] = sorted_boxes[0].get('text', 0)
                totals['nein'] = sorted_boxes[1].get('text', 0)
                totals['enthaltung'] = sorted_boxes[2].get('text', 0)
        
        return totals
    
    def _assign_members_by_known_mapping(self, member_blocks: List, member_party_mapping: Dict[str, str]) -> List[Party]:
        """Assign members to parties using known mapping from HTML"""
        from collections import defaultdict
        
        # Group members by party
        party_members = defaultdict(list)
        
        # Track which known members have been matched
        matched_known_members = set()
        
        for block in member_blocks:
            member_name = self._extract_text(block['bbox'])
            
            # Try to find matching member in mapping
            matched_party = None
            matched_name = ""
            
            # Direct match
            if member_name in member_party_mapping:
                matched_party = member_party_mapping[member_name]
                matched_name = member_name
                matched_known_members.add(member_name)
            elif member_name and len(member_name.strip()) >= 3:
                # Try multiple matching strategies
                best_match = None
                best_score = 0
                
                # Extract last name from OCR result
                ocr_parts = member_name.split()
                ocr_last_name = ocr_parts[-1] if ocr_parts else ""
                
                # Check if format is "Last, First" (e.g., "Schütz, N.")
                is_last_first = ',' in member_name
                
                for known_name, party in member_party_mapping.items():
                    if known_name in matched_known_members:
                        continue  # Skip already matched members
                    
                    # Strategy 1: Full fuzzy match
                    score = fuzzy_ratio(member_name.lower(), known_name.lower())
                    
                    # Strategy 2: Substring match (OCR name contained in known name)
                    if member_name.lower() in known_name.lower():
                        score = max(score, 0.85)
                    
                    # Strategy 3: Last name match
                    known_parts = known_name.split()
                    known_last_name = known_parts[-1] if known_parts else ""
                    if ocr_last_name and known_last_name:
                        last_name_score = fuzzy_ratio(ocr_last_name.lower(), known_last_name.lower())
                        if last_name_score > 0.8:
                            score = max(score, last_name_score * 0.9)
                    
                    # Strategy 4: Check if last name is substring
                    if ocr_last_name and known_last_name:
                        if ocr_last_name.lower() in known_last_name.lower() or known_last_name.lower() in ocr_last_name.lower():
                            score = max(score, 0.80)
                    
                    # Strategy 5: Handle "Last, First" or "Last, Initial" format
                    if is_last_first:
                        # Extract parts before and after comma
                        parts = member_name.split(',', 1)
                        if len(parts) == 2:
                            before_comma = parts[0].strip()
                            after_comma = parts[1].strip()
                            
                            if before_comma and after_comma:
                                # Check if last name matches
                                last_name_score = fuzzy_ratio(before_comma.lower(), known_last_name.lower())
                                
                                if last_name_score > 0.8:
                                    # Check if first name/initial matches
                                    known_first = known_parts[0] if known_parts else ""
                                    
                                    # Handle initial (single letter or letter with period)
                                    if len(after_comma) <= 2 and after_comma[0].isalpha():
                                        # It's an initial - check if it matches first letter of known first name
                                        if after_comma[0].upper() == known_first[0].upper():
                                            # Strong match: last name + initial match
                                            score = max(score, 0.95)
                                    else:
                                        # It's a full first name - fuzzy match
                                        first_name_score = fuzzy_ratio(after_comma.lower(), known_first.lower())
                                        if first_name_score > 0.8:
                                            score = max(score, first_name_score * 0.95)
                    
                    # Strategy 6: Handle OCR errors (e.g., "No&" -> "Noé")
                    # Try replacing common OCR errors
                    cleaned_name = member_name.replace('&', 'é').replace('0', 'o').replace('1', 'i')
                    if cleaned_name != member_name:
                        clean_score = fuzzy_ratio(cleaned_name.lower(), known_name.lower())
                        if clean_score > 0.8:
                            score = max(score, clean_score * 0.95)
                    
                    # Strategy 7: Direct character replacement for known OCR issues
                    # Common: & -> é, @ -> a, # -> h, etc.
                    ocr_replacements = {
                        '&': 'é', '@': 'a', '#': 'h', '$': 's', '%': 'p',
                        '0': 'o', '1': 'i', '3': 'e', '5': 's', '7': 't'
                    }
                    for ocr_char, correct_char in ocr_replacements.items():
                        if ocr_char in member_name:
                            test_name = member_name.replace(ocr_char, correct_char)
                            test_score = fuzzy_ratio(test_name.lower(), known_name.lower())
                            if test_score > 0.85:
                                score = max(score, test_score * 0.95)
                    
                    if score > best_score:
                        best_score = score
                        best_match = (known_name, party)
                
                # Lower threshold to 0.6 to catch more matches
                if best_score >= 0.60 and best_match:
                    matched_party = best_match[1]
                    matched_name = best_match[0]
                    matched_known_members.add(matched_name)
                    print(f"Matched '{member_name}' to '{matched_name}' (score: {best_score:.2f}), party: {matched_party}")
            else:
                # Empty or very short name - try to find unmatched member in same column
                # For now, skip and log
                print(f"Warning: Empty or very short name: '{member_name}' - counting as unmatched vote")
            
            if matched_party:
                member = MemberVote(
                    name=member_name if member_name else matched_name,
                    vote=block['vote'],
                    bbox=block['bbox'],
                    color_hsv=block['color'],
                    shape=block['shape']
                )
                party_members[matched_party].append(member)
            else:
                print(f"Warning: Could not assign member '{member_name}' to any party")
        
        # Now find unmatched members and assign them based on party member counts
        # This handles gray boxes (absent members) that have no text
        unmatched_members = []
        for known_name, party in member_party_mapping.items():
            if known_name not in matched_known_members:
                unmatched_members.append((known_name, party))
        
        # Group unmatched by party
        unmatched_by_party = defaultdict(list)
        for name, party in unmatched_members:
            unmatched_by_party[party].append(name)
        
        # For each party, check if we have fewer detected members than expected
        for party_name, expected_members in unmatched_by_party.items():
            detected_count = len(party_members[party_name])
            expected_count = len([name for name, p in member_party_mapping.items() if p == party_name])
            
            if detected_count < expected_count:
                # We're missing some members - they're likely gray boxes
                missing_count = expected_count - detected_count
                missing_members = expected_members[:missing_count]
                
                print(f"Adding {missing_count} unmatched members to {party_name}: {missing_members}")
                
                # Create placeholder members for missing ones
                for missing_name in missing_members:
                    member = MemberVote(
                        name=missing_name,
                        vote='GRAY',  # Absent members are gray
                        bbox=(0, 0, 0, 0),  # No bbox info
                        color_hsv=(0, 0, 0),
                        shape='unknown'
                    )
                    party_members[party_name].append(member)
        
        # Create Party objects with calculated bboxes
        parties = []
        for party_name, members in party_members.items():
            # Calculate bbox from member positions, excluding members with (0,0,0,0) bbox
            if members:
                valid_members = [m for m in members if m.bbox != (0, 0, 0, 0)]
                if valid_members:
                    min_x = min(m.bbox[0] for m in valid_members)
                    min_y = min(m.bbox[1] for m in valid_members)
                    max_x = max(m.bbox[0] + m.bbox[2] for m in valid_members)
                    max_y = max(m.bbox[1] + m.bbox[3] for m in valid_members)
                    bbox = (min_x, min_y, max_x - min_x, max_y - min_y)
                else:
                    bbox = (0, 0, 0, 0)
            else:
                bbox = (0, 0, 0, 0)
            
            party = Party(
                name=party_name,
                bbox=bbox,
                members=members
            )
            parties.append(party)
        
        return parties


def load_names_from_file(filepath: str) -> List[str]:
    """Load names from text file (one per line)"""
    path = Path(filepath)
    if not path.exists():
        return []
    
    with open(path, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip()]


def load_party_mapping(filepath: str) -> Dict[str, str]:
    """Load party name mapping from JSON file"""
    path = Path(filepath)
    if not path.exists():
        return {}
    
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_member_party_mapping(filepath: str) -> Dict[str, str]:
    """Load member-party mapping from JSON file"""
    path = Path(filepath)
    if not path.exists():
        return {}
    
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        # The JSON has a 'member_party' key
        if 'member_party' in data:
            return data['member_party']
        return data


def main():
    parser = argparse.ArgumentParser(description='Extract voting results from city council images')
    parser.add_argument('image', help='Path to input image')
    parser.add_argument('--output', '-o', default='votes.json', help='Output JSON file')
    parser.add_argument('--parties-file', help='File with known party names')
    parser.add_argument('--members-file', help='File with known member names')
    parser.add_argument('--party-mapping', help='JSON file mapping OCR results to party names')
    parser.add_argument('--member-party-mapping', help='JSON file mapping member names to parties (from HTML)')
    parser.add_argument('--shape', choices=['auto', 'rectangle', 'circle', 'donut'], 
                       default='auto', help='Force specific shape type')
    parser.add_argument('--visualize', action='store_true', help='Save visualization image')
    
    args = parser.parse_args()
    
    # Load known names
    known_parties = load_names_from_file(args.parties_file) if args.parties_file else None
    known_members = load_names_from_file(args.members_file) if args.members_file else None
    party_mapping = load_party_mapping(args.party_mapping) if args.party_mapping else {}
    member_party_mapping = load_member_party_mapping(args.member_party_mapping) if args.member_party_mapping else None
    
    # Create extractor
    config = {'shape_type': args.shape}
    extractor = VoteExtractor(config)
    
    # Extract
    results = extractor.extract(args.image, known_parties, known_members, party_mapping, member_party_mapping)
    
    # Save results
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(results.to_dict(), f, indent=2, ensure_ascii=False)
    
    print(f"\nResults saved to: {args.output}")
    
    # Visualization
    if args.visualize:
        viz_image = extractor.image.copy()
        
        # Draw OB box
        if results.ob_vote:
            x, y, w, h = results.ob_vote['bbox']
            cv2.rectangle(viz_image, (x, y), (x+w, y+h), (0, 255, 0), 2)
            cv2.putText(viz_image, f"OB: {results.ob_vote['vote']}", (x, y-10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        
        # Draw party and member boxes
        for party in results.parties:
            x, y, w, h = party.bbox
            cv2.rectangle(viz_image, (x, y), (x+w, y+h), (255, 0, 0), 2)
            cv2.putText(viz_image, party.name, (x, y-10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)
            
            for member in party.members:
                mx, my, mw, mh = member.bbox
                color = (0, 255, 0) if member.vote == "JA" else \
                       (0, 0, 255) if member.vote == "NEIN" else \
                       (255, 0, 0) if member.vote == "ENTHALTUNG" else (128, 128, 128)
                cv2.rectangle(viz_image, (mx, my), (mx+mw, my+mh), color, 2)
        
        viz_path = args.output.replace('.json', '_viz.png')
        cv2.imwrite(viz_path, viz_image)
        print(f"Visualization saved to: {viz_path}")


if __name__ == '__main__':
    main()
