{
  config,
  inputs,
  lib,
  pkgs,
  ...
}:
let
  cfg = config.weasel.roles.openclaw;
  system = pkgs.stdenv.hostPlatform.system;
  securePnpmOverlay = _final: prev: {
    pnpm_10 = prev.pnpm_10_latest;
  };
  openclawPkgs = import inputs.nix-openclaw.inputs.nixpkgs {
    inherit system;
    overlays = [
      securePnpmOverlay
      inputs.nix-openclaw.overlays.default
    ];
  };
  openclawPackages = import "${inputs.nix-openclaw}/nix/packages" {
    pkgs = openclawPkgs;
    sourceInfo = import "${inputs.nix-openclaw}/nix/sources/openclaw-source.nix";
    steipetePkgs = inputs.nix-openclaw.inputs.nix-steipete-tools.packages.${system} or { };
  };
  # The pinned prune runs root postinstall in a source archive without .git.
  # Use the frozen PNPM graph offline, retain the official Baileys hotfix, and
  # reject missing or incompatible bundled runtime dependencies.
  offlineRuntimeCheck = pkgs.writeText "openclaw-offline-runtime.mjs" ''
    // Packaging-only adapter: use the frozen, already installed PNPM graph.
    // This is run after prune and before the upstream install phase.
    import assert from 'node:assert/strict';
    import fs from 'node:fs';
    import crypto from 'node:crypto';
    import path from 'node:path';
    import { createRequire } from 'node:module';
    import { fileURLToPath, pathToFileURL } from 'node:url';

    const root = fs.realpathSync(process.cwd());
    const nodeModules = fs.realpathSync(path.join(root, 'node_modules'));
    const rootDistUrl = pathToFileURL(path.join(root, 'dist', 'index.js')).href;
    // The full Nix Node package wraps a slim executable; process.execPath alone
    // therefore does not identify npm's semver installation.
    const semver = createRequire(process.argv[2])('semver');
    // These exact directory trees survive gateway-install.sh: dist/node_modules
    // are moved and extensions are copied to the same relative output layout.
    assert.equal(nodeModules, path.join(root, 'node_modules'), 'root graph symlink escape');
    const graphRoots = [nodeModules];
    const pluginRoot = path.join(root, 'dist', 'extensions');
    assert.equal(fs.realpathSync(pluginRoot), pluginRoot, 'published plugin root symlink escape');
    for (const ent of fs.readdirSync(pluginRoot, {withFileTypes:true})) {
      assert(!ent.isSymbolicLink(), 'published plugin symlink escape');
      if (!ent.isDirectory()) continue;
      assert(/^[a-z0-9][a-z0-9_-]*$/i.test(ent.name), 'unsafe published plugin id');
      const published = path.join(pluginRoot, ent.name, 'package.json');
      if (!fs.existsSync(published)) continue;
      assert.equal(fs.realpathSync(published), published, 'published manifest symlink escape');
      const local = path.join(root, 'extensions', ent.name, 'node_modules');
      if (!fs.existsSync(local)) continue;
      for (const dir of [path.join(root, 'extensions'), path.dirname(local), local]) assert.equal(fs.realpathSync(dir), dir, 'preserved plugin graph symlink escape');
      assert(fs.lstatSync(local).isDirectory(), 'preserved plugin graph is not a directory');
      graphRoots.push(local);
    }
    const inside = p => graphRoots.some(graph => p.startsWith(graph + path.sep));
    const readPackage = p => JSON.parse(fs.readFileSync(path.join(p, 'package.json'), 'utf8'));
    const target = (from, name) => {
      for (let dir = from; dir !== path.dirname(dir); dir = path.dirname(dir)) {
        const candidate = path.join(dir, 'node_modules', ...name.split('/'));
        if (fs.existsSync(path.join(candidate, 'package.json'))) {
          const real = fs.realpathSync(candidate);
          assert(inside(real), `dependency escapes installed graph: ''${name}: ''${real}`);
          assert.equal(readPackage(real).name, name);
          return real;
        }
      }
      return null;
    };

    // Read-only enumeration before either measured root alias correction.
    const installedPackages = (() => {
      const result = new Map(), pending = [...graphRoots], visited = new Set();
      const add = p => {
        const real = fs.realpathSync(p);
        assert(inside(real), `package consumer escapes graph: ''${p}`);
        if (result.has(real)) return;
        assert(result.size < 12000, 'package consumer count bound');
        result.set(real, readPackage(real));
        if (fs.existsSync(path.join(real, 'node_modules'))) pending.push(path.join(real, 'node_modules'));
      };
      while (pending.length) {
        const nm = fs.realpathSync(pending.pop());
        assert(graphRoots.includes(nm) || inside(nm), 'nested consumer graph escape');
        if (visited.has(nm)) continue;
        visited.add(nm);
        for (const ent of fs.readdirSync(nm, {withFileTypes:true})) {
          if (ent.name === '.pnpm') {
            const pnpm = path.join(nm, ent.name);
            assert.equal(fs.realpathSync(pnpm), pnpm);
            for (const child of fs.readdirSync(pnpm, {withFileTypes:true})) {
              const nested = path.join(pnpm, child.name, 'node_modules');
              if (child.isDirectory() && fs.existsSync(nested)) pending.push(nested);
            }
          } else if (ent.name.startsWith('@')) {
            for (const child of fs.readdirSync(path.join(nm, ent.name))) add(path.join(nm, ent.name, child));
          } else if (!ent.name.startsWith('.')) add(path.join(nm, ent.name));
        }
      }
      return result;
    })();
    const measuredConsumers = (name, expected) => {
      const found = [];
      for (const [dir, meta] of installedPackages) for (const section of ['dependencies','optionalDependencies','devDependencies','peerDependencies']) {
        if (name in (meta[section] ?? {})) found.push({dir, name:meta.name, version:meta.version, section, spec:meta[section][name]});
      }
      const key = x => JSON.stringify(x);
      assert.deepEqual(found.sort((a,b)=>key(a).localeCompare(key(b))), expected.sort((a,b)=>key(a).localeCompare(key(b))), `unreviewed consumer of ''${name}`);
    };
    // Refuse every declared root conflict before either measured graph correction.
    for (const name of ['@pierre/theme','jwks-rsa']) {
      const meta = readPackage(root);
      for (const section of ['dependencies','optionalDependencies','devDependencies','peerDependencies']) assert(!(name in (meta[section] ?? {})), `root explicitly declares ''${name}`);
      for (const key of Object.keys(meta.pnpm?.overrides ?? {})) assert(!key.includes(name), `root overrides ''${name}`);
    }
    measuredConsumers('@pierre/theme', [{dir:target(root,'@pierre/diffs'),name:'@pierre/diffs',version:'1.1.13',section:'dependencies',spec:'0.0.28'}]);
    measuredConsumers('jwks-rsa', [{dir:target(root,'@microsoft/teams.apps'),name:'@microsoft/teams.apps',version:'2.0.7',section:'dependencies',spec:'^3.2.0'}]);

    const runtimeSnapshot = start => {
      const pending = [start], seen = new Set(), nodes = [], edges = [];
      while (pending.length) {
        const dir = pending.pop();
        if (seen.has(dir)) continue;
        seen.add(dir);
        assert(seen.size < 12000, 'runtime dependency count bound');
        const meta = readPackage(dir);
        nodes.push({dir,name:meta.name,version:meta.version,manifest_sha256:crypto.createHash('sha256').update(fs.readFileSync(path.join(dir,'package.json'))).digest('hex')});
        for (const [name,spec] of Object.entries({...meta.dependencies,...meta.optionalDependencies})) {
          const child = target(dir,name), optional = name in (meta.optionalDependencies ?? {});
          assert(child || optional, `missing preserved runtime dependency: ''${meta.name}/''${name}`);
          if (child) {
            assert(semver.validRange(spec) && semver.satisfies(readPackage(child).version,spec), `preserved runtime range mismatch: ''${meta.name}/''${name}`);
            pending.push(child);
          }
          edges.push({from:dir,name,spec,optional,to:child});
        }
      }
      const sort = xs => xs.sort((a,b)=>JSON.stringify(a).localeCompare(JSON.stringify(b)));
      return {nodes:sort(nodes),edges:sort(edges)};
    };
    const normalizedSnapshot = (value, from, to) => {
      const replace = p => typeof p === 'string' && (p === from || p.startsWith(from + path.sep)) ? to + p.slice(from.length) : p;
      const nodes = value.nodes.map(n=>({...n,dir:replace(n.dir)}));
      const edges = value.edges.map(e=>({...e,from:replace(e.from),to:replace(e.to)}));
      const sort = xs => xs.sort((a,b)=>JSON.stringify(a).localeCompare(JSON.stringify(b)));
      return {nodes:sort(nodes),edges:sort(edges)};
    };
    const packageTree = dir => {
      const result = [], pending = [dir];
      while (pending.length) {
        const base = pending.pop();
        for (const ent of fs.readdirSync(base,{withFileTypes:true})) {
          const file = path.join(base,ent.name), relative = path.relative(dir,file);
          if (ent.isSymbolicLink()) {assert(inside(fs.realpathSync(file)), 'package tree symlink escape');result.push({file:relative,link:fs.readlinkSync(file)});}
          else if (ent.isDirectory()) pending.push(file);
          else {assert(ent.isFile(), 'unexpected package tree file');result.push({file:relative,sha256:crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex')});}
        }
        assert(result.length < 50000, 'package tree file count bound');
      }
      return result.sort((a,b)=>a.file.localeCompare(b.file));
    };
    const repairPinnedJwksAlias = (name, packageDir, needs) => {
      if (name !== 'jwks-rsa' || !packageDir || needs.every(({spec})=>semver.satisfies(readPackage(packageDir).version,spec))) return packageDir;
      assert.equal(readPackage(packageDir).version,'3.2.2');
      assert.deepEqual(needs,[{plugin:'msteams',spec:'^4.0.1'}]);
      const rootPackage = readPackage(root);
      for (const section of ['dependencies','optionalDependencies','devDependencies','peerDependencies']) assert(!(name in (rootPackage[section] ?? {})), `root explicitly declares ''${name}`);
      for (const key of Object.keys(rootPackage.pnpm?.overrides ?? {})) assert(!key.includes(name), `root overrides ''${name}`);
      const wanted = target(path.join(root,'extensions','msteams'),name);
      assert(wanted && wanted !== packageDir,'missing distinct frozen Teams JWKS4.0.1');
      assert.equal(readPackage(wanted).version,'4.0.1');
      const consumer = target(root,'@microsoft/teams.apps');
      assert(consumer,'missing frozen Teams-apps context');
      assert.equal(readPackage(consumer).version,'2.0.7');
      assert.equal(readPackage(consumer).dependencies[name],'^3.2.0');
      const old = target(consumer,name);
      assert.equal(old,packageDir,'unexpected pre-existing Teams private JWKS');
      const link = path.join(root,'node_modules',name), original = fs.lstatSync(link);
      assert(original.isDirectory() && !original.isSymbolicLink() && fs.realpathSync(link) === link,'unexpected measured JWKS root layout');
      const before = runtimeSnapshot(old), wantedBefore = runtimeSnapshot(wanted), treeBefore = packageTree(old);
      const slot = path.join(consumer,'node_modules',name);
      try {fs.lstatSync(slot);assert.fail('refusing existing private JWKS slot');} catch(e) {if(e.code !== 'ENOENT') throw e;}
      const parent = path.dirname(slot);
      if (fs.existsSync(parent)) assert(fs.lstatSync(parent).isDirectory() && fs.realpathSync(parent) === parent,'private JWKS ancestor escape');
      else {try {fs.lstatSync(parent);assert.fail('dangling private JWKS ancestor');} catch(e) {if(e.code !== 'ENOENT') throw e;} fs.mkdirSync(parent);}
      fs.renameSync(link,slot);
      fs.symlinkSync(path.relative(path.dirname(link),wanted),link);
      assert.equal(target(root,name),wanted);
      assert.equal(target(consumer,name),slot);
      assert.deepEqual(packageTree(slot),treeBefore,'JWKS package contents changed');
      assert.deepEqual(runtimeSnapshot(slot),normalizedSnapshot(before,old,slot),'old JWKS runtime dependency graph changed');
      assert.deepEqual(runtimeSnapshot(wanted),wantedBefore,'new JWKS runtime dependency graph changed');
      const oldEntry = fs.realpathSync(fileURLToPath(import.meta.resolve(name,pathToFileURL(path.join(consumer,'__packaging_check__.mjs')).href)));
      assert.equal(oldEntry,path.join(slot,'src','index.js'));
      mirrors.push({name,version:'4.0.1',replaced_root_alias_version:'3.2.2',preserved_parent_private_version:'3.2.2',relocation:'hoisted-root-moved-intact-to-Teams-private-slot',preserved_runtime_nodes:before.nodes.length,preserved_runtime_edges:before.edges.length});
      return wanted;
    };

    // The frozen lock intentionally has two Pierre-theme versions: the diffs
    // plugin directly uses 0.0.29; @pierre/diffs 1.1.13 privately uses 0.0.28.
    // pnpm prune can leave the latter as the undeclared root alias. Correct only
    // that measured root layout; preserve every real package and private consumer.
    const repairPinnedThemeAlias = (name, packageDir, needs) => {
      if (name !== '@pierre/theme' || !packageDir || needs.every(({spec}) => semver.satisfies(readPackage(packageDir).version, spec))) return packageDir;
      assert.equal(readPackage(packageDir).version, '0.0.28');
      assert.deepEqual(needs, [{plugin:'diffs', spec:'0.0.29'}]);
      const rootPackage = readPackage(root);
      for (const section of ['dependencies', 'optionalDependencies', 'devDependencies', 'peerDependencies']) assert(!(name in (rootPackage[section] ?? {})), `root explicitly declares ''${name}`);
      for (const key of Object.keys(rootPackage.pnpm?.overrides ?? {})) assert(!key.includes(name), `root overrides ''${name}`);
      const wanted = target(path.join(root, 'extensions', 'diffs'), name);
      assert(wanted && wanted !== packageDir, 'missing distinct frozen diffs theme0.0.29');
      assert.equal(readPackage(wanted).version, '0.0.29');
      const diffsDir = target(root, '@pierre/diffs');
      assert(diffsDir, 'missing frozen Pierre-diffs context');
      assert.equal(readPackage(diffsDir).version, '1.1.13');
      const privateTheme = target(diffsDir, name);
      assert(privateTheme, 'missing Pierre-diffs private theme');
      assert.equal(readPackage(privateTheme).version, '0.0.28');
      const link = path.join(root, 'node_modules', ...name.split('/'));
      const original = fs.lstatSync(link);
      assert.equal(fs.realpathSync(link), packageDir);
      let preservedPrivate = privateTheme;
      let relocation = 'existing-private-link';
      if (original.isSymbolicLink()) {
        fs.unlinkSync(link);
      } else {
        assert(original.isDirectory() && packageDir === link, 'unexpected root package layout');
        assert.equal(privateTheme, packageDir, 'refusing an existing private graph conflict');
        const meta = readPackage(packageDir);
        assert.equal(Object.keys(meta.dependencies ?? {}).length, 0, 'theme has runtime dependencies');
        assert.equal(Object.keys(meta.optionalDependencies ?? {}).length, 0, 'theme has optional runtime dependencies');
        const slot = path.join(diffsDir, 'node_modules', ...name.split('/'));
        assert(!fs.existsSync(slot), 'refusing an existing private slot');
        try { fs.lstatSync(slot); assert.fail('refusing a dangling private slot'); } catch (e) { if (e.code !== 'ENOENT') throw e; }
        const parent = path.dirname(slot);
        for (const dir of [path.join(diffsDir, 'node_modules'), parent]) {
          try { const st = fs.lstatSync(dir); assert(st.isDirectory() && !st.isSymbolicLink() && fs.realpathSync(dir) === dir, 'private slot ancestor symlink escape'); } catch (e) { if (e.code !== 'ENOENT') throw e; }
        }
        fs.mkdirSync(parent, {recursive:true});
        for (const dir of [path.join(diffsDir, 'node_modules'), parent]) assert.equal(fs.realpathSync(dir), dir, 'private slot ancestor symlink escape');
        fs.renameSync(link, slot);
        preservedPrivate = fs.realpathSync(slot);
        assert.deepEqual(readPackage(preservedPrivate), meta, 'moved theme manifest changed');
        relocation = 'hoisted-root-moved-intact-to-private-slot';
      }
      fs.symlinkSync(path.relative(path.dirname(link), wanted), link);
      assert.equal(target(root, name), wanted);
      assert.equal(target(diffsDir, name), preservedPrivate, 'Pierre-diffs private resolution changed');
      assert.equal(readPackage(preservedPrivate).version, '0.0.28');
      mirrors.push({name, version:'0.0.29', replaced_root_alias_version:'0.0.28', preserved_parent_private_version:'0.0.28', relocation});
      return wanted;
    };

    const deps = new Map();
    assert(fs.existsSync(pluginRoot), 'built bundled plugins are missing');
    for (const ent of fs.readdirSync(pluginRoot, {withFileTypes:true})) {
      if (!ent.isDirectory()) continue;
      const file = path.join(pluginRoot, ent.name, 'package.json');
      if (!fs.existsSync(file)) continue;
      const manifest = JSON.parse(fs.readFileSync(file, 'utf8'));
      for (const [name, spec] of Object.entries({...manifest.dependencies, ...manifest.optionalDependencies})) {
        assert(semver.validRange(spec), `unsupported dependency range: ''${ent.name}/''${name}=''${spec}`);
        if (!deps.has(name)) deps.set(name, []);
        deps.get(name).push({plugin:ent.name, spec});
      }
    }
    const mirrors = [];
    for (const [name, needs] of deps) {
      let packageDir = repairPinnedJwksAlias(name, repairPinnedThemeAlias(name, target(root, name), needs), needs);
      if (!packageDir) {
        const options = needs.map(({plugin}) => target(path.join(root, 'extensions', plugin), name)).filter(Boolean);
        packageDir = options.find(p => needs.every(({spec}) => semver.satisfies(readPackage(p).version, spec)));
        assert(packageDir, `missing frozen runtime dependency: ''${name} (''${JSON.stringify(needs)})`);
        const link = path.join(root, 'node_modules', ...name.split('/'));
        assert(!fs.existsSync(link), `refusing to replace existing dependency: ''${name}`);
        fs.mkdirSync(path.dirname(link), {recursive:true});
        fs.symlinkSync(path.relative(path.dirname(link), packageDir), link);
        mirrors.push({name, version:readPackage(packageDir).version});
      }
      const manifest = readPackage(packageDir);
      for (const {plugin, spec} of needs) assert(semver.satisfies(manifest.version, spec), `''${plugin}/''${name}: ''${manifest.version} does not satisfy ''${spec}`);
      // This pinned package deliberately has no root export. The frozen Discord
      // runtime uses these two published subpaths (not a fabricated root module).
      const entries = name === 'discord-api-types' ? [name + '/v10', name + '/payloads/v10'] : name === '@tloncorp/tlon-skill' ? [] : [name];
      if (name === '@tloncorp/tlon-skill') {
        // This package exposes a CLI and skills, not a JavaScript root module.
        assert.equal(manifest.version,'0.3.5');
        assert.equal(manifest.main,undefined);assert.equal(manifest.exports,undefined);
        assert.deepEqual(manifest.bin,{tlon:'./bin/tlon.js'});
        for (const relative of ['package.json','bin/tlon.js','SKILL.md']) {
          const file=fs.realpathSync(path.join(packageDir,relative));
          assert(inside(file) && fs.statSync(file).isFile(),`missing or escaped Tlon CLI/skill asset: ''${relative}`);
        }
        const platformName=`@tloncorp/tlon-skill-''${process.platform}-''${process.arch}`;
        const platformDir=target(packageDir,platformName);
        assert(platformDir,'missing Tlon native platform package');
        assert.equal(readPackage(platformDir).version,'0.3.5');
        const native=fs.realpathSync(path.join(platformDir,'tlon'));
        assert(inside(native) && fs.statSync(native).isFile(),'missing or escaped Tlon native executable');
        fs.accessSync(native,fs.constants.X_OK);
        const wrapperRequire=createRequire(path.join(packageDir,'bin','tlon.js'));
        assert.equal(fs.realpathSync(path.dirname(wrapperRequire.resolve(platformName+'/package.json'))),platformDir);
      }
      if (name === 'discord-api-types') assert.equal(manifest.version, '0.38.45');
      for (const specifier of entries) {
        const entry = import.meta.resolve(specifier, rootDistUrl);
        assert(entry.startsWith('file:'), `non-file runtime entry: ''${specifier}`);
        assert(inside(fs.realpathSync(fileURLToPath(entry))), `runtime entry escapes graph: ''${specifier}`);
      }
      // Validate native optional children from their actual PNPM package context.
      for (const [child, spec] of Object.entries(manifest.optionalDependencies ?? {})) {
        const tokens = child.toLowerCase().split(/[/@._-]+/).filter(Boolean);
        if (!tokens.includes(process.platform) || !tokens.includes(process.arch)) continue;
        const glibc = Boolean(process.report.getReport().header.glibcVersionRuntime);
        if ((glibc && tokens.includes('musl')) || (!glibc && tokens.includes('gnu'))) continue;
        const childDir = target(packageDir, child);
        assert(childDir, `missing native child: ''${name}/''${child}`);
        assert(semver.satisfies(readPackage(childDir).version, spec), `native child range mismatch: ''${name}/''${child}`);
      }
    }
    const {applyBaileysEncryptedStreamFinishHotfix} = await import(pathToFileURL(path.join(root, 'scripts', 'postinstall-bundled-plugins.mjs')));
    const hotfix = applyBaileysEncryptedStreamFinishHotfix({packageRoot:root});
    assert(['patched', 'already_patched'].includes(hotfix.reason), `Baileys hotfix failed: ''${JSON.stringify(hotfix)}`);
    console.log(JSON.stringify({schema_version:1, runtime_dependencies:deps.size, mirrored:mirrors, baileys_hotfix:hotfix.reason, network_install:false}));
  '';
  # The pinned 0.4.0 wrapper downloads this native library in postinstall.
  # Stage the exact official asset without network access in the gateway build.
  matrixCryptoNative = openclawPkgs.fetchurl {
    name = "matrix-sdk-crypto-0.4.0-linux-x64-gnu.node";
    url = "https://github.com/matrix-org/matrix-rust-sdk-crypto-nodejs/releases/download/v0.4.0/matrix-sdk-crypto.linux-x64-gnu.node";
    hash = "sha256-cHjU3ZhxKPea/RksT2IfZK3s435D8qh1bx0KnwNN5xg=";
  };
  offlineGateway = openclawPackages.openclaw-gateway.overrideAttrs (old: {
    nativeBuildInputs = (old.nativeBuildInputs or [ ]) ++ [ openclawPkgs.patchelf ];
    # Preserve the upstream install and disabled generic fixup. Correct only
    # this measured bundled Linux binary after its final output layout exists.
    installPhase = ''
      ${old.installPhase}
      tlonPackage="$out/lib/openclaw/node_modules/@tloncorp/tlon-skill-linux-x64"
      tlonBinary="$tlonPackage/tlon"
      test "${openclawPkgs.stdenv.hostPlatform.system}" = x86_64-linux
      test -f "$tlonBinary" && test -x "$tlonBinary"
      test "$(realpath "$tlonBinary")" = "$tlonBinary"
      ${openclawPkgs.jq}/bin/jq -e '.name == "@tloncorp/tlon-skill-linux-x64" and .version == "0.3.5"' "$tlonPackage/package.json" >/dev/null
      test "$(sha256sum "$tlonBinary" | cut -d ' ' -f 1)" = 59455bde0f1817605753e90ff9255499b2dbcc22ecce959782638996d4aef39f
      test "$(${openclawPkgs.patchelf}/bin/patchelf --print-interpreter "$tlonBinary")" = /lib64/ld-linux-x86-64.so.2
      test -z "$(${openclawPkgs.patchelf}/bin/patchelf --print-rpath "$tlonBinary")"
      expectedNeeded="$(printf '%s\n' libc.so.6 ld-linux-x86-64.so.2 libpthread.so.0 libdl.so.2 libm.so.6 | LC_ALL=C sort)"
      test "$(${openclawPkgs.patchelf}/bin/patchelf --print-needed "$tlonBinary" | LC_ALL=C sort)" = "$expectedNeeded"
      tlonInterpreter="${openclawPkgs.stdenv.cc.bintools.dynamicLinker}"
      tlonRpath="${lib.makeLibraryPath [ openclawPkgs.glibc ]}"
      test -f "$tlonInterpreter" && test -x "$tlonInterpreter"
      # The actual patched native segfaults; the exact original runs with this
      # loader. Preserve its embedded payload and wrap only the native entry.
      tlonUnwrapped="$tlonPackage/tlon-unwrapped"
      test ! -e "$tlonUnwrapped" && test ! -L "$tlonUnwrapped"
      test -f "${openclawPkgs.runtimeShell}" && test -x "${openclawPkgs.runtimeShell}"
      mv "$tlonBinary" "$tlonUnwrapped"
      printf '#!%s\nexec "%s" --library-path "%s" "%s" "$@"\n' \
        "${openclawPkgs.runtimeShell}" "$tlonInterpreter" "$tlonRpath" "$tlonUnwrapped" > "$tlonBinary"
      chmod 0755 "$tlonBinary"
      test -f "$tlonBinary" && test -x "$tlonBinary"
      test "$(realpath "$tlonBinary")" = "$tlonBinary"
      test "$(realpath "$tlonUnwrapped")" = "$tlonUnwrapped"
      test "$(sha256sum "$tlonUnwrapped" | cut -d ' ' -f 1)" = 59455bde0f1817605753e90ff9255499b2dbcc22ecce959782638996d4aef39f
      printf '%s\n' 'Tlon 0.3.5 Linux x64 original bytes and selected glibc loader wrapper verified'
      matrixPackage="$out/lib/openclaw/node_modules/@matrix-org/matrix-sdk-crypto-nodejs"
      matrixBinary="$matrixPackage/matrix-sdk-crypto.linux-x64-gnu.node"
      test -d "$matrixPackage"
      test "$(realpath "$matrixPackage")" = "$matrixPackage"
      ${openclawPkgs.jq}/bin/jq -e '.name == "@matrix-org/matrix-sdk-crypto-nodejs" and .version == "0.4.0"' "$matrixPackage/package.json" >/dev/null
      test ! -e "$matrixBinary" && test ! -L "$matrixBinary"
      test "$(stat -c %s ${matrixCryptoNative})" = 22027000
      test "$(sha256sum ${matrixCryptoNative} | cut -d ' ' -f 1)" = 7078d4dd987128f79afd192c4f621f64adece37e43f2a8756f1d0a9f034de718
      install -m 0644 ${matrixCryptoNative} "$matrixBinary"
      test "$(realpath "$matrixBinary")" = "$matrixBinary"
      matrixNeeded="$(printf '%s\n' libgcc_s.so.1 libm.so.6 libc.so.6 ld-linux-x86-64.so.2 | LC_ALL=C sort)"
      test "$(${openclawPkgs.patchelf}/bin/patchelf --print-needed "$matrixBinary" | LC_ALL=C sort)" = "$matrixNeeded"
      test -z "$(${openclawPkgs.patchelf}/bin/patchelf --print-rpath "$matrixBinary")"
      matrixRpath="${
        lib.makeLibraryPath [
          openclawPkgs.stdenv.cc.cc.lib
          openclawPkgs.glibc
        ]
      }"
      test -f "${openclawPkgs.stdenv.cc.cc.lib}/lib/libgcc_s.so.1"
      ${openclawPkgs.patchelf}/bin/patchelf --set-rpath "$matrixRpath" "$matrixBinary"
      test "$(${openclawPkgs.patchelf}/bin/patchelf --print-rpath "$matrixBinary")" = "$matrixRpath"
      test "$(${openclawPkgs.patchelf}/bin/patchelf --print-needed "$matrixBinary" | LC_ALL=C sort)" = "$matrixNeeded"
      printf '%s\n' 'Matrix crypto 0.4.0 official native SHA256 7078d4dd987128f79afd192c4f621f64adece37e43f2a8756f1d0a9f034de718 and selected libgcc/glibc RPATH verified'
    '';
    buildPhase = ''
      env OPENCLAW_DISABLE_BUNDLED_PLUGIN_POSTINSTALL=1 ${old.buildPhase}
      ${openclawPkgs.nodejs_22}/bin/node --experimental-import-meta-resolve \
        ${offlineRuntimeCheck} ${openclawPkgs.nodejs_22}/lib/node_modules/npm/package.json
    '';
  });
  offlineOpenclaw = openclawPackages.openclaw.override {
    openclaw-gateway = offlineGateway;
  };
in
{
  options.weasel.roles.openclaw = {
    enable = lib.mkEnableOption "OpenClaw server role";
    gatewayTokenFile = lib.mkOption {
      type = lib.types.nullOr lib.types.path;
      default = null;
      description = "Optional token file for the OpenClaw gateway scaffold.";
    };
    documents = lib.mkOption {
      type = lib.types.path;
      default = ../../../openclaw/documents;
      description = "Pinned OpenClaw documents directory.";
    };
  };

  config = lib.mkIf cfg.enable {
    users.groups.openclaw = { };
    users.users.openclaw = {
      isNormalUser = true;
      description = "OpenClaw service user";
      group = "openclaw";
      home = "/var/lib/openclaw";
      createHome = true;
      linger = true;
    };

    systemd.tmpfiles.rules = [
      "d /var/lib/openclaw 0750 openclaw openclaw -"
      "d /var/lib/openclaw/.openclaw 0750 openclaw openclaw -"
      "d /var/lib/openclaw/workspace 0750 openclaw openclaw -"
    ];

    home-manager.users.openclaw = {
      imports = [ inputs.nix-openclaw.homeManagerModules.openclaw ];
      nixpkgs.overlays = [ securePnpmOverlay ];

      home = {
        username = "openclaw";
        homeDirectory = "/var/lib/openclaw";
        stateVersion = "24.11";
      };

      programs.home-manager.enable = true;
      programs.openclaw = {
        enable = true;
        package = offlineOpenclaw;
        documents = cfg.documents;
        exposePluginPackages = false;
        installApp = false;
        systemd.enable = false;
        launchd.enable = false;
        stateDir = "/var/lib/openclaw/.openclaw";
        workspaceDir = "/var/lib/openclaw/workspace";
        config = {
          gateway.mode = "local";
        };
      };
    };
  };
}
