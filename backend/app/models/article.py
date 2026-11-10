from pydantic import BaseModel
from typing import Optional

class ArticleCreate(BaseModel):
    title: str
    url: str
    published_at: Optional[str] = ""
    summary: Optional[str] = ""
    content: Optional[str] = ""
    takeaways: Optional[str] = ""
    audio_script: Optional[str] = ""

class Article(ArticleCreate):
    id: int
    created_at: Optional[str] = None