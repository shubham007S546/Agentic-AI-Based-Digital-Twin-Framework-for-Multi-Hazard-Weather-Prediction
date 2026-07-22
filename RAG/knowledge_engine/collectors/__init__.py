from .base import CollectorBase, CollectedSource
from .project_repo_collector import ProjectRepositoryCollector
from .local_documents_collector import LocalDocumentsCollector
from .government_collector import GovernmentDocumentsCollector
from .research_papers_collector import ResearchPapersCollector
from .dataset_metadata_collector import DatasetMetadataCollector
from .news_collector import NewsCollector
from .documentation_website_collector import DocumentationWebsiteCollector

__all__ = [
    "CollectorBase",
    "CollectedSource",
    "ProjectRepositoryCollector",
    "LocalDocumentsCollector",
    "GovernmentDocumentsCollector",
    "ResearchPapersCollector",
    "DatasetMetadataCollector",
    "NewsCollector",
    "DocumentationWebsiteCollector",
]
