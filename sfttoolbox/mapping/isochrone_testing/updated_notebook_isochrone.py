# NotebookIsochroneGenerator — GraphML-backed, concave hull (alphashape), NO 0.9 slowdown
from typing import Optional
import osmnx as ox
import networkx as nx
from alphashape import alphashape
from shapely.geometry import Polygon

class UpdatedNotebookIsochroneGenerator:
    def __init__(self, graphml_path: str = "somerset_geojson_files/somerset_road_network_bb.graphml",
                 default_speed: float = 48.28):
        """
        Loads a road network from a local GraphML.
        Changes from prior version:
          - Removed 0.9 speed multiplier
          - Always uses alphashape (concave hull) for polygons
        """
        self.default_speed = default_speed
        self.graphml_path = graphml_path
        self.G: Optional[nx.MultiDiGraph] = ox.load_graphml(graphml_path)
        self.__update_graph_with_times()

    def __update_graph_with_times(self) -> None:
        for _, _, _, data in self.G.edges(data=True, keys=True):
            max_speed = data.get("maxspeed")
            if max_speed:
                if isinstance(max_speed, list):
                    vals = [self.__parse_max_speed_to_kmh(s) for s in max_speed]
                    speed = sum(vals) / len(vals)
                else:
                    speed = self.__parse_max_speed_to_kmh(max_speed)
            else:
                speed = self.default_speed

            meters_per_minute = speed * 1000 / 60.0  # NO slowdown multiplier
            if data.get("length") is not None and meters_per_minute > 0:
                data["time"] = float(data["length"]) / meters_per_minute

    def __parse_max_speed_to_kmh(self, max_speed: str) -> float:
        if not max_speed or str(max_speed).strip().lower() == "none":
            return self.default_speed
        conv = 1.60934 if "mph" in str(max_speed).lower() else 1.0
        try:
            val = float(str(max_speed).split()[0])
            return val * conv
        except Exception:
            return self.default_speed

    def generate_isochrone(
        self,
        lat: float,
        lon: float,
        max_drive_time: float,
        alpha: float = 30.0,
    ) -> Polygon:
        center_node = ox.distance.nearest_nodes(self.G, lon, lat)
        subG = nx.ego_graph(self.G, center_node, radius=max_drive_time, distance="time")

        pts = [(data["x"], data["y"]) for _, data in subG.nodes(data=True)]
        poly = alphashape(pts, alpha=alpha)  # concave by default now

        # Fallback: if MultiPolygon, retry with smaller alpha
        if poly and getattr(poly, "geom_type", "") == "MultiPolygon":
            poly = alphashape(pts, alpha=alpha / 2.0)

        return poly