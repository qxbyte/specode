# test_registry.py —— registry.py 多库注册表（子进程端到端）
import os, sys, json, shutil, tempfile, subprocess, unittest

HERE = os.path.dirname(__file__)
REG = os.path.join(HERE, "registry.py")

class RegistryTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="reg-")
        self.vault = tempfile.mkdtemp(prefix="vlt-")
        self.addCleanup(shutil.rmtree, self.home, True)
        self.addCleanup(shutil.rmtree, self.vault, True)
        self.env = dict(os.environ, OBSIDIAN_WIKI_CONFIG_DIR=self.home)

    def reg(self, *args):
        return subprocess.run([sys.executable, REG, *args], env=self.env,
                              capture_output=True, text=True)

    def vaults(self):
        return json.load(open(os.path.join(self.home, "vaults.json"), encoding="utf-8"))

    def test_resolve_unconfigured_exits_3(self):
        self.assertEqual(self.reg("resolve").returncode, 3)

    def test_register_sets_active_and_resolves(self):
        r = self.reg("register", "--name", "notes", "--path", self.vault)
        self.assertEqual(r.returncode, 0, r.stderr)
        v = self.vaults()
        self.assertEqual(v["active"], "notes")
        self.assertEqual(os.path.realpath(v["vaults"]["notes"]["path"]),
                         os.path.realpath(self.vault))
        out = json.loads(self.reg("resolve").stdout)
        self.assertEqual(out["name"], "notes")
        self.assertFalse(out["config_exists"])

    def test_register_config_from_seeds_config(self):
        tmpl = os.path.join(self.home, "tmpl.json")
        os.makedirs(self.home, exist_ok=True)
        json.dump({"index_dir": "IDX"}, open(tmpl, "w", encoding="utf-8"))
        self.reg("register", "--name", "n", "--path", self.vault, "--config-from", tmpl)
        cfg = os.path.join(self.home, "configs", "n.json")
        self.assertTrue(os.path.isfile(cfg))
        self.assertEqual(json.load(open(cfg, encoding="utf-8"))["index_dir"], "IDX")

    def test_second_vault_keeps_active_then_set_active(self):
        v2 = tempfile.mkdtemp(prefix="vlt2-"); self.addCleanup(shutil.rmtree, v2, True)
        self.reg("register", "--name", "a", "--path", self.vault)
        self.reg("register", "--name", "b", "--path", v2)   # 不带 --activate
        self.assertEqual(self.vaults()["active"], "a")
        self.assertEqual(self.reg("set-active", "--name", "b").returncode, 0)
        self.assertEqual(self.vaults()["active"], "b")
        self.assertEqual(json.loads(self.reg("resolve").stdout)["name"], "b")
        self.assertEqual(json.loads(self.reg("resolve", "--name", "a").stdout)["name"], "a")

    def test_register_bad_path_errors(self):
        self.assertNotEqual(self.reg("register", "--name", "x",
                                     "--path", "/no/such/dir").returncode, 0)

if __name__ == "__main__":
    unittest.main()
