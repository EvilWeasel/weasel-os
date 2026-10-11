#!/usr/bin/env python3
"""PROPOSED separately approved, immutable 25.11 -> 26.05 policy transition.

Installed only through a separately reviewed signed bootstrap; ordinary
batch/request inputs do not authorize this opt-in.
Caller-supplied receipts, policy flags and arbitrary defaults are not accepted.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re


class MigrationError(RuntimeError):
    pass


# Explicit opt-in in the proposed immutable helper, never a request/CLI field.
# Installing this statement requires separate user authorization for the real
# sudo env_keep policy change, the narrow SSH adapter and activator hardening.
APPROVED_2511_TO_2605_ENV_KEEP = True
TRANSITION = {
    "old": {
        "release": "25.11",
        "locked": {"lastModified": 1777673416,
                   "narHash": "sha256-5c2POKPOjU40Kh0MirOdScBLG0bu9TAuPYAtPRNZMBs=",
                   "owner": "nixos", "repo": "nixpkgs", "type": "github",
                   "rev": "26ef669cffa904b6f6832ab57b77892a37c1a671"},
        "modules": {
            "nixos/modules/services/networking/ssh/sshd.nix":
                "7569d4d8e6259056de6e8e9e44d85cdc6bb11cc4811500a7393551b1661a86a4",
            "nixos/modules/system/activation/switchable-system.nix":
                "181ecbd6d6a7ff154f67d2a9e6e7c4d0df1e204a5416c90b57427d5dc83be4e8",
        },
    },
    "new": {
        "release": "26.05",
        "locked": {"lastModified": 1791426274,
                   "narHash": "sha256-MWhktfFtFE8Jl7bf9Pkp7TR5MSdYCjCswSo0Gkb4ywc=",
                   "owner": "nixos", "repo": "nixpkgs", "type": "github",
                   "rev": "7c8764b7c7b09b34f632464276218ef9090eaa11"},
        "modules": {
            "nixos/modules/services/networking/ssh/sshd.nix":
                "263b0bf3dfd9f106a33bcdc7db99fd0e4673666b2e4b4186c9c0907913c2d10c",
            "nixos/modules/system/activation/switchable-system.nix":
                "1197dc074558d7ef1d55daa1f2fd5b5cc4e4cd56e2bf3e458c3f7d70f81b528c",
        },
    },
}
SSH_OLD_KEYS = tuple(sorted([
    "AllowGroups", "AllowUsers", "AuthorizedPrincipalsFile", "Ciphers",
    "DenyGroups", "DenyUsers", "GatewayPorts", "KbdInteractiveAuthentication",
    "KexAlgorithms", "LogLevel", "Macs", "PasswordAuthentication",
    "PermitRootLogin", "PrintMotd", "StrictModes", "UseDns", "UsePAM",
    "X11Forwarding",
]))
SSH_ADDED_NULL_KEYS = ("AcceptEnv", "Banner")
SUDO_PREFIX = "Defaults env_keep+=NIXOS_NO_CHECK\n\n"
STORE = re.compile(r"/nix/store/[0-9a-z]{32}-[A-Za-z0-9.+_?=-]+")
HEX = re.compile(r"[0-9a-f]{64}")


def reject_switch_bypass_environment(environment):
    # Even an empty variable is a policy violation; never normalize it away.
    if "NIXOS_NO_CHECK" in environment:
        raise MigrationError("NIXOS_NO_CHECK is forbidden in protected activation")


LEGACY_BASELINE_LOCK_SHA256 = "734d9ff0fe2bdbfa8e8f0a1cf6273f38c2a4d8944f9bb02134734ad49e95cfc1"


def object_json(value, *, legacy_baseline_lock=False):
    legacy_permitted = (legacy_baseline_lock and isinstance(value, bytes) and
                        hashlib.sha256(value).hexdigest() == LEGACY_BASELINE_LOCK_SHA256)
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    def unique(items):
        result = {}
        for key, item in items:
            if key in result:
                if not (legacy_permitted and key == "systems_4" and result[key] == item):
                    raise MigrationError("Duplicate JSON field")
            result[key] = item
        return result
    try:
        parsed = json.loads(value, object_pairs_hook=unique,
                            parse_constant=lambda value: (_ for _ in ()).throw(MigrationError("Non-finite JSON")))
    except (ValueError, UnicodeError, TypeError) as error:
        raise MigrationError("Invalid migration evidence JSON") from error
    if not isinstance(parsed, dict):
        raise MigrationError("Migration evidence must be an object")
    return parsed


def check_lock(source, side):
    expected = TRANSITION[side]
    lock = object_json((Path(source) / "flake.lock").read_bytes(), legacy_baseline_lock=side == "old")
    try:
        target = lock["nodes"][lock["root"]]["inputs"]["nixpkgs"]
        if not isinstance(target, str):
            raise MigrationError("Migration requires the exact stable input, not an alias")
        node = lock["nodes"][target]
        original = {"owner": "nixos", "repo": "nixpkgs", "type": "github",
                    "ref": "nixos-" + expected["release"]}
        if node != {"locked": expected["locked"], "original": original}:
            raise MigrationError("Migration stable input is outside the reviewed exact revision")
    except (KeyError, TypeError) as error:
        raise MigrationError("Migration stable lock node is missing") from error



def etc_binding_fragment():
    """Match the actual installation targets, not just etc attribute names.

    Every enabled target must be canonical and unique. Protected parent paths,
    SSH namespace entries, system manager configuration and SSH PAM are bound
    to independently generated official entries including their ownership,
    enabled state and copy/symlink mode. No entry content leaves Nix.
    """
    return (
        'etcCanonical = target: builtins.isString target && target != "" && '
        'builtins.all (part: part != "" && part != "." && part != "..") (cleanPkgs.lib.splitString "/" target); '
        'etcProtected = target: target == "ssh" || cleanPkgs.lib.hasPrefix "ssh/" target || '
        'target == "systemd" || target == "systemd/system" || '
        'cleanPkgs.lib.hasPrefix "systemd/system/" target || '
        'builtins.elem target ["systemd/system.mode" "systemd/system.uid" "systemd/system.gid"] || '
        'cleanPkgs.lib.hasPrefix "systemd/system.conf" target || '
        'target == "pam.d" || cleanPkgs.lib.hasPrefix "pam.d/sshd" target; '
        'etcMetadata = entry: (select ["enable" "target" "mode" "uid" "gid" "user" "group"] entry) '
        '// { source = toString entry.source; }; '
        'etcProtectedEntries = entries: builtins.mapAttrs (_: etcMetadata) '
        '(cleanPkgs.lib.filterAttrs (_: entry: etcProtected entry.target) entries); '
        'etcEnabledTargets = map (entry: entry.target) '
        '(builtins.filter (entry: entry.enable) (builtins.attrValues c.environment.etc)); '
        'etcTargetsOkay = builtins.all (entry: etcCanonical entry.target) '
        '(builtins.attrValues c.environment.etc) && '
        'builtins.length etcEnabledTargets == builtins.length (cleanPkgs.lib.unique etcEnabledTargets) && '
        'builtins.toJSON (etcProtectedEntries c.environment.etc) == '
        'builtins.toJSON (etcProtectedEntries trustedEtcEntries); '
        'sshAuthEtc = etcProtectedEntries (cleanPkgs.lib.filterAttrs (_: entry: '
        'cleanPkgs.lib.hasPrefix "ssh/authorized_keys.d/" entry.target || '
        'cleanPkgs.lib.hasPrefix "ssh/authorized_principals.d/" entry.target) c.environment.etc); '
        'sshAuthRoles = builtins.mapAttrs (_: entry: (builtins.removeAttrs entry ["source"]) // { '
        'source = "exact independently composed authorized-file role"; }) sshAuthEtc; '
        'sshAuthData = builtins.mapAttrs (_: user: { inherit (user) name; '
        'keys = user.openssh.authorizedKeys.keys; '
        'key_files_sha256 = map (file: builtins.hashFile "sha256" file) user.openssh.authorizedKeys.keyFiles; '
        'principals = user.openssh.authorizedPrincipals; }) c.users.users; '
        'sshAuthDataSha256 = builtins.hashString "sha256" (builtins.toJSON sshAuthData); '
    )


def package_identity_fragment():
    """Bind every immutable output selection actually used by module helpers.

    Nix's package type accepts attrsets with a legitimate drvPath and spoofed
    default coercion/outPath. Compare those identities independently and retain
    outputSpecified semantics and both declared and conventional getOutput
    selections. Never import the SOURCE systemd package into expected modules.
    """
    return (
        'outputIdentity = package: { derivation_path = package.drvPath; output_path = package.outPath; '
        'coerced = toString package; outputName = package.outputName or null; '
        'outputSpecified = package.outputSpecified or false; }; '
        'packageIdentity = package: { default = outputIdentity package; '
        'outputs = package.outputs; selected = builtins.listToAttrs (map '
        '(name: { inherit name; value = if builtins.hasAttr name package then '
        'outputIdentity package.${name} else null; }) '
        '(cleanPkgs.lib.unique (package.outputs ++ ["out" "bin" "lib" "dev" "man" "doc" "info" "debug"]))); }; '
        'samePackage = actual: expected: builtins.toJSON (packageIdentity actual) == '
        'builtins.toJSON (packageIdentity expected); '
    )


CLIENT_LIBVIRT_EXTRA = "Include ${cleanPkgs.libvirt}/etc/ssh/ssh_config.d/30-libvirt-ssh-proxy.conf\n"
CLIENT_GPG_EXTRA = """# The SSH agent protocol doesn't have support for changing TTYs; however we
# can simulate this with the `exec` feature of openssh (see ssh_config(5))
# that hooks a command to the shell currently running the ssh program.
Match host * exec "${cleanPkgs.runtimeShell} -c '${cleanPkgs.gnupg}/bin/gpg-connect-agent --quiet updatestartuptty /bye >/dev/null 2>&1'"
"""


def client_extra_fragment():
    """Bind complete official generated stanzas; retain every authored byte.

    This is forced only by the SSH-policy fingerprint, preserving the existing
    complete SSH-unit predicate. Unused packages remain lazy on other hosts.
    """
    return (
        'clientFlags = { libvirtEnable = c.virtualisation.libvirtd.enable; '
        'libvirtSSHProxy = c.virtualisation.libvirtd.sshProxy; '
        'gnupgAgentEnable = c.programs.gnupg.agent.enable; '
        'gnupgSSHSupport = c.programs.gnupg.agent.enableSSHSupport; }; '
        'clientLibvirtUsed = clientFlags.libvirtEnable && clientFlags.libvirtSSHProxy; '
        'clientGpgUsed = clientFlags.gnupgAgentEnable && clientFlags.gnupgSSHSupport; '
        'clientLibvirtStanza = ' + json.dumps(CLIENT_LIBVIRT_EXTRA) + '; '
        'clientGpgStanza = ' + json.dumps(CLIENT_GPG_EXTRA) + '; '
        'clientLibvirtRole = "<exact-canonical-libvirt-client-include>\\n"; '
        'clientGpgRole = "<exact-canonical-gnupg-client-match>\\n"; '
        'clientCount = stanza: builtins.div '
        '(builtins.stringLength sshClient.extraConfig - '
        'builtins.stringLength (builtins.replaceStrings [stanza] [""] sshClient.extraConfig)) '
        '(builtins.stringLength stanza); '
        'clientBindingsOkay = builtins.all builtins.isBool (builtins.attrValues clientFlags) && '
        '!cleanPkgs.lib.hasInfix clientLibvirtRole sshClient.extraConfig && '
        '!cleanPkgs.lib.hasInfix clientGpgRole sshClient.extraConfig && '
        '(!clientLibvirtUsed || (samePackage c.virtualisation.libvirtd.package cleanPkgs.libvirt && '
        'clientCount clientLibvirtStanza == 1)) && '
        '(!clientGpgUsed || (samePackage c.programs.gnupg.package cleanPkgs.gnupg && '
        'samePackage host.pkgs.bash cleanPkgs.bash && '
        'builtins.isString host.pkgs.runtimeShell && host.pkgs.runtimeShell == cleanPkgs.runtimeShell && '
        'clientCount clientGpgStanza == 1)); '
        'clientNormalized = builtins.replaceStrings '
        '(cleanPkgs.lib.optional clientLibvirtUsed clientLibvirtStanza ++ cleanPkgs.lib.optional clientGpgUsed clientGpgStanza) '
        '(cleanPkgs.lib.optional clientLibvirtUsed clientLibvirtRole ++ cleanPkgs.lib.optional clientGpgUsed clientGpgRole) '
        'sshClient.extraConfig; '
    )


def ssh_binding_fragment(side, *, locked=None, release=None):
    """Independently compose the exact official SSH module without SOURCE code.

    SSH, xauth, systemd and output helpers are composed from plain locked inputs;
    default coercion and selected outputs must equal those trusted packages.
    Source server extraConfig, units, hooks, environment and custom etc drop-ins
    cannot influence the expected SSH module. Credentials remain inside Nix.
    """
    locked = TRANSITION[side]["locked"] if locked is None else locked
    release = TRANSITION[side]["release"] if release is None else release
    pinned_input = "{ " + "; ".join(key + " = " + json.dumps(locked[key]) for key in ["type", "owner", "repo", "rev", "narHash"]) + "; }"
    return (
        'trustedNixpkgs = builtins.fetchTree ' + pinned_input + '; '
        'cleanPkgs = import trustedNixpkgs.outPath { system = host.pkgs.stdenv.hostPlatform.system; config.allowUnfree = true; }; '
        + package_identity_fragment() +
        'sshCfg = c.services.openssh; sshClient = c.programs.ssh; '
        'pamLimitsSeed = map (limit: select ["domain" "type" "item" "value"] limit) c.security.pam.loginLimits; '
        'pamLimitsArtifact = cleanPkgs.writeText "limits.conf" (cleanPkgs.lib.concatMapStrings '
        '(limit: "${limit.domain} ${limit.type} ${limit.item} ${toString limit.value}\\n") pamLimitsSeed); '
        'nssCatalog = { systemd = cleanPkgs.systemd.out; nssmdns = cleanPkgs.nssmdns; libvirt = cleanPkgs.libvirt; }; '
        'nssNames = map (package: let matches = builtins.filter (name: samePackage package '
        'nssCatalog.${name}) (builtins.attrNames nssCatalog); '
        'in assert builtins.length matches == 1; builtins.head matches) c.system.nssModules.list; '
        'sshSeed = select ["enable" "openFirewall" "ports" "listenAddresses" "startWhenNeeded" '
        '"allowSFTP" "sftpFlags" "authorizedKeysInHomedir" "authorizedKeysCommand" '
        '"authorizedKeysCommandUser" "hostKeys" "settings"] sshCfg; '
        'trustedSSH = (import (trustedNixpkgs.outPath + "/nixos/lib/eval-config.nix") { '
        'system = host.pkgs.stdenv.hostPlatform.system; modules = [({ lib, ... }: { '
        'nixpkgs.pkgs = cleanPkgs; system.stateVersion = c.system.stateVersion; '
        'services.openssh = sshSeed // { package = cleanPkgs.openssh; '
        'authorizedKeysFiles = lib.mkForce sshCfg.authorizedKeysFiles; }; '
        'programs.ssh.setXAuthLocation = sshClient.setXAuthLocation; '
        'programs.ssh.extraConfig = sshClient.extraConfig; '
        'security.pam.package = cleanPkgs.pam; security.pam.loginLimits = lib.mkForce pamLimitsSeed; '
        'users.users = lib.mkForce (builtins.mapAttrs (_: user: select ["name" "openssh"] user) c.users.users); '
        'networking.enableIPv6 = c.networking.enableIPv6; '
        'system.nssModules = lib.mkForce (map (name: nssCatalog.${name}) nssNames); '
        'systemd.package = cleanPkgs.systemd; '
        'systemd.globalEnvironment = lib.mkForce c.systemd.globalEnvironment; '
        'system.fsPackages = lib.mkForce c.system.fsPackages; '
        '})]; }).config; '
        'trustedSelection = (import (trustedNixpkgs.outPath + "/nixos/lib/eval-config.nix") { '
        'system = host.pkgs.stdenv.hostPlatform.system; modules = [({ lib, ... }: { '
        'nixpkgs.pkgs = cleanPkgs; boot.isContainer = c.boot.isContainer; '
        'systemd.package = cleanPkgs.systemd; systemd.units = lib.mkForce c.systemd.units; '
        'systemd.suppressedSystemUnits = lib.mkForce c.systemd.suppressedSystemUnits; '
        'systemd.additionalUpstreamSystemUnits = lib.mkForce c.systemd.additionalUpstreamSystemUnits; '
        'systemd.packages = lib.mkForce c.systemd.packages; '
        'systemd.defaultUnit = c.systemd.defaultUnit; systemd.ctrlAltDelUnit = c.systemd.ctrlAltDelUnit; '
        '})]; }).config; '
        'pamLimitsEnabled = trustedSSH.security.pam.services.sshd.rules.session.limits.enable; '
        'pamLimitsPath = if pamLimitsEnabled then toString pamLimitsArtifact else null; '
        'pamLimitsOkay = !pamLimitsEnabled || '
        'trustedSSH.security.pam.services.sshd.rules.session.limits.settings.conf == pamLimitsPath; '
        'sshNames = units: builtins.filter (name: builtins.match "sshd.*" name != null) (builtins.attrNames units); '
        'sshUnits = config: builtins.listToAttrs (map (name: { inherit name; '
        'value = select ["enable" "text" "wantedBy" "requiredBy" "upheldBy" "aliases" "overrideStrategy"] '
        'config.systemd.units.${name} // { unitPath = toString config.systemd.units.${name}.unit; }; '
        '}) (sshNames config.systemd.units)); '
        'trustedUtils = import (trustedNixpkgs.outPath + "/nixos/lib/utils.nix") '
        '{ config = c; lib = cleanPkgs.lib; pkgs = cleanPkgs; }; '
        'unitArtifactsOkay = builtins.all (name: let unit = c.systemd.units.${name}; in '
        'unit.name == name && toString unit.unit == toString (trustedUtils.systemdUtils.lib.makeUnit name unit) && '
        '(builtins.match "sshd.*" name != null || builtins.all '
        '(alias: builtins.match "sshd.*" alias == null) unit.aliases)) (builtins.attrNames c.systemd.units); '
        'sshMiniTree = trustedUtils.systemdUtils.lib.generateUnits { type = "system"; '
        'units = select (sshNames c.systemd.units) c.systemd.units; '
        'upstreamUnits = []; upstreamWants = []; packages = c.systemd.packages; package = cleanPkgs.systemd; }; '
        'trustedManagerEntry = trustedSSH.environment.etc."systemd/system.conf" // { '
        'source = cleanPkgs.writeText "etc-systemd-system.conf" '
        '(trustedUtils.systemdUtils.lib.settingsToSections c.systemd.settings); }; '
        'trustedEtcEntries = trustedSSH.environment.etc // { '
        '"systemd/system" = trustedSelection.environment.etc."systemd/system"; '
        '"systemd/system.conf" = trustedManagerEntry; }; '
        'trustedEtc = (import (trustedNixpkgs.outPath + "/nixos/lib/eval-config.nix") { '
        'system = host.pkgs.stdenv.hostPlatform.system; modules = [({ lib, ... }: { '
        'nixpkgs.pkgs = cleanPkgs; environment.etc = lib.mkForce c.environment.etc; '
        'system.etc.overlay = c.system.etc.overlay; '
        '})]; }).config; '
        + etc_binding_fragment() +
        'sshBindingsOkay = f.inputs.nixpkgs.outPath == trustedNixpkgs.outPath && sshCfg.enable && sshCfg.allowSFTP && builtins.isBool sshClient.setXAuthLocation && !sshCfg.startWhenNeeded && '
        '(sshCfg.generateHostKeys or true) && '
        + ('(sshCfg.banner or null) == null && ' if release == '25.11' else 'sshCfg.settings.Banner == null && ') +
        'samePackage sshCfg.package cleanPkgs.openssh && '
        'samePackage c.systemd.package cleanPkgs.systemd && '
        'samePackage c.security.pam.package cleanPkgs.pam && pamLimitsOkay && '
        'samePackage host.pkgs.xauth cleanPkgs.xauth && '
        'sshCfg.moduliFile == "${cleanPkgs.openssh}/etc/ssh/moduli" && '
        'sshCfg.sftpServerExecutable == "${cleanPkgs.openssh}/libexec/sftp-server" && '
        'sshCfg.extraConfig == trustedSSH.services.openssh.extraConfig && '
        'toString c.environment.etc."ssh/sshd_config".source == '
        'toString trustedSSH.environment.etc."ssh/sshd_config".source && '
        'builtins.toJSON (sshUnits c) == builtins.toJSON (sshUnits trustedSSH) && '
        'etcTargetsOkay && !c.system.etc.overlay.enable && unitArtifactsOkay && '
        'samePackage c.system.build.etc trustedEtc.system.build.etc && '
        'c.system.build.etcActivationCommands == trustedEtc.system.build.etcActivationCommands && '
        'builtins.toJSON c.system.activationScripts.etc == builtins.toJSON trustedEtc.system.activationScripts.etc && '
        'toString c.environment.etc."systemd/system".source == '
        'toString trustedSelection.environment.etc."systemd/system".source && '
        'builtins.all (name: builtins.match "sshd.*" name == null) '
        '(c.systemd.suppressedSystemUnits ++ c.systemd.additionalUpstreamSystemUnits) && '
        'c.boot.extraSystemdUnitPaths == [] && '
        'builtins.attrNames c.systemd.managerEnvironment == ["LOCALE_ARCHIVE" "PATH" "TZDIR"] && '
        'builtins.toJSON c.systemd.managerEnvironment == builtins.toJSON trustedSSH.systemd.managerEnvironment && '
        '!(c.systemd.settings.Manager ? DefaultEnvironment) && '
        'c.systemd.settings.Manager.ManagerEnvironment == trustedSSH.systemd.settings.Manager.ManagerEnvironment; '
        'sshPolicy = (builtins.removeAttrs sshSeed ["settings"]) // { '
        'enableIPv6 = c.networking.enableIPv6; setXAuthLocation = sshClient.setXAuthLocation; '
        'clientExtraConfig = let ' + client_extra_fragment() +
        'in assert clientBindingsOkay; { flags = clientFlags; text = clientNormalized; }; '
        'pamLoginLimits = pamLimitsSeed; '
        'pamLimitsSha256 = if pamLimitsEnabled then builtins.hashFile "sha256" pamLimitsPath else null; '
        'authorizedKeysFiles = sshCfg.authorizedKeysFiles; '
        'nssModules = nssNames; auth_files = sshAuthRoles; auth_data_sha256 = sshAuthDataSha256; '
        'etcOverlay = c.system.etc.overlay; '
        'managerSettings = c.systemd.settings // { Manager = builtins.removeAttrs c.systemd.settings.Manager ["ManagerEnvironment"]; }; '
        'pamPolicy = if sshCfg.settings.UsePAM then builtins.replaceStrings '
        '([ (toString cleanPkgs.pam) (toString cleanPkgs.systemd) ] ++ cleanPkgs.lib.optional pamLimitsEnabled pamLimitsPath) '
        '([ "<exact-plain-locked-root-pam>" "<exact-plain-locked-root-systemd>" ] ++ '
        'cleanPkgs.lib.optional pamLimitsEnabled "<exact-canonical-pam-limits-conf>") '
        '(builtins.concatStringsSep "\\n" (map (line: let matched = builtins.match '
        '"(.* # [a-zA-Z0-9_-]+ [(]order )[0-9]+([)])" line; in '
        'if matched == null then line else builtins.elemAt matched 0 + "<exact-generated-order>" + builtins.elemAt matched 1) '
        '(cleanPkgs.lib.splitString "\\n" c.security.pam.services.sshd.text))) else null; '
        'extraConfig = "independently composed official defaults only"; '
        'configuration = "exact independently composed configuration"; '
        'units = "exact independently composed SSH units only"; }; '
    )


RELEASE_DEFAULT_MODULE_HASHES = {'old': {'nixos/modules/services/hardware/fwupd.nix': '9134b196b8223bc717256dcba10f1874560c33f09d049c4c559c1c70f95620d0', 'nixos/modules/services/networking/wpa_supplicant.nix': 'f32280d59c7738c6489568a08432ee706657c05cbb6e8010f05d3553b12d5494', 'nixos/modules/config/users-groups.nix': 'd6be558009cd13b9ab77b6b1777ecad2eb5633e3177cc5caef188e8148013c86', 'nixos/modules/services/networking/networkmanager.nix': '7b3931f661a297499880aac2085d12e78e5843e4066a71ea22b5a1e72db8f626'}, 'new': {'nixos/modules/services/hardware/fwupd.nix': '0fd23f2fc41bcfa96e3b8b37a9817b1abe29c328b737611eb03a105ad84078be', 'nixos/modules/services/networking/wpa_supplicant.nix': 'a89c0a1970cc138be81d0336ee5f65ae4e6fd8b8694cfc3438331959567bb5ca', 'nixos/modules/config/users-groups.nix': 'aecddf364abdea311aa6ec3774c422fce7d9b852bc3e2d8cf6092f7f0625499c', 'nixos/modules/services/networking/networkmanager.nix': '3ee6969c2af4a590251fce63a030c9649c04f908d7a7148c366fe9f443defc6b'}}

FWUPD_REFRESH_RULE = """polkit.addRule(function(action, subject) {
  if ((action.id == "org.freedesktop.fwupd.get-remotes" ||
       action.id == "org.freedesktop.fwupd.refresh-remote") &&
      subject.user == "fwupd-refresh") {
    return polkit.Result.YES;
  }
});
"""


def release_defaults_fragment(side):
    """Finite migration-only proof of two exact independently composed defaults.

    No ordinary-batch input enables this projection. Account credentials, groups,
    packages and selected/vendor units are checked before removing either delta.
    """
    if side not in TRANSITION:
        raise MigrationError("Unknown release-default proof side")
    old = side == "old"
    controlled = ("builtins.isAttrs rw.userControlled && builtins.attrNames rw.userControlled == [\"enable\" \"group\"] && "
                  "rw.userControlled.enable == false && rw.userControlled.group == \"wheel\"" if old else
                  "builtins.isBool rw.userControlled && rw.userControlled == false")
    controlled_seed = '{ enable = false; group = "wheel"; }' if old else 'false'
    auto_detect = ('true' if old else
                   'builtins.isBool rw.autoDetectInterfaces && '
                   'builtins.isBool trustedReleaseDefaults.networking.wireless.autoDetectInterfaces && '
                   'rw.autoDetectInterfaces == trustedReleaseDefaults.networking.wireless.autoDetectInterfaces')
    return (
        'rw = c.networking.wireless; nm = c.networking.networkmanager; '
        'releaseNMFlags = { enable = nm.enable; unmanaged = nm.unmanaged; backend = nm.wifi.backend; }; '
        'releaseNMFlagsOkay = builtins.isBool releaseNMFlags.enable && builtins.isList releaseNMFlags.unmanaged && '
        'builtins.all builtins.isString releaseNMFlags.unmanaged && builtins.isString releaseNMFlags.backend && '
        'builtins.elem releaseNMFlags.backend ["wpa_supplicant" "iwd"]; '
        'releaseNMMode = releaseNMFlagsOkay && releaseNMFlags.enable && releaseNMFlags.unmanaged == [] && '
        'releaseNMFlags.backend == "wpa_supplicant"; '
        'releaseFlags = { networkManager = releaseNMFlags; wireless = if releaseNMMode then '
        '{ interfaces = rw.interfaces; } else select ["enable" "dbusControlled" "interfaces"] rw; '
        'userControlled = false; fwupdEnable = c.services.fwupd.enable; supportedLocales = c.i18n.supportedLocales; }; '
        'releaseControlOkay = ' + controlled + '; '
        'trustedReleaseDefaults = (import (trustedNixpkgs.outPath + "/nixos/lib/eval-config.nix") { '
        'system = host.pkgs.stdenv.hostPlatform.system; modules = [({ lib, ... }: { '
        'nixpkgs.pkgs = cleanPkgs; system.stateVersion = c.system.stateVersion; '
        'users.mutableUsers = c.users.mutableUsers; boot.isContainer = c.boot.isContainer; '
        'systemd.package = cleanPkgs.systemd; i18n.supportedLocales = releaseFlags.supportedLocales; '
        'networking.wireless = releaseFlags.wireless // { userControlled = ' + controlled_seed + '; }; '
        'networking.networkmanager = lib.mkIf releaseNMMode { enable = releaseNMFlags.enable; '
        'unmanaged = releaseNMFlags.unmanaged; wifi.backend = releaseNMFlags.backend; package = cleanPkgs.networkmanager; }; '
        'services.fwupd.enable = releaseFlags.fwupdEnable; services.fwupd.package = cleanPkgs.fwupd; '
        '})]; }).config; '
        'releaseUser = user: select ["uid" "isNormalUser" "isSystemUser" "home" "homeMode" "createHome" '
        '"group" "extraGroups" "hashedPassword" "hashedPasswordFile" "password" "initialPassword" '
        '"initialHashedPassword" "openssh" "expires" "linger" "cryptHomeLuks" "pamMount"] user; '
        'releaseGroup = group: select ["gid" "members"] group; '
        'releaseAccountOkay = name: let actual = c.users.users.${name}; expected = trustedReleaseDefaults.users.users.${name}; '
        'in actual.name == name && expected.name == name && '
        'c.users.groups.${name}.name == name && trustedReleaseDefaults.users.groups.${name}.name == name && '
        'builtins.toJSON (releaseUser actual) == builtins.toJSON (releaseUser expected) && '
        'actual.isSystemUser && !actual.isNormalUser && actual.extraGroups == [] && '
        'builtins.toJSON actual.openssh == builtins.toJSON expected.openssh && '
        'samePackage actual.shell cleanPkgs.shadow && samePackage expected.shell cleanPkgs.shadow && '
        'actual.shell.shellPath == expected.shell.shellPath && expected.shell.shellPath == "/bin/nologin" && '
        'builtins.toJSON (releaseGroup c.users.groups.${name}) == '
        'builtins.toJSON (releaseGroup trustedReleaseDefaults.users.groups.${name}) && '
        'c.users.groups.${name}.members == []; '
        'releaseUnit = config: name: let u = config.systemd.units.${name}; in '
        'select ["enable" "text" "wantedBy" "requiredBy" "upheldBy" "aliases" "overrideStrategy"] u // '
        '{ unitPath = toString u.unit; }; '
        'releaseWpaNames = config: builtins.filter (name: builtins.match "wpa_supplicant.*" name != null) '
        '(builtins.attrNames config.systemd.units); '
        'releaseWpaUnits = config: builtins.listToAttrs (map (name: { inherit name; '
        'value = releaseUnit config name; }) (releaseWpaNames config)); '
        'releaseWpaExpected = ' + ('false' if old else 'rw.enable') + '; '
        'releaseNMOkay = !releaseNMMode || (rw.networks == {} && '
        'samePackage nm.package cleanPkgs.networkmanager && '
        'builtins.toJSON (select ["enable" "dbusControlled"] rw) == '
        'builtins.toJSON (select ["enable" "dbusControlled"] trustedReleaseDefaults.networking.wireless)); '
        'releaseWpaOkay = (if releaseWpaExpected then '
        'releaseAccountOkay "wpa_supplicant" && rw.enableHardening == true && '
        'rw.enableHardening == trustedReleaseDefaults.networking.wireless.enableHardening '
        'else !(c.users.users ? wpa_supplicant) && !(c.users.groups ? wpa_supplicant)) && '
        '(!rw.enable || (samePackage host.pkgs.wpa_supplicant cleanPkgs.wpa_supplicant && '
        'rw.networks == {} && rw.secretsFile == null && rw.extraConfigFiles == [] && '
        'rw.extraConfig == trustedReleaseDefaults.networking.wireless.extraConfig && '
        'builtins.toJSON (releaseWpaUnits c) == builtins.toJSON (releaseWpaUnits trustedReleaseDefaults))); '
        'releaseLocaleOkay = builtins.isList releaseFlags.supportedLocales && '
        'builtins.all builtins.isString releaseFlags.supportedLocales && '
        'samePackage c.i18n.glibcLocales trustedReleaseDefaults.i18n.glibcLocales && '
        'builtins.toJSON c.systemd.globalEnvironment == builtins.toJSON trustedReleaseDefaults.systemd.globalEnvironment; '
        'releaseFwupdProviders = builtins.filter (p: builtins.pathExists (toString p + "/lib/systemd/system/fwupd-refresh.service")) c.systemd.packages; '
        'releaseFwupdOkay = !releaseFlags.fwupdEnable || '
        '(samePackage c.services.fwupd.package cleanPkgs.fwupd && builtins.length releaseFwupdProviders == 1 && '
        'samePackage (builtins.head releaseFwupdProviders) cleanPkgs.fwupd && releaseAccountOkay "fwupd-refresh" && '
        'builtins.toJSON (releaseUnit c "fwupd-refresh.service") == '
        'builtins.toJSON (releaseUnit trustedReleaseDefaults "fwupd-refresh.service") && '
        'builtins.readFile (toString c.environment.etc."systemd/system".source + "/fwupd-refresh.service") == '
        'builtins.readFile (toString cleanPkgs.fwupd + "/lib/systemd/system/fwupd-refresh.service")); '
        'releaseRule = ' + json.dumps(FWUPD_REFRESH_RULE) + '; '
        'releaseHasRule = ' + ('false' if old else 'releaseFlags.fwupdEnable') + '; '
        'releasePolkitText = v.polkit.extraConfig; '
        'releaseRuleCount = builtins.div (builtins.stringLength releasePolkitText - '
        'builtins.stringLength (builtins.replaceStrings [releaseRule] [""] releasePolkitText)) '
        '(builtins.stringLength releaseRule); '
        'releaseRuleOkay = if releaseHasRule then releaseRuleCount == 1 && '
        'builtins.stringLength releasePolkitText > builtins.stringLength releaseRule && '
        'builtins.substring (builtins.stringLength releasePolkitText - builtins.stringLength releaseRule - 1) 1 releasePolkitText == "\\n" && '
        'builtins.substring (builtins.stringLength releasePolkitText - builtins.stringLength releaseRule) '
        '(builtins.stringLength releaseRule) releasePolkitText == releaseRule else releaseRuleCount == 0; '
        'releasePolkitNormalized = if releaseHasRule then builtins.substring 0 '
        '(builtins.stringLength releasePolkitText - builtins.stringLength releaseRule - 1) releasePolkitText '
        'else releasePolkitText; '
        'releaseGroups = builtins.mapAttrs (_: group: releaseGroup group) c.users.groups; '
        'releaseGroupsNormalized = if releaseWpaExpected then builtins.removeAttrs releaseGroups ["wpa_supplicant"] else releaseGroups; '
        'releaseUsersNormalized = if releaseWpaExpected then builtins.removeAttrs v.users ["wpa_supplicant"] else v.users; '
        'releaseSSHPolicy = sshPolicy // cleanPkgs.lib.optionalAttrs releaseWpaExpected '
        '{ auth_data_sha256 = hash (builtins.removeAttrs sshAuthData ["wpa_supplicant"]); }; '
        'releaseDefaultsOkay = releaseNMFlagsOkay && releaseNMOkay && releaseControlOkay && releaseLocaleOkay && builtins.isBool releaseFlags.fwupdEnable && '
        'builtins.isBool rw.enable && builtins.isBool rw.dbusControlled && '
        '(' + auto_detect + ') && '
        'builtins.isList releaseFlags.wireless.interfaces && builtins.all builtins.isString releaseFlags.wireless.interfaces && releaseWpaOkay && releaseFwupdOkay && releaseRuleOkay; '
    )


def expression(sensitive_expression, source, host, side):
    """Preserve every original assertion and private hash; expose no secrets."""
    raw = sensitive_expression(source, host)
    suffix = 'builtins.hashString "sha256" (builtins.toJSON v)'
    if not raw.endswith(suffix):
        raise MigrationError("Sensitive expression changed; adapter must be reviewed again")
    expected = TRANSITION[side]
    nix_list = lambda values: "[" + " ".join(json.dumps(value) for value in values) + "]"
    names = nix_list(SSH_ADDED_NULL_KEYS)
    prefix = json.dumps(SUDO_PREFIX)
    old_keys = nix_list(SSH_OLD_KEYS)
    wanted_keys = old_keys if side == "old" else nix_list(sorted(SSH_OLD_KEYS + SSH_ADDED_NULL_KEYS))
    ssh_shape = ('builtins.attrNames v.ssh.settings == ' + wanted_keys +
                 (' && !builtins.hasAttr "AcceptEnv" v.ssh.settings && !builtins.hasAttr "Banner" v.ssh.settings'
                  if side == "old" else
                  ' && v.ssh.settings.AcceptEnv == null && v.ssh.settings.Banner == null'))
    sudo_shape = ('true' if side == "old" else
                  'builtins.substring 0 (builtins.stringLength prefix) v.sudo.extraConfig == prefix')
    sudo_value = ('v.sudo.extraConfig' if side == "old" else
                  'builtins.substring (builtins.stringLength prefix) (builtins.stringLength v.sudo.extraConfig) v.sudo.extraConfig')
    module_fields = '; '.join(json.dumps(name) + ' = builtins.hashFile "sha256" (f.inputs.nixpkgs.outPath + ' +
                             json.dumps("/" + name) + ')' for name in (expected["modules"] | RELEASE_DEFAULT_MODULE_HASHES[side]))
    result = (
        'let hash = value: builtins.hashString "sha256" (builtins.toJSON value); '
        + ssh_binding_fragment(side) + release_defaults_fragment(side) +
        'prefix = ' + prefix + '; '
        'normalized = v // { '
        'ssh = v.ssh // { settings = builtins.removeAttrs v.ssh.settings ' + names + '; }; '
        'sudo = v.sudo // { extraConfig = ' + sudo_value + '; }; '
        'users = releaseUsersNormalized; polkit = v.polkit // { extraConfig = releasePolkitNormalized; }; }; '
        'in assert (sshBindingsOkay && releaseDefaultsOkay && ' + ssh_shape + ' && ' + sudo_shape + '); '
        'builtins.toJSON { schema = 1; raw_sha256 = hash v; normalized_sha256 = hash (normalized // { sshPolicy = releaseSSHPolicy; releaseDefaults = { flags = releaseFlags; groups = releaseGroupsNormalized; }; }); '
        'release = c.system.nixos.release; ssh_keys = builtins.attrNames v.ssh.settings; '
        'ssh_added_fields_are_null = ' + ('false' if side == "old" else 'true') + '; '
        'sudo_prefix_accepted = ' + ('false' if side == "old" else 'true') + '; '
        'module_sha256 = { ' + module_fields + '; }; }'
    )
    return raw[:-len(suffix)] + result


def validate_envelope(value, side):
    value = object_json(value)
    fields = {"schema", "raw_sha256", "normalized_sha256", "release", "ssh_keys",
              "ssh_added_fields_are_null", "sudo_prefix_accepted", "module_sha256"}
    expected = TRANSITION[side]
    expected_keys = list(SSH_OLD_KEYS) if side == "old" else sorted(SSH_OLD_KEYS + SSH_ADDED_NULL_KEYS)
    if set(value) != fields or type(value["schema"]) is not int or value["schema"] != 1:
        raise MigrationError("Unknown migration evidence schema or fields")
    if any(not isinstance(value[key], str) or not HEX.fullmatch(value[key])
           for key in ["raw_sha256", "normalized_sha256"]):
        raise MigrationError("Invalid migration fingerprint")
    if (value["release"] != expected["release"] or value["ssh_keys"] != expected_keys or
        value["ssh_added_fields_are_null"] is not (side == "new") or
        value["sudo_prefix_accepted"] is not (side == "new") or
        value["module_sha256"] != (expected["modules"] | RELEASE_DEFAULT_MODULE_HASHES[side])):
        raise MigrationError("Migration evidence is outside the typed reviewed transition")
    return value


def parse_effective_output(data):
    if isinstance(data, bytes):
        data = data.decode("utf-8")
    if len(data) > 1024 * 1024:
        raise MigrationError("Effective SSH output is too large")
    values = {}
    spellings = {}
    for line in data.splitlines():
        if not line or " " not in line:
            raise MigrationError("Malformed effective SSH output")
        keyword, value = line.split(" ", 1)
        if not re.fullmatch("[A-Za-z][A-Za-z0-9]*", keyword):
            raise MigrationError("Unexpected effective SSH keyword")
        # OpenSSH 10.5 prints MixedCase names. Fold only strict ASCII keys;
        # values remain exact and differently cased aliases never merge.
        key = keyword.lower()
        if key in spellings and spellings[key] != keyword:
            raise MigrationError("Duplicate case-insensitive effective SSH keyword alias")
        spellings[key] = keyword
        values.setdefault(key, []).append(value)
    return values


# sshd -T emits these scalar authentication/policy fields on both pinned
# releases. Allow/Deny lists may legitimately be absent (empty); everything
# else in the full output is compared too, including previously unselected
# AuthenticationMethods, PubkeyAuthentication and PermitUserEnvironment.
OPTIONAL_EMPTY_KEYS = {"allowgroups", "allowusers", "denygroups", "denyusers"}
REQUIRED_EFFECTIVE_KEYS = (set(v.lower() for v in SSH_OLD_KEYS) - OPTIONAL_EMPTY_KEYS) | {
    "banner", "authenticationmethods", "pubkeyauthentication", "permituserenvironment",
    "hostbasedauthentication", "ignorerhosts", "ignoreuserknownhosts", "permitemptypasswords",
    "maxauthtries", "maxsessions", "maxstartups", "authorizedkeysfile", "authorizedkeyscommand",
    "authorizedkeyscommanduser", "forcecommand", "chrootdirectory", "trustedusercakeys",
    "revokedkeys", "permittty", "permituserrc", "allowtcpforwarding", "allowagentforwarding",
    "allowstreamlocalforwarding", "disableforwarding", "permitopen", "permitlisten",
    "port", "addressfamily", "subsystem", "xauthlocation",
}
# Plain locked-root OpenSSH is built without Kerberos/GSSAPI, so its daemon
# omits GSSAPIAuthentication from -T. If emitted, it remains in the complete
# equality comparison below; presence, value and scalar duplication must match.
# Only public multi-valued output forms documented/observed in the official
# daemon can repeat. Singleton duplication always fails, even if byte-equal.
MULTIVALUED_EFFECTIVE_KEYS = {"hostkey", "listenaddress", "subsystem", "acceptenv"}


SSH_DEFAULT_TRANSITION_VERSIONS = ("10.2p1", "10.5p1")
SSH_DEFAULT_TRANSITION_VALUES = {'casignaturealgorithms': ('ssh-ed25519,ecdsa-sha2-nistp256,ecdsa-sha2-nistp384,ecdsa-sha2-nistp521,sk-ssh-ed25519@openssh.com,sk-ecdsa-sha2-nistp256@openssh.com,rsa-sha2-512,rsa-sha2-256', 'ssh-ed25519,ecdsa-sha2-nistp256,ecdsa-sha2-nistp384,ecdsa-sha2-nistp521,sk-ssh-ed25519@openssh.com,sk-ecdsa-sha2-nistp256@openssh.com,webauthn-sk-ecdsa-sha2-nistp256@openssh.com,rsa-sha2-512,rsa-sha2-256'), 'hostbasedacceptedalgorithms': ('ssh-ed25519-cert-v01@openssh.com,ecdsa-sha2-nistp256-cert-v01@openssh.com,ecdsa-sha2-nistp384-cert-v01@openssh.com,ecdsa-sha2-nistp521-cert-v01@openssh.com,sk-ssh-ed25519-cert-v01@openssh.com,sk-ecdsa-sha2-nistp256-cert-v01@openssh.com,rsa-sha2-512-cert-v01@openssh.com,rsa-sha2-256-cert-v01@openssh.com,ssh-ed25519,ecdsa-sha2-nistp256,ecdsa-sha2-nistp384,ecdsa-sha2-nistp521,sk-ssh-ed25519@openssh.com,sk-ecdsa-sha2-nistp256@openssh.com,rsa-sha2-512,rsa-sha2-256', 'ssh-ed25519-cert-v01@openssh.com,ecdsa-sha2-nistp256-cert-v01@openssh.com,ecdsa-sha2-nistp384-cert-v01@openssh.com,ecdsa-sha2-nistp521-cert-v01@openssh.com,sk-ssh-ed25519-cert-v01@openssh.com,sk-ecdsa-sha2-nistp256-cert-v01@openssh.com,webauthn-sk-ecdsa-sha2-nistp256-cert-v01@openssh.com,rsa-sha2-512-cert-v01@openssh.com,rsa-sha2-256-cert-v01@openssh.com,ssh-ed25519,ecdsa-sha2-nistp256,ecdsa-sha2-nistp384,ecdsa-sha2-nistp521,sk-ssh-ed25519@openssh.com,sk-ecdsa-sha2-nistp256@openssh.com,webauthn-sk-ecdsa-sha2-nistp256@openssh.com,rsa-sha2-512,rsa-sha2-256'), 'hostkeyalgorithms': ('ssh-ed25519-cert-v01@openssh.com,ecdsa-sha2-nistp256-cert-v01@openssh.com,ecdsa-sha2-nistp384-cert-v01@openssh.com,ecdsa-sha2-nistp521-cert-v01@openssh.com,sk-ssh-ed25519-cert-v01@openssh.com,sk-ecdsa-sha2-nistp256-cert-v01@openssh.com,rsa-sha2-512-cert-v01@openssh.com,rsa-sha2-256-cert-v01@openssh.com,ssh-ed25519,ecdsa-sha2-nistp256,ecdsa-sha2-nistp384,ecdsa-sha2-nistp521,sk-ssh-ed25519@openssh.com,sk-ecdsa-sha2-nistp256@openssh.com,rsa-sha2-512,rsa-sha2-256', 'ssh-ed25519-cert-v01@openssh.com,ecdsa-sha2-nistp256-cert-v01@openssh.com,ecdsa-sha2-nistp384-cert-v01@openssh.com,ecdsa-sha2-nistp521-cert-v01@openssh.com,sk-ssh-ed25519-cert-v01@openssh.com,sk-ecdsa-sha2-nistp256-cert-v01@openssh.com,webauthn-sk-ecdsa-sha2-nistp256-cert-v01@openssh.com,rsa-sha2-512-cert-v01@openssh.com,rsa-sha2-256-cert-v01@openssh.com,ssh-ed25519,ecdsa-sha2-nistp256,ecdsa-sha2-nistp384,ecdsa-sha2-nistp521,sk-ssh-ed25519@openssh.com,sk-ecdsa-sha2-nistp256@openssh.com,webauthn-sk-ecdsa-sha2-nistp256@openssh.com,rsa-sha2-512,rsa-sha2-256'), 'pubkeyacceptedalgorithms': ('ssh-ed25519-cert-v01@openssh.com,ecdsa-sha2-nistp256-cert-v01@openssh.com,ecdsa-sha2-nistp384-cert-v01@openssh.com,ecdsa-sha2-nistp521-cert-v01@openssh.com,sk-ssh-ed25519-cert-v01@openssh.com,sk-ecdsa-sha2-nistp256-cert-v01@openssh.com,rsa-sha2-512-cert-v01@openssh.com,rsa-sha2-256-cert-v01@openssh.com,ssh-ed25519,ecdsa-sha2-nistp256,ecdsa-sha2-nistp384,ecdsa-sha2-nistp521,sk-ssh-ed25519@openssh.com,sk-ecdsa-sha2-nistp256@openssh.com,rsa-sha2-512,rsa-sha2-256', 'ssh-ed25519-cert-v01@openssh.com,ecdsa-sha2-nistp256-cert-v01@openssh.com,ecdsa-sha2-nistp384-cert-v01@openssh.com,ecdsa-sha2-nistp521-cert-v01@openssh.com,sk-ssh-ed25519-cert-v01@openssh.com,sk-ecdsa-sha2-nistp256-cert-v01@openssh.com,webauthn-sk-ecdsa-sha2-nistp256-cert-v01@openssh.com,rsa-sha2-512-cert-v01@openssh.com,rsa-sha2-256-cert-v01@openssh.com,ssh-ed25519,ecdsa-sha2-nistp256,ecdsa-sha2-nistp384,ecdsa-sha2-nistp521,sk-ssh-ed25519@openssh.com,sk-ecdsa-sha2-nistp256@openssh.com,webauthn-sk-ecdsa-sha2-nistp256@openssh.com,rsa-sha2-512,rsa-sha2-256'), 'persourcepenalties': ('crash:90 authfail:5 noauth:1 grace-exceeded:10 refuseconnection:10 max:600 min:15 max-sources4:65536 max-sources6:65536 overflow:permissive overflow6:permissive', 'crash:90.000000 authfail:5.000000 noauth:1.000000 invaliduser:5.000000 grace-exceeded:10.000000 refuseconnection:10.000000 max:600.000000 min:15.000000 max-sources4:65536 max-sources6:65536 overflow:permissive overflow6:permissive')}


def verify_compiled_default_output(output, *, version=None):
    """Validate canonical /dev/null defaults, not a configured SSH policy.

    The exact daemon has no configured SFTP subsystem with /dev/null. Only
    that required key differs; configured-output comparison below still
    requires it. Preserve every observed field and the complete output digest.
    """
    values = parse_effective_output(output)
    required = REQUIRED_EFFECTIVE_KEYS - {"subsystem"}
    # The exact 10.5 canonical /dev/null parse renders an empty RevokedKeys
    # array by omission. A configured override is never inferred from this.
    omitted_revocation = version == "10.5p1" and "revokedkeys" not in values
    if version == "10.5p1" and "revokedkeys" in values:
        raise MigrationError("Canonical OpenSSH 10.5 empty revocation rendering changed")
    if omitted_revocation:
        required = required - {"revokedkeys"}
    if not required <= set(values):
        raise MigrationError("Canonical SSH defaults omit required policy fields")
    if any(len(items) != 1 for key, items in values.items() if key not in MULTIVALUED_EFFECTIVE_KEYS):
        raise MigrationError("Canonical SSH defaults duplicate a scalar policy field")
    if values["banner"] != ["none"]:
        raise MigrationError("Canonical SSH defaults do not preserve Banner none")
    if values.get("acceptenv", []) != []:
        raise MigrationError("Canonical SSH defaults accept caller environment")
    if any(key in values and values[key] == [""] for key in OPTIONAL_EMPTY_KEYS):
        raise MigrationError("Ambiguous empty SSH defaults list output")
    digest = hashlib.sha256(output if isinstance(output, bytes) else output.encode()).hexdigest()
    return {"ok": True, "coverage": "Complete canonical /dev/null defaults; required unique policy fields except unconfigured subsystem; parse-only",
            "checked_keys": sorted(values), "optional_absent_keys": sorted(OPTIONAL_EMPTY_KEYS - set(values)),
            "verified_executable_path_substitutions": False, "version": version,
            "canonical_empty_revocation_omitted": omitted_revocation,
            "old_output_sha256": digest, "new_output_sha256": digest}


def compare_effective_outputs(old_output, new_output, identities=None):
    before, after = (parse_effective_output(v) for v in [old_output, new_output])
    for values in [before, after]:
        if not REQUIRED_EFFECTIVE_KEYS <= set(values):
            raise MigrationError("Fresh built SSH output omits required complete policy fields")
        if any(len(items) != 1 for key, items in values.items() if key not in MULTIVALUED_EFFECTIVE_KEYS):
            raise MigrationError("Fresh built SSH output duplicates a scalar policy field")
        if values["banner"] != ["none"]:
            raise MigrationError("Fresh built SSH daemon does not preserve Banner none")
        if values.get("acceptenv", []) != []:
            raise MigrationError("Fresh built SSH daemon accepts new caller environment")
        if any(key in values and values[key] == [""] for key in OPTIONAL_EMPTY_KEYS):
            raise MigrationError("Ambiguous empty SSH list output")
    # Store-path changes are permitted only for the exact plain locked-root
    # xauth binary and exact official openssh sftp executable bound by the
    # independently composed module. No arbitrary path/command is normalized.
    if identities is not None:
        if len(identities) != 2:
            raise MigrationError("Missing paired trusted SSH executable identities")
        if any(type(identity.get("set_xauth_location")) is not bool for identity in identities):
            raise MigrationError("Missing typed SSH XAuth configuration identity")
        if identities[0]["set_xauth_location"] != identities[1]["set_xauth_location"]:
            raise MigrationError("SSH XAuth configuration option changed")
        for values, identity in zip([before, after], identities):
            if values["xauthlocation"] != [identity["xauth"]]:
                raise MigrationError("Effective SSH xauth executable is outside the trusted package")
            if values["subsystem"] != [identity["subsystem"]]:
                raise MigrationError("Effective SSH subsystem is outside the trusted package")
            # A false option retains the literal default emitted by this exact
            # canonical daemon with /dev/null; it is never a store substitution.
            if identity["set_xauth_location"]:
                values["xauthlocation"] = ["<exact-plain-locked-root-xauth>"]
            values["subsystem"] = ["<exact-plain-locked-root-sftp>"]
            for keyword, executable in [("sshdauthpath", "sshd-auth"), ("sshdsessionpath", "sshd-session")]:
                if keyword in identity:
                    expected = identity[keyword]
                    if (not isinstance(expected, str) or
                        not re.fullmatch(STORE.pattern + "/libexec/" + executable, expected) or
                        values.get(keyword) != [expected]):
                        raise MigrationError("Effective SSH helper is outside the trusted package: " + keyword)
                    values[keyword] = ["<exact-plain-locked-root-" + executable + ">"]
    if before != after:
        changed = sorted(key for key in set(before) | set(after) if before.get(key) != after.get(key))
        raise MigrationError("Fresh built SSH daemon changes effective policy: " + ", ".join(changed))
    return {"ok": True, "coverage": "Complete effective SSH output; required unique policy fields; parse-only, no SSH listener/authentication",
            "checked_keys": sorted(before), "optional_absent_keys": sorted(OPTIONAL_EMPTY_KEYS - set(before)),
            "verified_executable_path_substitutions": identities is not None,
            "old_output_sha256": hashlib.sha256(old_output if isinstance(old_output, bytes) else old_output.encode()).hexdigest(),
            "new_output_sha256": hashlib.sha256(new_output if isinstance(new_output, bytes) else new_output.encode()).hexdigest()}


def compare_proven_effective_outputs(old_output, new_output, identities, default_outputs, *, allow_default_transition=False):
    """Keep configured policy strict; accept only canonical evidenced deltas.

    Default outputs come from this invocation's exact canonical daemons, not
    a request, source file or historical receipt. Ordinary batches retain no
    opt-in for semantic algorithm/penalty changes.
    """
    if type(allow_default_transition) is not bool:
        raise MigrationError("SSH default transition authorization must be typed")
    if len(identities) != 2 or len(default_outputs) != 2:
        raise MigrationError("Missing paired canonical SSH default evidence")
    versions = tuple(identity.get("version") for identity in identities)
    default_proofs = [verify_compiled_default_output(output, version=version)
                      for output, version in zip(default_outputs, versions)]
    defaults = [parse_effective_output(output) for output in default_outputs]
    configured = [parse_effective_output(output) for output in [old_output, new_output]]
    for canonical, identity in zip(defaults, identities):
        for keyword in ["sshdauthpath", "sshdsessionpath"]:
            if keyword in identity and canonical.get(keyword) != [identity[keyword]]:
                raise MigrationError("Canonical SSH default helper is outside the trusted package: " + keyword)
    omitted_revocation = []
    for values, canonical, version in zip(configured, defaults, versions):
        omitted = "revokedkeys" not in values
        if omitted:
            if version != "10.5p1" or "revokedkeys" in canonical:
                raise MigrationError("Configured SSH revocation omission lacks exact canonical evidence")
            values["revokedkeys"] = ["none"]
        omitted_revocation.append(omitted)
    approved = []
    if allow_default_transition:
        if versions != SSH_DEFAULT_TRANSITION_VERSIONS:
            raise MigrationError("SSH default transition is outside exact OpenSSH 10.2 to 10.5")
        if defaults[0].get("revokedkeys") != ["none"] or "revokedkeys" in defaults[1]:
            raise MigrationError("Canonical SSH default revocation transition changed")
        if set(defaults[0]) - set(defaults[1]) != {"revokedkeys"} or set(defaults[1]) - set(defaults[0]):
            raise MigrationError("Canonical SSH default transition introduces unexpected fields")
        for keyword, expected in SSH_DEFAULT_TRANSITION_VALUES.items():
            if any(values.get(keyword) != [value] for values, value in zip(defaults, expected)):
                raise MigrationError("Canonical SSH default transition changed: " + keyword)
            if configured[0].get(keyword) != configured[1].get(keyword):
                if any(values.get(keyword) != canonical.get(keyword)
                       for values, canonical in zip(configured, defaults)):
                    raise MigrationError("Authored SSH policy differs from its own canonical defaults: " + keyword)
                for values in configured:
                    values[keyword] = ["<exact-reviewed-10.2-to-10.5-default-" + keyword + ">"]
                approved.append(keyword)
    encode = lambda values: "".join(key + " " + value + "\n" for key, items in sorted(values.items()) for value in items)
    result = compare_effective_outputs(*(encode(values) for values in configured), identities)
    result.update({"old_output_sha256": hashlib.sha256(old_output if isinstance(old_output, bytes) else old_output.encode()).hexdigest(),
                   "new_output_sha256": hashlib.sha256(new_output if isinstance(new_output, bytes) else new_output.encode()).hexdigest(),
                   "canonical_default_sha256": [proof["old_output_sha256"] for proof in default_proofs],
                   "proven_empty_revocation_rendering": omitted_revocation,
                   "approved_default_transition_fields": approved})
    return result


def verify_selected_ssh_units(tree, units):
    """Bind the built system unit tree to every independently composed unit.

    Packages passed to the official tree builder may supply additional files;
    they must not shadow a reviewed SSH unit or contribute SSH drop-ins.
    No systemd manager or service is queried or executed.
    """
    tree = Path(tree)
    if not tree.is_dir() or tree.resolve() != tree:
        raise MigrationError("Built SSH unit tree is absent or not canonical")
    # Official 26.05 systemd SSH-vsock definitions are exact asDropin units.
    # Their canonical generated files still have the base unit names; only
    # these two independently composed units select overrides.conf instead.
    dropins = {"sshd-vsock.socket", "sshd-vsock@.service"}
    represented = {name + ".d" if name in dropins else name for name in units}
    selected = {path.name for path in tree.iterdir() if path.name.startswith("sshd")}
    if selected != represented:
        raise MigrationError("Built SSH unit tree adds or omits a unit/drop-in")
    result = {}
    for name, root in sorted(units.items()):
        expected = Path(root) / name
        actual = tree / name
        if name in dropins:
            directory = tree / (name + ".d")
            if (not directory.is_dir() or directory.is_symlink() or
                {path.name for path in directory.iterdir()} != {"overrides.conf"}):
                raise MigrationError("Built SSH drop-in directory differs from the independently composed unit")
            actual = directory / "overrides.conf"
            if not actual.is_symlink():
                raise MigrationError("Built SSH drop-in selection is not its exact canonical symlink")
        if (not expected.is_file() or not actual.is_file() or
            actual.resolve() != expected.resolve() or
            not str(expected.resolve()).startswith("/nix/store/")):
            raise MigrationError("Built SSH unit selection differs from the independently composed unit")
        result[name] = {"expected_unit": str(expected), "selected_file": str(actual.resolve()),
                        "sha256": hashlib.sha256(expected.read_bytes()).hexdigest()}
    return result


def verify_built_ssh(old_source, new_source, host, evaluator, executor, *, locked_pair=None, releases=None, allow_default_transition=False):
    """Build both exact configured daemons/configs, then parse in private /etc.

    Executors are fixed closures from the immutable preparer/root verifier,
    never a caller receipt or request argument. No host key, login, socket or
    daemon is used. -G -T matches both official modules' parse-only check.
    """
    if executor is None:
        raise MigrationError("Fresh built effective SSH verification is required")
    reject_switch_bypass_environment(os.environ)
    observations = []
    for index, source in enumerate([old_source, new_source]):
        side = "old" if index == 0 else "new"
        base = ('let f = builtins.getFlake ' + json.dumps("path:" + str(Path(source).absolute())) +
                '; host = f.nixosConfigurations.' + host + '; c = host.config; '
                'select = names: attrs: builtins.listToAttrs (map (name: { inherit name; value = attrs.${name} or null; }) names); ' +
                ssh_binding_fragment(side, locked=None if locked_pair is None else locked_pair[index],
                                     release=None if releases is None else releases[index]))
        package = 'c.services.openssh.package.out'
        config = 'c.environment.etc."ssh/sshd_config".source'
        unit_tree = 'sshMiniTree'
        xauth = '"${cleanPkgs.xauth}/bin/xauth"'
        subsystem = '"sftp ${cleanPkgs.openssh}/libexec/sftp-server${if sshCfg.sftpFlags == [] then "" else " " + builtins.concatStringsSep " " sshCfg.sftpFlags}"'
        # This phase is an actual bounded build. Deep evaluation of full unit
        # provenance can require source IFD without realizing the full tree.
        # The typed migration also reads its selected vendor files, so realize
        # that exact aggregate output before the compiler-free information and
        # policy evaluations. Ordinary batches keep the selected SSH outputs.
        # The exact canonical limits artifact, when enabled, is realized here too;
        # an evaluator failure never enables a fallback or another expression.
        migration_tree = ' ++ [c.environment.etc."systemd/system".source]' if allow_default_transition is True else ''
        built = json.loads(executor("nix", ["build", "--no-write-lock-file", "--no-link", "--json", "--impure",
                                           "--option", "allow-import-from-derivation", "true",
                                           "--max-jobs", "1", "--cores", "2", "--expr", base + 'in assert sshBindingsOkay; builtins.deepSeq (toString c.environment.etc."systemd/system".source) [' + package + ' ' + config + ' ' + unit_tree + '] ++ cleanPkgs.lib.optional pamLimitsEnabled pamLimitsArtifact' + migration_tree]))
        info = object_json(evaluator(base + 'in assert sshBindingsOkay; builtins.toJSON { package = toString ' + package +
                                     '; config = toString ' + config + '; ports = c.services.openssh.ports; xauth = ' + xauth +
                                     '; set_xauth_location = sshClient.setXAuthLocation; pam_limits = pamLimitsPath; version = cleanPkgs.openssh.version' +
                                     '; subsystem = ' + subsystem + '; unit_tree = toString ' + unit_tree +
                                     '; root_unit_tree = toString c.environment.etc."systemd/system".source; '
                                     'units = builtins.mapAttrs (_: value: value.unitPath) (sshUnits trustedSSH); }'))
        if (set(info) != {"package", "config", "ports", "xauth", "set_xauth_location", "pam_limits", "version", "subsystem", "unit_tree", "root_unit_tree", "units"} or
            any(not isinstance(info[k], str) or not STORE.fullmatch(info[k]) for k in ["package", "config", "unit_tree", "root_unit_tree"]) or
            not isinstance(info["xauth"], str) or not re.fullmatch(STORE.pattern + r"/bin/xauth", info["xauth"]) or
            type(info["set_xauth_location"]) is not bool or
            not isinstance(info["version"], str) or not re.fullmatch(r"[0-9]+\.[0-9]+p[0-9]+", info["version"]) or
            (info["pam_limits"] is not None and
             (not isinstance(info["pam_limits"], str) or not STORE.fullmatch(info["pam_limits"]))) or
            not isinstance(info["subsystem"], str) or not info["subsystem"].startswith("sftp " + info["package"] + "/libexec/sftp-server") or
            not isinstance(info["units"], dict) or not info["units"] or
            any(not isinstance(k, str) or k not in {"sshd.service", "sshd@.service", "sshd-keygen.service", "sshd-vsock.socket", "sshd-vsock@.service"} or
                not isinstance(v, str) or not STORE.fullmatch(v) for k, v in info["units"].items()) or
            not isinstance(info["ports"], list) or not info["ports"] or
            len(info["ports"]) != len(set(info["ports"])) or
            any(type(v) is not int or not 1 <= v <= 65535 for v in info["ports"])):
            raise MigrationError("Configured SSH build identity is invalid")
        try:
            roots = {p for entry in built for p in entry["outputs"].values()}
        except (TypeError, KeyError) as error:
            raise MigrationError("Configured SSH build outputs are invalid") from error
        expected_roots = {info["package"], info["config"], info["unit_tree"]}
        if info["pam_limits"] is not None:
            expected_roots.add(info["pam_limits"])
        if allow_default_transition is True:
            expected_roots.add(info["root_unit_tree"])
        if roots != expected_roots:
            raise MigrationError("Built SSH outputs do not match this exact configured source")
        daemon = Path(info["package"]) / "bin/sshd"
        configuration = Path(info["config"])
        if not daemon.is_file() or not configuration.is_file():
            raise MigrationError("Built SSH daemon/configuration is missing")
        selected_units = verify_selected_ssh_units(info["unit_tree"], info["units"])
        contexts = [None] + ["user=" + user + ",host=private.invalid,addr=" + address + ",laddr=127.0.0.1,lport=" + str(port)
                             for port in info["ports"] for user in ["evilweasel", "root"]
                             for address in ["127.0.0.1", "198.51.100.23"]]
        parse_arguments = ["--die-with-parent", "--new-session", "--unshare-all", "--clearenv",
                         "--setenv", "LC_ALL", "C", "--setenv", "HOME", "/private",
                         "--ro-bind", "/nix/store", "/nix/store", "--proc", "/proc", "--dev", "/dev",
                         "--tmpfs", "/etc", "--dir", "/etc/ssh", "--tmpfs", "/run", "--dir", "/run/sshd",
                         "--tmpfs", "/tmp", "--tmpfs", "/var", "--dir", "/var/empty",
                         "--dir", "/private", "--chdir", "/private", "--", str(daemon),
                         "-G", "-T", "-f"]
        xauth_identity = info["xauth"]
        compiled_default_proof = None
        default_output = executor("bwrap", parse_arguments + ["/dev/null"])
        # Defaults are always freshly parsed from this exact canonical daemon;
        # the recorded 10.5 empty-array rendering is not a missing-field opt-in.
        compiled_default_proof = verify_compiled_default_output(default_output, version=info["version"])
        if not info["set_xauth_location"]:
            xauth_identity = parse_effective_output(default_output)["xauthlocation"][0]
            if not xauth_identity.startswith("/") or "\n" in xauth_identity:
                raise MigrationError("Canonical compiled XAuth default is invalid")
        outputs = []
        for context in contexts:
            arguments = parse_arguments + [str(configuration)]
            if context is not None:
                arguments += ["-C", context]
            outputs.append(executor("bwrap", arguments))
        observations.append({"package": info["package"], "configuration": info["config"],
                             "daemon_sha256": hashlib.sha256(daemon.read_bytes()).hexdigest(),
                             "configuration_sha256": hashlib.sha256(configuration.read_bytes()).hexdigest(),
                             "contexts": contexts, "outputs": outputs, "selected_units": selected_units,
                             "unit_tree": info["unit_tree"], "full_root_tree_derivation": info["root_unit_tree"],
                             "pam_limits": info["pam_limits"], "compiled_default_proof": compiled_default_proof,
                             "default_output": default_output,
                             "executable_identity": {"xauth": xauth_identity, "subsystem": info["subsystem"],
                                                     "set_xauth_location": info["set_xauth_location"], "version": info["version"],
                                                     "sshdauthpath": info["package"] + "/libexec/sshd-auth",
                                                     "sshdsessionpath": info["package"] + "/libexec/sshd-session"}})
    if observations[0]["contexts"] != observations[1]["contexts"]:
        raise MigrationError("SSH listen-port policy changed")
    results = [compare_proven_effective_outputs(a, b, [v["executable_identity"] for v in observations],
                                               [v["default_output"] for v in observations],
                                               allow_default_transition=allow_default_transition)
               for a, b in zip(observations[0]["outputs"], observations[1]["outputs"])]
    for observation in observations:
        observation.pop("outputs")
        observation.pop("default_output")
    return {"ok": True, "built": observations, "contexts": results}


def general_lock(source, *, legacy_baseline):
    """Independently pin plain packages for ordinary batches without opt-ins."""
    lock = object_json((Path(source)/"flake.lock").read_bytes(), legacy_baseline_lock=legacy_baseline)
    try:
        target=lock["nodes"][lock["root"]]["inputs"]["nixpkgs"]
        if not isinstance(target,str):raise MigrationError("General SSH stable input cannot be an alias")
        node=lock["nodes"][target];locked=node["locked"];original=node["original"]
        if (set(node)!={"locked","original"} or
            set(locked)!={"type","owner","repo","rev","narHash","lastModified"} or
            locked["type"]!="github" or locked["owner"]!="nixos" or locked["repo"]!="nixpkgs" or
            not isinstance(locked["rev"],str) or not re.fullmatch("[0-9a-f]{40}",locked["rev"]) or
            not isinstance(locked["narHash"],str) or not re.fullmatch(r"sha256-[A-Za-z0-9+/]{43}=",locked["narHash"]) or
            type(locked["lastModified"]) is not int or locked["lastModified"]<0 or
            set(original)!={"type","owner","repo","ref"} or
            {k:original[k] for k in ["type","owner","repo"]}!={k:locked[k] for k in ["type","owner","repo"]} or
            original["ref"] not in ["nixos-25.11","nixos-26.05"]):
            raise MigrationError("General SSH package provenance is outside supported stable channels")
        return locked,original["ref"][6:]
    except (KeyError,TypeError) as error:
        raise MigrationError("General SSH root lock metadata is malformed") from error


def general_expression(sensitive_expression,source,host,locked,release):
    raw=sensitive_expression(source,host)
    suffix='builtins.hashString "sha256" (builtins.toJSON v)'
    if not raw.endswith(suffix):raise MigrationError("Sensitive expression changed; general SSH proof needs review")
    fragment=ssh_binding_fragment("old",locked=locked,release=release)
    result=('let hash = value: builtins.hashString "sha256" (builtins.toJSON value); '+fragment+
            'in assert sshBindingsOkay; builtins.toJSON { schema=1; raw_sha256=hash v; '
            'ssh_policy_sha256=hash (sshPolicy // { settings=v.ssh.settings; }); '
            'release=c.system.nixos.release; ssh_module_sha256=builtins.hashFile "sha256" '
            '(trustedNixpkgs.outPath + "/nixos/modules/services/networking/ssh/sshd.nix"); }')
    return raw[:-len(suffix)]+result


def validate_general_envelope(value,release):
    value=object_json(value)
    if (set(value)!={"schema","raw_sha256","ssh_policy_sha256","release","ssh_module_sha256"} or
        type(value["schema"]) is not int or value["schema"]!=1 or value["release"]!=release or
        any(not isinstance(value[k],str) or not HEX.fullmatch(value[k])
            for k in ["raw_sha256","ssh_policy_sha256","ssh_module_sha256"])):
        raise MigrationError("Invalid general SSH policy evidence")
    return value


def verify_general(sensitive_expression,old_source,new_source,host,evaluator,executor):
    # No migration opt-in, sudo normalization or accepted auth delta here.
    reject_switch_bypass_environment(os.environ)
    metadata=[general_lock(source,legacy_baseline=index==0)
              for index,source in enumerate([old_source,new_source])]
    releases=[v[1] for v in metadata];locked=[v[0] for v in metadata]
    if releases[0]!=releases[1]:raise MigrationError("Ordinary SSH batch cannot change release")
    expressions=[general_expression(sensitive_expression,source,host,pin,release)
                 for source,pin,release in zip([old_source,new_source],locked,releases)]
    effective=verify_built_ssh(old_source,new_source,host,evaluator,executor,locked_pair=locked,releases=releases)
    observations=[validate_general_envelope(evaluator(expr),release) for expr,release in zip(expressions,releases)]
    if observations[0]["raw_sha256"]!=observations[1]["raw_sha256"]:
        raise MigrationError("Ordinary batch changes protected raw authentication state")
    if observations[0]["ssh_policy_sha256"]!=observations[1]["ssh_policy_sha256"]:
        raise MigrationError("Ordinary batch changes authored SSH policy")
    for expr,release,before in zip(expressions,releases,observations):
        if validate_general_envelope(evaluator(expr),release)!=before:
            raise MigrationError("General SSH source policy changed during fresh proof")
    return {"old":observations[0]["raw_sha256"],"new":observations[1]["raw_sha256"],
            "ssh_policy_sha256":observations[0]["ssh_policy_sha256"],
            "old_module_sha256":observations[0]["ssh_module_sha256"],
            "new_module_sha256":observations[1]["ssh_module_sha256"],"ssh_effective":effective}


def verify(sensitive_expression, old_source, new_source, host, evaluator, executor):
    if APPROVED_2511_TO_2605_ENV_KEEP is not True:
        raise MigrationError("The real sudo policy transition has not been explicitly approved")
    reject_switch_bypass_environment(os.environ)
    for source, side in [(old_source, "old"), (new_source, "new")]:
        check_lock(source, side)
    effective = verify_built_ssh(old_source, new_source, host, evaluator, executor, allow_default_transition=True)
    before = validate_envelope(evaluator(expression(sensitive_expression, old_source, host, "old")), "old")
    after = validate_envelope(evaluator(expression(sensitive_expression, new_source, host, "new")), "new")
    if before["normalized_sha256"] != after["normalized_sha256"]:
        raise MigrationError("Migration changes another authentication/stateVersion invariant")
    if before["raw_sha256"] == after["raw_sha256"]:
        raise MigrationError("The expected explicit policy transition is absent")
    for source, side, observed in [(old_source, "old", before), (new_source, "new", after)]:
        if validate_envelope(evaluator(expression(sensitive_expression, source, host, side)), side) != observed:
            raise MigrationError("Migration source policy changed during fresh proof")
    return {"old": before["raw_sha256"], "new": after["raw_sha256"],
            "unchanged_protected_sha256": before["normalized_sha256"],
            "approved_real_policy_delta": "Defaults env_keep+=NIXOS_NO_CHECK; protected activator rejects this variable",
            "ssh_effective": effective, "old_release": "25.11", "new_release": "26.05"}
