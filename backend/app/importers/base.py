from dataclasses import dataclass
@dataclass
class ImportIssue:row_number:int|None;column_name:str|None;error_code:str;message:str;preview:str|None=None
class BaseImporter:
 def validate(self,rows):raise NotImplementedError
 def import_rows(self,rows):raise NotImplementedError
