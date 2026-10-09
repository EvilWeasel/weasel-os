#!/usr/bin/env python3
"""Source adapter regressions using disposable local fixtures; no GUI or outbound network."""
import datetime as dt, importlib.util, pathlib, shutil, tempfile, unittest
from unittest import mock
ROOT=pathlib.Path(__file__).resolve().parents[1]
def module(name):
    spec=importlib.util.spec_from_file_location("proposed_"+name,ROOT/"scripts"/("weasel-update-"+name+".py"))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
d,g,b,p,a=(module(n) for n in ("discover","gates","batch","prepare","activate"))
SOURCE=(ROOT/d.SOURCE_FILES["codex"]).read_bytes()
COMMIT="c1382380de69521303b416720a52f42d51af6248"
ID="20261009T190000Z-1234abcd"
class Network:
    def __init__(self,version="0.163.0",name="@openai/codex"):
        self.version,self.name,self.calls=version,name,[]
    def json(self,url):
        self.calls.append(url);return {"name":self.name,"version":self.version}
    def artifact(self,*args,**kwargs):raise AssertionError("Forbidden asset download")
class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="source-test-")
        self.path=pathlib.Path(self.tmp.name)
        self.before,self.after=self.path/"before",self.path/"after"
        for repo in (self.before,self.after):
            (repo/"packages").mkdir(parents=True)
            shutil.copytree(ROOT/"packages/codex-source",repo/"packages/codex-source")
            for lane in ("t3","chatgpt"):
                dest=repo/d.SOURCE_FILES[lane];dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(ROOT/d.SOURCE_FILES[lane],dest)
    def tearDown(self):self.tmp.cleanup()
    def transition(self,name,old,new):
        log=b"# Prior\n"
        return b.validate_changes({name:(old,new),"agent-learnings.md":(log,log+b.learning_suffix(ID,"batch",[name]))},"batch",ID)
