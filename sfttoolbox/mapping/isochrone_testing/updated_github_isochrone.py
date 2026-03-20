# UpdatedGitHubIsochroneGenerator — OSM-backed, concave hull (alphashape), NO 0.9 slowdown
from typing import Optional
import osmnx as ox
import networkx as nx
from alphashape import alphashape
from shapely.geometry import Polygon

class UpdatedGitHubIsochroneGenerator:
    def __init__(self, default_speed: float = 48.28032):
        """
        Loads graphs from OSM by place or point.
        Changes from prior version:
          - Removed 0.9 speed multiplier
          - Always uses alphashape (concave hull) for polygons
        """
        self.default_speed = default_speed
        self.G: Optional[nx.MultiDiGraph] = None
        self.graphs = {}  # keep compatibility with place_name keying

    def load_graph(
        self,
        place_name: Optional[str] = None,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        distance: float = 64374,            # ~40 miles in meters
        network_type: str = "drive",
    ) -> nx.MultiDiGraph:
        if lat is not None and lon is not None:
            G = ox.graph_from_point(
                center_point=[lat, lon],
                dist=distance,
                dist_type="network",
                network_type=network_type,
                simplify=True,
            )
            # if loaded by lat/lon, still let caller reference by place_name they provide
            key = place_name or f"{lat:.5f},{lon:.5f}"
        elif place_name:
            G = ox.graph_from_place(place_name, network_type=network_type)
            key = place_name
        else:
            raise ValueError("Provide either place_name or (lat, lon) to load a graph.")

        self.__update_graph_with_times(G)
        self.graphs[key] = G
        self.G = G
        return G

    def __update_graph_with_times(self, G: nx.MultiDiGraph) -> None:
        for _, _, _, data in G.edges(data=True, keys=True):
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
        place_name: str,
        isochrone_name: str,   # kept for compatibility; registry not used here
        lat: float,
        lon: float,
        drive_time: float,
        alpha: float = 30.0,
    ) -> Polygon:
        # use the graph keyed by place_name that was loaded earlier
        G = self.graphs.get(place_name)
        if G is None:
            raise RuntimeError(f"No graph loaded for place_name='{place_name}'. Call load_graph(...) first.")

        center_node = ox.distance.nearest_nodes(G, lon, lat)
        subG = nx.ego_graph(G, center_node, radius=drive_time, distance="time")

        pts = [(data["x"], data["y"]) for _, data in subG.nodes(data=True)]
        poly = alphashape(pts, alpha=alpha)  # concave by default now

        # Fallback: if MultiPolygon, retry with smaller alpha
        if poly and getattr(poly, "geom_type", "") == "MultiPolygon":
            poly = alphashape(pts, alpha=alpha / 2.0)

        return poly