import logging
import random
import time
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)
RETRYABLE = {429, 500, 502, 503, 504}


def execute(request, retry_safe=True):
    """Reintentar lecturas y escrituras a rangos fijos; nunca duplicar create/insert."""
    for attempt in range(4):
        try:
            return request.execute(num_retries=0)
        except HttpError as error:
            if not retry_safe or error.resp.status not in RETRYABLE or attempt == 3:
                raise
            logger.warning('Google HTTP %s; reintento %s/3', error.resp.status, attempt + 1)
            time.sleep(2 ** attempt + random.random())