class Identity(unittest.TestCase):
    def test_actual_root_source_with_rust_equality_is_valid(self):
        self.assertIn(b'toolchain.rustc.version == "1.95.0"',SOURCE)
        pin=d.read_pin("codex",SOURCE)
        self.assertEqual(set(pin),{"kind","version","commit","url","hash"})
        self.assertEqual((pin["kind"],pin["version"],pin["commit"]),("pinned-source","0.162.0",COMMIT))
        self.assertNotEqual(pin["url"],d.pin_url("codex",pin["version"]))
    def test_name_url_and_embedded_commit_must_agree(self):
        for old,new in [
            (('name = "codex-'+COMMIT).encode(),b'name = "codex-'+b"a"*40),
            (('STABLE_GIT_COMMIT = "'+COMMIT).encode(),b'STABLE_GIT_COMMIT = "'+b"a"*40),
            (("tar.gz/"+COMMIT).encode(),("tar.gz/"+COMMIT[:-1]+"9").encode()),
            (b"codeload.github.com/openai",b"codeload.github.com/attacker")]:
            with self.subTest(old=old),self.assertRaises(d.DiscoveryError):d.read_pin("codex",SOURCE.replace(old,new,1))
    def test_duplicate_alias_bad_hash_and_v8_pair_refused(self):
        for changed in [
            SOURCE.replace(b'  version = "0.162.0";',b'  version = "0.162.0";\n  version = "0.163.0";'),
            SOURCE.replace(b'  version = "0.162.0";',b'  version = alias;'),
            SOURCE.replace(b"sha256-YG/9",b"sha256-!G/9"),
            SOURCE.replace(b"sha256-UTu+",b"sha256-!Tu+"),
            SOURCE.replace(b'v150.4.0/src_binding',b'v151.0.0/src_binding')]:
            with self.subTest(case=changed[:30]),self.assertRaises(d.DiscoveryError):d.read_pin("codex",changed)
    def test_npm_type_and_automatic_update_refused(self):
        with self.assertRaises(d.DiscoveryError):d.validate_pin("codex",{"version":"0.162.0","url":d.pin_url("codex","0.162.0"),"hash":d.sri(bytes(32))})
        with self.assertRaises(d.DiscoveryError):d.replace_pin("codex",SOURCE,d.read_pin("codex",SOURCE))
        with self.assertRaises(d.DiscoveryError):d.validate_transition("codex",SOURCE,SOURCE,network=False)
        with self.assertRaises(d.DiscoveryError):d.verify_exact("codex","0.163.0",Network())
    def test_finite_hold_current_older_newer_and_no_asset_download(self):
        for version in ("0.161.0","0.162.0","0.163.0"):
            net=Network(version);result=d.discover("codex",d.read_pin("codex",SOURCE),net=net)
            self.assertEqual(result["status"],"held-local-patch");self.assertIsNone(result["candidate"])
            self.assertEqual(result["upstream_latest"],version)
            self.assertEqual(result["next_review"],(dt.datetime.now(dt.timezone.utc).date()+dt.timedelta(days=1)).isoformat())
            self.assertEqual(len(net.calls),1);self.assertEqual(set(result["source_files"]),set(d.CODEX_BUNDLE))
    def test_invalid_latest_is_error_not_unchanged(self):
        for net in (Network(name="@attacker/codex"),Network(version="1.2.3;touch x"),Network(version="0.163.0-alpha.1")):
            with self.assertRaises(d.DiscoveryError):d.discover("codex",d.read_pin("codex",SOURCE),net=net)
    def test_prepare_rejects_before_prune_or_baseline(self):
        with mock.patch.object(p,"peer",side_effect=lambda name:d if name=="discover" else g),mock.patch.object(p,"prune_candidates",side_effect=AssertionError("prune happened")),mock.patch.object(p,"require_resolved",side_effect=AssertionError("baseline inspected")):
            with self.assertRaisesRegex(p.Blocked,"source adapter"):p.prepare(pathlib.Path("/unused"),pathlib.Path("/unused"),"codex",pathlib.Path("/forged"))
    def test_two_exact_cli_prefixes_only(self):
        prefix="/nix/store/"+"a"*32+"-"
        for name in ("codex-0.162.0","codex-scoped-cancel-0.162.0"):self.assertEqual(g._app_version("codex",prefix+name),"0.162.0")
        for name in ("codex-acp-0.162.0","codex-scoped-cancel-0.162.0-extra","codex-scope-0.162.0"):
            with self.assertRaises(g.GateError):g._app_version("codex",prefix+name)
    def test_maps_and_source_gate(self):
        self.assertEqual(d.SOURCE_FILES["codex"],g.SOURCE_FILES["codex"]);self.assertEqual(a.LANES[d.SOURCE_FILES["codex"]],"codex")
        with self.assertRaises(g.GateError):g._validate_source_changes(["wrong"],{"codex"})
        with self.assertRaises(g.GateError):g._validate_source_changes({d.SOURCE_FILES["codex"]:(SOURCE,SOURCE+b"\n")},{"codex"})
class Bundle(Fixture):
    def test_receipt_includes_all_five_files_and_nonflake_dependency(self):
        bundle=d.codex_source_bundle(self.before)
        self.assertEqual(set(bundle["files_sha256"]),set(d.CODEX_BUNDLE))
        self.assertEqual(bundle["toolchain"]["rustVersion"],"1.95.0")
        self.assertEqual(bundle["toolchain"]["revision"],"64c08a7ca051951c8eae34e3e3cb1e202fe36786")
        self.assertEqual(bundle["dependencies"]["v8Version"],"150.4.0")
        self.assertIn("recursive",bundle["dependencies"]["sourceHashMode"])
    def test_missing_extra_or_symlink_refused(self):
        target=self.before/d.CODEX_BUNDLE[2];original=target.read_bytes();target.unlink()
        with self.assertRaises(d.DiscoveryError):d.codex_source_bundle(self.before)
        target.write_bytes(original);extra=self.before/"packages/codex-source/new.nix";extra.write_text("{}")
        with self.assertRaises(d.DiscoveryError):d.codex_source_bundle(self.before)
        extra.unlink();target.unlink();target.symlink_to(self.after/d.CODEX_BUNDLE[2])
        with self.assertRaises(d.DiscoveryError):d.codex_source_bundle(self.before)
    def test_source_namespace_immutable_in_broad_batch(self):
        for name in list(d.CODEX_BUNDLE)+["packages/codex-source/new.nix"]:
            with self.subTest(name=name),self.assertRaisesRegex(b.BatchError,"source adapter"):self.transition(name,b"old",b"new")
    def test_other_packages_continue_with_unchanged_source(self):
        self.assertEqual(self.transition("packages/example.nix",b"{version=1;}",b"{version=2;}")["mode"],"batch")
        with mock.patch.object(b,"discovery",return_value=d),mock.patch.object(b.os,"geteuid",return_value=1000),mock.patch.object(d,"Network",side_effect=AssertionError("network happened")):
            result=b.verify_published(self.before,self.after)
        self.assertTrue(result["ok"]);self.assertFalse(result["published_pins"]["codex"]["changed"])
    def test_any_bundle_byte_change_refused_even_version_unchanged(self):
        for name in d.CODEX_BUNDLE:
            target=self.after/name;original=target.read_bytes();target.write_bytes(original+b"\n# changed\n")
            with self.subTest(name=name),mock.patch.object(b,"discovery",return_value=d),mock.patch.object(b.os,"geteuid",return_value=1000):
                with self.assertRaises(b.BatchError):b.verify_published(self.before,self.after)
            target.write_bytes(original)
    def test_ownership_predicate_uses_candidate_and_not_fixed_baseline_drv(self):
        expr=b.codex_ownership_predicate(self.after,"nixy-laptop")
        self.assertIn(str(self.after/"packages/codex-source"),expr);self.assertIn("selected.drvPath == expectedCodex.drvPath",expr)
        self.assertIn("expectedAcp.drvPath",expr);self.assertNotIn("63jyk",expr)
        self.assertEqual(b.codex_ownership_predicate(self.after,"michapc"),"true")
