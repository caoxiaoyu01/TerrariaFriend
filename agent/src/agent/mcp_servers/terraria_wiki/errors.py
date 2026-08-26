from enum import StrEnum


class WikiErrorCode(StrEnum):
    INVALID_ENTITY = "INVALID_ENTITY"
    INVALID_INTENT = "INVALID_INTENT"
    PAGE_NOT_FOUND = "PAGE_NOT_FOUND"
    PAGE_UNRESOLVED = "PAGE_UNRESOLVED"
    LANGUAGE_MAPPING_UNAVAILABLE = "LANGUAGE_MAPPING_UNAVAILABLE"
    WIKI_TIMEOUT = "WIKI_TIMEOUT"
    WIKI_HTTP_ERROR = "WIKI_HTTP_ERROR"
    WIKI_PARSE_ERROR = "WIKI_PARSE_ERROR"
    REDIS_UNAVAILABLE = "REDIS_UNAVAILABLE"


class WikiRetrievalError(Exception):
    def __init__(self, code: WikiErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
