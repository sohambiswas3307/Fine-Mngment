"""
Classic CV-based Traffic Violation Detector (Non-YOLO)
=====================================================
Uses Background Subtraction (MOG2) and Contour Analysis to detect vehicles.
Uses Color Masking to detect Traffic Light status.

NO YOLO / ULTRALYTICS REQUIRED.
"""

import cv2
import numpy as np
import time
import collections

class ViolationDetector:
    def __init__(self, camera_id='CAM-001', stop_line_ratio=0.70):
        self.camera_id = camera_id
        self.stop_line_ratio = stop_line_ratio
        
        # Background Subtractor for vehicle detection
        self.back_sub = cv2.createBackgroundSubtractorMOG2(history=500, varThreshold=50, detectShadows=True)
        
        # Tracking state
        self.next_track_id = 1
        self.tracks = {}  # id -> {last_centroid, last_bottom_y, last_violation_time}
        self._last_violation_t = {}
        
    def _get_centroid(self, x, y, w, h):
        return (int(x + w/2), int(y + h/2))

    def _analyze_light(self, frame):
        """
        Classic CV approach: Search for high-intensity red/green blobs 
        in the top half of the frame.
        """
        h, w = frame.shape[:2]
        roi = frame[0:h//2, :] # Search top half for lights
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        
        # Red ranges
        lower_red1 = np.array([0, 150, 150])
        upper_red1 = np.array([10, 255, 255])
        lower_red2 = np.array([170, 150, 150])
        upper_red2 = np.array([180, 255, 255])
        
        # Green range
        lower_green = np.array([40, 100, 100])
        upper_green = np.array([90, 255, 255])
        
        mask_red = cv2.inRange(hsv, lower_red1, upper_red1) + cv2.inRange(hsv, lower_red2, upper_red2)
        mask_green = cv2.inRange(hsv, lower_green, upper_green)
        
        red_pixels = cv2.countNonZero(mask_red)
        green_pixels = cv2.countNonZero(mask_green)
        
        if red_pixels > 50 and red_pixels > green_pixels:
            return 'red'
        elif green_pixels > 50:
            return 'green'
        return 'unknown'

    def process(self, video_path, output_path=None):
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise IOError(f"Cannot open video: {video_path}")

        W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        FPS = max(1, int(cap.get(cv2.CAP_PROP_FPS)))
        total = max(1, int(cap.get(cv2.CAP_PROP_FRAME_COUNT)))
        stop_line_y = int(H * self.stop_line_ratio)

        writer = None
        if output_path:
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            writer = cv2.VideoWriter(output_path, fourcc, FPS, (W, H))

        frame_no = 0
        light_state_buffer = collections.deque(maxlen=15)

        try:
            while True:
                ret, frame = cap.read()
                if not ret: break
                
                frame_no += 1
                progress = int(frame_no / total * 100)
                timestamp = frame_no / FPS
                violations = []

                # 1. Traffic Light Analysis
                current_light = self._analyze_light(frame)
                light_state_buffer.append(current_light)
                dominant_light = collections.Counter(light_state_buffer).most_common(1)[0][0]

                # 2. Vehicle Detection (Background Subtraction)
                fg_mask = self.back_sub.apply(frame)
                _, thresh = cv2.threshold(fg_mask, 250, 255, cv2.THRESH_BINARY)
                kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
                closing = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
                contours, _ = cv2.findContours(closing, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

                current_detections = []
                for cnt in contours:
                    area = cv2.contourArea(cnt)
                    if area < 1500: continue # Skip small noise
                    x, y, w, h = cv2.boundingRect(cnt)
                    current_detections.append((x, y, w, h))

                # 3. Simple Centroid Tracking & Violation Logic
                new_tracks = {}
                for (x, y, w, h) in current_detections:
                    cx, cy = self._get_centroid(x, y, w, h)
                    bottom_y = y + h
                    
                    # Match with existing tracks
                    matched_id = None
                    min_dist = 100
                    for tid, tdata in self.tracks.items():
                        dist = np.sqrt((cx - tdata['cx'])**2 + (cy - tdata['cy'])**2)
                        if dist < min_dist:
                            min_dist = dist
                            matched_id = tid
                    
                    if matched_id is None:
                        matched_id = self.next_track_id
                        self.next_track_id += 1
                    
                    # Check for Signal Jumping
                    if matched_id in self.tracks:
                        prev_y = self.tracks[matched_id]['bottom_y']
                        if dominant_light == 'red' and prev_y < stop_line_y <= bottom_y:
                            last_v = self._last_violation_t.get(matched_id, 0)
                            if time.time() - last_v > 5: # Cooldown
                                violations.append({
                                    'type': 'Signal Jumping',
                                    'confidence': 85,
                                    'timestamp': round(timestamp, 2),
                                    'camera_id': self.camera_id,
                                    'frame_no': frame_no
                                })
                                self._last_violation_t[matched_id] = time.time()
                                cv2.putText(frame, "VIOLATION: SIGNAL JUMP!", (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,0,255), 2)

                    new_tracks[matched_id] = {'cx': cx, 'cy': cy, 'bottom_y': bottom_y}
                    
                    # Draw boxes
                    cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
                    cv2.putText(frame, f"Vehicle {matched_id}", (x, y-5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

                self.tracks = new_tracks

                # Annotations
                cv2.line(frame, (0, stop_line_y), (W, stop_line_y), (0, 255, 255), 2)
                light_color = (0,0,255) if dominant_light == 'red' else (0,255,0) if dominant_light == 'green' else (128,128,128)
                cv2.circle(frame, (W-50, 50), 25, light_color, -1)
                cv2.putText(frame, f"LIGHT: {dominant_light.upper()}", (W-150, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.6, light_color, 2)

                if writer: writer.write(frame)
                yield progress, frame, violations

        finally:
            cap.release()
            if writer: writer.release()