class Acp(unittest.TestCase):
    def test_unique_actual_export_not_comment(self):
        good="/nix/store/"+"a"*32+"-codex-scoped-cancel-0.162.0/bin/codex"
        wrong="/nix/store/"+"b"*32+"-codex-0.162.0/bin/codex"
        self.assertEqual(g._acp_codex_path(("export CODEX_PATH='"+good+"'\n").encode()),good)
        self.assertEqual(g._acp_codex_path(("# expected CODEX_PATH="+good+"\nexport CODEX_PATH='"+wrong+"'\n").encode()),wrong)
        for data in [("# CODEX_PATH="+good+"\n").encode(),("export CODEX_PATH='"+good+"'\nexport CODEX_PATH='"+wrong+"'\n").encode(),b'export CODEX_PATH="$OTHER/bin/codex"\n',("CODEX_PATH='"+good+"'\n").encode(),("export CODEX_PATH='"+good+"'; exec other\n").encode()]:
            with self.assertRaises(g.GateError):g._acp_codex_path(data)
class Profile(Fixture):
    def test_actual_symlinks_refuse_renamed_priority_owner(self):
        profile,app,acp,foreign=[self.path/n for n in ("profile","app","acp","renamed-owner")]
        for root in (profile,app,acp,foreign):(root/"bin").mkdir(parents=True)
        for root,name in ((app,"codex"),(acp,"codex-acp"),(foreign,"codex")):(root/"bin"/name).write_text("# fixture\n")
        (profile/"bin/codex").symlink_to(app/"bin/codex");(profile/"bin/codex-acp").symlink_to(acp/"bin/codex-acp")
        # These paths intentionally are private fixtures. Parser/store-root checks
        # are independently exercised above; no actual profile or store modified.
        with mock.patch.object(g,"_store_root",side_effect=lambda v:str(v)),mock.patch.object(g,"_acp_codex_path",return_value=str(app)+"/bin/codex"):
            self.assertTrue(g.verify_codex_profile(profile,app,acp)["ok"])
            (profile/"bin/codex").unlink();(profile/"bin/codex").symlink_to(foreign/"bin/codex")
            with self.assertRaisesRegex(g.GateError,"another codex"):g.verify_codex_profile(profile,app,acp)



