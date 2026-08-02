#!/usr/bin/env python3
"""Visualize the detected regions on the image"""

import cv2
import numpy as np

# Load image
img = cv2.imread('abstimmung.png')
hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

# Create masks
ja_lower = np.array([19, 100, 100])
ja_upper = np.array([90, 255, 255])
ja_mask = cv2.inRange(hsv, ja_lower, ja_upper)

nein_lower1 = np.array([0, 100, 100])
nein_upper1 = np.array([15, 255, 255])
nein_mask1 = cv2.inRange(hsv, nein_lower1, nein_upper1)
nein_lower2 = np.array([165, 100, 100])
nein_upper2 = np.array([180, 255, 255])
nein_mask2 = cv2.inRange(hsv, nein_lower2, nein_upper2)
nein_mask = cv2.bitwise_or(nein_mask1, nein_mask2)

enth_lower = np.array([90, 100, 100])
enth_upper = np.array([140, 255, 255])
enth_mask = cv2.inRange(hsv, enth_lower, enth_upper)

# Find contours
ja_contours, _ = cv2.findContours(ja_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
nein_contours, _ = cv2.findContours(nein_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
enth_contours, _ = cv2.findContours(enth_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

# Draw on image
viz = img.copy()

# Draw JA contours (green)
for contour in ja_contours:
    area = cv2.contourArea(contour)
    if area > 5000:
        x, y, w, h = cv2.boundingRect(contour)
        cv2.rectangle(viz, (x, y), (x+w, y+h), (0, 255, 0), 2)
        cv2.putText(viz, 'JA', (x, y-5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

# Draw NEIN contours (red)
for contour in nein_contours:
    area = cv2.contourArea(contour)
    if area > 5000:
        x, y, w, h = cv2.boundingRect(contour)
        cv2.rectangle(viz, (x, y), (x+w, y+h), (0, 0, 255), 2)
        cv2.putText(viz, 'NEIN', (x, y-5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)

# Draw ENTHALTUNG contours (blue)
for contour in enth_contours:
    area = cv2.contourArea(contour)
    if area > 100:
        x, y, w, h = cv2.boundingRect(contour)
        cv2.rectangle(viz, (x, y), (x+w, y+h), (255, 0, 0), 2)
        cv2.putText(viz, 'ENTH', (x, y-5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)

# Draw grid lines for reference
height, width = viz.shape[:2]
for y in range(0, height, 200):
    cv2.line(viz, (0, y), (width, y), (128, 128, 128), 1)
    cv2.putText(viz, str(y), (5, y+15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (128, 128, 128), 1)

for x in range(0, width, 200):
    cv2.line(viz, (x, 0), (x, height), (128, 128, 128), 1)
    cv2.putText(viz, str(x), (x+5, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (128, 128, 128), 1)

cv2.imwrite('debug_layout.png', viz)
print(f"Saved layout visualization to debug_layout.png")
print(f"Image size: {width}x{height}")
print(f"\nJA contours > 5000: {sum(1 for c in ja_contours if cv2.contourArea(c) > 5000)}")
print(f"NEIN contours > 5000: {sum(1 for c in nein_contours if cv2.contourArea(c) > 5000)}")
print(f"ENTH contours > 100: {sum(1 for c in enth_contours if cv2.contourArea(c) > 100)}")

# Also check the top region for donuts
print(f"\n\nAnalyzing top region (y < 600) for donuts...")
top_region = img[0:600, :]
top_hsv = hsv[0:600, :]

# Look for circular shapes in top region
gray = cv2.cvtColor(top_region, cv2.COLOR_BGR2GRAY)
edges = cv2.Canny(gray, 50, 150)
circles = cv2.HoughCircles(gray, cv2.HOUGH_GRADIENT, 1, 50,
                           param1=150, param2=30, minRadius=30, maxRadius=200)

if circles is not None:
    circles = np.uint16(np.around(circles))
    print(f"Found {len(circles[0])} circles in top region")
    for i, circle in enumerate(circles[0][:10]):
        print(f"  Circle {i+1}: center=({circle[0]}, {circle[1]}), radius={circle[2]}")
else:
    print("No circles found in top region")
