{ ... }:
{
  # Manage only this fragment; the user's other SSH aliases remain in config.
  # ~/.ssh/config includes it before those aliases. The initial repair wrote
  # the same fragment as a regular file, so activation replaces that file.
  home.file.".ssh/weasel-vps.conf" = {
    source = ./vps-ssh.conf;
    force = true;
  };
}