class Orchestration(unittest.TestCase):
    def test_root_checks_actual_profile_before_unchanged_output_skip(self):
        import types
        codex=pathlib.Path("/nix/store/"+"a"*32+"-codex-scoped-cancel-0.162.0")
        acp=pathlib.Path("/nix/store/"+"b"*32+"-codex-acp-2.1.1")
        profile=pathlib.Path("/nix/store/"+"c"*32+"-home-manager-path")
        verify=mock.Mock(return_value={"ok":True,"profile":str(profile)})
        gates_peer=types.SimpleNamespace(verify_codex_profile=verify)
        def build(runner,source,attribute,expression=None):
            return profile if attribute is not None else acp
        with mock.patch.object(a,"build_application",return_value=codex),mock.patch.object(a,"nix_build",side_effect=build),mock.patch.object(a,"import_peer",return_value=gates_peer) as imported:
            pairs,tests=a.probe_applications(object(),pathlib.Path("/old"),pathlib.Path("/new"),["codex"],pathlib.Path("/unused"),pathlib.Path("/unused"),changed_outputs_only=True)
        imported.assert_called_once_with("weasel-update-gates.py")
        verify.assert_called_once_with(profile,codex,acp)
        self.assertFalse(tests["codex"]["probed"]);self.assertTrue(tests["codex"]["profile_ownership"]["ok"])
    def test_wrong_acp_export_with_correct_comment_refused_before_process(self):
        with tempfile.TemporaryDirectory(prefix="acp-export-") as tmp:
            output=pathlib.Path(tmp);(output/"bin").mkdir()
            selected="/nix/store/"+"a"*32+"-codex-scoped-cancel-0.162.0"
            wrong="/nix/store/"+"b"*32+"-codex-0.162.0"
            (output/"bin/codex-acp").write_text("# CODEX_PATH="+selected+"/bin/codex\nexport CODEX_PATH='"+wrong+"/bin/codex'\n")
            with mock.patch.object(g.subprocess,"Popen",side_effect=AssertionError("must refuse first")),self.assertRaisesRegex(g.GateError,"tested candidate"):
                g._acp_worker(output,pathlib.Path(selected),output)


class NixOwnerFixture(Fixture):
    def owner(self, selected=None, extra=None, acp=True, suffix="one"):
        import json, subprocess
        executable=shutil.which("nix")
        if executable is None:self.skipTest("Nix unavailable; private source-owner expression not evaluated")
        source="/fixture/source-codex-"+suffix+".drv";adapter="/fixture/source-acp-"+suffix+".drv"
        pkgset=self.path/"private-pkgset.nix"
        pkgset.write_text('{ system, config }: { callPackage = src: args: if builtins.baseNameOf src == "codex-source" then { drvPath = '+json.dumps(source)+'; } else { drvPath = '+json.dumps(adapter)+'; }; }\n')
        packages=[{"pname":"codex-scoped-cancel","drvPath":source}]
        if acp:packages.append({"pname":"codex-acp","drvPath":adapter})
        if extra:packages.append(extra)
        hm={"evilweasel":{"home":{"packages":packages},"weasel":{"hephaestusRecoveryConsole":{"package":{"drvPath":selected or source}}}}}
        expr=('let f = { inputs.nixpkgs-unstable = '+str(pkgset)+'; }; '
              'host = { pkgs.stdenv.hostPlatform.system = "x86_64-linux"; }; '
              "hm = builtins.fromJSON ''"+json.dumps(hm)+"''; in "+b.codex_ownership_predicate(self.after,"nixy-laptop"))
        result=subprocess.run([executable,"eval","--store",str(self.path/"eval-store"),"--raw","--offline","--impure","--no-write-lock-file","--expr",
                               'if ('+expr+') then "true" else "false"'],capture_output=True,timeout=30,check=True)
        return result.stdout.decode().strip()
    def test_candidate_relative_source_drv_can_advance(self):
        self.assertEqual(self.owner(suffix="one"),"true")
        self.assertEqual(self.owner(suffix="two"),"true")
    def test_selected_stock_codex_missing_acp_and_foreign_normal_cli_refused(self):
        self.assertEqual(self.owner(selected="/fixture/stock-codex.drv"),"false")
        self.assertEqual(self.owner(acp=False),"false")
        self.assertEqual(self.owner(extra={"pname":"codex","drvPath":"/fixture/stock-codex.drv"}),"false")
    def test_renamed_extra_requires_separate_actual_profile_gate(self):
        # A derivation label cannot attest the selected executable. The
        # production built-profile gate and its filesystem test cover this.
        self.assertEqual(self.owner(extra={"pname":"renamed","drvPath":"/fixture/foreign.drv"}),"true")


if __name__=="__main__":unittest.main()
