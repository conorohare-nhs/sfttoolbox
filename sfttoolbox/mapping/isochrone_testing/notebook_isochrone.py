# --- Standard library ---
import functools
import os

# --- Third‑party libraries ---
import pandas as pd
import geopandas as gpd
import networkx as nx
import osmnx as ox
from alphashape import alphashape
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

# --- External client libraries ---
import warehouse_client

# --- Project modules ---
from sfttoolbox import mapping

class IsochroneGenerator:
    def __init__(self):
        """
        Initialize the IsochroneGenerator.

        Parameters:
        - graph_path (str): Path to the road network graphml file.
        """
        self.DEFAULT_SPEED: float = 48.28
        self.G: nx.Graph = ox.load_graphml('../examples/somerset_geojson_files/somerset_road_network_bb.graphml')
        self.__update_graph_with_times()

    def __update_graph_with_times(self) -> None:
        """
        Update graph edges with travel times based on maximum speed limits.
        """
        for u, v, k, data in self.G.edges(data=True, keys=True):
            if max_speed := data.get("maxspeed"):
                if isinstance(max_speed, list):
                    speed = sum(max_speeds := [self.__parse_max_speed_to_kmh(speed) for speed in max_speed]) / len(max_speeds)
                else:
                    speed = self.__parse_max_speed_to_kmh(max_speed)
            else:
                speed = self.DEFAULT_SPEED

            meters_per_minute = speed * 1000 / 60 #km per hour to m per minute       
            data['time'] = data['length'] / meters_per_minute

    def __parse_max_speed_to_kmh(self, max_speed: str) -> float:
        """
        Parse maximum speed string to kilometers per hour.

        Parameters:
        - max_speed (str): Maximum speed string.

        Returns:
        - float: Speed in kilometers per hour.
        """
        # convert to km/h if no units, set to 0
        conversion = 1.60934 if "mph" in max_speed else 0
        speed = int(max_speed.split()[0]) * conversion if conversion else self.DEFAULT_SPEED
        return speed

    @functools.lru_cache
    def generate_isochrone(self, lat: float, lon: float, max_drive_time: float, use_alphashape: bool = False) -> Polygon:
        """
        Generate isochrone polygons based on travel time.

        Parameters:
        - lat (float): Latitude of the center point.
        - lon (float): Longitude of the center point.
        - max_drive_time (float): Maximum travel time in minutes.
        - use_alphashape (bool): Use alphashape to generate concave hulls.

        Returns:
        - Union[Polygon, List[Polygon]]: Isochrone polygon or list of polygons.
        """
        # TODO: check if nearest node is too far away?
        center_node = ox.distance.nearest_nodes(self.G, lon, lat)

        nodes_within_travel_time = [
            Point(data['x'], data['y'])
            for _, data in nx.ego_graph(self.G, center_node, radius=max_drive_time, distance='time').nodes(data=True)
        ]

        # TODO: Check if this is meant to be within the multi polygon section
        polys = gpd.GeoSeries(nodes_within_travel_time).unary_union.convex_hull
        if use_alphashape:
            # TODO: Check why the alphas are inconsistent
            if alphashape([(x.x, x.y) for x in nodes_within_travel_time], alpha=20).geom_type == 'MultiPolygon':
                pass
            else:
                polys = alphashape([(x.x, x.y) for x in nodes_within_travel_time], alpha=10)

        return polys