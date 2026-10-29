import os
import subprocess
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(os.name=='nt','Windows native controller')
class NativeLootTests(unittest.TestCase):
    def test_transactional_toggle_and_restore_on_fake_vm(self):
        root=Path(__file__).resolve().parents[1]
        compiler=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'check.exe'
            result=subprocess.run([str(compiler),'/nologo','/target:exe','/out:'+str(target),
                '/r:System.Core.dll','/r:System.Web.Extensions.dll','/nowarn:0649',
                str(root/'native/LootSelector.cs'),str(root/'tests/native_loot_harness.cs')],capture_output=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            result=subprocess.run([str(target)],capture_output=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn(b'PASS second-span partial write restores both originals',result.stdout)
            self.assertIn(b'PASS changed save globals restore both spans',result.stdout)
            self.assertIn(b'PASS reload, retry and code reset preserve all seven selections',result.stdout)
            self.assertIn(b'PASS cancelling during reload prevents automatic re-enable',result.stdout)
