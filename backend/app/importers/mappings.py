PROFILES={
'CANONICAL_ELECTORAL_PROCESS':['process_code','name','process_type','election_date','status','is_final'],
'CANONICAL_POLITICAL_ORGANIZATION':['organization_code','name','short_name','organization_type','list_number','scope'],
'CANONICAL_ELECTORAL_CANDIDATE':['process_code','office_type','contest_code','candidate_code','full_name','organization_code','list_number','ballot_order'],
'CANONICAL_ELECTORAL_TURNOUT':['process_code','contest_code','geography_level','geography_code','province_dpa','canton_dpa','parish_dpa','zone_code','precinct_code','jrv_code','registered_voters','ballots_cast','valid_votes','blank_votes','null_votes','other_votes','is_final'],
'CANONICAL_ELECTORAL_CANDIDATE_RESULT':['process_code','contest_code','geography_level','geography_code','candidate_code','votes','is_final'],
'CANONICAL_DEMOGRAPHIC_INDICATOR':['indicator_code','name','description','category','unit','value_type'],
'CANONICAL_DEMOGRAPHIC_OBSERVATION':['indicator_code','reference_year','geography_level','province_dpa','canton_dpa','parish_dpa','value','numerator','denominator'],
'CANONICAL_ELECTORAL_ROLL_SNAPSHOT':['snapshot_date','process_code','geography_level','province_dpa','canton_dpa','parish_dpa','registered_voters','male_voters','female_voters','electoral_zones','juntas']}
PROFILES['CANONICAL_SURVEY_AGGREGATE_RESULT']=['study_code','question_code','question_text','question_type','option_code','option_label','percentage','base_n','parish_dpa']
# Nombres de columna propios (no "address"/"latitude"/"longitude" a secas) para
# no colisionar con FORBIDDEN_HEADERS: un recinto electoral es un dato
# operativo/estructural público, no una ubicación individual, pero el chequeo
# global de microdatos se aplica sobre todas las cabeceras del archivo sin
# distinguir perfil.
PROFILES['CANONICAL_POLLING_PLACE']=['process_code','province_dpa','canton_dpa','parish_dpa','polling_place_code','polling_place_name','polling_place_address','polling_place_latitude','polling_place_longitude']
PROFILES['CANONICAL_ELECTORAL_BOARD']=['process_code','polling_place_code','board_code','board_number','sex_category','registered_voters']
DATASET_PROFILE={'CNE_TURNOUT':'CANONICAL_ELECTORAL_TURNOUT','CNE_ELECTORAL_RESULTS':'CANONICAL_ELECTORAL_CANDIDATE_RESULT','CNE_CANDIDATES':'CANONICAL_ELECTORAL_CANDIDATE','CNE_POLITICAL_ORGANIZATIONS':'CANONICAL_POLITICAL_ORGANIZATION','CNE_ELECTORAL_ROLL_SNAPSHOT':'CANONICAL_ELECTORAL_ROLL_SNAPSHOT','INEC_DEMOGRAPHIC_INDICATORS':'CANONICAL_DEMOGRAPHIC_INDICATOR'}
DATASET_PROFILE['SURVEY_AGGREGATE_RESULTS']='CANONICAL_SURVEY_AGGREGATE_RESULT'
DATASET_PROFILE['CNE_POLLING_PLACES']='CANONICAL_POLLING_PLACE'
DATASET_PROFILE['CNE_ELECTORAL_BOARDS']='CANONICAL_ELECTORAL_BOARD'
DATASET_LABELS={'CNE_ELECTORAL_ROLL_SNAPSHOT':'CNE · Registro electoral preelectoral','CNE_ELECTORAL_RESULTS':'CNE · Resultados electorales','CNE_CANDIDATES':'CNE · Candidaturas','CNE_POLITICAL_ORGANIZATIONS':'CNE · Organizaciones políticas','CNE_TURNOUT':'CNE · Participación electoral','INEC_DEMOGRAPHIC_INDICATORS':'INEC · Indicadores demográficos','INEC_POPULATION_PROJECTIONS':'INEC · Proyecciones poblacionales','INEC_GEOGRAPHIC_CLASSIFIER':'INEC · Clasificador geográfico','OTHER_AGGREGATED_OFFICIAL':'Otra fuente oficial agregada','CNE_POLLING_PLACES':'CNE · Recintos electorales','CNE_ELECTORAL_BOARDS':'CNE · Juntas receptoras del voto'}
DATASET_VERSION_KIND={'CNE_ELECTORAL_ROLL_SNAPSHOT':'SNAPSHOT_VERSIONED','CNE_TURNOUT':'UPSERT_GOVERNED','CNE_ELECTORAL_RESULTS':'UPSERT_GOVERNED','CNE_CANDIDATES':'UPSERT_GOVERNED','CNE_POLITICAL_ORGANIZATIONS':'UPSERT_GOVERNED','INEC_DEMOGRAPHIC_INDICATORS':'UPSERT_GOVERNED','INEC_POPULATION_PROJECTIONS':'UPSERT_GOVERNED','INEC_GEOGRAPHIC_CLASSIFIER':'UPSERT_GOVERNED','OTHER_AGGREGATED_OFFICIAL':'UPSERT_GOVERNED','CNE_POLLING_PLACES':'UPSERT_GOVERNED','CNE_ELECTORAL_BOARDS':'UPSERT_GOVERNED'}
DATASET_VERSION_KIND_LABELS={'SNAPSHOT_VERSIONED':'Histórico por corte','UPSERT_GOVERNED':'Versión administrativa','DERIVED_MODEL':'Modelo derivado'}
FORBIDDEN_HEADERS={'cedula','identificacion','nombres','apellidos','telefono','correo','email','direccion','fecha_nacimiento','persona_id','hogar_id','ip_address','respondent_name','national_id','phone','address','latitude','longitude','device_id','individual_vote_choice','nombre_votante','voter_id'}
