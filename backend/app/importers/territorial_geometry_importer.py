from app.importers.geojson_utils import parse_feature_collection,validate_geometry
class TerritorialGeometryImporter:
    parse=staticmethod(parse_feature_collection);validate_geometry=staticmethod(validate_geometry)
