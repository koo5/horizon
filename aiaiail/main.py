#!/usr/bin/env python3
import sys
import os
import argparse
import math
from PySide6.QtWidgets import QApplication, QMainWindow, QSplitter, QWidget, QVBoxLayout, QLabel, QScrollArea
from PySide6.QtCore import Qt, Slot, QUrl, QObject, Signal
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtGui import QPixmap
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS

# Set environment variable to ignore GPU blocklist (optional)
# os.environ['QTWEBENGINE_CHROMIUM_FLAGS'] = '--ignore-gpu-blocklist'

def parse_args():
    parser = argparse.ArgumentParser(description='Photo Map Viewer')
    parser.add_argument('directory', help='Directory to scan for photos')
    return parser.parse_args()

def get_exif_data(image):
    exif_data = {}
    info = image._getexif()
    if info:
        for tag, value in info.items():
            decoded = TAGS.get(tag, tag)
            if decoded == "GPSInfo":
                gps_info = {}
                for t in value:
                    sub_decoded = GPSTAGS.get(t, t)
                    gps_info[sub_decoded] = value[t]
                exif_data[decoded] = gps_info
            else:
                exif_data[decoded] = value
    return exif_data

def get_lat_lon_direction(exif_data):
    gps_info = exif_data.get("GPSInfo")
    if not gps_info:
        return None, None, None

    def _convert_to_degrees(value):
        d = value[0]
        m = value[1]
        s = value[2]
        return d + (m / 60.0) + (s / 3600.0)

    lat = lon = direction = None

    try:
        lat = _convert_to_degrees(gps_info["GPSLatitude"])
        if gps_info["GPSLatitudeRef"] != "N":
            lat = -lat

        lon = _convert_to_degrees(gps_info["GPSLongitude"])
        if gps_info["GPSLongitudeRef"] != "E":
            lon = -lon

        direction = gps_info.get("GPSImgDirection")
        if isinstance(direction, tuple):
            direction = direction[0] / direction[1]
        elif isinstance(direction, (int, float)):
            direction = float(direction)
    except KeyError:
        pass

    return lat, lon, direction

def scan_directory(directory):
    photo_list = []
    for root, dirs, files in os.walk(directory):
        for filename in files:
            if filename.lower().endswith(('.jpg', '.jpeg')):
                filepath = os.path.join(root, filename)
                try:
                    image = Image.open(filepath)
                    exif_data = get_exif_data(image)
                    lat, lon, direction = get_lat_lon_direction(exif_data)
                    if lat is not None and lon is not None and direction is not None:
                        photo_data = {
                            'filepath': filepath,
                            'latitude': lat,
                            'longitude': lon,
                            'direction': direction
                        }
                        photo_list.append(photo_data)
                except Exception as e:
                    print(f"Error processing {filepath}: {e}")
    return photo_list

def haversine(lon1, lat1, lon2, lat2):
    # Haversine formula
    lon1_rad, lat1_rad = map(math.radians, [lon1, lat1])
    lon2_rad, lat2_rad = map(math.radians, [lon2, lat2])
    dlon = lon2_rad - lon1_rad
    dlat = lat2_rad - lat1_rad
    a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    r = 6371  # Earth radius in kilometers
    return c * r

def compute_bearing(lat1, lon1, lat2, lon2):
    # Bearing calculation
    lat1_rad, lat2_rad = map(math.radians, [lat1, lat2])
    diffLong = math.radians(lon2 - lon1)
    x = math.sin(diffLong) * math.cos(lat2_rad)
    y = math.cos(lat1_rad) * math.sin(lat2_rad) - (math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(diffLong))
    initial_bearing = math.atan2(x, y)
    compass_bearing = (math.degrees(initial_bearing) + 360) % 360
    return compass_bearing

def angle_difference(a1, a2):
    diff = (a2 - a1 + 180 + 360) % 360 - 180
    return diff

class MapBackend(QObject):
    mapChangedSignal = Signal(float, float, float)  # lat, lng, rotation

    @Slot(float, float, float)
    def mapChanged(self, lat, lng, rotation):
        self.mapChangedSignal.emit(lat, lng, rotation)

