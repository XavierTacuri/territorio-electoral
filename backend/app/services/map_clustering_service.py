from app.repositories.map_repository import MapRepository
class MapClusteringService:
 def __init__(self,db):self.repository=MapRepository(db)
 def clusters(self,*args,**kwargs):return self.repository.activity_clusters(*args,**kwargs)
