import json
from datetime import date
from uuid import uuid4
import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session
from app.importers.geojson_utils import parse_feature_collection,validate_geometry
from app.models.user import User
from app.models.assignments import CampaignUser,TerritorialAssignment
from app.core.security import hash_password
from app.services.role_service import RoleService
from app.schemas.campaign import CampaignCreate
from app.schemas.historical import DataSourceCreate
from app.schemas.maps import GeoJSONFeature,GeoJSONFeatureCollectionRead,GeoJSONPoint,MapFilters
from app.scripts.seed_gualaceo import seed as seed_gualaceo
from app.services.campaign_service import CampaignService
from app.services.data_source_service import DataSourceService
from app.services.exceptions import BusinessRuleError
from app.services.geometry_import_service import GeometryImportService
from app.services.map_service import MapService

@pytest.fixture
def map_context(db:Session,admin):
 _,canton,parishes=seed_gualaceo(db);db.commit();campaign=CampaignService(db).create(CampaignCreate(name='Mapa Gualaceo',slug='mapa-gualaceo',canton_id=canton.id,office_type='MAYOR',election_name='Seccionales 2027',election_date=date(2027,2,14),status='DRAFT'),admin);return campaign,canton,parishes

def test_bbox_validation_and_hierarchy():
 bbox=MapFilters(bbox='-78.9,-3,-78.7,-2.8').bbox;assert bbox.as_list()==[-78.9,-3.0,-78.7,-2.8]
 for value in ['-78,-3,-77','-181,-3,-77,-2','-78,-91,-77,-2','-77,-3,-78,-2','nan,-3,-77,-2']:
  with pytest.raises(ValidationError):MapFilters(bbox=value)
 with pytest.raises(ValidationError):MapFilters(community_id=uuid4())

def test_geojson_contract_has_no_crs_or_sensitive_fields():
 point=GeoJSONPoint(coordinates=[-78.8,-2.9]);feature=GeoJSONFeature(id='x',geometry=point,properties={'resource_id':'x','name':'Sitio'});collection=GeoJSONFeatureCollectionRead(bbox=[-78.9,-3,-78.7,-2.8],features=[feature]);payload=collection.model_dump(mode='json')
 assert payload['type']=='FeatureCollection' and payload['features'][0]['geometry']['type']=='Point'
 assert 'crs' not in payload and not {'created_at','ip_address','user_agent','submission_key_hash'}.intersection(str(payload))

def test_geojson_parser_rejects_crs_geometry_collection_and_bad_point():
 valid={'type':'FeatureCollection','features':[]};assert parse_feature_collection(json.dumps(valid).encode())==valid
 with pytest.raises(BusinessRuleError):parse_feature_collection(json.dumps({**valid,'crs':{}}).encode())
 with pytest.raises(BusinessRuleError):validate_geometry({'type':'GeometryCollection','geometries':[]},'POINT')
 with pytest.raises(BusinessRuleError):validate_geometry({'type':'Point','coordinates':[200,95]},'POINT')

def test_polygon_is_normalized_without_modifying_source():
 original={'type':'Polygon','coordinates':[[[0,0],[1,0],[1,1],[0,0]]]};normalized=validate_geometry(original,'MULTIPOLYGON')
 assert normalized['type']=='MultiPolygon' and original['type']=='Polygon'

def test_map_missing_geometries_returns_controlled_payload(db,admin,map_context):
 campaign,_,parishes=map_context;service=MapService(db,lambda:date(2026,8,3));filters=MapFilters()
 assert service.bounds(campaign.id,admin,filters)['geometry_available'] is False
 boundaries=service.boundaries(campaign.id,admin,filters);assert boundaries['features']==[] and boundaries['unmapped_count']==9
 quality=service.quality(campaign.id,admin,filters);assert any(x['code']=='PARISH_GEOMETRY_MISSING' for x in quality['issues'])

def test_layer_catalog_uses_neutral_names(db,admin,map_context):
 campaign,_,_=map_context;payload=MapService(db).layers(campaign.id,admin,MapFilters());codes={x['code'] for x in payload['layers']}
 assert {'CANTON_BOUNDARY','PARISH_BOUNDARIES','ACTIVITIES','OPERATIONAL_COVERAGE','NEEDS','COMMITMENTS','SURVEY_PARTICIPATION','ELECTORAL_HISTORY','DEMOGRAPHICS'}<=codes
 assert all(word not in str(payload).lower() for word in ['persuadible','probabilidad de apoyo','territorio fuerte'])

