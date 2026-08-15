import hashlib,html,re
from dataclasses import dataclass
from datetime import datetime,timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin
from xml.etree import ElementTree

SCRIPT=re.compile(r"<(script|style)[^>]*>.*?</\1>",re.I|re.S);TAGS=re.compile(r"<[^>]+>");DANGEROUS=re.compile(r"javascript:|onerror\s*=|onload\s*=",re.I)
def plain(value:str|None,limit:int=2000)->str|None:
    if not value:return None
    value=DANGEROUS.sub("",SCRIPT.sub("",value));return " ".join(html.unescape(TAGS.sub(" ",value)).split())[:limit]
def dt(value:str|None):
    if not value:return None
    try:return parsedate_to_datetime(value).astimezone(timezone.utc)
    except Exception:
        try:return datetime.fromisoformat(value.replace("Z","+00:00")).astimezone(timezone.utc)
        except Exception:return None
@dataclass
class CanonicalItem:
    external_id:str|None;title:str;url:str;published_at:datetime|None;author:str|None;summary:str|None;excerpt:str|None;item_type:str="ARTICLE";metadata:dict|None=None
    @property
    def content_hash(self):return hashlib.sha256("\n".join((self.title,self.summary or "",self.excerpt or "",self.url)).encode()).hexdigest()
class SourceAdapter:
    def normalize(self,content:bytes,base_url:str)->list[CanonicalItem]:raise NotImplementedError
class RSSAdapter(SourceAdapter):
    def normalize(self,content:bytes,base_url:str):
        root=ElementTree.fromstring(content);out=[]
        nodes=root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
        for node in nodes:
            def val(*names):
                for name in names:
                    el=node.find(name)
                    if el is not None:return el.get("href") or el.text
            title=plain(val("title","{http://www.w3.org/2005/Atom}title"),500) or "Sin título";link=val("link","{http://www.w3.org/2005/Atom}link") or base_url;summary=plain(val("description","summary","{http://www.w3.org/2005/Atom}summary"));out.append(CanonicalItem(val("guid","id","{http://www.w3.org/2005/Atom}id"),title,urljoin(base_url,link),dt(val("pubDate","published","updated","{http://www.w3.org/2005/Atom}published","{http://www.w3.org/2005/Atom}updated")),plain(val("author","{http://www.w3.org/2005/Atom}author"),255),summary,summary,"ARTICLE",{}))
        return out
class JsonApiAdapter(SourceAdapter):
    def __init__(self,config:dict):self.config=config
    def normalize(self,content:bytes,base_url:str):
        import json
        data=json.loads(content);rows=data if isinstance(data,list) else data.get(self.config.get("items_key","items"),[]);out=[]
        for row in rows:
            get=lambda key:row.get(self.config.get(key,key));title=plain(str(get("title") or "Sin título"),500);url=urljoin(base_url,str(get("url") or base_url));summary=plain(str(get("summary") or ""));out.append(CanonicalItem(str(get("external_id")) if get("external_id") is not None else None,title,url,dt(get("published_at")),plain(get("author"),255),summary,summary,self.config.get("item_type","ARTICLE"),row))
        return out
