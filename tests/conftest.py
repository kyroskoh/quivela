# Copyright 2018 Amazon.com, Inc. or its affiliates. All Rights Reserved.
# 
# Licensed under the Apache License, Version 2.0 (the "License").
# You may not use this file except in compliance with the License.
# A copy of the License is located at
# 
#     http://www.apache.org/licenses/LICENSE-2.0
# 
# or in the "license" file accompanying this file. This file is distributed 
# on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either 
# express or implied. See the License for the specific language governing 
# permissions and limitations under the License.


import os
import re
import subprocess
import sys

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))  ## XXX HACK
from prove import prove
from run import run
from frontend.rosette import RosetteRuntime
from frontend.dafny import DafnyRuntime
from frontend.config import Config


Config.init_args()

# test cases
def pytest_collect_file(parent, path):
    if path.ext == ".sbl":
        dirname = os.path.basename(path.dirname)
        if dirname == "eval":
            return UCEvalFile(path, parent)
        elif dirname == "proofs":
            return UCProofFile(path, parent)
    elif path.ext == ".dfy":
        dirname = os.path.basename(path.dirname)
        print(path.basename)
        if dirname == "etm":
            if "eval" not in path.basename:
                return DafnyVerifyFile(path, parent)
            else:
                return DafnyEvalFile(path, parent)

# which backend to use
def pytest_addoption(parser):
    parser.addoption("--backend", choices=['dafny', 'rosette'], default='dafny', help="which logical backend to use")


# top-level pytest item, handles parsing UC programs and extracting any tags
class UCItem(pytest.Item):
    def __init__(self, name, path, parent, prog):
        super(UCItem, self).__init__(name, parent)
        self.program = prog
        self.path = path
        self.tags = {}
        lines = prog.split("\n")
        for l in prog.split("\n"):
            m = re.match(r"//\s*([A-Z]+):\s*(.*)", l)
            if m:
                self.tags[m.group(1)] = m.group(2)
    def _is_me(self, typ):
        if typ == "*":
            return True
        if typ == self.config.getoption("backend"):
            return True
        return False


# test item for proofs
class UCProofFile(pytest.File):
    def collect(self):
        with self.fspath.open() as f:
            yield UCProof("prove", self.name, self, f.read())
class UCProof(UCItem):
    def runtest(self):
        if self.tags.get("SKIP", None) and self._is_me(self.tags["SKIP"]):
            pytest.skip("SKIP: {}".format(self.tags["SKIP"]))
        backend = DafnyRuntime if self.config.getoption("backend") == 'dafny' else RosetteRuntime
        ret, path = prove(self.program, backend_cls=backend)
        if self.tags.get("XFAIL", None) and self._is_me(self.tags["XFAIL"]):
            assert not ret
        else:
            assert ret
    def reportinfo(self):
        return self.fspath, 0, "proof: %s" % self.path


# test item for evaluations
class UCEvalFile(pytest.File):
    def collect(self):
        with self.fspath.open() as f:
            yield UCEval("run", self.name, self, f.read())
class UCEval(UCItem):
    def runtest(self):
        assert "EXPECT" in self.tags
        backend = DafnyRuntime if self.config.getoption("backend") == 'dafny' else RosetteRuntime
        # construct the context if specified
        ctx = None
        if "CONTEXT" in self.tags:
            ctx = list(map(str.strip, self.tags["CONTEXT"].split("=")))
        ret, path = run(self.program, backend_cls=backend, init_ctx=ctx, expect=self.tags["EXPECT"])
        # make sure there's an assert in the output file
        with open(path) as f:
            script = f.read()
            # A bit hacky, since this depends on internal details of the two backends:
            assert ("assert" in script or "SUCCESS" in script)
        # and then check we got the right result
        if self.tags.get("XFAIL", None) and self._is_me(self.tags["XFAIL"]):
            assert not ret
        else:
            assert ret
    def reportinfo(self):
        return self.fspath, 0, "eval: %s" % self.path

# TODO: remove duplication and boilerplate:
class DafnyVerifyFile(pytest.File):
    def collect(self):
        with self.fspath.open() as f:
            yield DafnyVerifyItem("dafny", self.name, self, f.read())

class DafnyEvalFile(pytest.File):
    def collect(self):
        with self.fspath.open() as f:
            yield DafnyEvalItem("dafny", self.name, self, f.read())

class DafnyEvalItem(pytest.Item):
    def __init__(self, name, path, parent, code):
        super(DafnyEvalItem, self).__init__(name, parent)
        self.path = path
        self.parent = parent
        self.code = code

    def runtest(self):
        proc = subprocess.run(["dafny", "/compile:3", self.path],
                              stdout=subprocess.PIPE)
        assert "False" not in proc.stdout.decode('utf-8')

    def _is_me(self, typ):
        if typ == "*":
            return True
        return False

    def reportinfo(self):
        return self.fspath, 0, "dafny-eval: %s" % self.path

class DafnyVerifyItem(pytest.Item):
    def __init__(self, name, path, parent, code):
        super(DafnyVerifyItem, self).__init__(name, parent)
        self.path = path
        self.parent = parent
        self.code = code

    def runtest(self):
        proc = subprocess.run(["dafny", "/compile:0", self.path])
        assert proc.returncode == 0

    def _is_me(self, typ):
        if typ == "*":
            return True
        return False

    def reportinfo(self):
        return self.fspath, 0, "dafny-verify: %s" % self.path
