#
# Copyright (c) 2025 Airbyte, Inc., all rights reserved.
#


import sys

from airbyte_cdk.entrypoint import launch
from .source import SourcePulseNetskope

def run():
    source = SourcePulseNetskope()
    launch(source, sys.argv[1:])