class MainWindow(QMainWindow):
    def __init__(self, photo_list):
        super().__init__()
        self.photo_list = photo_list
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Photo Map Viewer")
        splitter = QSplitter(Qt.Horizontal)

        # Left pane for photos
        self.left_widget = QWidget()
        self.left_layout = QVBoxLayout()
        self.left_widget.setLayout(self.left_layout)
        # Add scroll area to handle many photos
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(self.left_widget)
        splitter.addWidget(scroll_area)

        # Right pane for the map
        self.right_widget = QWebEngineView()
        splitter.addWidget(self.right_widget)

        self.setCentralWidget(splitter)

        # Set up the web channel for communication
        self.channel = QWebChannel()
        self.backend = MapBackend()
        self.backend.mapChangedSignal.connect(self.on_map_changed)
        self.channel.registerObject('backend', self.backend)
        self.right_widget.page().setWebChannel(self.channel)

        self.load_map()

    def load_map(self):
        # Load the map HTML code
        html_content = self.get_map_html()
        self.right_widget.setHtml(html_content, QUrl(''))

    def get_map_html(self):
        # Return the HTML code for the map
        return map_html_code

    @Slot(float, float, float)
    def on_map_changed(self, lat, lng, rotation):
        self.update_left_pane(lat, lng, rotation)

    def update_left_pane(self, lat, lng, rotation):
        # Clear the left layout
        for i in reversed(range(self.left_layout.count())):
            widget_to_remove = self.left_layout.itemAt(i).widget()
            self.left_layout.removeWidget(widget_to_remove)
            widget_to_remove.setParent(None)

        # Compute which photos to display
        selected_photos = []
        for photo in self.photo_list:
            # Compute distance and angle
            distance = haversine(lng, lat, photo['longitude'], photo['latitude'])
            angle_to_photo = compute_bearing(lat, lng, photo['latitude'], photo['longitude'])
            angle_diff = angle_difference(rotation, angle_to_photo)
            if abs(angle_diff) <= 30:  # within 30 degrees of map orientation
                selected_photos.append((distance, photo))

        # Sort by distance (nearest first)
        selected_photos.sort(key=lambda x: x[0])

        # Display photos
        for distance, photo in selected_photos:
            label = QLabel()
            pixmap = QPixmap(photo['filepath'])
            label.setPixmap(pixmap.scaledToWidth(200))
            self.left_layout.addWidget(label)

map_html_code = '''
<!DOCTYPE html>
<html>
<head>
    <title>Map</title>
    <meta charset="utf-8" />
    <style>
        html, body, #map { height: 100%; margin: 0; padding: 0; }
    </style>
    <!-- Leaflet CSS -->
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <!-- Leaflet JS -->
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <!-- Leaflet Rotation Plugin -->
    <script src="https://raw.githubusercontent.com/w8r/Leaflet.Rotate/master/dist/leaflet-rotate.min.js"></script>
    <!-- Qt WebChannel JS -->
    <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
</head>
<body>
    <div id="map"></div>
    <script type="text/javascript">
        var backend;
        new QWebChannel(qt.webChannelTransport, function(channel) {
            backend = channel.objects.backend;
        });

        var map = L.map('map').setView([0, 0], 2);

        // Add OpenStreetMap tile layer
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; OpenStreetMap contributors'
        }).addTo(map);

        // Add rotation control
        var rotationControl = L.control.rotation();
        rotationControl.addTo(map);

        // User location marker
        var userMarker = L.marker([0, 0]).addTo(map);

        function sendMapChanged() {
            var center = map.getCenter();
            var rotation = map.getBearing() || 0;
            backend.mapChanged(center.lat, center.lng, rotation);
        }

        map.on('moveend', sendMapChanged);
        map.on('rotateend', sendMapChanged);
        map.on('zoomend', sendMapChanged);

        // Initial signal
        map.whenReady(sendMapChanged);
    </script>
</body>
</html>
'''

def main():
    app = QApplication(sys.argv)
    args = parse_args()
    photo_list = scan_directory(args.directory)
    if not photo_list:
        print("No photos with GPS and orientation data found in the specified directory.")
        sys.exit(1)
    window = MainWindow(photo_list)
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
