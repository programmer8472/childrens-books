"""Repository layer — one class per table, no raw SQL escaping into business logic."""
from app.db.repos.audit_log import AuditLogRepo
from app.db.repos.book import BookRepo
from app.db.repos.character_asset import CharacterAssetRepo
from app.db.repos.image import ImageRepo
from app.db.repos.judgement import JudgementRepo
from app.db.repos.story_version import StoryVersionRepo

__all__ = [
    "AuditLogRepo",
    "BookRepo",
    "CharacterAssetRepo",
    "ImageRepo",
    "JudgementRepo",
    "StoryVersionRepo",
]
