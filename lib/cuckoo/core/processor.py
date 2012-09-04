# Copyright (C) 2010-2012 Cuckoo Sandbox Developers.
# This file is part of Cuckoo Sandbox - http://www.cuckoosandbox.org
# See the file 'docs/LICENSE' for copying permission.

import copy
import logging
import pkgutil
from distutils.version import StrictVersion

from lib.cuckoo.common.config import Config
from lib.cuckoo.common.constants import CUCKOO_VERSION
from lib.cuckoo.common.abstracts import Processing, Signature
from lib.cuckoo.common.exceptions import CuckooProcessingError
import modules.processing as processing
import modules.signatures as signatures

log = logging.getLogger(__name__)

class Processor:
    """Analysis processing module."""

    def __init__(self, analysis_path):
        """@param analysis_path: analysis folder path."""
        self.analysis_path = analysis_path
        self._populate(processing)
        self._populate(signatures)

    def _populate(self, modules):
        """Load modules.
        @param modules: modules.
        """
        prefix = modules.__name__ + "."
        for loader, name, ispkg in pkgutil.iter_modules(modules.__path__, prefix):
            if ispkg:
                continue

            __import__(name, globals(), locals(), ["dummy"], -1)

    def _run_processing(self, module):
        """Run a processing module.
        @param module: processing module to run.
        @param results: results dict.
        @return: results generated by module.
        """
        current = module()
        current.set_path(self.analysis_path)
        current.cfg = Config(current.conf_path)

        try:
            data = current.run()
            log.debug("Executed processing module \"%s\" on analysis at \"%s\"" % (current.__class__.__name__, self.analysis_path))
            return {current.key : data}
        except NotImplementedError:
            log.debug("The processing module \"%s\" is not correctly implemented" % current.__classs__.__name__)
        except CuckooProcessingError as e:
            log.warning("The processing module \"%s\" returned the following error: %s" % (current.__class__.__name__, e))
        except Exception as e:
            log.exception("Failed to run the processing module \"%s\":" % (current.__class__.__name__))

        return None

    def _run_signature(self, signature, results):
        """Run a signature.
        @param signature: signature to run.
        @param signs: signature results dict.
        @return: matched signature.
        """
        current = signature()
        log.debug("Running signature \"%s\"" % current.name)

        if not current.enabled:
            return None

        version = CUCKOO_VERSION.split("-")[0]
        if current.minimum:
            try:
                if StrictVersion(version) < StrictVersion(current.minimum.split("-")[0]):
                    log.debug("You are running an older incompatible version of Cuckoo, the signature \"%s\" requires minimum version %s"
                              % (current.name, current.minimum))
                    return None
            except ValueError:
                log.debug("Wrong minor version number in signature %s" % current.name)
                return None

        if current.maximum:
            try:
                if StrictVersion(version) > StrictVersion(current.maximum.split("-")[0]):
                    log.debug("You are running a newer incompatible version of Cuckoo, the signature \"%s\" requires maximum version %s"
                              % (current.name, current.maximum))
                    return None
            except ValueError:
                log.debug("Wrong major version number in signature %s" % current.name)
                return None

        try:
            if current.run(copy.deepcopy(results)):
                matched = {"name" : current.name,
                           "description" : current.description,
                           "severity" : current.severity,
                           "references" : current.references,
                           "data" : current.data,
                           "alert" : current.alert}
                log.debug("Analysis at \"%s\" matched signature \"%s\"" % (self.analysis_path, current.name))
                return matched
        except NotImplementedError:
            log.debug("The signature \"%s\" is not correctly implemented" % current.name)
        except Exception as e:
            log.exception("Failed to run signature \"%s\":" % (current.name))

        return None

    def run(self):
        """Run all processing modules and all signatures.
        @return: processing results.
        """
        results = {}
        Processing()

        for module in Processing.__subclasses__():
            result = self._run_processing(module)
            if result:
                results.update(result)

        Signature()
        sigs = []

        for signature in Signature.__subclasses__():
            match = self._run_signature(signature, results)
            if match:
                sigs.append(match)

        sigs.sort(key=lambda key: key["severity"])
        results["signatures"] = sigs

        return results