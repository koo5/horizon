#!/usr/bin/env python3

"""
Interactive linux app in python with kivy. The app will take a directory as a command line parameter. It will scan the directory recursively for jpeg files that contain location and orientation information ('GPS GPSImgDirection') in metadata. It will index all these files in an in-memory list.

The main window will be split in two halves: the right half displays a map from a public api, such as open street map. The center of the map represents current user location, and is marked by a red marker point. Each geolocated photo is represented on the map with a small thumbnail.

The map can be panned, zoomed, and rotated, triggering an event handler that lays out relevant photos in the left pane.

The left pane is dedicated to displaying the photos. Photos are selected and arranged by their geolocation and orientation information, with photos near user location overlaying those further away, as if one was looking from the current map location in given direction. The left panel overdraws when the right panel (user location, orientation and map zoom) changes.
"""

import os
import sys
import exifread
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.image import Image
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.floatlayout import FloatLayout
from kivy_garden.mapview import MapView, MapMarkerPopup, MapMarker
from kivy.uix.widget import Widget
from kivy.graphics import Color, Ellipse


# Helper function to extract latitude and longitude from EXIF data
def get_decimal_coordinates(tags):
	def _convert_to_degrees(value):
		d = float(value.values[0].num) / float(value.values[0].den)
		m = float(value.values[1].num) / float(value.values[1].den)
		s = float(value.values[2].num) / float(value.values[2].den)
		return d + (m / 60.0) + (s / 3600.0)

	gps_latitude = tags.get("GPS GPSLatitude")
	gps_latitude_ref = tags.get("GPS GPSLatitudeRef")
	gps_longitude = tags.get("GPS GPSLongitude")
	gps_longitude_ref = tags.get("GPS GPSLongitudeRef")

	if gps_latitude and gps_longitude:
		lat = _convert_to_degrees(gps_latitude)
		lon = _convert_to_degrees(gps_longitude)

		if gps_latitude_ref.values[0] != "N":
			lat = -lat
		if gps_longitude_ref.values[0] != "E":
			lon = -lon

		return lat, lon
	return None, None


# Function to get orientation from EXIF data
def get_orientation(tags):
	r = tags.get('GPS GPSImgDirection', None)
	if r is None:
		return None
	return r.values[0].num / r.values[0].den


# Recursive directory scan for JPEG files with EXIF metadata
def scan_directory_for_images(directory):
	images = []
	for root, _, files in os.walk(directory):
		for file in files:
			if file.lower().endswith(".jpg") or file.lower().endswith(".jpeg"):
				filepath = os.path.join(root, file)
				try:
					with open(filepath, 'rb') as f:
						tags = exifread.process_file(f)
						lat, lon = get_decimal_coordinates(tags)
						orientation = get_orientation(tags)
						if lat and lon:
							images.append({'path': filepath, 'latitude': lat, 'longitude': lon, 'orientation': orientation})
				except Exception as e:
					print(f"Error processing {filepath}: {e}")
	return images


class PhotoMapApp(App):
	def __init__(self, directory, **kwargs):
		super().__init__(**kwargs)
		self.images_with_metadata = scan_directory_for_images(directory)

	def build(self):
		self.root = BoxLayout(orientation='horizontal')

		# Left pane: Image viewer
		self.left_pane = ScrollView(size_hint=(0.5, 1))
		self.left_layout = GridLayout(cols=4, rows=4, size_hint_y=None)
		self.left_layout.bind(minimum_height=self.left_layout.setter('height'), minimum_width=self.left_layout.setter('width'))
		self.left_pane.add_widget(self.left_layout)

		self.load_images()

		# Right pane: Map viewer
		self.right_pane = GridLayout(cols=1, rows=1, size_hint=(0.5, 1))
		self.map_view = MapView(zoom=5, lat=0, lon=0)
		self.map_view.map_source.min_zoom = 1


		self.map_view.bind(on_map_relocated=self.on_map_event)
		self.map_view.bind(on_map_rotated=self.on_map_event)
		self.right_pane.add_widget(self.map_view)

		# Add user location marker
		self.user_location_marker = MapMarker(lat=0, lon=0, source='user.png')
		self.map_view.add_marker(self.user_location_marker)

		for img in self.images_with_metadata:
			marker = MapMarkerPopup(lat=img['latitude'], lon=img['longitude'])
			marker.add_widget(Image(source=img['path'], size_hint=(None, None), size=(150, 150)))
			self.map_view.add_marker(marker)

		# Add the panes to the root layout
		self.root.add_widget(self.left_pane)
		self.root.add_widget(self.right_pane)

		return self.root

	def load_images(self):
		print()
		print("Loading images")
		self.left_layout.clear_widgets()
		for img in self.images_with_metadata:
			print(f"Image: {img}")
			image_widget = Image(source=img['path'], size_hint_y=None, height=300)
			self.left_layout.add_widget(image_widget)

	def on_map_event(self, instance, value, idk):
		print(f"Map event: {instance}, {value}, {idk}")
		self.load_images()


if __name__ == '__main__':
	if len(sys.argv) != 2:
		print("Usage: python main.py <directory>")
		sys.exit(1)
	directory = sys.argv[1]
	PhotoMapApp(directory).run()
