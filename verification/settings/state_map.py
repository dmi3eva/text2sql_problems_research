from verification.src.controller import *

ERROR_DESCRIBING_MAP = {
    Status.ERROR_DESCRIBING_FLUENCY: Status.IN_PROGRESS_EQUIVALENT,
    Status.ERROR_DESCRIBING_EQUIVALENT: Status.IN_PROGRESS_SQL,
    Status.ERROR_DESCRIBING_SQL: Status.ERROR_DESCRIBING_EQUIVALENT
}