def test_geometry_validation_job_is_non_mutating(db,admin,map_context):
 _,canton,_=map_context;source=DataSourceService(db).create(DataSourceCreate(code='INEC_TEST_GEOMETRY',institution='INEC',dataset_name='Geometría sintética',dataset_type='OTHER_AGGREGATED_OFFICIAL'),admin)
 content=json.dumps({'type':'FeatureCollection','features':[{'type':'Feature','properties':{'dpa_code':'0103','name':'Gualaceo'},'geometry':{'type':'Polygon','coordinates':[[[-78.8,-2.9],[-78.7,-2.9],[-78.7,-2.8],[-78.8,-2.9]]]}}]}).encode();job=GeometryImportService(db).run(source.id,'gualaceo.geojson',content,admin,'CANTON',validation_only=True)
 assert job.status=='VALIDATED' and job.rows_valid==1 and canton.geometry is None
 assert job.file_sha256 and len(job.file_sha256)==64

def test_geometry_import_rejects_missing_territory_atomically(db,admin,map_context):
 _,canton,_=map_context;source=DataSourceService(db).create(DataSourceCreate(code='INEC_BAD_GEOMETRY',institution='INEC',dataset_name='Geometría inválida',dataset_type='OTHER_AGGREGATED_OFFICIAL'),admin)
 content=json.dumps({'type':'FeatureCollection','features':[{'type':'Feature','properties':{'dpa_code':'9999'},'geometry':{'type':'Polygon','coordinates':[[[0,0],[1,0],[1,1],[0,0]]]}}]}).encode();job=GeometryImportService(db).run(source.id,'bad.json',content,admin,'CANTON')
 assert job.status=='REJECTED' and job.rows_updated==0 and canton.geometry is None

def test_map_http_routes_and_auth(client,admin_headers,map_context):
 campaign,_,parishes=map_context;base=f'/api/v1/campaigns/{campaign.id}/map';paths=['/layers','/bounds','/boundaries','/communities','/sectors','/activities','/operational-coverage','/needs','/commitments','/surveys','/data-quality',f'/features/PARISH/{parishes[0].id}']
 for path in paths:
  response=client.get(base+path,headers=admin_headers);assert response.status_code==200,(path,response.text);assert 'created_at' not in response.text and 'submission_key_hash' not in response.text
 assert client.get(base+'/layers').status_code==401

def test_map_invalid_bbox_and_tolerance_are_controlled(client,admin_headers,map_context):
 campaign,_,_=map_context;base=f'/api/v1/campaigns/{campaign.id}/map/boundaries'
 assert client.get(base+'?bbox=-77,-3,-78,-2',headers=admin_headers).status_code==422
 assert client.get(base+'?simplify_tolerance=1',headers=admin_headers).status_code==400


def test_map_unassigned_user_is_forbidden(db,map_context):
 campaign,_,_=map_context;role=RoleService(db).repository.get_by_code('ANALYST');user=User(email='map-out@example.com',username='map-out',first_name='Map',last_name='Out',hashed_password=hash_password('MapOut123'),is_active=True,is_superuser=False,roles=[role]);db.add(user);db.commit()
 with pytest.raises(PermissionError):MapService(db).layers(campaign.id,user,MapFilters())


def test_map_coordinator_only_gets_assigned_parish(db,admin,map_context):
 campaign,_,parishes=map_context;role=RoleService(db).repository.get_by_code('TERRITORIAL_COORDINATOR');user=User(email='map-coord@example.com',username='map-coord',first_name='Map',last_name='Coord',hashed_password=hash_password('MapCoord123'),is_active=True,is_superuser=False,roles=[role]);db.add(user);db.flush();db.add(CampaignUser(campaign_id=campaign.id,user_id=user.id,assigned_by_user_id=admin.id,is_active=True));db.add(TerritorialAssignment(campaign_id=campaign.id,user_id=user.id,parish_id=parishes[2].id,assigned_by_user_id=admin.id,is_active=True));db.commit();result=MapService(db).boundaries(campaign.id,user,MapFilters())
 assert result['unmapped_count']==1
 with pytest.raises(PermissionError):MapService(db).boundaries(campaign.id,user,MapFilters(parish_id=parishes[0].id))