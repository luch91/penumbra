import logging

import gltest.logging as _gltest_logging

_gltest_logging.logger.disabled = False
_gltest_logging.logger.setLevel(logging.WARNING)
_gltest_logging.logger.addHandler(logging.StreamHandler())
